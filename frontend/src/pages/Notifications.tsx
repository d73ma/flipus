import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../lib/api';
import { useAuth } from '../lib/auth';

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

const PER_PAGE_OPTIONS = [25, 50, 100];

const Notifications = () => {
  const navigate = useNavigate();
  const { tenant } = useAuth();
  const [items, setItems] = useState<Notification[]>([]);
  const [total, setTotal] = useState(0);
  const [unreadCount, setUnreadCount] = useState(0);
  const [page, setPage] = useState(1);
  const [perPage, setPerPage] = useState(25);
  const [filter, setFilter] = useState<'all' | 'unread'>('all');
  const [typeFilter, setTypeFilter] = useState<string>('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const fetchList = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const params: Record<string, any> = { page, per_page: perPage };
      if (filter === 'unread') params.unread_only = true;
      const resp = await api.get<{
        items: Notification[];
        total: number;
        unread_count: number;
        page: number;
        per_page: number;
      }>('/v1/notifications', { params });
      let filteredItems = resp.data.items;
      if (typeFilter) {
        filteredItems = filteredItems.filter((n) => n.event_type === typeFilter);
      }
      setItems(filteredItems);
      setTotal(resp.data.total);
      setUnreadCount(resp.data.unread_count);
    } catch (err: any) {
      setError('Gagal load notifikasi');
    } finally {
      setLoading(false);
    }
  }, [page, perPage, filter, typeFilter]);

  useEffect(() => {
    fetchList();
  }, [fetchList]);

  const handleMarkRead = async (n: Notification) => {
    if (!n.is_read) {
      try {
        await api.post(`/v1/notifications/${n.id}/read`);
        setItems((prev) =>
          prev.map((it) =>
            it.id === n.id ? { ...it, is_read: true, read_at: new Date().toISOString() } : it
          )
        );
        setUnreadCount((c) => Math.max(0, c - 1));
      } catch {
        // ignore
      }
    }
    if (n.link) navigate(n.link);
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

  const handleClearRead = async () => {
    if (!confirm('Hapus semua notifikasi yang sudah dibaca?')) return;
    try {
      await api.delete('/v1/notifications/clear-all');
      fetchList();
    } catch {
      // ignore
    }
  };

  const handleDelete = async (id: number) => {
    try {
      await api.delete(`/v1/notifications/${id}`);
      setItems((prev) => prev.filter((n) => n.id !== id));
      setTotal((t) => Math.max(0, t - 1));
    } catch {
      // ignore
    }
  };

  const eventTypes = Array.from(new Set(items.map((i) => i.event_type)));

  const formatFull = (iso: string) => {
    return new Date(iso).toLocaleString('id-ID', {
      day: 'numeric',
      month: 'short',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  const totalPages = Math.max(1, Math.ceil(total / perPage));

  return (
    <div className="max-w-4xl mx-auto">
      <div className="flex justify-between items-start mb-6">
        <div>
          <h1 className="text-3xl font-bold" style={{ color: tenant?.primary_color || '#1B4332' }}>
            🔔 Semua Notifikasi
          </h1>
          <p className="text-gray-600 text-sm mt-1">
            {unreadCount > 0 ? `${unreadCount} belum dibaca` : 'Semua sudah dibaca'} · Total {total}
          </p>
        </div>
        <div className="flex gap-2">
          {unreadCount > 0 && (
            <button
              onClick={handleMarkAllRead}
              className="px-4 py-2 bg-blue-600 text-white rounded-xl text-sm hover:bg-blue-700"
            >
              Tandai semua dibaca
            </button>
          )}
          <button
            onClick={handleClearRead}
            className="px-4 py-2 border border-gray-300 rounded-xl text-sm hover:bg-gray-50"
          >
            Hapus yang sudah dibaca
          </button>
        </div>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-2xl mb-4">
          {error}
        </div>
      )}

      {/* Filters */}
      <div className="bg-white rounded-2xl shadow p-4 mb-4 flex flex-wrap gap-3 items-center">
        <div className="flex gap-2">
          <button
            onClick={() => setFilter('all')}
            className={`px-3 py-1.5 rounded-full text-sm ${
              filter === 'all' ? 'bg-sabbath-dark text-white' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
            }`}
          >
            Semua
          </button>
          <button
            onClick={() => setFilter('unread')}
            className={`px-3 py-1.5 rounded-full text-sm ${
              filter === 'unread' ? 'bg-sabbath-dark text-white' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
            }`}
          >
            Belum dibaca ({unreadCount})
          </button>
        </div>
        {eventTypes.length > 0 && (
          <select
            value={typeFilter}
            onChange={(e) => setTypeFilter(e.target.value)}
            className="px-3 py-1.5 border border-gray-300 rounded-full text-sm bg-white"
          >
            <option value="">Semua tipe event</option>
            {eventTypes.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        )}
        <div className="ml-auto flex items-center gap-2 text-sm">
          <span className="text-gray-600">Per halaman:</span>
          <select
            value={perPage}
            onChange={(e) => {
              setPerPage(Number(e.target.value));
              setPage(1);
            }}
            className="px-2 py-1 border border-gray-300 rounded"
          >
            {PER_PAGE_OPTIONS.map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* List */}
      <div className="bg-white rounded-2xl shadow">
        {loading && items.length === 0 ? (
          <div className="p-12 text-center text-gray-500">Loading...</div>
        ) : items.length === 0 ? (
          <div className="p-12 text-center text-gray-500">
            <div className="text-5xl mb-3">📭</div>
            <p>Tidak ada notifikasi</p>
          </div>
        ) : (
          <div className="divide-y divide-gray-100">
            {items.map((n) => (
              <div
                key={n.id}
                className={`px-5 py-4 hover:bg-gray-50 transition-colors ${
                  !n.is_read ? 'bg-blue-50/30' : ''
                }`}
              >
                <div className="flex items-start gap-4">
                  <div className="text-3xl flex-shrink-0">{n.icon}</div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex-1">
                        <p className="font-semibold text-base">{n.title}</p>
                        <p className="text-sm text-gray-700 mt-1">{n.message}</p>
                        <div className="flex flex-wrap items-center gap-3 mt-2">
                          <span className="text-xs text-gray-500">{formatFull(n.created_at)}</span>
                          <span className="text-xs px-2 py-0.5 bg-gray-100 rounded text-gray-600">
                            {n.event_type}
                          </span>
                          {n.link && (
                            <button
                              onClick={() => handleMarkRead(n)}
                              className="text-xs text-blue-600 hover:underline"
                            >
                              Buka →
                            </button>
                          )}
                          {!n.is_read && (
                            <button
                              onClick={async () => {
                                await api.post(`/v1/notifications/${n.id}/read`);
                                setItems((prev) =>
                                  prev.map((it) =>
                                    it.id === n.id
                                      ? { ...it, is_read: true, read_at: new Date().toISOString() }
                                      : it
                                  )
                                );
                                setUnreadCount((c) => Math.max(0, c - 1));
                              }}
                              className="text-xs text-gray-500 hover:text-gray-700"
                            >
                              Tandai dibaca
                            </button>
                          )}
                        </div>
                      </div>
                      <button
                        onClick={() => handleDelete(n.id)}
                        className="text-gray-400 hover:text-red-500 text-xl flex-shrink-0"
                        aria-label="Hapus"
                      >
                        ×
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex justify-between items-center mt-4 text-sm">
          <span className="text-gray-600">
            Halaman {page} dari {totalPages}
          </span>
          <div className="flex gap-2">
            <button
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page === 1}
              className="px-3 py-1 border border-gray-300 rounded disabled:opacity-50 hover:bg-gray-50"
            >
              ← Sebelumnya
            </button>
            <button
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              disabled={page === totalPages}
              className="px-3 py-1 border border-gray-300 rounded disabled:opacity-50 hover:bg-gray-50"
            >
              Berikutnya →
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

export default Notifications;