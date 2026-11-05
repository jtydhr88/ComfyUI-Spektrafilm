import { resolve } from 'path'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import cssInjectedByJs from 'vite-plugin-css-injected-by-js'

export default defineConfig({
  plugins: [vue(), cssInjectedByJs()],
  resolve: {
    alias: { '@': resolve(__dirname, './src') }
  },
  define: {
    'process.env.NODE_ENV': JSON.stringify('production')
  },
  build: {
    lib: {
      entry: resolve(__dirname, './src/main.ts'),
      formats: ['es'],
      fileName: 'main'
    },
    outDir: 'web/js',
    emptyOutDir: true,
    rollupOptions: {
      external: ['../../../scripts/app.js', '../../../scripts/api.js'],
      output: { entryFileNames: 'main.js' }
    },
    minify: false
  }
})
