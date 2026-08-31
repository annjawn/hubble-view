import { defineConfig, externalizeDepsPlugin } from 'electron-vite'

export default defineConfig({
  main: {
    plugins: [externalizeDepsPlugin()],
    build: { outDir: 'dist-electron/main', lib: { entry: 'electron/main.ts', formats: ['es'], fileName: () => 'main.js' } },
  },
  preload: {
    plugins: [externalizeDepsPlugin()],
    build: {
      outDir: 'dist-electron/preload',
      lib: { entry: 'electron/preload.ts', formats: ['cjs'], fileName: () => 'preload.js' },
    },
  },
})
