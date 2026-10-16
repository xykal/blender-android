# RENDERERS — "kok cuma Vulkan?" dan bagaimana caranya biar lebih dari itu

Dokumen ini jawab pertanyaan inti proyek: **renderer apa saja yang bisa didukung di Android, dengan biaya berapa, dan urutan mengerjakannya.**

---

## 0. Kenapa port lain cuma Vulkan

Faktanya bukan "malas", tapi struktural:

1. **Android tidak punya desktop OpenGL.** Yang tersedia native hanya **OpenGL ES** (via EGL) dan **Vulkan**. Driver vendor Android tidak mengekspos GL 4.3.
2. **Blender wajib butuh salah satu dari:**
   - **Vulkan 1.1+** (Blender 5.3 menurunkan minimum dari 1.3 → 1.1 khusus supaya kelas mobile bisa masuk), **atau**
   - **OpenGL 4.3** dengan **dua extension wajib**: `GL_ARB_shader_draw_parameters` **dan** `GL_ARB_clip_control`. Bukan "lebih bagus kalau ada" — tanpa itu Blender menolak start.
3. GLES 3.2 (puncak yang dijamin di Android) **tidak memenuhi** syarat nomor 2: tidak ada `ARB_shader_draw_parameters`, tidak ada `ARB_clip_control`, tidak ada geometry/tessellation shader.

Maka jalan realistisnya ada dua keluarga besar:

- **Keluarga Vulkan** — Blender pakai backend Vulkan-nya, driver-nya yang kita variasikan (vendor / Mesa Turnip / software lavapipe).
- **Keluarga OpenGL** — Blender pakai backend GL-nya, tapi GL-nya **dipalsukan** di atas Vulkan memakai **Zink** (Mesa), atau di atas Adreno langsung pakai **Freedreno** (Mesa).

Tambahan: **GLES native** — nulis backend baru di modul `gpu` Blender. Ini satu-satunya yang bisa menolong device tanpa Vulkan sama sekali, dan ini proyek riset berbulan-bulan → `docs/GLES-BACKEND.md`.

---

## 1. Matriks lengkap (jujur, dengan alasan)

| # | Renderer | Backend Blender | Lapisan bawah | Device yang terjangkau | Status | Biaya | Verdict |
|---|---|---|---|---|---|---|---|
| 1 | **Vulkan (driver vendor)** | Vulkan | driver Adreno/Mali/Xclipse | Android 10+, arm64/x86_64, punya Vulkan 1.1 | ✅ jalan (upstream) | – | **Default** |
| 2 | **Vulkan (Turnip)** | Vulkan | Mesa Turnip → KGSL | Adreno 6xx/7xx (+8xx) | ✅ terbukti di port komunitas | Sedang: build Mesa + packaging ICD | **Kejar** (R1) |
| 3 | **OpenGL via Zink** (kopper EGL) | OpenGL | Zink → Vulkan (vendor atau Turnip) | sama seperti #1/#2 | 🟡 terbukti di Android (Termux & Winlator) | Sedang–berat: build Mesa + GHOST EGL path | **Kejar** (R2) — ini pembeda utama |
| 4 | **OpenGL via Freedreno** | OpenGL | Freedreno → KGSL (native, tanpa terjemahan) | Adreno 6xx/7xx | ❓ belum diverifikasi | Sedang: build Mesa + verifikasi caps | **Spike** (R3) |
| 5 | **Vulkan via lavapipe** (software) | Vulkan | Mesa lavapipe (LLVM) | apa saja, tanpa GPU | 🟡 mungkin | Berat: LLVM di APK (+ratusan MB), sangat lambat | **Hanya CI + last resort** (R4) |
| 6 | **GLES native** | backend `gpu` baru | GLES 3.1/3.2 | **device tanpa Vulkan** (satu-satunya jalan) | 🔴 belum ada | **Proyek riset, berbulan-bulan** | **Moonshot** (R5) |
| 7 | VirGL | OpenGL | virglrenderer-android → GLES 3.x | GLES 3.x | ❌ **buntu untuk Blender** | – | **Tolak** (lihat §2) |
| 8 | ANGLE / GL4ES | – | GLES↔Vulkan / GL 2.x | – | ❌ tidak relevan | – | **Tolak** (lihat §2) |
| 9 | Blender 2.79 + GL4ES | OpenGL 2.1 | GL4ES → GLES 2.0 | device GLES 2.0 jadul | 💡 ide liar | Berat, hasil terbatas | **Ide nakal** (lihat §7) |

