import { useRef, useState, useCallback, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useReceipt } from '../../store/ReceiptContext'
import type { ParseResult } from '@splitleh/core'
import {
  chargesFromParse,
  extractMerchant,
  formatCurrency,
  type Reconciliation,
} from '@splitleh/core'
import { scanReceipt } from '../../adapters/browserPaddleOcrProvider'
import { localStorageSessionRepository as sessionRepo } from '../../adapters/localStorageSessionRepository'
import { preprocessReceiptImage } from '../../utils/receiptImage'
import styles from './Scan.module.css'

// ── State machine ─────────────────────────────────────────────────────────────

type ScanState =
  | { mode: 'idle' }
  | { mode: 'preview';  dataUrl: string; processedUrl?: string; showProcessed: boolean }
  | { mode: 'scanning'; dataUrl: string; ocrStatus: string; progress: number }
  | { mode: 'parsed';   dataUrl: string; rawText: string; parseResult: ParseResult; reconciliation: Reconciliation }
  | { mode: 'error';    dataUrl: string; message: string }

// ── Helpers ───────────────────────────────────────────────────────────────────

function modeSubtitle(mode: ScanState['mode']): string {
  if (mode === 'preview')  return 'Looks good? Tap Scan to extract items automatically.'
  if (mode === 'scanning') return 'Running OCR in your browser…'
  if (mode === 'parsed')   return 'Check items and receipt math before continuing.'
  if (mode === 'error')    return 'Something went wrong with OCR.'
  return 'Upload or photograph your receipt. OCR runs in your browser - nothing is uploaded.'
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function Scan() {
  const navigate  = useNavigate()
  const { draft, dispatch } = useReceipt()
  const cameraRef  = useRef<HTMLInputElement>(null)
  const galleryRef = useRef<HTMLInputElement>(null)
  const [state, setState] = useState<ScanState>({ mode: 'idle' })
  const [isDragging, setIsDragging] = useState(false)
  const [heicWarning, setHeicWarning] = useState(false)

  // ── File selection ──────────────────────────────────────────────────────────

  const handleFile = useCallback((file: File) => {
    if (file.type.startsWith('image/')) {
      const name = file.name.toLowerCase()
      if (file.type === 'image/heic' || file.type === 'image/heif' || name.endsWith('.heic') || name.endsWith('.heif')) {
        setHeicWarning(true)
        return
      }
      setHeicWarning(false)
      const reader = new FileReader()
      reader.onload = (e) => {
        const dataUrl = e.target?.result as string
        setState({ mode: 'preview', dataUrl, showProcessed: false })
      }
      reader.readAsDataURL(file)
    }
  }, [])

  const onFileChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0]
      if (file) handleFile(file)
      // Reset input so the same file can be re-selected after Retake
      e.target.value = ''
    },
    [handleFile],
  )

  const onDragEnter = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(true)
  }, [])

  const onDragLeave = useCallback((e: React.DragEvent<HTMLElement>) => {
    if (e.currentTarget.contains(e.relatedTarget as Node)) return
    setIsDragging(false)
  }, [])

  const onDrop = useCallback(
    (e: React.DragEvent<HTMLDivElement>) => {
      e.preventDefault()
      setIsDragging(false)
      const file = e.dataTransfer.files?.[0]
      if (file) handleFile(file)
    },
    [handleFile],
  )

  // ── OCR ─────────────────────────────────────────────────────────────────────

  // Preprocess in background so the user can preview the enhanced image before OCR.
  useEffect(() => {
    if (state.mode === 'preview') {
      let cancelled = false
      preprocessReceiptImage(state.dataUrl)
        .then((processedUrl) => {
          if (cancelled) return
          setState((prev) =>
            prev.mode === 'preview' ? { ...prev, processedUrl } : prev,
          )
        })
        .catch(() => {})
      return () => { cancelled = true }
    }
  }, [state.mode === 'preview' ? state.dataUrl : null])

  const startScan = useCallback(
    async (dataUrl: string, processedUrl?: string) => {
      setState({ mode: 'scanning', dataUrl, ocrStatus: 'Starting…', progress: 0 })

      try {
        const { rawText, parseResult, reconciliation } = await scanReceipt(
          dataUrl,
          (ocrStatus, progress) => {
            setState((prev) =>
              prev.mode === 'scanning' ? { ...prev, ocrStatus, progress } : prev,
            )
          },
          processedUrl,
        )

        // Store image + raw text on-device; never sent to a server
        dispatch({
          type: 'SET_RECEIPT_META',
          payload: { rawImageDataUrl: dataUrl, rawText },
        })

        setState({ mode: 'parsed', dataUrl, rawText, parseResult, reconciliation })
      } catch (err) {
        setState({
          mode: 'error',
          dataUrl,
          message: err instanceof Error ? err.message : String(err),
        })
      }
    },
    [dispatch],
  )

  // ── Confirm parsed items ─────────────────────────────────────────────────────

  const confirmScan = useCallback(
    (parseResult: ParseResult, rawText: string) => {
      const items = parseResult.items.map((it) => ({
        id: sessionRepo.generateId(),
        name: it.name,
        unitPrice: it.unitPrice,
        quantity: it.quantity,
        totalPrice: it.totalPrice,
      }))
      const charges = chargesFromParse(parseResult)
      const merchant = extractMerchant(rawText)

      dispatch({
        type: 'APPLY_SCAN_RESULT',
        payload: { items, charges, merchant },
      })
      navigate('/review')
    },
    [dispatch, navigate],
  )

  // ── No session guard ────────────────────────────────────────────────────────

  if (!draft) {
    return (
      <div className={styles.page}>
        <div className={styles.emptyPage}>
          <p>No active session. Go home and start a new split.</p>
          <button className="btn btn-primary" onClick={() => navigate('/')}>
            Go Home
          </button>
        </div>
      </div>
    )
  }

  // ── Render ──────────────────────────────────────────────────────────────────

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <h1 className={styles.title}>Scan Receipt</h1>
        <p className={styles.sub}>{modeSubtitle(state.mode)}</p>
      </header>

      {/* ── Idle: capture options ─────────────────────────────────────── */}
      {state.mode === 'idle' && (
        <>
          {heicWarning && (
            <div className={styles.heicWarning}>
              <span className={styles.heicIcon}>⚠️</span>
              <div className={styles.heicBody}>
                <strong>HEIC not supported in browser</strong>
                <p>On iPhone: Settings → Camera → Formats → Most Compatible to shoot JPEG instead.</p>
              </div>
              <button
                className={styles.heicDismiss}
                onClick={() => setHeicWarning(false)}
                aria-label="Dismiss warning"
              >✕</button>
            </div>
          )}

          <section
            className={`${styles.captureSection} ${isDragging ? styles.captureSectionDragging : ''}`}
            onDrop={onDrop}
            onDragOver={(e) => e.preventDefault()}
            onDragEnter={onDragEnter}
            onDragLeave={onDragLeave}
            aria-label="Drop receipt image here"
          >
            {isDragging ? (
              <div className={styles.dropOverlay}>
                <UploadIcon />
                <span>Drop photo here</span>
              </div>
            ) : (
              <>
                <div className={styles.captureCards}>
                  <button
                    type="button"
                    className={`${styles.captureCard} ${styles.captureCardCamera}`}
                    onClick={() => cameraRef.current?.click()}
                  >
                    <span className={styles.captureCardIcon}><CameraIcon size={28} /></span>
                    <span className={styles.captureCardLabel}>Take Photo</span>
                    <span className={styles.captureCardHint}>Opens camera</span>
                  </button>
                  <button
                    type="button"
                    className={styles.captureCard}
                    onClick={() => galleryRef.current?.click()}
                  >
                    <span className={styles.captureCardIcon}><GalleryIcon /></span>
                    <span className={styles.captureCardLabel}>Browse Library</span>
                    <span className={styles.captureCardHint}>Gallery or files</span>
                  </button>
                </div>
                <p className={styles.dropHint}>drag &amp; drop also works</p>
              </>
            )}
          </section>

          <input
            ref={cameraRef}
            type="file"
            accept="image/*"
            capture="environment"
            onChange={onFileChange}
            className={styles.hiddenInput}
            aria-label="Take photo with camera"
          />
          <input
            ref={galleryRef}
            type="file"
            accept="image/*"
            onChange={onFileChange}
            className={styles.hiddenInput}
            aria-label="Choose from gallery or files"
          />

          <div className={styles.divider}><span>or skip OCR</span></div>

          <div className={styles.skipActions}>
            <button
              className="btn btn-secondary btn-full"
              onClick={() => navigate('/review')}
            >
              <PencilIcon /> Enter Items Manually
            </button>
          </div>
        </>
      )}

      {/* ── Preview ───────────────────────────────────────────────────── */}
      {state.mode === 'preview' && (
        <div className={styles.photoBlock}>
          <img
            src={
              state.showProcessed && state.processedUrl
                ? state.processedUrl
                : state.dataUrl
            }
            alt="Receipt preview"
            className={styles.receiptImg}
          />
          <div className={styles.previewToolbar}>
            <button
              type="button"
              className={`${styles.previewToggle} ${state.showProcessed ? '' : styles.previewToggleActive}`}
              onClick={() => setState((prev) =>
                prev.mode === 'preview' ? { ...prev, showProcessed: false } : prev,
              )}
            >
              Original
            </button>
            <button
              type="button"
              className={`${styles.previewToggle} ${state.showProcessed ? styles.previewToggleActive : ''}`}
              onClick={() => setState((prev) =>
                prev.mode === 'preview' ? { ...prev, showProcessed: true } : prev,
              )}
              disabled={!state.processedUrl}
            >
              Enhanced{state.processedUrl ? '' : '…'}
            </button>
          </div>
          <p className={styles.previewHint}>
            {state.processedUrl
              ? 'Enhanced view shows how OCR sees your receipt. Retake if text looks washed out.'
              : 'Preparing enhanced preview…'}
          </p>
          <div className={styles.photoActions}>
            <button
              className="btn btn-secondary"
              onClick={() => setState({ mode: 'idle' })}
            >
              <CameraIcon /> Retake
            </button>
            <button
              className="btn btn-primary"
              onClick={() => startScan(state.dataUrl, state.processedUrl)}
            >
              <ScanIcon /> Scan Receipt
            </button>
          </div>
        </div>
      )}

      {/* ── Scanning ──────────────────────────────────────────────────── */}
      {state.mode === 'scanning' && (
        <div className={styles.scanningBlock}>
          <img
            src={state.dataUrl}
            alt="Receipt being scanned"
            className={`${styles.receiptImg} ${styles.receiptImgDim}`}
          />

          <div className={`${styles.progressCard} card`}>
            <div className={styles.progressHeader}>
              <span className={styles.progressStatus}>{state.ocrStatus}</span>
              <span className={styles.progressPct}>{state.progress}%</span>
            </div>
            <div className={styles.progressTrack}>
              <div
                className={styles.progressFill}
                style={{ width: `${state.progress}%` }}
              />
            </div>
            {state.progress < 45 && (
              <p className={styles.progressHint}>
                Language data downloads once and is cached on your device.
              </p>
            )}
            {state.progress >= 48 && state.progress < 95 && (
              <p className={styles.progressHint}>
                Trying multiple read modes for best accuracy…
              </p>
            )}
          </div>
        </div>
      )}

      {/* ── Parsed ────────────────────────────────────────────────────── */}
      {state.mode === 'parsed' && (
        <ParsedView
          dataUrl={state.dataUrl}
          rawText={state.rawText}
          parseResult={state.parseResult}
          reconciliation={state.reconciliation}
          currency={draft.receipt.currency}
          onConfirm={() => confirmScan(state.parseResult, state.rawText)}
          onRetake={() => setState({ mode: 'idle' })}
          onSkip={() => navigate('/review')}
        />
      )}

      {/* ── Error ─────────────────────────────────────────────────────── */}
      {state.mode === 'error' && (
        <ErrorView
          dataUrl={state.dataUrl}
          message={state.message}
          onRetry={() => startScan(state.dataUrl)}
          onRetake={() => setState({ mode: 'idle' })}
          onSkip={() => navigate('/review')}
        />
      )}

    </div>
  )
}

