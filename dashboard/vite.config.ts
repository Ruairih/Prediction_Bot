import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const isTest = process.env.VITEST === 'true'
  || process.env.NODE_ENV === 'test'
  || process.env.npm_lifecycle_event === 'test'

export default defineConfig({
  plugins: [react()],
  server: {
    host: isTest ? '127.0.0.1' : (process.env.VITE_HOST ?? '0.0.0.0'),
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://localhost:9050',
        changeOrigin: true,
      },
      '/health': {
        target: 'http://localhost:9050',
        changeOrigin: true,
      },
    },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: './src/test/setup.ts',
    css: true,
    exclude: ['**/node_modules/**', '**/e2e/**'],
    server: {
      host: process.env.VITE_HOST ?? '127.0.0.1',
    },
  },
})
