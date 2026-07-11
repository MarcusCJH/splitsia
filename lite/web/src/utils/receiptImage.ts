// Browser-side receipt photo preprocessing for PaddleOCR.
// On mobile, getContext('2d') can return null when the device is low on memory.
function ctx2d(canvas: HTMLCanvasElement): CanvasRenderingContext2D {
  const ctx = canvas.getContext('2d')
  if (!ctx) throw new Error('Canvas 2D context unavailable - device may be low on memory.')
  return ctx
}

// Pipeline: grayscale → crop dark margins → (optional CLAHE) → (optional binarize).
//
// Memory budget (worst case at MAX=1600, portrait 1200×1600):
//   canvas ImageData : 1200×1600×4 =  7.7 MB
//   CLAHE gray+output: 1200×1600×1 =  1.9 MB ×2
//   Int32 integral   : 1201×1601×4 =  7.7 MB   ← single integral, not two Float64s
//   output ImageData : 1200×1600×4 =  7.7 MB
//   Total peak       :            ≈ 27 MB

function buildTileHistogram(
  gray: Uint8Array, width: number,
  x0: number, y0: number, x1: number, y1: number,
): { hist: Uint32Array; count: number } {
  const hist = new Uint32Array(256)
  let count = 0
  for (let y = y0; y < y1; y++) {
    for (let x = x0; x < x1; x++) {
      hist[gray[y * width + x]]++
      count++
    }
  }
  return { hist, count }
}

function clipAndRedistribute(hist: Uint32Array, count: number, clipLimit: number): void {
  const clipThreshold = Math.max(1, Math.floor((count / 256) * clipLimit))
  let excess = 0
  for (let i = 0; i < 256; i++) {
    if (hist[i] > clipThreshold) {
      excess += hist[i] - clipThreshold
      hist[i] = clipThreshold
    }
  }
  const redist = Math.floor(excess / 256)
  for (let i = 0; i < 256; i++) hist[i] += redist
}

function buildClaheLut(hist: Uint32Array, count: number): Uint8Array {
  const cdf = new Uint32Array(256)
  cdf[0] = hist[0]
  for (let i = 1; i < 256; i++) cdf[i] = cdf[i - 1] + hist[i]
  const cdfMin = cdf.find((v) => v > 0) ?? 0
  const scale = cdfMin < count ? 255 / (count - cdfMin) : 0
  const lut = new Uint8Array(256)
  for (let i = 0; i < 256; i++) {
    lut[i] = scale > 0 ? Math.round((cdf[i] - cdfMin) * scale) : i
  }
  return lut
}

function applyLutToTile(
  gray: Uint8Array, output: Uint8Array, lut: Uint8Array, width: number,
  bounds: { x0: number; y0: number; x1: number; y1: number },
): void {
  const { x0, y0, x1, y1 } = bounds
  for (let y = y0; y < y1; y++) {
    for (let x = x0; x < x1; x++) {
      output[y * width + x] = lut[gray[y * width + x]]
    }
  }
}

function applyClahe(gray: Uint8Array, width: number, height: number): void {
  const tilesX = 8
  const tilesY = 8
  const clipLimit = 2.5
  const tileW = Math.ceil(width / tilesX)
  const tileH = Math.ceil(height / tilesY)
  const output = new Uint8Array(gray.length)

  for (let ty = 0; ty < tilesY; ty++) {
    for (let tx = 0; tx < tilesX; tx++) {
      const x0 = tx * tileW
      const y0 = ty * tileH
      const x1 = Math.min(width, x0 + tileW)
      const y1 = Math.min(height, y0 + tileH)
      const { hist, count } = buildTileHistogram(gray, width, x0, y0, x1, y1)
      clipAndRedistribute(hist, count, clipLimit)
      const lut = buildClaheLut(hist, count)
      applyLutToTile(gray, output, lut, width, { x0, y0, x1, y1 })
    }
  }

  gray.set(output)
}

function cropToContent(imageData: ImageData, pad = 12): ImageData {
  const { data, width, height } = imageData

  // Average the four corner pixels to estimate background color.
  const corners = [
    0,
    (width - 1) * 4,
    (height - 1) * width * 4,
    ((height - 1) * width + (width - 1)) * 4,
  ]
  let bg = 0
  for (const i of corners) bg += data[i]
  bg /= corners.length

  let minX = width
  let minY = height
  let maxX = 0
  let maxY = 0

  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      const i = (y * width + x) * 4
      const v = data[i]
      // A pixel is "content" if it differs from the corner background by more
      // than 25 grey levels. No extra "|| v < 210" rule: that clause was
      // designed for light-background photos but causes dark backgrounds (where
      // bg ≈ 0) to mark ALL pixels as content, preventing any cropping.
      if (Math.abs(v - bg) > 25) {
        minX = Math.min(minX, x)
        minY = Math.min(minY, y)
        maxX = Math.max(maxX, x)
        maxY = Math.max(maxY, y)
      }
    }
  }

  if (maxX <= minX || maxY <= minY) return imageData

  minX = Math.max(0, minX - pad)
  minY = Math.max(0, minY - pad)
  maxX = Math.min(width - 1, maxX + pad)
  maxY = Math.min(height - 1, maxY + pad)

  const cropW = maxX - minX + 1
  const cropH = maxY - minY + 1
  const cropped = new ImageData(cropW, cropH)
  for (let y = 0; y < cropH; y++) {
    for (let x = 0; x < cropW; x++) {
      const src = ((minY + y) * width + (minX + x)) * 4
      const dst = (y * cropW + x) * 4
      cropped.data[dst]     = data[src]
      cropped.data[dst + 1] = data[src + 1]
      cropped.data[dst + 2] = data[src + 2]
      cropped.data[dst + 3] = 255
    }
  }
  return cropped
}