// ── ParsedView ────────────────────────────────────────────────────────────────

interface ParsedViewProps {
  dataUrl: string
  rawText: string
  parseResult: ParseResult
  reconciliation: Reconciliation
  currency: string
  onConfirm: () => void
  onRetake: () => void
  onSkip: () => void
}

function ParsedView({
  dataUrl, rawText, parseResult, reconciliation, currency, onConfirm, onRetake, onSkip,
}: Readonly<ParsedViewProps>) {
  const [showRaw, setShowRaw] = useState(false)
  const { items } = parseResult
  const hasItems = items.length > 0
  const mathOk = reconciliation.status === 'ok'
  const mathWarn = reconciliation.status === 'warn'

  let badgeClass = styles.thumbBadgeFail
  if (mathOk) badgeClass = styles.thumbBadgeOk
  else if (mathWarn) badgeClass = styles.thumbBadgeWarn

  let badgeText = ' Math mismatch'
  if (mathOk) badgeText = ' Math checks out'
  else if (mathWarn) badgeText = ' Review math'

  let mathCardMod = styles.mathFail
  if (mathOk) mathCardMod = styles.mathOk
  else if (mathWarn) mathCardMod = styles.mathWarn

  return (
    <div className={styles.parsedBlock}>
      {/* Thumbnail + result badge */}
      <div className={styles.thumbRow}>
        <img src={dataUrl} alt="Scanned receipt" className={styles.thumb} />
        <div className={styles.thumbMeta}>
          {hasItems ? (
            <>
              <span className={badgeClass}>
                {mathOk ? <CheckIcon /> : <WarnIcon />}
                {badgeText}
              </span>
              <p className={styles.thumbCount}>
                Found <strong>{items.length}</strong> item{items.length === 1 ? '' : 's'}
              </p>
            </>
          ) : (
            <>
              <span className={styles.thumbBadgeWarn}>
                <WarnIcon /> No items found
              </span>
              <p className={styles.thumbCount}>
                Add items manually on the next screen.
              </p>
            </>
          )}
        </div>
      </div>

      {/* Receipt math reconciliation */}
      {hasItems && reconciliation.lines.length > 1 && (
        <div className={`card ${styles.mathCard} ${mathCardMod}`}>
          <h3 className={styles.mathTitle}>Receipt math</h3>
          <ul className={styles.mathLines}>
            {reconciliation.lines.map((line, i) => (
              <li
                key={`${line.label}-${i}`}
                className={
                  line.label.startsWith('Total') || line.label.startsWith('Calculated')
                    ? styles.mathLineTotal
                    : styles.mathLine
                }
              >
                <span>{line.label}</span>
                <span>{formatCurrency(line.amount, currency)}</span>
              </li>
            ))}
          </ul>
          {reconciliation.messages.length > 0 && (
            <p className={styles.mathHint}>{reconciliation.messages[0]}</p>
          )}
        </div>
      )}

      {/* Parsed item list */}
      {hasItems && (
        <ul className={styles.parsedList}>
          {items.map((item, i) => (
            <li key={`${item.name}-${i}`} className={styles.parsedItem}>
              <span className={styles.parsedName}>
                {item.name}
                <span className={styles.parsedQty}>
                  {' '}{item.quantity} × {formatCurrency(item.unitPrice, currency)}
                </span>
              </span>
              <span className={styles.parsedPrice}>
                {formatCurrency(item.totalPrice, currency)}
              </span>
            </li>
          ))}
        </ul>
      )}

      {/* CTAs */}
      <div className={styles.parsedActions}>
        {hasItems ? (
          <button type="button" className="btn btn-primary" onClick={onConfirm}>
            Review &amp; Edit &rarr;
          </button>
        ) : (
          <button type="button" className="btn btn-primary" onClick={onSkip}>
            Add Manually &rarr;
          </button>
        )}
        <button type="button" className="btn btn-ghost" onClick={onRetake}>
          <CameraIcon /> Retake
        </button>
      </div>

      {/* Raw text disclosure - below CTAs so sticky overlay never blocks it */}
      <button
        className={styles.rawToggle}
        onClick={() => setShowRaw((v) => !v)}
        aria-expanded={showRaw}
      >
        <ChevronIcon open={showRaw} /> Raw OCR text
      </button>
      {showRaw && (
        <pre className={styles.rawText}>{rawText || '(empty)'}</pre>
      )}
    </div>
  )
}

