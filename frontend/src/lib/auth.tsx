import { createContext, useContext, useState, ReactNode, useEffect } from 'react';
import api from './api';

export interface TenantInfo {
  id: number;
  slug: string;
  subdomain: string | null;
  nama_uni: string;
  nama_kantor_misi: string;
  nama_jemaat_lokal: string;
  plan: string;
  status: string;
  is_active: boolean;
  contact_email: string | null;
  contact_phone: string | null;
  nama_pendeta: string | null;
  nama_ketua_keuangan: string | null;
  nama_bendahara: string | null;
  initial_jemaat: string | null;
}

interface AuthContextType {
  token: string | null;
  role: string | null;
  tenant_id: string | null;
  tenant_slug: string | null;
  tenant: TenantInfo | null;
  login: (username: string, password: string, tenantSlug?: string) => Promise<{ requires_2fa?: boolean; partial_token?: string; username?: string } | void>;
  loginStep2: (partialToken: string, totpCode: string) => Promise<void>;
  logout: () => void;
  refreshTenant: () => Promise<void>;
  isAuthenticated: boolean;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider = ({ children }: { children: ReactNode }) => {
  const [token, setToken] = useState<string | null>(localStorage.getItem('token'));
  const [role, setRole] = useState<string | null>(localStorage.getItem('role'));
  const [tenant_id, setTenantId] = useState<string | null>(localStorage.getItem('tenant_id'));
  const [tenant_slug, setTenantSlug] = useState<string | null>(localStorage.getItem('tenant_slug'));
  const [tenant, setTenant] = useState<TenantInfo | null>(null);
  const [isAuthenticated, setIsAuthenticated] = useState(!!token);

  const fetchTenant = async () => {
    try {
      const response = await api.get('/v1/tenants/me');
      setTenant(response.data);
    } catch (error) {
      console.error('Failed to fetch tenant info:', error);
      setTenant(null);
    }
  };

  const login = async (username: string, password: string, tenantSlug?: string) => {
    try {
      const payload: { username: string; password: string; tenant_slug?: string } = {
        username,
        password,
      };
      if (tenantSlug) {
        payload.tenant_slug = tenantSlug;
      }
      const response = await api.post('/v1/auth/login', payload);

      // T23-7: Check if 2FA required
      if (response.data.requires_2fa) {
        return {
          requires_2fa: true,
          partial_token: response.data.partial_token,
          username: response.data.username,
        };
      }

      // Direct login (no 2FA)
      const { access_token, role, tenant_id, tenant_slug: returnedSlug } = response.data;

      localStorage.setItem('token', access_token);
      localStorage.setItem('role', role);
      localStorage.setItem('tenant_id', tenant_id);
      if (returnedSlug) {
        localStorage.setItem('tenant_slug', returnedSlug);
      }

      setToken(access_token);
      setRole(role);
      setTenantId(tenant_id);
      setTenantSlug(returnedSlug || null);
      setIsAuthenticated(true);

      // Fetch tenant info setelah login (dipakai di navbar/dashboard)
      await fetchTenant();
    } catch (error) {
      console.error('Login failed:', error);
      throw error;
    }
  };

  const loginStep2 = async (partialToken: string, totpCode: string) => {
    try {
      const response = await api.post('/v1/auth/2fa/login', {
        partial_token: partialToken,
        totp_code: totpCode,
      });
      const { access_token, role, tenant_id, tenant_slug: returnedSlug } = response.data;

      localStorage.setItem('token', access_token);
      localStorage.setItem('role', role);
      localStorage.setItem('tenant_id', tenant_id);
      if (returnedSlug) {
        localStorage.setItem('tenant_slug', returnedSlug);
      }

      setToken(access_token);
      setRole(role);
      setTenantId(tenant_id);
      setTenantSlug(returnedSlug || null);
      setIsAuthenticated(true);

      await fetchTenant();
    } catch (error) {
      console.error('2FA login step 2 failed:', error);
      throw error;
    }
  };

  const refreshTenant = async () => {
    await fetchTenant();
  };

  const logout = async () => {
    // v1.5-A: Hit backend POST /auth/logout dulu untuk blacklist JWT ini
    // (best-effort — kalau backend error, tetap clear local state)
    const currentToken = localStorage.getItem('token');
    if (currentToken) {
      try {
        await api.post('/v1/auth/logout');
      } catch (e) {
        console.warn('Backend logout failed (token may already be revoked):', e);
      }
    }
    localStorage.removeItem('token');
    localStorage.removeItem('role');
    localStorage.removeItem('tenant_id');
    localStorage.removeItem('tenant_slug');
    setToken(null);
    setRole(null);
    setTenantId(null);
    setTenantSlug(null);
    setTenant(null);
    setIsAuthenticated(false);
    window.location.href = '/login';
  };

  // Fetch tenant info on mount kalau sudah authenticated
  useEffect(() => {
    if (token) {
      fetchTenant();
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    setIsAuthenticated(!!token);
  }, [token]);

  return (
    <AuthContext.Provider
      value={{
        token,
        role,
        tenant_id,
        tenant_slug,
        tenant,
        login,
        loginStep2,
        logout,
        refreshTenant,
        isAuthenticated,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (undefined === context) {
    throw new Error('useAuth must be used within AuthProvider');
  }
  return context;
};
