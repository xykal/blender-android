# Blender for Android — port sendiri (unofficial)

Fork & build port Blender untuk Android: **arm64-v8a** (utama), **x86_64** (Chromebook/emulator), **armeabi-v7a** (legacy 32-bit), dengan sasaran jangka panjang **multi-renderer** (Vulkan + Turnip + OpenGL via Zink), bukan cuma satu jalur.

> ⚠️ **Unofficial.** Proyek ini **tidak berafiliasi dengan, dan tidak di-endorse oleh Blender Foundation.** Blender adalah merek dagang Blender Foundation. Semua kode Blender berlisensi **GPLv3** — baca `NOTICE.md` sebelum distribusi.

**Status:** 🚧 M0 — menyiapkan build pipeline. Belum ada rilis.

**Prinsip proyek:**

1. **Nggak build di lokal.** Semua build jalan di GitHub Actions (repo publik = menit Actions gratis). Repo ini isinya patch + skrip + CI, bukan source Blender.
2. **Basis upstream, bukan hard-fork.** Ambil branch `android` dari `blender/blender`, tempel patch sesedikit mungkin.
3. **Satu ABI satu APK** (dan nanti: satu renderer satu varian, kalau perlu).
4. **Jujur soal kompatibilitas.** Nggak ada klaim "jalan di semua HP".

---

## Tier kompatibilitas + renderer

| Tier | ABI | Android | GPU | Renderer | Isi |
|---|---|---|---|---|---|
| **A — Utama** | arm64-v8a | 10+ (API 29) | Vulkan 1.1 | Vulkan driver vendor | Full |
| **A-lite** | arm64-v8a | 10+ | Vulkan 1.1, RAM kecil | Vulkan driver vendor | Lite |
| **A-turnip** | arm64-v8a | 10+ | Adreno 6xx/7xx | Vulkan **Turnip** (Mesa) | Full + |
| **A-gl** | arm64-v8a | 10+ | Vulkan 1.1 apa saja | **OpenGL via Zink** | Full + Mesa |
| **B — Desktop-mode** | x86_64 | 10+ | Vulkan 1.1 | Vulkan driver vendor | Full |
| **C — ARM 32-bit** | armeabi-v7a | 10+ | Vulkan 1.1 **wajib** | Vulkan driver vendor | **Lite** (profil deps memangkas Embree/OIDN/USD/MaterialX/OpenVDB/Alembic) — eksperimental, sedang diiterasi di CI |
| **D — No-Vulkan** | apa saja | – | – | – | ❌ belum ada; butuh backend GLES (proyek riset) |

Tidak ada jalur OpenGL/GLES **native** di Android. Device tanpa driver Vulkan **tidak bisa** menjalankan app ini sampai backend GLES ada — detail lengkap, alasan, dan jalannya ada di **`docs/RENDERERS.md`**.

---

## Struktur repo

```
.
├── .github/
│   ├── workflows/android-build.yml   # CI build (arm64 / x64 / armv7)
│   └── ISSUE_TEMPLATE/compat-report.yml
├── docs/
│   ├── PLAN.md            # rencana besar: strategi ABI, optimasi, risiko, milestone awal
│   ├── RENDERERS.md       # ⭐ multi-renderer: matriks, alasan, selector, fase R1–R6
│   ├── GLES-BACKEND.md    # ⭐ proyek backend OpenGL ES native (moonshot, tanpa jadwal)
│   ├── ROADMAP.md         # M0–M6 + status, dikerjakan bertahap
│   ├── UPSTREAM-NOTES.md  # hasil riset source upstream + anchor patch (biar nggak riset 2×)
│   └── DEVICE-TEST.md     # cara ngetes pakai HP doang (tanpa PC) + template laporan
├── patches/README.md      # konvensi & status setiap patch
└── scripts/
    ├── apply-port-patches.py   # patcher idempoten (armv7 + minSdk)
    ├── verify-apk.sh           # cek ABI, alignment 16 KB, Vulkan di APK
    └── check-device.sh         # cek kesanggupan HP (jalankan di Termux, tanpa root)
```

## Cara build (lewat GitHub Actions)

1. Push repo ini ke GitHub (publik — menit Actions gratis + sekalian penuhi syarat source GPL).
2. **Actions** → workflow **android-build** → **Run workflow** → pilih ABI (`arm64` dulu).
3. Selesai → unduh APK dari **Artifacts**.

Build penuh **1–3 jam** (deps Blender gede; ke-cache untuk build berikutnya). Tidak butuh secret apa pun: build type `release` di skeleton Gradle upstream di-sign dengan debug keystore.

Build armv7? Jalankan workflow dengan pilihan ABI **armv7** — CI memakai jalur `make deps android armv7` + `make android armv7 lite`, kegagalannya tidak memblokir build arm64/x64, dan log deps-nya otomatis di-dump untuk dijadikan patch berikutnya.

Ingin minSdk lebih rendah? Tambahkan input lewat patch: `python3 scripts/apply-port-patches.py --blender blender --minsdk 28` (Android 9). Ini **lebih murah** daripada mengejar armv7 dan menjangkau lebih banyak device nyata.

## Testing tanpa PC

Jalankan `scripts/check-device.sh` di Termux (atau pakai AIDA64/DevCheck) → tahu sebelum mengunduh 200+ MB: ABI, versi Android, dan ada/tidaknya `libvulkan.so`. Checklist lengkap + protokol laporan: `docs/DEVICE-TEST.md`.

## Lisensi & kepatuhan

- Kode Blender: **GPLv3** (atau lebih baru). Patch di repo ini ikut GPLv3.
- Kalau lo distribusiin APK hasil build, **wajib** sediakan source yang sesuai — CI sudah otomatis menghasilkan `porting-<abi>.patch` + `upstream-commit-<abi>.txt` tiap build; sertakan itu di setiap rilis.
- Jangan pakai nama/logo Blender seolah resmi. Selalu "unofficial community port".
