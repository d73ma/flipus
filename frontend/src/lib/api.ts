import axios from 'axios';

// Pakai relative path "/api" + Vite proxy → backend di http://localhost:8000.
// Vite proxy di vite.config.ts handle forwarding sehingga frontend TIDAK perlu
// tahu hostname backend. Untuk LAN demo (device lain akses via IP MacBook),
// proxy terjadi di server Vite (MacBook Jerry), jadi otomatis jalan tanpa
// konfigurasi CORS tambahan.
// Override pakai VITE_API_URL kalau perlu (misal production build static).
const apiBaseURL = (import.meta.env.VITE_API_URL as string | undefined)
  || '/api';

const api = axios.create({
  baseURL: apiBaseURL,
  timeout: 15000, // 15s — biar tidak loading stuck tanpa batas kalau backend hang
  headers: {
    'Content-Type': 'application/json',
  }
});

// Request interceptor - tambah token dari localStorage
api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// Response interceptor - handle 401
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('token');
      localStorage.removeItem('role');
      localStorage.removeItem('tenant_id');
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

export default api;