---

## 2. Yang ditolak, dan kenapa (supaya nggak diulang orang lain)

**VirGL** kelihatan menjanjikan: "OpenGL di atas GLES, jalan di GPU apa saja". Tapi lihat tabel fitur di source `virglrenderer` (`vrend_renderer.c`):

```
FEAT(clip_control,   45, UNAVAIL, "GL_ARB_clip_control", "GL_EXT_clip_control"),
FEAT(draw_parameters, 46, 0,      "ARB_shader_draw_parameters"),
```

Angka **45/46** = butuh **host GL 4.5/4.6**. Di Android "host"-nya adalah GLES 3.x (via `virglrenderer-android`), yang tidak punya keduanya → **Blender akan langsung ditolak saat cek extension**. VirGL bagus untuk game OpenGL lama (GL 1.x–3.x), bukan untuk Blender 5.x. Ini bukan opini, ini isi tabel fitur-nya.

**ANGLE** = GLES di atas Vulkan/D3D. Arahnya salah: kita butuh *desktop GL*, bukan GLES.
**GL4ES** = desktop GL 2.x di atas GLES 2.0. Level API-nya jauh di bawah kebutuhan Blender 5.x (4.3 + 2 extension).

Keduanya baru relevan kalau kita mengerjakan §7 (Blender generasi lama).

---

## 3. Arsitektur: runtime renderer selector + fallback otomatis

Ini bagian yang bikin port ini beda: **satu APK, beberapa renderer, dipilih otomatis saat start.**

### Urutan percobaan default

```
1. Vulkan  — driver vendor        (paling cepat, tanpa tambahan ukuran)
2. Vulkan  — Mesa Turnip          (Adreno: sering lebih stabil/cepat dari driver vendor)
3. OpenGL  — Zink di atas Turnip  (kalau backend Vulkan Blender bermasalah di device itu)
4. OpenGL  — Zink di atas Vulkan vendor
5. (opsional) Vulkan — lavapipe   (software; khusus device tanpa GPU wajar / CI)
6. gagal → layar diagnostik
```

### Sumber konfigurasi (prioritas dari atas)

1. Argumen CLI: `--gpu-backend vulkan|opengl` (sudah ada di Blender; berguna buat power user).
2. Env var: `BLENDER_ANDROID_RENDERER=vulkan-vendor|vulkan-turnip|gl-zink-turnip|gl-zink-vendor|vulkan-lavapipe`.
3. File preferensi app: `<storage privat app>/config/renderer.conf` (di-set dari UI Android atau dari dalam Blender).
4. Hasil auto-detect terakhir yang berhasil (disimpan di `renderer.last_ok`).

### Logika startup (yang harus diimplementasikan)

```
baca config → kalau user memaksa renderer tertentu, coba HANYA itu
             → kalau tidak, coba berurutan sesuai daftar fallback:
   untuk tiap kandidat:
     set env (VK_ICD_FILENAMES / LD_LIBRARY_PATH / BLENDER_GPU_BACKEND)
     jalankan Blender dengan timeout ~20 detik
     kalau proses hidup & viewport tampil   → simpan sebagai last_ok, selesai
     kalau proses mati / exit != 0          → catat, lanjut kandidat berikut
   kalau 2x gagal di kandidat yang sama    → blacklist sementara (anti crash-loop)
```

Deteksi "viewport tampil" yang paling praktis: tulis penanda (`renderer.probe.ok`) setelah frame pertama dirender dari dalam Blender (satu hook kecil di `wm` / `gpu`), lalu Activity cek file itu.

