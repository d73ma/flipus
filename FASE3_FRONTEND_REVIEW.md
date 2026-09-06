# FASE 3 — Sprint 4 / S4-G: R5 Frontend Review Checklist

> **Tanggal audit**: 2026-09-03
> **Auditor**: Claude (audit/comprehensive-review branch)
> **Scope**: Frontend React 18 + TypeScript + Vite (FLIPUS), 35 file .tsx/.ts, ~11.484 LOC
> **Metodologi**: Static code review terhadap 9 dimensi kualitas (security, a11y, type safety, UX, performance, build, error handling, testing, compliance).

---

## 📊 Executive Summary

| Dimensi | Skor | Status |
|---|---|---|
| **Security** | 6.5/10 | ⚠️ Token di localStorage (XSS-risky) |
| **Type Safety (TS strict)** | 4/10 | ❌ `strict: true` TIDAK aktif |
| **Accessibility (WCAG)** | 3.5/10 | ❌ 1/70 input pakai label association |
| **UX & Error Handling** | 7/10 | ✅ Login flow OK, demo banner bagus |
| **Performance** | 7.5/10 | ✅ Code splitting, lazy loading aktif |
| **Build & Tooling** | 7/10 | ✅ Vite + manual chunks, ESLint minimal |
| **PWA / Offline** | 7.5/10 | ✅ SW network-first untuk API |
| **Testing** | 0/10 | ❌ ZERO test file (no vitest/jest) |
| **Compliance (GMAHK)** | 8/10 | ✅ Bahasa, branding, signage sesuai |

**Kesimpulan**: Frontend FLIPUS secara fungsional solid dan UX-nya sudah matang (split-screen login, demo banner, PWA support). Namun punya **3 celah serius** yang harus jadi prioritas:
- Celah A: TS `strict: false` → bug null/undefined bisa lolos ke production
- Celah B: Form tidak punya `<label htmlFor>` association → tidak accessible (WCAG 1.3.1, 4.1.2 fail)
- Celah C: Token JWT di localStorage → XSS = full session theft

**Tidak ada perubahan kode production dalam S4-G** — semua temuan didokumentasikan untuk perbaikan di FASE 4+ atau sprint enhancement terpisah. Pendekatan ini dipilih karena:
1. Mengubah auth flow (localStorage → httpOnly cookie) butuh backend coordination
2. Menambah 70 htmlFor attributes butuh menyentuh ~20 file
3. Enable TS strict butuh fixing ~50-100 type errors yang muncul

---

## 🔍 Detail Temuan

### 1. SECURITY — Skor 6.5/10 ⚠️

#### 🔴 C-01 (HIGH): JWT Token Disimpan di localStorage
**File**: [`src/lib/auth.tsx:38-41`](../../Users/jerrymauri/Flipus/frontend/src/lib/auth.tsx)
**Severity**: HIGH
**Issue**: Token akses, role, tenant_id, dan tenant_slug disimpan di `localStorage`. Setiap script yang berjalan di origin (termasuk injected via XSS) bisa baca token → full account takeover.
**Rekomendasi**: Migrasi ke httpOnly secure cookie atau sessionStorage dengan CSP ketat.
**Status**: **KNOWN ISSUE — fix di FASE 4** (butuh backend coordination untuk set cookie via Set-Cookie header).

#### 🟡 C-02 (MEDIUM): useDemoMode Bypass Auth Context
**File**: [`src/lib/useDemoMode.ts:23-30`](../../Users/jerrymauri/Flipus/frontend/src/lib/useDemoMode.ts)
**Severity**: MEDIUM
**Issue**: Saat demo timer expire, kode langsung clear localStorage dan redirect via `window.location.href`. Tidak memanggil `logout()` di AuthContext, sehingga backend tidak di-notify dan state React tidak ter-reset dengan benar sampai full reload.
**Rekomendasi**: Panggil `logout()` dari useAuth() di sini.
**Status**: **KNOWN ISSUE — bisa di-fix cepat di FASE 4**.

