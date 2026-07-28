import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    // jsdom v25 refuses `localStorage` on the default `about:blank` "opaque"
    // origin; tests that clear/read the store need a concrete origin so the
    // per-window Storage instance can persist. See
    // https://github.com/jsdom/jsdom/blob/main/Changelog.md
    environmentOptions: {
      jsdom: {
        url: 'http://localhost:3000/',
      },
    },
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    css: false,
    include: ['src/**/*.{test,spec}.{ts,tsx}'],
  },
})
