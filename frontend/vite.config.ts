import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // Backend mount semua router di /api/v1/*
      // Frontend baseURL di api.ts adalah '/api' → full request path '/api/v1/...'
      // Proxy cocok '/api' → strip '/api' → forward ke http://localhost:8000/api/v1/...
      // (path suffix '/v1/...' di-append ke target, hasilnya '/api/v1/...' benar)
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        secure: false,
      },
    },
  },
  build: {
    // ===== Code splitting strategy =====
    rollupOptions: {
      output: {
        // Manual chunks untuk optimize caching + initial bundle size
        manualChunks: {
          // React core + ReactDOM (~140KB gzipped)
          'react-vendor': ['react', 'react-dom', 'react-router-dom'],
          // HTTP client
          'axios': ['axios'],
        },
      },
    },
    // Target modern browsers (smaller polyfills)
    target: 'es2020',
    // Minify dengan terser (default, tapi explicit)
    minify: 'terser',
    // Chunk size warning threshold
    chunkSizeWarningLimit: 500,
  },
  // Optimize deps — pre-bundle libraries besar
  optimizeDeps: {
    include: ['react', 'react-dom', 'react-router-dom', 'axios'],
  },
});