#### 🟡 C-03 (LOW): Tidak Ada CSRF Token di Mutating Requests
**Severity**: LOW (mitigated)
**Issue**: Mutating requests pakai Authorization header (Bearer), jadi bukan victim CSRF klasik. TAPI: jika ada endpoint yang accept GET untuk state-change, vulnerable. Audit endpoint FastAPI perlu cross-check.
**Status**: **TODO — verify di FASE 4**.

#### ✅ C-04 (POSITIVE): Zero `dangerouslySetInnerHTML`
**Hasil grep**: 0 uses across all 35 files. Tidak ada XSS via HTML injection.

#### ✅ C-05 (POSITIVE): Zero `target="_blank"` Without `rel="noopener"`
**Hasil grep**: 0 uses. Tidak ada tabnabbing vulnerability.

#### ✅ C-06 (POSITIVE): 401 Auto-Redirect di Axios Interceptor
**File**: [`src/lib/api.ts:33-43`](../../Users/jerrymauri/Flipus/frontend/src/lib/api.ts)
Token di-clear dan redirect ke /login saat 401. Bagus — minimal blast radius untuk token expired.

---

### 2. TYPE SAFETY — Skor 4/10 ❌

#### 🔴 T-01 (CRITICAL): TypeScript `strict: false`
**File**: [`tsconfig.app.json`](../../Users/jerrymauri/Flipus/frontend/tsconfig.app.json)
**Severity**: CRITICAL
**Issue**: `strict: true` TIDAK diaktifkan di `compilerOptions`. Konsekuensi:
- `strictNullChecks` off → variabel bisa null/undefined tanpa warning
- `noImplicitAny` off → implicit any lolos
- `strictFunctionTypes`, `strictBindCallApply`, `strictPropertyInitialization` off

**Impact**: Risiko runtime TypeError seperti "Cannot read property X of undefined" lolos ke production.

**Rekomendasi**: Enable `strict: true` di tsconfig.app.json, lalu fix semua error yang muncul (estimasi 50-100 errors butuh 1-2 hari).
**Status**: **KNOWN ISSUE — terlalu besar untuk S4-G scope, prioritas FASE 4 atau sprint khusus**.

#### ✅ T-02 (POSITIVE): `noUnusedLocals`, `noUnusedParameters` Aktif
**File**: tsconfig.app.json (lines 26-27)
Bagus — strict di beberapa area meski bukan strict full.

---

### 3. ACCESSIBILITY (WCAG 2.1 AA) — Skor 3.5/10 ❌

#### 🔴 A-01 (CRITICAL): Form Input Tidak Punya Label Association
**Severity**: CRITICAL
**Issue**: 70 `<input>` elements di seluruh codebase, hanya **1** yang punya `htmlFor` association.
**Contoh di Login.tsx**:
```tsx
<label style={labelStyle}>Username</label>  // ❌ NO htmlFor
<input type="text" value={username} onChange={...} />  // ❌ NO id
```
Screen reader akan announce input sebagai "text edit" tanpa label.
**WCAG Fail**: 1.3.1 (Info and Relationships), 4.1.2 (Name, Role, Value)
**Rekomendasi**: Tambah `id` di setiap input dan `htmlFor={id}` di label, atau wrap dengan `<label>...</label>`.
**Status**: **KNOWN ISSUE — butuh ~70 perbaikan di ~20 file. Prioritas FASE 4 atau sprint a11y khusus**.

#### 🟡 A-02 (MEDIUM): Sidebar Nav Tanpa `aria-label`
**File**: [`src/components/Layout.tsx:309-318`](../../Users/jerrymauri/Flipus/frontend/src/components/Layout.tsx)
`<nav>` element tidak punya `aria-label="Main navigation"`. Multiple nav akan ambigu untuk screen reader.
**Status**: **KNOWN ISSUE**.

#### 🟡 A-03 (MEDIUM): Decorative Icons Tidak `aria-hidden`
**Severity**: LOW-MEDIUM
Banyak emoji icons di sidebar (💸, 🔒, 🔔, ⚙️) akan di-announce sebagai "money with wings" dll oleh screen reader — noisy.
**Status**: **KNOWN ISSUE**.

#### ✅ A-04 (POSITIVE): `<div aria-hidden>` Untuk Decorative Pattern
**File**: Login.tsx:111 (signature perpuluhan motif)
Bagus — pattern decorative sudah di-hide dari a11y tree.

