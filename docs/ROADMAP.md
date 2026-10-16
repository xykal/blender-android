# ROADMAP — dikerjakan bertahap

Aturan main: **satu milestone selesai → baru lanjut.** Jangan lompat ke 32-bit atau ke backend GLES sebelum baseline 64-bit stabil; 90% nilainya ada di baseline.

Legenda: `[ ]` belum · `[~]` jalan · `[x]` selesai

---

## M0 — APK arm64 hasil build sendiri  ⬅️ SEKARANG

- [ ] Repo publik dibuat & file di repo ini di-push
- [ ] Workflow `android-build` sukses bikin APK `arm64`
- [ ] APK ke-install & nyala di device tes, bisa buka file .blend sederhana
- [ ] Simpan APK sebagai GitHub Release (plus tag)

## M1 — Multi-ABI (x86_64)

- [ ] Workflow matrix jalan buat `x64`
- [ ] Diuji di emulator / Chromebook
- [ ] Skema `versionCode` per-ABI terbukti (upgrade antar ABI tidak error)

## M2 — Optimasi & profil Lite

- [ ] Profil **Lite**: tanpa video/FFmpeg, tanpa USD/Alembic, addon dipangkas
- [ ] Python stdlib dipangkas + `.pyc` precompiled
- [ ] Link flag: 16 KB page align, gc-sections, strip semua `.so`
- [ ] Pipeline cache Vulkan di-persist (kurangi stutter shader)
- [ ] Default EEVEE ramah mobile (TAA 8, motion blur off), viewport scale 0.85
- [ ] Benchmark terdokumentasi (startup, FPS viewport, EEVEE, Cycles CPU)
- [ ] Tombol "share startup log" di app (agar bisa lapor tanpa PC)

## M2.5 — Runtime renderer: multi-jalur (lihat `docs/RENDERERS.md`)

Ini "pembeda" proyek: Blender punya 2 backend (Vulkan + OpenGL), kita sediakan >1 implementasi driver di bawahnya + pemilihan otomatis.

- [ ] **R1 — Selector + layar diagnostik.** Baca preferensi/env, coba kandidat berurutan, simpan `last_ok`, anti crash-loop, tampilkan driver/extension di app
- [ ] **R2 — Bundel Turnip** (Vulkan open-source, Adreno): build Mesa, packaging ICD, varian APK `-turnip`
- [ ] **R3 — Bundel Zink + kopper** (desktop GL di atas Vulkan): jalur GHOST EGL/`EGL_OPENGL_API`, `--gpu-backend opengl` hidup
- [ ] **R4 — Spike Freedreno**: verifikasi `ARB_shader_draw_parameters` + `ARB_clip_control` ada/tidak
- [ ] **R5 — lavapipe untuk CI**: uji render headless tanpa device fisik
- [ ] Varian APK per-renderer + sufiks digit `versionCode`

**Prasyarat:** M2 selesai dulu (baseline stabil), karena debugging renderer di atas baseline yang labil itu neraka.

## M3 — UI sentuh + stylus

- [ ] Angkat pekerjaan UI dari fork komunitas (tool variant long-press, chrome ukuran jari)
- [ ] Stylus: tekanan + tilt
- [ ] Gesture: 1 jari orbit, 2 jari pan/pinch, undo gesture
- [ ] Panel shortcut keyboard virtual
- [ ] Uji Samsung DeX / desktop mode dengan mouse + keyboard eksternal

## M4 — Spike 32-bit (armeabi-v7a) — gerbang keputusan

- [x] Patch toolchain (allowlist ABI + NEON) — sudah di `scripts/apply-port-patches.py`
- [x] Patch digit `versionCode` + arch triple sysroot — sudah
- [x] Patch `LIBDIR_ANDROID` di `platform_unix.cmake` — sudah
- [x] Patch routing arch di `GNUmakefile` (`armv7` goal + `ANDROID_ABI`) — sudah
- [x] Profil **deps armv7 Lite** di patcher (lewati Embree/OIDN/USD/MaterialX/OpenVDB/Alembic + guard `BLENDER_ANDROID_ARMV7_LITE`) — sudah
- [~] `make deps android armv7` tembus — sedang diiterasi di CI (job armv7 + dump log otomatis)
- [x] Goal build `lite` dipakai untuk armv7 (`make android armv7 lite`) — sudah
- [ ] Blender nyala di **minimal satu** device armv7
- [ ] Keputusan: lanjut 32-bit, atau stop dan alihkan ke `--minsdk 28` (Android 9, arm64)

## M4.5 — minSdk lebih rendah (lebih murah dari armv7)

- [x] Patch `ANDROID_PLATFORM android-28` + `timespec_get` di `uuid.cc` — sudah di `apply-port-patches.py --minsdk 28`
- [ ] Uji di device Android 9/10 64-bit sungguhan
- [ ] (opsional) API ≤ 27: patch OpenJPH (`aligned_alloc`) — belum

## M5 — Rilis komunitas

- [ ] GitHub Releases per-ABI/per-renderer + catatan kompatibilitas
- [ ] Job CI yang membundel source GPL (`porting-<abi>.patch` + build script) di tiap rilis
- [ ] Tabel perangkat teruji (dari laporan issue)
- [ ] Dokumentasi instalasi untuk user awam

## M6 — Backend GLES native (proyek riset, tanpa jadwal)

Hanya jalur ini yang bisa menolong device tanpa Vulkan. Rencana lengkap: `docs/GLES-BACKEND.md`.

- [ ] S1: inisialisasi GLES + cetak capability dari app Android
- [ ] S2: Workbench satu objek benar (termasuk depth & sRGB)
- [ ] S3: UI Blender ter-render (uji emulasi `clip_control`)
- [ ] S4: clipping & selection benar
- [ ] S5: scene 100k–500k tri, bandingkan visual dengan GL desktop
- [ ] Gate: kalau S3 tersangkut > ~2 bulan → hentikan, alihkan ke opsi "Blender 2.79 + GL4ES" untuk device jadul

---

## Ide setelah M5 (belum dijanjikan)

- Terjemahan UI Indonesia untuk istilah teknis Blender
- Preset "mobile" (startup file khusus HP)
- Deteksi device → auto pilih default yang pas (thread count, resolusi viewport, renderer)
- Integrasi stylus tingkat lanjut (radial menu dengan tekanan)
- "Safe mode" otomatis: kalau crash 2×, turunkan ke renderer paling konservatif + viewport paling sederhana