### Layar diagnostik (wajib ada — ini yang bikin laporan bug berguna)

Tampilkan: ABI, versi Android, GPU + driver, backend yang dicoba, hasil tiap percobaan, dan hasil cek extension:

- Vulkan: `VK_KHR_android_surface`, `VK_KHR_swapchain`, `VK_KHR_shader_draw_parameters`, versi apiVersion.
- OpenGL: `GL_VERSION`, `GL_RENDERER`, `GL_ARB_shader_draw_parameters`, `GL_ARB_clip_control`.

Blender sendiri sudah punya ini lewat `--debug-gpu` dan Help → Save System Info; yang belum ada adalah **permukaan UI yang menampilkannya tanpa keyboard**.

### Titik sentuh di source

| Kebutuhan | File |
|---|---|
| Argumen launch + preferensi | `release/android/app/src/main/java/org/blender/blender/` (Activity) |
| Pemilihan context GPU | `intern/ghost/intern/GHOST_ContextVK.*`, `GHOST_ContextEGL.*`, `GHOST_ContextSDL.*` |
| Parsing `--gpu-backend` | `source/blender/creator/` |
| Hook "frame pertama tampil" | `source/blender/wm/` atau `source/blender/gpu/` |

---

## 4. R1 — Turnip (Vulkan open-source untuk Adreno)

**Kenapa:** banyak device Adreno punya driver vendor yang rusak/tua (yang sering jadi alasan "Blender crash di HP lain"). Turnip = driver Vulkan open source Mesa untuk Adreno, jalan lewat KGSL. Port komunitas sudah mengirim build "Turnip" — jadi ini bukan spekulasi.

**Kerja:**
1. Skrip build Mesa (target Android arm64): `-Dvulkan-drivers=freedreno -Dgallium-drivers=` (Turnip saja) + `-Dplatforms=android`.
2. Packaging: `libvulkan_freedreno.so` + JSON ICD → `jniLibs/` atau `assets/`, lalu set `VK_ICD_FILENAMES` saat launch.
3. Integrasi ke selector (§3) sebagai kandidat #2.
4. Varian APK terpisah (`blender-arm64-turnip.apk`) supaya ukuran build biasa tetap kecil.

**Kriteria selesai:** di device Adreno yang gagal dengan driver vendor, Blender jalan dengan Turnip; System Info menampilkan renderer Turnip.

**Risiko:** build Mesa untuk Android bukan pekerjaan sepele (butuh NDK + meson, dan koordinasi versi dengan NDK yang dipakai Blender). Wheel-nya sudah ada, tapi tetap berhari-hari.

---

## 5. R2 — OpenGL via Zink (pembeda utama proyek ini)

**Konsep:** Blender's **OpenGL backend** sudah dikompilasi masuk di binary (itu backend baseline Blender). Yang tidak ada di Android adalah *implementasi desktop GL*. Zink menyediakan itu: GL 4.6 di atas Vulkan, plus **kopper** (EGL di atas Vulkan) supaya bisa dipakai app native tanpa X11.

**Bukti kelayakan (bukan teori):**
- Di lingkungan Termux, Blender 4.3.2 melaporkan `OpenGL 4.6 core profile` dengan renderer `zink Vulkan 1.4 (Adreno ... MESA_TURNIP)` — artinya backend GL Blender memang bisa jalan penuh di Android lewat Zink.
- Winlator mengirim Mesa (Turnip/Zink/VirGL) di dalam APK Android native dan memakainya untuk memberi aplikasi Windows desktop GL sampai 4.6. Jadi pola "bundel Zink dalam APK Android" sudah terbukti di produksi.

