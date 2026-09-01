import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  base: process.env.GITHUB_ACTIONS ? '/timofeeva-academic/' : '/',
  build: {
    rollupOptions: {
      input: { main: 'index.html', publications: 'publications.html' },
    },
  },
})
