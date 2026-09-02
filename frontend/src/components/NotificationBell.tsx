import { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../lib/api';

interface Notification {
  id: number;
  event_type: string;
  title: string;
  message: string;
  icon: string;
  link: string | null;
  related_entity_type: string | null;
  related_entity_id: string | null;
  is_read: boolean;
  created_at: string;
  read_at: string | null;
}

interface NotificationList {
  items: Notification[];
  total: number;
  unread_count: number;
  page: number;
  per_page: number;
}

const POLL_INTERVAL_MS = 30000; // 30 detik

export const NotificationBell = () => {
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [unreadCount, setUnreadCount] = useState(0);
  const [items, setItems] = useState<Notification[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const dropdownRef = useRef<HTMLDivElement>(null);

  const fetchUnreadCount = useCallback(async () => {
    try {
      const resp = await api.get<{ unread_count: number }>('/v1/notifications/unread-count');
      setUnreadCount(resp.data.unread_count);
    } catch {
      // Silent fail — user not authenticated or server down
    }
  }, []);

  const fetchList = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const resp = await api.get<NotificationList>('/v1/notifications?per_page=10');
      setItems(resp.data.items);
      setUnreadCount(resp.data.unread_count);
    } catch (err: any) {
      setError('Gagal load notifikasi');
    } finally {
      setLoading(false);
    }
  }, []);

  // Poll unread count
  useEffect(() => {
    fetchUnreadCount();
    const interval = setInterval(fetchUnreadCount, POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [fetchUnreadCount]);

  // Click outside closes dropdown
  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    if (open) {
      document.addEventListener('mousedown', handleClick);
      return () => document.removeEventListener('mousedown', handleClick);
    }
  }, [open]);

  // When opening: fetch fresh list
  useEffect(() => {
    if (open) fetchList();
  }, [open, fetchList]);

  const handleMarkRead = async (notif: Notification) => {
    if (!notif.is_read) {
      try {
        await api.post(`/v1/notifications/${notif.id}/read`);
        setItems((prev) =>
          prev.map((n) =>
            n.id === notif.id ? { ...n, is_read: true, read_at: new Date().toISOString() } : n
          )
        );
        setUnreadCount((c) => Math.max(0, c - 1));
      } catch {
        // ignore
      }
    }
    if (notif.link) {
      setOpen(false);
      navigate(notif.link);
    }
  };

  const handleMarkAllRead = async () => {
    try {
      await api.post('/v1/notifications/read-all');
      setItems((prev) =>
        prev.map((n) => ({ ...n, is_read: true, read_at: new Date().toISOString() }))
      );
      setUnreadCount(0);
    } catch {
      // ignore
    }
  };

  const handleDelete = async (id: number, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await api.delete(`/v1/notifications/${id}`);
      setItems((prev) => prev.filter((n) => n.id !== id));
    } catch {
      // ignore
    }
  };

  const formatRelative = (iso: string) => {
    const diff = Date.now() - new Date(iso).getTime();
    const sec = Math.floor(diff / 1000);
    if (sec < 60) return 'baru saja';
    const min = Math.floor(sec / 60);
    if (min < 60) return `${min}m lalu`;
    const hr = Math.floor(min / 60);
    if (hr < 24) return `${hr}j lalu`;
    const day = Math.floor(hr / 24);
    if (day < 7) return `${day}h lalu`;
    return new Date(iso).toLocaleDateString('id-ID');
  };

  return (
    <div className="relative" ref={dropdownRef}>
      <button
        onClick={() => setOpen((o) => !o)}
        className="relative text-white/80 hover:text-white px-2 py-1 text-lg"
        aria-label="Notifikasi"
      >
        🔔
        {unreadCount > 0 && (
          <span className="absolute -top-1 -right-1 min-w-[20px] h-5 px-1 bg-red-500 text-white text-xs font-bold rounded-full flex items-center justify-center">
            {unreadCount > 99 ? '99+' : unreadCount}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 mt-2 w-96 max-h-[32rem] bg-white text-gray-800 rounded-2xl shadow-2xl border border-gray-200 z-50 overflow-hidden flex flex-col">
          {/* Header */}
          <div className="px-4 py-3 border-b border-gray-200 flex justify-between items-center bg-gray-50">
            <h3 className="font-bold text-sm">Notifikasi</h3>
            <div className="flex gap-2">
              {unreadCount > 0 && (
                <button
                  onClick={handleMarkAllRead}
                  className="text-xs text-blue-600 hover:underline"
                >
                  Tandai semua dibaca
                </button>
              )}
            </div>
          </div>

          {/* Body */}
          <div className="flex-1 overflow-y-auto">
            {loading && items.length === 0 ? (
              <div className="p-6 text-center text-sm text-gray-500">Loading...</div>
            ) : error ? (
              <div className="p-6 text-center text-sm text-red-500">{error}</div>
            ) : items.length === 0 ? (
              <div className="p-6 text-center text-sm text-gray-500">
                <div className="text-3xl mb-2">📭</div>
                Belum ada notifikasi
              </div>
            ) : (
              items.map((n) => (
                <div
                  key={n.id}
                  onClick={() => handleMarkRead(n)}
                  className={`px-4 py-3 border-b border-gray-100 hover:bg-gray-50 cursor-pointer transition-colors ${
                    !n.is_read ? 'bg-blue-50/40' : ''
                  }`}
                >
                  <div className="flex items-start gap-3">
                    <div className="text-xl flex-shrink-0">{n.icon}</div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-start justify-between gap-2">
                        <p className="font-medium text-sm leading-tight">{n.title}</p>
                        <button
                          onClick={(e) => handleDelete(n.id, e)}
                          className="text-gray-400 hover:text-red-500 text-xs flex-shrink-0"
                          aria-label="Hapus"
                        >
                          ×
                        </button>
                      </div>
                      <p className="text-xs text-gray-600 mt-1 line-clamp-2">{n.message}</p>
                      <div className="flex items-center gap-2 mt-1">
                        <span className="text-xs text-gray-400">{formatRelative(n.created_at)}</span>
                        {!n.is_read && (
                          <span className="w-2 h-2 bg-blue-500 rounded-full inline-block" />
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>

          {/* Footer */}
          <div className="px-4 py-2 border-t border-gray-200 text-center bg-gray-50">
            <button
              onClick={() => {
                setOpen(false);
                navigate('/notifications');
              }}
              className="text-xs text-blue-600 hover:underline font-medium"
            >
              Lihat semua notifikasi →
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

export default NotificationBell;