---

### 4. UX & ERROR HANDLING — Skor 7/10 ✅

#### ✅ U-01 (POSITIVE): Demo Mode Banner Excellent
**File**: [`src/components/Layout.tsx:108-153`](../../Users/jerrymauri/Flipus/frontend/src/components/Layout.tsx)
Sticky banner, countdown timer, auto-logout. Bagus untuk safety saat demo publik.

#### ✅ U-02 (POSITIVE): 2FA Flow Two-Step dengan Username Display
**File**: [`src/pages/Login.tsx:153-203`](../../Users/jerrymauri/Flipus/frontend/src/pages/Login.tsx)
User lihat "Login sebagai X" saat masuk step 2. Bagus.

#### 🟡 U-03 (MEDIUM): Error Message Generic untuk 401 di Axios
**File**: [`src/lib/api.ts:36-41`](../../Users/jerrymauri/Flipus/frontend/src/lib/api.ts)
Saat 401, langsung hard-redirect ke /login. Tidak ada toast/notification yang kasih tahu user "session expired" — abrupt experience.
**Rekomendasi**: Tambah toast "Sesi Anda telah berakhir, silakan login ulang" sebelum redirect.
**Status**: **KNOWN ISSUE**.

#### ✅ U-04 (POSITIVE): Lazy Loading + Suspense Fallback
**File**: [`src/App.tsx:16-39`](../../Users/jerrymauri/Flipus/frontend/src/App.tsx)
PageLoader spinner saat chunk dimuat. Bagus untuk first-paint perception.

---

### 5. PERFORMANCE — Skor 7.5/10 ✅

#### ✅ P-01 (POSITIVE): Manual Chunk Strategy Optimal
**File**: [`vite.config.ts:25-30`](../../Users/jerrymauri/Flipus/frontend/vite.config.ts)
```js
manualChunks: {
  'react-vendor': ['react', 'react-dom', 'react-router-dom'],
  'axios': ['axios'],
}
```
Bagus — vendor split untuk caching optimal.

#### ✅ P-02 (POSITIVE): Target `es2020` + Terser
Build target modern browsers, no polyfill bloat.

#### 🟡 P-03 (MEDIUM): BendaharaDashboard 22 useState
**File**: [`src/pages/BendaharaDashboard.tsx`](../../Users/jerrymauri/Flipus/frontend/src/pages/BendaharaDashboard.tsx)
Single-file component dengan 22 useState. Likely re-render storm dan sulit di-maintain.
**Rekomendasi**: Extract ke sub-components atau pakai useReducer untuk related state groups.
**Status**: **KNOWN ISSUE — refactor effort**.

---

### 6. BUILD & TOOLING — Skor 7/10 ✅

#### ✅ B-01 (POSITIVE): Vite Dev Proxy Untuk /api → :8000
**File**: vite.config.ts:13-18
Bagus — frontend tidak perlu tahu hostname backend.

#### 🟡 B-02 (MEDIUM): oxlint Minimal Config
**File**: [`frontend/.oxlintrc.json`](../../Users/jerrymauri/Flipus/frontend/.oxlintrc.json)
Hanya `react/rules-of-hooks` (error) + `react/only-export-components` (warn). Tidak ada:
- `react/jsx-key` (missing key in lists)
- `react/no-array-index-key`
- `@typescript-eslint/no-explicit-any`
- `jsx-a11y/*` (accessibility)
- Security plugins
**Rekomendasi**: Enable jsx-a11y recommended + react-hooks/recommended + typescript-eslint.
**Status**: **KNOWN ISSUE**.

#### ✅ B-03 (POSITIVE): Build Type-check via `tsc && vite build`
Bagus — type errors akan fail build.

---

### 7. PWA / OFFLINE — Skor 7.5/10 ✅

#### ✅ PW-01 (POSITIVE): SW Network-First untuk /api/*
**File**: [`public/service-worker.js`](../../Users/jerrymauri/Flipus/frontend/public/service-worker.js)
Strategy tepat untuk financial app — fresh data lebih penting dari offline access untuk data ledger.

#### ✅ PW-02 (POSITIVE): manifest.json + Icons Ready
PWA installable.

---