**Kerja:**
1. Build Mesa untuk Android dengan `gallium-drivers=zink`, `platforms=android`, kopper aktif; hasil: `libEGL`, `libGLESv2`/`libGL` Mesa + `zink_dri`.
2. Jalur GHOST: **EGL + desktop GL** (`EGL_OPENGL_API`), bukan `EGL_OPENGL_ES_API`. Ada `GHOST_ContextEGL` di tree — kerjaannya adalah memastikan ia bisa diarahkan ke Mesa/libEGL bundel, bukan ke `libEGL.so` sistem (yang cuma GLES).
3. Loader: `LD_LIBRARY_PATH` + var Mesa (`MESA_LOADER_DRIVER_OVERRIDE=zink`, `LIBGL_DRIVERS_PATH`), di-set oleh Activity sebelum `dlopen` Blender.
4. Selector (§3): kandidat #3 dan #4.
5. Verifikasi wajib: Blender harus melihat `GL_ARB_shader_draw_parameters` + `GL_ARB_clip_control`. Zink mendukung keduanya (level GL-nya 4.6), tapi **tetap harus dites di device**, termasuk saat memakai driver Vulkan vendor yang berbeda-beda.

**Kriteria selesai:** `--gpu-backend opengl` hidup di Android; Preferences → System menampilkan renderer `zink ...`.

**Risiko:** ini zona paling "banyak variabel" — tiga lapisan (Blender → Zink → Vulkan → driver). Bug bisa muncul di lapisan mana saja. Mitigasi: selector §3, plus mode Aman (paksa backend Vulkan) yang selalu tersedia.

---

## 6. R3 — Freedreno (GL native untuk Adreno, tanpa terjemahan)

Freedreno adalah driver **OpenGL** Mesa untuk Adreno (KGSL), native — bukan terjemahan. Kalau ini jalan, backend GL Blender dapat jalur tercepat dan paling "bersih" di Qualcomm.

**Tapi ada satu syarat mati:** Freedreno harus mengekspos `GL_ARB_shader_draw_parameters` dan `GL_ARB_clip_control`. Belum gw verifikasi untuk semua generasi Adreno.

**Spike (cukup 1 hari):** di device Adreno, dengan Mesa Freedreno dimuat, jalankan pemeriksa extension (`glmark2`, atau Build System Info Blender sendiri) dan lihat apakah dua extension itu ada. Kalau ya → naikkan ke R2.5 (jalur GL lebih cepat). Kalau tidak → ada opsi `MESA_EXTENSION_OVERRIDE="+GL_ARB_shader_draw_parameters +GL_ARB_clip_control"` untuk memaksa; ini **hack** yang bisa berujung render salah, jadi kalau dipakai harus jelas berlabel eksperimen dan hanya untuk modeler ringan.

Ada preseden komunitas: Winlator versi komunitas (varian "Ludashi") menambahkan dukungan Freedreno — jadi setidaknya ada orang yang sudah bisa memuatnya di Android.

---

## 7. R4 — lavapipe (software) dan ide nakal Blender 2.79

**lavapipe (Vulkan software)**: satu-satunya cara memberi "Vulkan" ke device tanpa GPU yang layak. Realistisnya lambat (semua rasterisasi di CPU). Berguna untuk:
- **CI**: uji smoke rendering headless tanpa device fisik — ini nilai nyatanya.
- **Last resort** di device aneh yang tidak punya Vulkan tapi RAM besar.
Konsekuensi: LLVM ikut masuk APK → ukuran naik drastis → wajib APK varian terpisah.

**Ide nakal (Blender 2.79 + GL4ES)**: kalau tujuannya "device GLES 2.0 jadul pun bisa Blender", cara termurah adalah **jangan bawa Blender 5.x ke sana**. Blender 2.79 (2018) hanya butuh GL 2.1 — dan GL4ES menyediakan GL 2.x di atas GLES 2.0. Jadi port 2.79 + GL4ES bisa menghidupkan device lama **tanpa menulis backend GLES baru**. Tapi: 2.79 tidak punya EEVEE (hanya Workbench-era lebih tua lagi, render pakai Cycles CPU lama / Blender Internal sudah lama mati), addon modern banyak mati, dan UI-nya beda. Sebagai "tier terpisah khusus device jadul", ini masuk akal; sebagai pengganti Blender 5.x, tidak.

---

## 8. Ukuran dan kerumitan yang harus lo terima

