/// <reference types="vitest" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Set base to '/splitleh/' for GitHub Pages; change to '/' for custom domains.
export default defineConfig({
  plugins: [react()],
  base: '/splitleh/',
  optimizeDeps: {
    // Exclude WASM-backed packages — onnxruntime-web registers WASM backends
    // at import time and breaks when Vite's CJS-to-ESM shim wraps it.
    exclude: ['onnxruntime-web', 'ppu-paddle-ocr'],
  },
  test: {
    environment: 'node',
  },
})
