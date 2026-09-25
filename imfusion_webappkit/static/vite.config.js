import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  // Assets folder is served as static files (copied to dist during build)
  publicDir: 'assets',
  server: {
    port: 3000,
    proxy: {
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true
      },
      '/config': {
        target: 'http://localhost:8000',
      },
      '/sample-datasets': {
        target: 'http://localhost:8000',
      }
    }
  },
  build: {
    outDir: 'dist',
    rollupOptions: {
      input: {
        main: './index.html'
      }
    }
  }
});