// ── ErrorView ─────────────────────────────────────────────────────────────────

interface ErrorViewProps {
  dataUrl: string
  message: string
  onRetry: () => void
  onRetake: () => void
  onSkip: () => void
}

function ErrorView({ dataUrl, message, onRetry, onRetake, onSkip }: Readonly<ErrorViewProps>) {
  const [showDetail, setShowDetail] = useState(false)
  const isOffline = navigator.onLine === false || message.toLowerCase().includes('fetch')

  return (
    <div className={styles.errorBlock}>
      <img src={dataUrl} alt="Receipt" className={`${styles.receiptImg} ${styles.receiptImgDim}`} />

      <div className={`${styles.errorCard} card`}>
        <span className={styles.errorIcon}>⚠️</span>
        <div>
          <strong>OCR failed</strong>
          <p>
            {isOffline
              ? 'Language data needs to download on first use. Check your connection and try again.'
              : 'Something went wrong while reading the receipt.'}
          </p>
        </div>
      </div>

      <button className={styles.rawToggle} onClick={() => setShowDetail((v) => !v)}>
        <ChevronIcon open={showDetail} /> Error details
      </button>
      {showDetail && <pre className={styles.rawText}>{message}</pre>}

      <div className={styles.errorActions}>
        <button className="btn btn-secondary" onClick={onRetry}>Retry OCR</button>
        <button className="btn btn-ghost" onClick={onRetake}>Retake Photo</button>
        <button className="btn btn-primary btn-full" onClick={onSkip}>
          Add Items Manually &rarr;
        </button>
      </div>
    </div>
  )
}

