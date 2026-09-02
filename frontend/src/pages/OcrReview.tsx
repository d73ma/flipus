import { useState, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../lib/api';

interface BatchItem {
  path: string;
  nama_umat: string;
  perpuluhan_X_angka: number;
  PT_angka: number;
  total_pemberian_angka: number;
  porsi_kantor_misi: number;
  porsi_kas_jemaat: number;
  img_hash?: string;
  ocr_status?: 'VALID_MATCH' | 'NEED_REVIEW';
  ocr_source?: 'gemini' | 'ollama_fallback';
  needs_manual_review?: boolean;
}

interface BatchResult {
  total_amplop: number;
  total_x_terbaca: number;
  total_pt_terbaca: number;
  need_review_count?: number;
  items: BatchItem[];
}

/**
 * Item yang sudah di-staging (siap dikirim ke backend).
 * `source` membedakan OCR vs Manual entry.
 * `tempId` untuk identifikasi visual di Section Data Sementara.
 */
interface StagingItem {
  tempId: string;
  source: 'ocr' | 'manual';
  path?: string;
  nama_umat: string;
  nomor_whatsapp: string;
  perpuluhan_x_angka: number;
  pt_angka: number;
  khusus_angka: number;
  ocr_source?: 'gemini' | 'ollama_fallback';
}

interface SavedItem {
  nomor_kuitansi: string;
  nama_umat: string | null;
  perpuluhan_x_angka: number;
  pt_angka: number;
  khusus_angka: number;
  total_pemberian_angka: number;
  auto_thanks_sent: boolean;
}

interface OcrBatchSaveOut {
  status: string;
  saved_count: number;
  auto_thanks_count: number;
  items: SavedItem[];
}

const EMPTY_MANUAL_FORM: Omit<StagingItem, 'tempId' | 'source'> = {
  nama_umat: '',
  nomor_whatsapp: '',
  perpuluhan_x_angka: 0,
  pt_angka: 0,
  khusus_angka: 0,
};

const newTempId = () => `temp_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;

const OcrReview = () => {
  const navigate = useNavigate();
  const fileInputRef = useRef<HTMLInputElement>(null);

  // ===== Upload + OCR =====
  const [files, setFiles] = useState<File[]>([]);
  const [ocrResult, setOcrResult] = useState<BatchResult | null>(null);
  const [ocrDraft, setOcrDraft] = useState<StagingItem | null>(null);
  const [loading, setLoading] = useState(false);

  // ===== Manual entry =====
  const [manualForm, setManualForm] = useState(EMPTY_MANUAL_FORM);

  // ===== Staging & save =====
  const [staging, setStaging] = useState<StagingItem[]>([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [savedResult, setSavedResult] = useState<OcrBatchSaveOut | null>(null);

  // ===== Handlers: Upload =====
  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      setFiles(Array.from(e.target.files));
      setOcrResult(null);
      setOcrDraft(null);
      setError('');
    }
  };

  const handleUpload = async () => {
    if (files.length === 0) {
      alert('Pilih minimal 1 foto amplop');
      return;
    }

    setLoading(true);
    setError('');
    try {
      const formData = new FormData();
      files.forEach((f) => formData.append('files', f));
      const r = await api.post<BatchResult>('/v1/scan/batch-upload', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      setOcrResult(r.data);

      // Ambil item pertama sebagai draft untuk Section Review.
      // (Per design: OCR 1 foto → 1 row review)
      const first = r.data.items[0];
      setOcrDraft(
        first
          ? {
              tempId: newTempId(),
              source: 'ocr',
              path: first.path,
              nama_umat: first.nama_umat || '',
              nomor_whatsapp: '',
              perpuluhan_x_angka: first.perpuluhan_X_angka || 0,
              pt_angka: first.PT_angka || 0,
              khusus_angka: 0,
              ocr_source: first.ocr_source,
            }
          : null
      );

      // Kosongkan file input supaya bisa upload lagi
      if (fileInputRef.current) fileInputRef.current.value = '';
      setFiles([]);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'OCR gagal');
    } finally {
      setLoading(false);
    }
  };

  // ===== Handlers: Edit OCR draft =====
  const updateOcrDraft = (field: keyof StagingItem, value: string | number) => {
    setOcrDraft((prev) => (prev ? { ...prev, [field]: value } : prev));
  };

  // ===== Handlers: Save OCR to staging =====
  const saveOcrToStaging = () => {
    if (!ocrDraft) return;
    setStaging((prev) => [...prev, ocrDraft]);
    setOcrDraft(null);
    setOcrResult(null);
  };

  const discardOcrDraft = () => {
    setOcrDraft(null);
    setOcrResult(null);
  };

  // ===== Handlers: Manual entry =====
  const updateManual = (field: keyof typeof EMPTY_MANUAL_FORM, value: string | number) => {
    setManualForm((prev) => ({ ...prev, [field]: value }));
  };

  const saveManualToStaging = () => {
    if (!manualForm.nama_umat.trim() && manualForm.perpuluhan_x_angka === 0 && manualForm.pt_angka === 0 && manualForm.khusus_angka === 0) {
      alert('Isi minimal nama atau salah satu nominal');
      return;
    }
    setStaging((prev) => [
      ...prev,
      {
        tempId: newTempId(),
        source: 'manual',
        ...manualForm,
      },
    ]);
    setManualForm(EMPTY_MANUAL_FORM);
  };

  const resetManual = () => setManualForm(EMPTY_MANUAL_FORM);

  // ===== Handlers: Staging =====
  const removeFromStaging = (tempId: string) => {
    setStaging((prev) => prev.filter((it) => it.tempId !== tempId));
  };

  // ===== Final save to DB =====
  const handleFinalSave = async () => {
    if (staging.length === 0) {
      alert('Data sementara kosong. Tambahkan minimal 1 kuitansi.');
      return;
    }
    if (
      !confirm(
        `Simpan ${staging.length} kuitansi ke database? Pastikan total sudah cocok dengan cash tunai yang diterima.`
      )
    )
      return;

    setSaving(true);
    setError('');
    try {
      // Kirim hanya field yang dibutuhkan backend
      const items = staging.map((it) => ({
        path: it.path,
        nama_umat: it.nama_umat,
        nomor_whatsapp: it.nomor_whatsapp,
        perpuluhan_x_angka: it.perpuluhan_x_angka,
        pt_angka: it.pt_angka,
        khusus_angka: it.khusus_angka,
      }));
      console.log('[FLIPUS save-batch] payload:', JSON.stringify({ items, send_auto_thanks: true }));
      const r = await api.post<OcrBatchSaveOut>('/v1/scan/save-batch', {
        items,
        send_auto_thanks: true,
      });
      console.log('[FLIPUS save-batch] response:', r.data);
      setSavedResult(r.data);
    } catch (err: any) {
      console.error('[FLIPUS save-batch] error:', err);
      const status = err.response?.status;
      const detail = err.response?.data?.detail || err.response?.data || err.message || 'Save gagal';
      setError(`Save gagal (${status}): ${typeof detail === 'string' ? detail : JSON.stringify(detail)}`);
    } finally {
      setSaving(false);
    }
  };

  // ===== Reset untuk batch baru (setelah save berhasil) =====
  const resetAll = () => {
    setFiles([]);
    setOcrResult(null);
    setOcrDraft(null);
    setManualForm(EMPTY_MANUAL_FORM);
    setStaging([]);
    setSavedResult(null);
    setError('');
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  // ===== Computed =====
  const stagingTotal = staging.reduce(
    (sum, it) => sum + it.perpuluhan_x_angka + it.pt_angka + it.khusus_angka,
    0
  );

  // ===== View: Hasil final setelah save =====
  if (savedResult) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
        <div
          style={{
            background: '#1B4332',
            color: 'white',
            padding: '2rem',
            borderRadius: '1.5rem',
          }}
        >
          <h2 style={{ fontSize: '1.75rem', fontWeight: 700, marginBottom: '0.5rem' }}>
            ✓ Berhasil Disimpan!
          </h2>
          <p style={{ opacity: 0.9 }}>
            {savedResult.saved_count} kuitansi tersimpan •{' '}
            {savedResult.auto_thanks_count} auto-thanks WA terkirim
          </p>
        </div>

        <div
          style={{
            background: 'white',
            borderRadius: '1.5rem',
            boxShadow: '0 1px 3px rgba(0,0,0,0.05)',
            padding: '2rem',
          }}
        >
          <h3 style={{ fontSize: '1.25rem', fontWeight: 600, color: '#1B4332', marginBottom: '1rem' }}>
            Detail Kuitansi
          </h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
            {savedResult.items.map((it, idx) => (
              <div
                key={idx}
                style={{
                  background: '#F5F1E8',
                  padding: '1rem',
                  borderRadius: '1rem',
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                }}
              >
                <div>
                  <p style={{ fontFamily: 'monospace', fontSize: '0.875rem', fontWeight: 700, color: '#1B4332' }}>
                    {it.nomor_kuitansi}
                  </p>
                  <p style={{ fontSize: '0.875rem', color: '#4B5563' }}>
                    {it.nama_umat || 'Tanpa nama'}
                  </p>
                </div>
                <div style={{ textAlign: 'right' }}>
                  <p style={{ fontWeight: 700, color: '#1B4332' }}>
                    Rp {it.total_pemberian_angka.toLocaleString()}
                  </p>
                  <p style={{ fontSize: '0.75rem', color: it.auto_thanks_sent ? '#16A34A' : '#9CA3AF' }}>
                    {it.auto_thanks_sent ? '✓ WA terkirim' : '— WA tidak dikirim'}
                  </p>
                </div>
              </div>
            ))}
          </div>

          <div style={{ display: 'flex', gap: '0.75rem', marginTop: '1.5rem' }}>
            <button
              onClick={resetAll}
              style={{
                flex: 1,
                padding: '0.75rem 1rem',
                background: '#1B4332',
                color: 'white',
                borderRadius: '1rem',
                fontWeight: 500,
                border: 'none',
                cursor: 'pointer',
              }}
            >
              Reset — Mulai Batch Baru
            </button>
            <button
              onClick={() => navigate('/bendahara')}
              style={{
                flex: 1,
                padding: '0.75rem 1rem',
                background: 'white',
                color: '#1B4332',
                border: '1px solid #D1D5DB',
                borderRadius: '1rem',
                fontWeight: 500,
                cursor: 'pointer',
              }}
            >
              Kembali ke Dashboard
            </button>
          </div>
        </div>
      </div>
    );
  }

  // ===== View: Main =====
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      <div>
        <h2 style={{ fontSize: '2rem', fontWeight: 700, color: '#1B4332' }}>
          Upload & Review Foto Amplop
        </h2>
      </div>

      {error && (
        <div
          style={{
            background: '#FEF2F2',
            border: '1px solid #FECACA',
            color: '#B91C1C',
            padding: '1rem',
            borderRadius: '1rem',
          }}
        >
          {error}
        </div>
      )}

      {/* ===== Section 1: Upload Foto ===== */}
      <section
        style={{
          background: 'white',
          borderRadius: '1.5rem',
          boxShadow: '0 1px 3px rgba(0,0,0,0.05)',
          padding: '1.5rem',
        }}
      >
        <h3 style={{ fontSize: '1.15rem', fontWeight: 600, color: '#1B4332', marginBottom: '0.75rem' }}>
          1. Pilih Foto Amplop
        </h3>
        <input
          ref={fileInputRef}
          type="file"
          accept="image/*"
          multiple
          onChange={handleFileChange}
          style={{
            width: '100%',
            padding: '0.75rem',
            border: '1px solid #D1D5DB',
            borderRadius: '1rem',
          }}
        />
        <p style={{ fontSize: '0.875rem', color: '#6B7280', marginTop: '0.5rem' }}>
          {files.length > 0 ? `${files.length} foto dipilih` : 'Belum ada foto'}
        </p>
        <button
          onClick={handleUpload}
          disabled={loading || files.length === 0}
          style={{
            marginTop: '0.75rem',
            width: '100%',
            padding: '0.85rem',
            background: '#1B4332',
            color: 'white',
            borderRadius: '1rem',
            fontWeight: 500,
            border: 'none',
            cursor: loading || files.length === 0 ? 'not-allowed' : 'pointer',
            opacity: loading || files.length === 0 ? 0.5 : 1,
          }}
        >
          {loading ? 'Processing OCR...' : 'Jalankan OCR'}
        </button>
      </section>

      {/* ===== Section 2: Review dari OCR (horizontal) ===== */}
      {ocrDraft && (
        <section
          style={{
            background: ocrDraft && (ocrResult?.items[0]?.needs_manual_review ?? true)
              ? '#FFFBEB'
              : 'white',
            borderRadius: '1.5rem',
            border: '1px solid',
            borderColor: ocrResult?.items[0]?.needs_manual_review ? '#FCD34D' : '#E5E7EB',
            boxShadow: '0 1px 3px rgba(0,0,0,0.05)',
            padding: '1.5rem',
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
            <h3 style={{ fontSize: '1.15rem', fontWeight: 600, color: '#1B4332' }}>
              2. Review dari OCR
            </h3>
            <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
              {ocrResult?.items[0]?.needs_manual_review && (
                <span
                  style={{
                    fontSize: '0.7rem',
                    background: '#FCD34D',
                    color: '#78350F',
                    padding: '0.15rem 0.6rem',
                    borderRadius: '999px',
                    fontWeight: 500,
                  }}
                >
                  ⚠ Perlu dicek
                </span>
              )}
              {ocrDraft.ocr_source && (
                <span
                  style={{
                    fontSize: '0.7rem',
                    background: '#F3F4F6',
                    color: '#4B5563',
                    padding: '0.15rem 0.6rem',
                    borderRadius: '999px',
                  }}
                >
                  via {ocrDraft.ocr_source === 'ollama_fallback' ? 'Ollama' : 'Gemini'}
                </span>
              )}
            </div>
          </div>

          <div
            style={{
              display: 'grid',
              gridTemplateColumns: '2fr 1.2fr 1fr 1fr 1fr',
              gap: '0.5rem',
              alignItems: 'end',
            }}
          >
            <Field
              label="Nama Umat"
              value={ocrDraft.nama_umat}
              onChange={(v) => updateOcrDraft('nama_umat', v)}
            />
            <Field
              label="No. WA"
              value={ocrDraft.nomor_whatsapp}
              onChange={(v) => updateOcrDraft('nomor_whatsapp', v)}
              placeholder="628123456789"
            />
            <NumField
              label="X"
              value={ocrDraft.perpuluhan_x_angka}
              onChange={(v) => updateOcrDraft('perpuluhan_x_angka', v)}
            />
            <NumField
              label="PT"
              value={ocrDraft.pt_angka}
              onChange={(v) => updateOcrDraft('pt_angka', v)}
            />
            <NumField
              label="Khusus"
              value={ocrDraft.khusus_angka}
              onChange={(v) => updateOcrDraft('khusus_angka', v)}
            />
          </div>

          <div
            style={{
              marginTop: '1rem',
              display: 'flex',
              gap: '0.75rem',
              justifyContent: 'flex-end',
              alignItems: 'center',
            }}
          >
            <p
              style={{
                fontSize: '0.85rem',
                fontWeight: 600,
                color: '#1B4332',
                marginRight: 'auto',
              }}
            >
              Total: Rp{' '}
              {(
                ocrDraft.perpuluhan_x_angka +
                ocrDraft.pt_angka +
                ocrDraft.khusus_angka
              ).toLocaleString()}
            </p>
            <button
              onClick={discardOcrDraft}
              style={{
                padding: '0.6rem 1.25rem',
                background: 'transparent',
                color: '#6B7280',
                border: '1px solid #D1D5DB',
                borderRadius: '0.75rem',
                fontSize: '0.85rem',
                cursor: 'pointer',
                whiteSpace: 'nowrap',
              }}
            >
              Lewati
            </button>
            <button
              onClick={saveOcrToStaging}
              style={{
                padding: '0.6rem 1.5rem',
                background: '#1B4332',
                color: 'white',
                border: 'none',
                borderRadius: '0.75rem',
                fontWeight: 600,
                fontSize: '0.85rem',
                cursor: 'pointer',
                whiteSpace: 'nowrap',
              }}
            >
              Simpan →
            </button>
          </div>
        </section>
      )}

      {/* ===== Section 3: Isi Manual (horizontal) ===== */}
      <section
        style={{
          background: 'white',
          borderRadius: '1.5rem',
          boxShadow: '0 1px 3px rgba(0,0,0,0.05)',
          padding: '1.5rem',
        }}
      >
        <h3 style={{ fontSize: '1.15rem', fontWeight: 600, color: '#1B4332', marginBottom: '0.75rem' }}>
          3. Isi Manual
        </h3>

        <div
          style={{
            display: 'grid',
            gridTemplateColumns: '2fr 1.2fr 1fr 1fr 1fr',
            gap: '0.5rem',
            alignItems: 'end',
          }}
        >
          <Field
            label="Nama Umat"
            value={manualForm.nama_umat}
            onChange={(v) => updateManual('nama_umat', v)}
          />
          <Field
            label="No. WA"
            value={manualForm.nomor_whatsapp}
            onChange={(v) => updateManual('nomor_whatsapp', v)}
            placeholder="628123456789"
          />
          <NumField
            label="X"
            value={manualForm.perpuluhan_x_angka}
            onChange={(v) => updateManual('perpuluhan_x_angka', v)}
          />
          <NumField
            label="PT"
            value={manualForm.pt_angka}
            onChange={(v) => updateManual('pt_angka', v)}
          />
          <NumField
            label="Khusus"
            value={manualForm.khusus_angka}
            onChange={(v) => updateManual('khusus_angka', v)}
          />
        </div>

        <div
          style={{
            marginTop: '1rem',
            display: 'flex',
            gap: '0.75rem',
            justifyContent: 'flex-end',
            alignItems: 'center',
          }}
        >
          <p
            style={{
              fontSize: '0.85rem',
              fontWeight: 600,
              color: '#1B4332',
              marginRight: 'auto',
            }}
          >
            Total: Rp{' '}
            {(
              manualForm.perpuluhan_x_angka +
              manualForm.pt_angka +
              manualForm.khusus_angka
            ).toLocaleString()}
          </p>
          <button
            onClick={resetManual}
            style={{
              padding: '0.6rem 1.25rem',
              background: 'transparent',
              color: '#6B7280',
              border: '1px solid #D1D5DB',
              borderRadius: '0.75rem',
              fontSize: '0.85rem',
              cursor: 'pointer',
              whiteSpace: 'nowrap',
            }}
          >
            Reset
          </button>
          <button
            onClick={saveManualToStaging}
            style={{
              padding: '0.6rem 1.5rem',
              background: '#B8860B',
              color: 'white',
              border: 'none',
              borderRadius: '0.75rem',
              fontWeight: 600,
              fontSize: '0.85rem',
              cursor: 'pointer',
              whiteSpace: 'nowrap',
            }}
          >
            Simpan →
          </button>
        </div>
      </section>

      {/* ===== Section 4: Data Sementara (staging) ===== */}
      <section
        style={{
          background: '#F5F1E8',
          borderRadius: '1.5rem',
          padding: '1.5rem',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
          <h3 style={{ fontSize: '1.15rem', fontWeight: 600, color: '#1B4332' }}>
            4. Data Sementara ({staging.length} kuitansi)
          </h3>
          {staging.length > 0 && (
            <span style={{ fontSize: '0.85rem', color: '#1B4332', fontWeight: 600 }}>
              Total: Rp {stagingTotal.toLocaleString()}
            </span>
          )}
        </div>

        {staging.length === 0 ? (
          <p
            style={{
              padding: '1.5rem',
              textAlign: 'center',
              color: '#9CA3AF',
              fontSize: '0.9rem',
              background: 'white',
              borderRadius: '1rem',
              border: '1px dashed #D1D5DB',
            }}
          >
            Belum ada kuitansi di data sementara. Simpan dari Section 2 atau 3 untuk menambah.
          </p>
        ) : (
          <>
            {/* Header tabel */}
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: '0.5fr 0.7fr 1.5fr 1fr 0.9fr 0.9fr 0.7fr 1fr 0.6fr',
                gap: '0.4rem',
                padding: '0.5rem 0.75rem',
                fontSize: '0.7rem',
                fontWeight: 700,
                color: '#6B7280',
                textTransform: 'uppercase',
                letterSpacing: '0.05em',
              }}
            >
              <div>#</div>
              <div>Sumber</div>
              <div>Nama</div>
              <div>WA</div>
              <div style={{ textAlign: 'right' }}>X</div>
              <div style={{ textAlign: 'right' }}>PT</div>
              <div style={{ textAlign: 'right' }}>Khusus</div>
              <div style={{ textAlign: 'right' }}>Total</div>
              <div style={{ textAlign: 'center' }}>Aksi</div>
            </div>

            {staging.map((it, idx) => {
              const total = it.perpuluhan_x_angka + it.pt_angka + it.khusus_angka;
              return (
                <div
                  key={it.tempId}
                  style={{
                    display: 'grid',
                    gridTemplateColumns: '0.5fr 0.7fr 1.5fr 1fr 0.9fr 0.9fr 0.7fr 1fr 0.6fr',
                    gap: '0.4rem',
                    padding: '0.65rem 0.75rem',
                    background: 'white',
                    borderRadius: '0.75rem',
                    marginTop: '0.4rem',
                    alignItems: 'center',
                    fontSize: '0.85rem',
                  }}
                >
                  <div style={{ color: '#9CA3AF', fontFamily: 'monospace' }}>{idx + 1}</div>
                  <div>
                    <span
                      style={{
                        fontSize: '0.65rem',
                        padding: '0.1rem 0.5rem',
                        borderRadius: '999px',
                        background: it.source === 'ocr' ? '#DBEAFE' : '#FEF3C7',
                        color: it.source === 'ocr' ? '#1E40AF' : '#92400E',
                        fontWeight: 500,
                      }}
                    >
                      {it.source === 'ocr' ? 'OCR' : 'Manual'}
                    </span>
                  </div>
                  <div style={{ color: '#1B4332', fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {it.nama_umat || '(tanpa nama)'}
                  </div>
                  <div style={{ color: '#6B7280', fontSize: '0.8rem' }}>
                    {it.nomor_whatsapp || '—'}
                  </div>
                  <div style={{ textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>
                    {it.perpuluhan_x_angka > 0 ? it.perpuluhan_x_angka.toLocaleString() : '—'}
                  </div>
                  <div style={{ textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>
                    {it.pt_angka > 0 ? it.pt_angka.toLocaleString() : '—'}
                  </div>
                  <div style={{ textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>
                    {it.khusus_angka > 0 ? it.khusus_angka.toLocaleString() : '—'}
                  </div>
                  <div style={{ textAlign: 'right', fontWeight: 700, color: '#1B4332' }}>
                    {total.toLocaleString()}
                  </div>
                  <div style={{ textAlign: 'center' }}>
                    <button
                      onClick={() => removeFromStaging(it.tempId)}
                      style={{
                        padding: '0.3rem 0.65rem',
                        background: 'transparent',
                        color: '#DC2626',
                        border: '1px solid #FECACA',
                        borderRadius: '0.5rem',
                        fontSize: '0.75rem',
                        fontWeight: 500,
                        cursor: 'pointer',
                      }}
                    >
                      Hapus
                    </button>
                  </div>
                </div>
              );
            })}

            <div
              style={{
                marginTop: '0.75rem',
                padding: '0.85rem 1rem',
                background: '#1B4332',
                color: 'white',
                borderRadius: '0.75rem',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
              }}
            >
              <span style={{ fontWeight: 600 }}>
                {staging.length} amplop siap simpan
              </span>
              <span style={{ fontWeight: 700, fontSize: '1.1rem' }}>
                Rp {stagingTotal.toLocaleString()}
              </span>
            </div>

            <button
              onClick={handleFinalSave}
              disabled={saving}
              style={{
                marginTop: '1rem',
                width: '100%',
                padding: '1rem',
                background: '#B8860B',
                color: 'white',
                border: 'none',
                borderRadius: '1rem',
                fontWeight: 700,
                fontSize: '1rem',
                cursor: saving ? 'not-allowed' : 'pointer',
                opacity: saving ? 0.5 : 1,
              }}
            >
              {saving
                ? 'Menyimpan ke Database...'
                : `Simpan ${staging.length} Kuitansi ke Dasbor`}
            </button>
            <p
              style={{
                marginTop: '0.5rem',
                fontSize: '0.75rem',
                color: '#6B7280',
                textAlign: 'center',
              }}
            >
              Pastikan total di atas sudah cocok dengan jumlah cash tunai yang diterima.
            </p>
          </>
        )}
      </section>
    </div>
  );
};

// ===== Inline input components (anti-Tailwind misconfig, per memory) =====
// Penting: `minWidth: 0` di wrapper agar grid child bisa shrink.
// Tanpa ini, input dengan content panjang memaksa kolom grid melebar → overlap.
const fieldStyle: React.CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  gap: '0.25rem',
  minWidth: 0,
};

const fieldLabelStyle: React.CSSProperties = {
  fontSize: '0.7rem',
  color: '#6B7280',
  fontWeight: 500,
};

// `box-sizing: border-box` + `minWidth: 0` di input supaya
// width: 100% benar-benar fit dalam grid column tanpa meluber.
const inputStyle: React.CSSProperties = {
  padding: '0.5rem 0.6rem',
  border: '1px solid #D1D5DB',
  borderRadius: '0.5rem',
  fontSize: '0.85rem',
  outline: 'none',
  width: '100%',
  minWidth: 0,
  boxSizing: 'border-box',
  background: 'white',
};

interface FieldProps {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
}

const Field = ({ label, value, onChange, placeholder }: FieldProps) => (
  <div style={fieldStyle}>
    <label style={fieldLabelStyle}>{label}</label>
    <input
      type="text"
      value={value}
      placeholder={placeholder}
      onChange={(e) => onChange(e.target.value)}
      style={inputStyle}
    />
  </div>
);

interface NumFieldProps {
  label: string;
  value: number;
  onChange: (v: number) => void;
}

/**
 * Number input dengan format ribuan Indonesia (1.000.000) dan zero-placeholder UX:
 * - Tampilkan angka dengan titik sebagai pemisah ribuan
 * - Saat field fokus + user mulai ketik, REPLACE nilai lama (bukan append)
 *   → Cegah bug "input 1 jadi 10" saat placeholder masih "0"
 * - Tetap pertahankan tampilan "0" sebagai visual cue saat nilai = 0
 */
const NumField = ({ label, value, onChange }: NumFieldProps) => {
  const [isFocused, setIsFocused] = useState(false);
  // Local string untuk display; sinkron dengan `value` prop saat tidak fokus.
  const [draft, setDraft] = useState<string>(() =>
    value > 0 ? value.toLocaleString('id-ID') : ''
  );

  // Sync external value → local draft saat tidak fokus
  // (supaya reset dari parent ter-reflect ke field, tanpa ganggu user yang sedang mengetik)
  useEffect(() => {
    if (!isFocused) {
      setDraft(value > 0 ? value.toLocaleString('id-ID') : '');
    }
  }, [value, isFocused]);

  const handleFocus = (e: React.FocusEvent<HTMLInputElement>) => {
    setIsFocused(true);
    // Select all supaya user bisa langsung replace angka existing
    e.target.select();
  };

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    // Strip semua non-digit. Hasil: string digit murni (atau kosong).
    const raw = e.target.value.replace(/\D/g, '');
    setDraft(raw);
    const num = raw === '' ? 0 : parseInt(raw, 10);
    onChange(Number.isFinite(num) ? num : 0);
  };

  const handleBlur = () => {
    setIsFocused(false);
    // Saat blur, format ulang dengan pemisah ribuan
    const num = draft === '' ? 0 : parseInt(draft, 10);
    setDraft(num > 0 ? num.toLocaleString('id-ID') : '');
    // Pastikan onChange dipanggil dengan nilai clean number
    if (num !== value) onChange(num);
  };

  // Tampilan: saat fokus → raw digits (biar mudah edit tanpa titik); saat blur → formatted.
  const displayValue = isFocused ? draft : value > 0 ? value.toLocaleString('id-ID') : '';

  return (
    <div style={fieldStyle}>
      <label style={fieldLabelStyle}>{label}</label>
      <input
        type="text"
        inputMode="numeric"
        value={displayValue}
        onChange={handleChange}
        onFocus={handleFocus}
        onBlur={handleBlur}
        placeholder="0"
        style={{
          ...inputStyle,
          textAlign: 'right',
          fontVariantNumeric: 'tabular-nums',
        }}
      />
    </div>
  );
};

export default OcrReview;