// Mean-based adaptive threshold via a single integral image (Int32).
// Int32 is safe here: max value = 255 × w × h ≤ 255 × 900 × 1200 = 274 M < 2.1 B.
// Uses less than half the memory of Sauvola (which needs two Float64 integrals).
function adaptiveBinarize(imageData: ImageData, radius = 25, bias = 8): ImageData {
  const { data, width, height } = imageData
  const n = width * height

  const integral = new Int32Array((width + 1) * (height + 1))
  for (let y = 0; y < height; y++) {
    let rowSum = 0
    for (let x = 0; x < width; x++) {
      rowSum += data[(y * width + x) * 4]
      integral[(y + 1) * (width + 1) + (x + 1)] =
        rowSum + integral[y * (width + 1) + (x + 1)]
    }
  }

  const output = new ImageData(width, height)
  const out = output.data
  for (let i = 0; i < n; i++) {
    const y = Math.floor(i / width)
    const x = i % width
    const y1 = Math.max(0, y - radius)
    const y2 = Math.min(height - 1, y + radius)
    const x1 = Math.max(0, x - radius)
    const x2 = Math.min(width - 1, x + radius)
    const count = (x2 - x1 + 1) * (y2 - y1 + 1)
    const sum =
      integral[(y2 + 1) * (width + 1) + (x2 + 1)] -
      integral[y1       * (width + 1) + (x2 + 1)] -
      integral[(y2 + 1) * (width + 1) + x1      ] +
      integral[y1       * (width + 1) + x1      ]
    const threshold = sum / count - bias
    const val = data[i * 4] >= threshold ? 255 : 0
    const j = i * 4
    out[j] = val; out[j + 1] = val; out[j + 2] = val; out[j + 3] = 255
  }
  return output
}

function scaleAndGrayscale(dataUrl: string): Promise<{
  imageData: ImageData
  w: number
  h: number
}> {
  return new Promise((resolve, reject) => {
    const img = new Image()
    img.onload = () => {
      const MAX = 1600
      const MIN = 1000
      const longest = Math.max(img.width, img.height)
      let scale = 1
      if (longest > MAX) scale = MAX / longest
      else if (longest < MIN) scale = Math.min(2, MIN / longest)

      const w = Math.round(img.width * scale)
      const h = Math.round(img.height * scale)

      const canvas = document.createElement('canvas')
      canvas.width = w
      canvas.height = h
      const ctx = ctx2d(canvas)

      ctx.filter = 'grayscale(1) contrast(1.15)'
      ctx.drawImage(img, 0, 0, w, h)

      // Crop BEFORE CLAHE: background detection uses raw grayscale values.
      // After CLAHE, dark corners get stretched to near-zero, making bg ≈ 0
      // and the entire image appear as "content" - no crop happens.
      const imageData = cropToContent(ctx.getImageData(0, 0, w, h))
      resolve({ imageData, w: imageData.width, h: imageData.height })
    }
    img.onerror = reject
    img.src = dataUrl
  })
}

/**
 * Scale + CSS grayscale + crop (NO CLAHE).
 * Used for line segmentation: CLAHE equalises local brightness, which
 * destroys the global row-mean differences needed to detect text lines.
 */
export async function preprocessRawGrayscale(dataUrl: string): Promise<string> {
  const { imageData, w, h } = await scaleAndGrayscale(dataUrl)
  const canvas = document.createElement('canvas')
  canvas.width = w
  canvas.height = h
  ctx2d(canvas).putImageData(imageData, 0, 0)
  return canvas.toDataURL('image/png')
}

/** CLAHE + crop, no binarization - enhances local contrast for OCR display. */
export async function preprocessReceiptImageGrayscale(dataUrl: string): Promise<string> {
  const { imageData, w, h } = await scaleAndGrayscale(dataUrl)
  const gray = new Uint8Array(w * h)
  for (let i = 0; i < w * h; i++) gray[i] = imageData.data[i * 4]
  applyClahe(gray, w, h)

  const canvas = document.createElement('canvas')
  canvas.width = w
  canvas.height = h
  const ctx = ctx2d(canvas)
  const out = new ImageData(w, h)
  for (let i = 0; i < w * h; i++) {
    out.data[i * 4] = gray[i]
    out.data[i * 4 + 1] = gray[i]
    out.data[i * 4 + 2] = gray[i]
    out.data[i * 4 + 3] = 255
  }
  ctx.putImageData(out, 0, 0)
  return canvas.toDataURL('image/png')
}

/** CLAHE + crop + adaptive binarization - best for clean scans. */
export async function preprocessReceiptImage(dataUrl: string): Promise<string> {
  const { imageData, w, h } = await scaleAndGrayscale(dataUrl)
  const gray = new Uint8Array(w * h)
  for (let i = 0; i < w * h; i++) gray[i] = imageData.data[i * 4]
  applyClahe(gray, w, h)

  const claheImageData = new ImageData(w, h)
  for (let i = 0; i < w * h; i++) {
    claheImageData.data[i * 4] = gray[i]
    claheImageData.data[i * 4 + 1] = gray[i]
    claheImageData.data[i * 4 + 2] = gray[i]
    claheImageData.data[i * 4 + 3] = 255
  }

  const binarized = adaptiveBinarize(claheImageData)
  const canvas = document.createElement('canvas')
  canvas.width = w
  canvas.height = h
  ctx2d(canvas).putImageData(binarized, 0, 0)
  return canvas.toDataURL('image/png')
}