// ── Icons ─────────────────────────────────────────────────────────────────────

function PencilIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M17 3a2.828 2.828 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5L17 3z"/>
    </svg>
  )
}

function CameraIcon({ size = 16 }: Readonly<{ size?: number }>) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/>
      <circle cx="12" cy="13" r="4"/>
    </svg>
  )
}

function GalleryIcon() {
  return (
    <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>
      <circle cx="8.5" cy="8.5" r="1.5"/>
      <polyline points="21 15 16 10 5 21"/>
    </svg>
  )
}

function UploadIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="16 16 12 12 8 16"/>
      <line x1="12" y1="12" x2="12" y2="21"/>
      <path d="M20.39 18.39A5 5 0 0 0 18 9h-1.26A8 8 0 1 0 3 16.3"/>
    </svg>
  )
}

function ScanIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="4 7 4 4 7 4"/>
      <polyline points="17 4 20 4 20 7"/>
      <polyline points="20 17 20 20 17 20"/>
      <polyline points="7 20 4 20 4 17"/>
      <line x1="5" y1="12" x2="19" y2="12"/>
    </svg>
  )
}

function CheckIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="20 6 9 17 4 12"/>
    </svg>
  )
}

function WarnIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
      <line x1="12" y1="9" x2="12" y2="13"/>
      <line x1="12" y1="17" x2="12.01" y2="17"/>
    </svg>
  )
}

function ChevronIcon({ open }: Readonly<{ open: boolean }>) {
  return (
    <svg
      width="13" height="13"
      viewBox="0 0 24 24"
      fill="none" stroke="currentColor"
      strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"
      style={{ transform: open ? 'rotate(90deg)' : 'none', transition: 'transform 0.15s' }}
    >
      <polyline points="9 18 15 12 9 6"/>
    </svg>
  )
}
