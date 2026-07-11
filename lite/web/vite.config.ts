/// <reference types="vitest" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'node:path'

export default defineConfig({
  plugins: [react()],
  base: '/splitleh/',
  resolve: {
    alias: {
      '@splitleh/core': path.resolve(__dirname, '../core/src/index.ts'),
    },
  },
  optimizeDeps: {
    exclude: ['onnxruntime-web', 'ppu-paddle-ocr'],
  },
  test: {
    environment: 'node',
  },
})
