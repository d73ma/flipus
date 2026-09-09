/**
 * FLIPUS — reusable dropdown "Daerah Misi/Konferens".
 *
 * Render <optgroup> 2 grup dengan header TIDAK bisa dipilih:
 *   - "Daerah Konferens" (jenis=KONFERENS)
 *   - "Daerah Misi" (jenis=MISI)
 *
 * Data dari API /v1/master/misi?uni_id=... — backend auto-ensure 13 Daerah
 * UKIKT sesuai spec. Urutan sesuai data master (konferens dulu, misi).
 * Nilai yang disimpan = misi_konferens_id (number), nama tersimpan di DB
 * adalah string lengkap mis. "Daerah Konferens Minahasa".
 *
 * Props:
 * - uniId, value (id number|''), onChange (id), disabled, required,
 *   placeholder, style
 */
import { useEffect, useState } from 'react';
import api from '../lib/api';

interface Misi {
  id: number;
  uni_id: number;
  kode: string;
  nama_resmi: string;
  jenis: string; // KONFERENS / MISI
}

interface Props {
  uniId: number | '';
  value: number | '';
  onChange: (id: number) => void;
  disabled?: boolean;
  required?: boolean;
  placeholder?: string;
  style?: React.CSSProperties;
}

export default function DaerahMisiKonferensSelect({
  uniId,
  value,
  onChange,
  disabled = false,
  required = true,
  placeholder = '— Pilih Misi/Konferens —',
  style,
}: Props) {
  const [misiList, setMisiList] = useState<Misi[]>([]);
  const [loadError, setLoadError] = useState(false);

  useEffect(() => {
    if (!uniId) {
      setMisiList([]);
      setLoadError(false);
      return;
    }
    let cancelled = false;
    api
      .get<Misi[]>('/v1/master/misi', { params: { uni_id: uniId } })
      .then((r) => {
        if (!cancelled) setMisiList(r.data || []);
      })
      .catch(() => {
        if (!cancelled) setLoadError(true);
      });
    return () => {
      cancelled = true;
    };
  }, [uniId]);

  const konferens = misiList.filter((m) => m.jenis === 'KONFERENS');
  const misi = misiList.filter((m) => m.jenis === 'MISI');

  return (
    <select
      required={required}
      disabled={disabled || !uniId}
      value={value === '' ? '' : String(value)}
      onChange={(e) => onChange(e.target.value ? Number(e.target.value) : 0)}
      style={style}
    >
      <option value="" disabled>
        {loadError ? '— Gagal memuat daerah —' : placeholder}
      </option>
      {konferens.length > 0 && (
        <optgroup label="Daerah Konferens">
          {konferens.map((m) => (
            <option key={m.id} value={m.id}>
              {m.nama_resmi}
            </option>
          ))}
        </optgroup>
      )}
      {misi.length > 0 && (
        <optgroup label="Daerah Misi">
          {misi.map((m) => (
            <option key={m.id} value={m.id}>
              {m.nama_resmi}
            </option>
          ))}
        </optgroup>
      )}
    </select>
  );
}