| Varian APK | Tambahan ukuran (perkiraan) | Untuk siapa |
|---|---|---|
| arm64 Full (Vulkan vendor) | baseline ~270 MB | mayoritas device |
| arm64 + Turnip | +10–25 MB | Adreno dengan driver vendor bermasalah |
| arm64 + Zink/Mesa | +20–40 MB | user yang butuh backend GL |
| arm64 + lavapipe | +150–300 MB | CI & last resort |
| armv7 Lite | ~150–200 MB | device 32-bit (eksperimental) |

Konsekuensi desain: **jangan satu APK untuk semua**. Pakai varian + `versionCode` ber-digit ABI (skema upstream) dan, kalau perlu, sufiks digit renderer.

---

## 9. Urutan kerja (masuk ke ROADMAP sebagai M2.5)

| Fase | Isi | Kriteria selesai |
|---|---|---|
| **R1** | Runtime selector + layar diagnostik (tanpa renderer baru) | Bisa memaksa backend via env/CLI; layar diagnostik menampilkan driver & extension |
| **R2** | Bundel Turnip + kandidat #2 | Device Adreno dengan driver vendor rusak jalan via Turnip |
| **R3** | Bundel Zink (kopper) + jalur GHOST EGL/GL | `--gpu-backend opengl` hidup; System Info menunjukkan `zink` |
| **R4** | Spike Freedreno | Terjawab: `ARB_shader_draw_parameters` + `ARB_clip_control` ada/tidak |
| **R5** | lavapipe untuk CI (headless smoke test) | Uji render jalan di CI tanpa device |
| **R6** | Backend GLES native | Lihat `docs/GLES-BACKEND.md` — proyek terpisah |

**Aturan:** R1 dulu (murah, langsung berguna, dan bikin debugging renderer berikutnya jauh lebih gampang). R2/R3 baru setelah M2 (optimasi) selesai, supaya baseline-nya sudah stabil.

---

## 10. Yang harus lo verifikasi sendiri di checkout (sebelum mengklaim apa pun)

```bash
# 1. Backend GL benar-benar ikut dikompilasi untuk Android?
ls source/blender/gpu/opengl/ | head
grep -rn "WITH_VULKAN_BACKEND\|GPU_BACKEND_OPENGL" CMakeLists.txt build_files/cmake/options.cmake | head -n 20

# 2. Apakah Android build mengaktifkan keduanya?
grep -rn "ANDROID" build_files/cmake/options.cmake | head -n 20

# 3. Titik pemilihan backend saat runtime
grep -rn "gpu-backend\|GPU_BACKEND_" source/blender/creator/*.cc | head -n 20
grep -rn "gpu_backend_type\|GPU_BACKEND_VULKAN" source/blender/gpu/*.cc | head -n 20

# 4. Cek jalur EGL di GHOST (apakah bisa diarahkan ke Mesa bundel)
grep -rn "EGL_OPENGL_API\|eglGetPlatformDisplay\|EGL_OPENGL_ES_API" intern/ghost/intern/GHOST_ContextEGL.cc | head -n 20
```

Kalau poin 1 & 2 ternyata menunjukkan backend GL **tidak** dikompilasi untuk Android, tambahkan kerja kecil: aktifkan `WITH_OPENGL_BACKEND`-nya (atau setara) di konfigurasi Android — itu satu patch kecil, jauh lebih murah dari apa pun di dokumen ini.

---

## 11. Kesimpulan jujur

- **"Semua renderer" bisa dicapai** dalam arti: Blender punya dua backend (Vulkan + OpenGL) dan kita sediakan **4–5 implementasi driver** di bawahnya, dipilih otomatis. Ini memang beda dari port lain yang cuma kirim satu jalur.
- **Tapi** semua itu tetap berlandas Vulkan. Device **tanpa Vulkan** hanya bisa ditolong oleh backend **GLES native** (R6) — proyek riset, bukan tugas akhir pekan.
- **Prioritas nilai:** R1 (selector + diagnostik) → R2 (Turnip) → R3 (Zink/GL) → R4/R5 → R6.
