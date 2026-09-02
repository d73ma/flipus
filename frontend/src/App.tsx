import { lazy, Suspense } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './lib/auth';
import Login from './pages/Login';
import Layout from './components/Layout';

// ===== Lazy-loaded pages (code splitting) =====
// Auth pages — sync load (small + needed immediately)
import Register from './pages/Register';
import RegisterPendeta from './pages/RegisterPendeta';
import RegisterAuditor from './pages/RegisterAuditor';
import RegisterAdmin from './pages/RegisterAdmin';
import ForgotPassword from './pages/ForgotPassword';

// Protected dashboards — lazy load
const BendaharaDashboard = lazy(() => import('./pages/BendaharaDashboard'));
const KetuaDashboard = lazy(() => import('./pages/KetuaDashboard'));
const PendetaDashboard = lazy(() => import('./pages/PendetaDashboard'));
const AuditorDashboard = lazy(() => import('./pages/AuditorDashboard'));
const AdminDashboard = lazy(() => import('./pages/AdminDashboard'));
const OcrReview = lazy(() => import('./pages/OcrReview'));
const TenantSettings = lazy(() => import('./pages/TenantSettings'));
const TwoFactorSetup = lazy(() => import('./pages/TwoFactorSetup'));
const Notifications = lazy(() => import('./pages/Notifications'));
const LandingPage = lazy(() => import('./pages/LandingPage'));
const Settings = lazy(() => import('./pages/Settings'));
const QuickInput = lazy(() => import('./pages/QuickInput'));
const PengeluaranInput = lazy(() => import('./pages/PengeluaranInput'));
const PengeluaranApproval = lazy(() => import('./pages/PengeluaranApproval'));

// Loading fallback saat chunk sedang di-fetch
const PageLoader = () => (
  <div className="flex items-center justify-center min-h-screen">
    <div className="text-center">
      <div className="w-16 h-16 border-4 border-sabbath-green border-t-transparent rounded-full animate-spin mx-auto mb-4" />
      <p className="text-sabbath-dark font-display">Loading...</p>
    </div>
  </div>
);

const ProtectedRoute = ({ children, requiredRole }: { children: React.ReactNode; requiredRole?: string }) => {
  const { isAuthenticated, role } = useAuth();
  if (!isAuthenticated) return <Navigate to="/login" />;
  if (requiredRole && role !== requiredRole) return <Navigate to="/login" />;
  return <>{children}</>;
};

const App = () => {
  return (
    <AuthProvider>
      <Router>
        <Suspense fallback={<PageLoader />}>
          <Routes>
            {/* Public routes (no auth) */}
            <Route path="/login" element={<Login />} />
            <Route path="/register" element={<Register />} />
            <Route path="/register/pendeta" element={<RegisterPendeta />} />
            <Route path="/register/auditor" element={<RegisterAuditor />} />
            <Route path="/register/admin" element={<RegisterAdmin />} />
            <Route path="/forgot-password" element={<ForgotPassword />} />
            <Route path="/" element={<LandingPage />} />

            {/* Protected routes (with Layout) */}
            <Route element={<Layout />}>
              <Route index element={<Navigate to="/bendahara" />} />
              <Route path="bendahara" element={
                <ProtectedRoute requiredRole="BENDAHARA">
                  <BendaharaDashboard />
                </ProtectedRoute>
              } />
              <Route path="bendahara/ocr" element={
                <ProtectedRoute requiredRole="BENDAHARA">
                  <OcrReview />
                </ProtectedRoute>
              } />
              <Route path="bendahara/quick" element={
                <ProtectedRoute requiredRole="BENDAHARA">
                  <QuickInput />
                </ProtectedRoute>
              } />
              <Route path="bendahara/pengeluaran" element={
                <ProtectedRoute requiredRole="BENDAHARA">
                  <PengeluaranInput />
                </ProtectedRoute>
              } />
              <Route path="ketua/pengeluaran" element={
                <ProtectedRoute requiredRole="KETUA_KEUANGAN">
                  <PengeluaranApproval role="KETUA_KEUANGAN" />
                </ProtectedRoute>
              } />
              <Route path="pendeta/pengeluaran" element={
                <ProtectedRoute requiredRole="PENDETA">
                  <PengeluaranApproval role="PENDETA" />
                </ProtectedRoute>
              } />
              <Route path="ketua" element={
                <ProtectedRoute requiredRole="KETUA_KEUANGAN">
                  <KetuaDashboard />
                </ProtectedRoute>
              } />
              <Route path="pendeta" element={
                <ProtectedRoute requiredRole="PENDETA">
                  <PendetaDashboard />
                </ProtectedRoute>
              } />
              <Route path="auditor" element={
                <ProtectedRoute requiredRole="AUDITOR_MISI">
                  <AuditorDashboard />
                </ProtectedRoute>
              } />
              <Route path="admin" element={
                <ProtectedRoute requiredRole="ADMIN_UNI">
                  <AdminDashboard />
                </ProtectedRoute>
              } />
              <Route path="settings/branding" element={
                <ProtectedRoute requiredRole="ADMIN_UNI">
                  <TenantSettings />
                </ProtectedRoute>
              } />
              <Route path="settings/2fa" element={
                <ProtectedRoute>
                  <TwoFactorSetup />
                </ProtectedRoute>
              } />
              <Route path="notifications" element={
                <ProtectedRoute>
                  <Notifications />
                </ProtectedRoute>
              } />
              <Route path="settings" element={
                <ProtectedRoute>
                  <Settings />
                </ProtectedRoute>
              } />
            </Route>
          </Routes>
        </Suspense>
      </Router>
    </AuthProvider>
  );
};

export default App;