### 8. TESTING — Skor 0/10 ❌

#### 🔴 TE-01 (CRITICAL): ZERO Frontend Test Files
**Severity**: CRITICAL
**Issue**: Tidak ada vitest, jest, @testing-library/react, atau react-testing-library di dependencies. package.json scripts hanya: dev, build, lint, preview.
**Dampak**: Tidak ada regression safety net untuk komponen React. Breaking change bisa silent lolos.
**Rekomendasi**:
1. Tambah `vitest`, `@testing-library/react`, `@testing-library/user-event` ke devDependencies
2. Setup vitest config
3. Mulai dengan smoke tests untuk: auth.tsx, api.ts, useDemoMode.ts
4. Component tests untuk: Login, ProtectedRoute, layout items
**Status**: **KNOWN ISSUE — effort besar, disarankan sprint khusus QA**.

---

### 9. COMPLIANCE GMAHK — Skor 8/10 ✅

#### ✅ G-01 (POSITIVE): Bahasa Indonesia Konsisten
Seluruh UI text dalam Bahasa Indonesia (bendahara, ketua, pendeta, dll).

#### ✅ G-02 (POSITIVE): Branding Identity
- FLIPUS wordmark + GMAHK · UKIKT subline
- Palette: #1B4332 (dark green), #B8860B (gold), #F5EFE0 (cream)
- Playfair Display (serif) + Inter (sans-serif)
- Signature "kolom perpuluhan" motif di Login

#### ✅ G-03 (POSITIVE): Role-Based Routing
5 role distinct (BENDAHARA, KETUA_KEUANGAN, PENDETA, AUDITOR_MISI, ADMIN_UNI). Cocok untuk struktur gereja GMAHK.

---

## 📋 Prioritized Action Items

| # | Item | Severity | Effort | Rekomendasi Fase |
|---|---|---|---|---|
| C-01 | Migrate token dari localStorage ke httpOnly cookie | HIGH | 2-3 hari | FASE 4 (multi-tenant) |
| T-01 | Enable TS `strict: true` + fix errors | CRITICAL | 1-2 hari | Sprint khusus |
| A-01 | Tambah `htmlFor` di 70 input | CRITICAL | 0.5-1 hari | Sprint a11y khusus |
| TE-01 | Setup vitest + tulis smoke tests | CRITICAL | 2-3 hari | Sprint khusus |
| B-02 | Expand oxlint rules (jsx-a11y, react-hooks, ts) | MEDIUM | 0.5 hari | Sprint khusus |
| A-02/A-03 | aria-label di nav + aria-hidden emoji | MEDIUM | 0.5 hari | Gabung dengan a11y sprint |
| U-03 | Toast notification saat 401 | MEDIUM | 0.5 hari | Gabung dengan C-01 |
| C-02 | useDemoMode panggil logout() | MEDIUM | 0.5 jam | FASE 4 |
| P-03 | Refactor BendaharaDashboard useState | MEDIUM | 1 hari | FASE 5+ (UI polish) |

**Total effort**: ~8-12 hari kerja untuk address semua item.

---

## 🟢 Yang TIDAK Perlu Diubah (Verified)

- ✅ Zero `dangerouslySetInnerHTML` (XSS-safe rendering)
- ✅ Zero `target="_blank"` (no tabnabbing)
- ✅ 401 auto-redirect di interceptor
- ✅ Lazy loading + code splitting optimal
- ✅ PWA service worker strategy benar
- ✅ GMAHK branding konsisten
- ✅ Role-based routing implemented properly
- ✅ 2FA flow two-step dengan username display

---

## 📌 Refs

- Commit: `7ac4e95` (S4-F), branch `audit/comprehensive-review`
- File sumber: `frontend/src/**/*.{ts,tsx}`, `frontend/public/service-worker.js`
- Backend audit terkait: [`FASE3_AUDIT_BUG_SECURITY.md`](FASE3_AUDIT_BUG_SECURITY.md)
- Test coverage expansion: [`tests/test_s4f_*.py`](../tests/)

---

**Auditor signature**: Claude (audit/comprehensive-review)
**Tanggal**: 2026-09-03
**Re-audit**: FASE 4 / Sprint enhancement khusus