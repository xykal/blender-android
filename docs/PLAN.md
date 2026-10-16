# Blender for Android — Rencana Port Sendiri (arm64 + x86_64 + armeabi-v7a)

**Status dokumen:** riset awal, 16 Oktober 2026
**Tujuan:** fork sendiri, bebas kustomisasi, optimasi, dan target "semua Android 32 + 64 bit".
**Lisensi Blender:** GPLv3 → boleh banget di-port, dimodifikasi, dan dibagikan. Syaratnya: kalau lo distribusiin binary-nya, source lengkap (termasuk patch lo) wajib dipublikasikan. Ada port 2024 yang progress-nya dihapus karena nggak publish source — jangan ulangi.

---

## 0. TL;DR — verdict per target

| Target | Verdict | Catatan |
|---|---|---|
| **arm64-v8a** (64-bit ARM) | ✅ **Jalan, sekarang** | Ini yang dipakai port resmi & komunitas. Upstream Blender sudah punya build system-nya. |
| **x86_64** (Chromebook/Googlebook/emulator) | ✅ **Jalan, sekarang** | Upstream baru nambah support ini (PR #164424, merged 5 Okt 2026). Bagus buat testing di emulator. |
| **armeabi-v7a** (32-bit ARM) | ⚠️ **Proyek riset, bisa tapi dipotong banyak** | Bukan "tinggal tambah abiFilters". Lihat §2. |
| **x86** (32-bit Intel) | ❌ | ABI-nya sudah dibuang dari NDK r17. Lupakan. |
| **armeabi** (ARMv5/v6) | ❌ | Sama, sudah dibuang dari NDK. |

**Kesimpulan jujur:** target "semua Android 32 + 64" itu bisa diraih, tapi jangan dibayangkan satu APK jalan di semua device. Realistisnya: **3 APK terpisah** (arm64, x86_64, armv7-legacy), di mana yang armv7 adalah build "Lite" dengan fitur dipotong dan device-nya (device 32-bit itu semua keluaran era 2015–2020 dengan ROM 32-bit).

---

## 1. Kabar penting: upstream Blender sudah punya branch Android

Ini titik start terbaik, jadi lo nggak mulai dari nol:

- PR **#164188 "WIP: Android: Initial Platform Support"** — nambah **cross-compilation** ke build system Blender + **Android CMake toolchain wrapper**, plus perubahan besar di **dependency builder** (`make deps android`), Android app skeleton, dan Gradle packaging.
- PR **#164424** (merged 5 Oktober 2026) — nyelesaiin cross-compile dari Linux & Windows, dan **nambah ABI `x86_64`** di samping default `arm64-v8a`.
- Hasilnya, sekarang target convenience-nya:
  ```bash
  make android          # = arm64-v8a (default)
  make android x64      # = x86_64
  ```
- Precompiled library disediakan sebagai submodule git: `blender/lib-android_arm64` dan `blender/lib-android_x64` → jadi lo nggak perlu compile OpenImageIO, USD, Python, dll dari nol buat 64-bit.
- Versi resmi Blender bilang targetnya **rilis semester 1 2027**, fokus tablet + stylus, dan APK demo udah beredar. Artinya: kalau lo fork dari branch `android`, perubahan upstream berikutnya gampang di-merge (ini alasan kuat buat nggak bikin port dari branch sendiri yang jauh).

**Penting:** toolchain file upstream **menolak ABI selain arm64-v8a dan x86_64** dengan `FATAL_ERROR "Unsupported Android ABI"`. Jadi 32-bit = lo harus patch toolchain + gradle + build system sendiri, bukan sekadar ganti satu variabel.

---

## 2. 32-bit: apa yang sebenarnya diminta dan seberapa berat

Ini bagian yang harus lo tahu sebelum janjiin ke diri sendiri (atau ke orang lain).

### 2.1 Blender sendiri sudah buang 32-bit sejak 2.81

- Buildbot 32-bit dimatiin dan library 32-bit dihapus dari repo deps-nya (issue T67184, 2019). 2.80 adalah rilis terakhir dengan build 32-bit resmi.
- Setelah itu, kode Blender **tidak secara aktif** dijaga buat 32-bit. Maintainer-nya bilang: build 32-bit bukan prioritas, tapi patch kecil yang bikin hidup downstream gampang masih diterima.
- Konsekuensi praktis: Blender 5.x di armv7 = lo nge-build kode yang **tidak ada yang test**. Bug-nya bakal berupa crash random (pointer truncation, `size_t`/`long` 32-bit, alignment) yang susah dibedah, dan lo yang bakal jadi satu-satunya orang yang maintain.

### 2.2 Batas 4 GB address space

Proses 32-bit cuma punya ruang alamat 4 GB (realistis di Android: ~2–3 GB sebelum kena OOM-killer), dipakai buat meshes, texture, cache, Python heap, dan VRAM staging. Untuk Blender:

- Scene menengah ke atas → OOM. Sculpting multi-juta poly → OOM.
- Cycles render resolusi tinggi → OOM.
- Python addon + numpy → makan alamat cepat.

Jadi build 32-bit itu, secara desain, **hanya layak untuk scene kecil / modeling ringan**. Ini bukan bug yang bisa lo optimasi; ini dinding arsitektur.

### 2.3 Dependency yang kemungkinan besar gagal di armv7

Ini yang paling nyata "biaya"-nya. Waktu lo jalankan `make deps` buat armv7, kandidat bermasalah:

| Library | Status di 32-bit ARM | Efek kalau absen |
|---|---|---|
| Embree (BVH ray tracing) | Dirancang buat SIMD 128-bit; rilis Neon-nya ngarah ke aarch64 | Cycles kehilangan percepatan ray tracing → render jauh lebih lambat |
| OpenImageDenoise (OIDN) | Dukungan ARM modernnya ARM64 | Nggak ada denoise GPU/NEON → pakai denoiser lambat atau tanpa denoise |
| ISPC kernels | ISPC nggak nargetin armv7-Android | Cycles fallback ke kernel C++ (lebih lambat, tapi jalan) |
| USD / OpenSubdiv / OpenVDB / OpenEXR / FFmpeg / Python 3.13 | Umumnya masih bisa armv7 | Aman, tapi harus diuji satu-satu |
| Compute backend (HIP/DPC++) | Sudah di-exclude upstream di Android | Cycles tetap **CPU-only** di Android, baik 32 maupun 64 bit |

Jadi angka realistis: build armv7 = **Blender Lite**, Cycles CPU tanpa Embree/OIDN/ISPC, tanpa video, tanpa format exchange (sama seperti profil "Lite" yang dipakai build komunitas, plus lebih sedikit lagi).

### 2.4 Dinding GPU: Android nggak punya desktop OpenGL

Blender butuh **OpenGL 4.3** dengan extension `ARB_shader_draw_parameters` dan `ARB_clip_control` — dan itu **wajib**, bukan opsional (device tanpa extension ini langsung nolak jalan). Android cuma nge-expose **OpenGL ES**. Jadi:

- **Jalur A (harus dipilih):** pakai backend **Vulkan** Blender. Ini yang dipakai semua port Android, dan Blender 5.3 bikin Vulkan makin toleran (minimal Vulkan 1.1, fitur-fitur yang nggak ada di GPU mobile dijadiin optional).
- **Jalur B (mimpi buruk):** nulis backend **OpenGL ES** di modul `gpu/` Blender + `glClipControl`-nya. Ini bukan pekerjaan porting, ini pekerjaan riset berbulan-bulan dengan hasil nggak pasti. **Jangan.**

Masalahnya: **Vulkan 1.1 itu cuma diwajibkan Google untuk device 64-bit** (Android 10 ke atas). Device 32-bit boleh banget nggak punya Vulkan sama sekali. Artinya:

- Sebagian device armv7 punya driver Vulkan 32-bit (Adreno 5xx/6xx di ROM 32-bit, sebagian Mali) → bisa jalan.
- Sebagian besar device armv7 murah/entry (Mali-400, Adreno 3xx/4xx, PowerVR lama) → **nggak akan pernah** jalan, mau lo seoptim apa pun, karena nggak ada Vulkan-nya.

**Cara cek device:** `adb shell ls /system/lib/libvulkan.so` — kalau ada, device itu punya driver Vulkan 32-bit. (Lib 32-bit ada di `/system/lib`, 64-bit di `/system/lib64`.) Alternatif tanpa ADB: aplikasi AIDA64 / DevCheck / Vulkan Hardware Capability Viewer.

### 2.5 Android version floor

Port yang ada sekarang butuh **Android 12 / API 31**. Kalau lo mau nyentuh device 32-bit (banyak yang Android 7–11), minSdk-nya harus turun, dan itu **kerjaan tambahan** sendiri:

- AAudio (audio, API 26+) → butuh fallback OpenSL ES buat yang di bawahnya.
- Perubahan lifecycle / surface handling / permission model di API < 30.
- Makin turun minSdk = makin banyak jalur kode alternatif = makin banyak kombinasi yang harus dites.

---

## 3. Strategi ABI & packaging

**Jangan bikin satu APK gemuk berisi semua ABI.** Build arm64 full aja ~194–276 MB; digabung bertiga tembus 500 MB+ dan Android bakal lambat install-nya.

Strategi yang direkomendasikan (dan sejalan sama yang dipakai upstream):

| APK | ABI | Nama | Isi |
|---|---|---|---|
| `blender-arm64-v8a.apk` | arm64-v8a | **Full 64-bit** | Semua fitur. Target utama 90% user. |
| `blender-x86_64.apk` | x86_64 | **Full 64-bit x86** | Chromebook / Googlebook / emulator (buat dev & testing lo sendiri). |
| `blender-armeabi-v7a.apk` | armeabi-v7a | **Legacy 32-bit Lite** | Fitur dipotong (lihat §6). Target device lama. |
| (opsional) `blender-arm64-lite.apk` | arm64-v8a | **Lite 64-bit** | Buat device RAM 4–6 GB / Mali kelas bawah. |

Detail packaging:

- `versionCode` pakai skema upstream: digit tertinggi nunjukin ABI (**arm64-v8a=1**, **x86_64=4**; buat armv7 lo pilih angka sendiri, misal 0). Tujuannya biar device milih APK paling cocok ketika upgrade. Contoh upstream: `5.4.1 arm64 → 105040100`.
- **Play Store rule:** kalau lo kirim ABI 32-bit, lo wajib nyertain yang 64-bit. Kalau distribusi lewat GitHub Releases (sideload), nggak ada aturan itu — tapi tetap pakai dua-tiga APK terpisah.
- **16 KB page size:** Android 15+ dan syarat Play buat app baru/update (sejak Nov 2025) minta native lib di-align ke 16 KB. Pasang `-Wl,-z,max-page-size=16384` di link flags. Ini bukan opsional buat jangka panjang.
- Device 64-bit-only (Pixel 7 ke atas, banyak flagship baru) **nggak bisa install APK armv7** — jadi jangan harap APK 32-bit bisa jadi fallback universal.

---

## 4. Pilih basis kode (dan kenapa)

| Opsi | Isi | Plus | Minus |
|---|---|---|---|
| **A. `blender/blender` branch `android`** (REKOMENDASI) | Port resmi, build system + toolchain + deps sudah ada | Nggak mulai dari nol, bakal ke-merge upstream, arm64 + x86_64 langsung | Belum ada 32-bit; UI sentuh masih mentah |
| **B. `simfeo/blender` (fork komunitas, alpha-4)** | Fork yang nge-track upstream, nambah audio AAudio, Cycles denoise, Turnip builds, perbaikan lighting | Referensi paling matang buat fitur mobile; lognya detail (baca [porting log-nya](https://blenderandroid.github.io/)) | Bukan basis upstream → mergenya bisa konflik |
| **C. `Wanderson-Magalhaes/blender_for_android`** | Fork yang fokus UI sentuh + keyboard, di-tuning buat satu device | Referensi **kode UI sentuh** (tool variant long-press, chrome khusus jari) | Dituning buat 1 device (S24 Ultra) |
| **D. epai (projects.blender.org)** | Port pionir 2025 | Jejak sejarah & diskusi masalah awal | Sudah ketinggalan jauh |

**Saran:** mulai dari **A**, lalu *cherry-pick* pelajaran dari **B** dan **C** (jangan hard-fork UI-nya sekaligus — nanti ribet merge).

---

## 5. Setup build (host Linux, jalur upstream)

Host yang didukung upstream: **Linux dan macOS** (dan Windows, setelah PR #164424). Rekomendasi: **Ubuntu 24.04**, disk **~80–100 GB** kosong buat deps + build (deps Blender itu gede — nggak cukup 20 GB).

```bash
# 1. Ambil toolchain dasar
sudo apt install -y build-essential cmake ninja-build git python3 python3-pip \
                    openjdk-17-jdk scons wget unzip
# Gradle & Android SDK: install via Android command line tools, atau andalkan staging Gradle upstream

# 2. Android NDK (cek versi yang diharapkan branch android — jangan asal pakai terbaru)
export ANDROID_NDK_ROOT=$HOME/android-ndk-r27d    # sesuaikan
export ANDROID_HOME=$HOME/android-sdk

# 3. Clone Blender di branch android, LENGKAP dengan submodule precompiled lib
git clone --depth 1 -b android https://projects.blender.org/blender/blender.git
cd blender
git submodule update --init --recursive   # ini yang narik lib-android_arm64

# 4. Build dependency Android (sekali, lama: hitungan jam)
make deps android          # arm64-v8a
make deps android x64      # x86_64 (opsional, buat emulator/Chromebook)

# 5. Build Blender + packaging APK
make android               # arm64-v8a
make android x64           # x86_64

# 6. Hasil ada di release/android/ (staging Gradle → jniLibs + assets)
```

Catatan penting dari PR upstream:

- Host tools (`datatoc`, `makesdna`, `makesrna`, `shader_tool`) harus dibangun **native** dulu (x86_64 host), karena dia dipakai saat build target Android. Upstream sudah ngurus ini via `HOST_LIBDIR` / `BLENDER_HOST_TOOLS_DIR`.
- Konsep Gradle staging: **native lib masuk `jniLibs/<abi>/`** (di-extract installer saat install), **runtime files masuk `assets/<target>/`** (di-unpack ke storage privat app saat launch pertama — sekitar 100 MB, makanya splash screen-nya lama).
- Ada repo alternatif yang bikin ini jalan di **GitHub Actions x86_64 runner** (lihat `nuarted/BlenderForAndroid`) — bagus buat referensi CI lo.

---

## 6. Rencana 32-bit (armeabi-v7a) — kerjaan konkretnya

Urut sesuai tingkat kesulitan, kerjain **setelah** 64-bit stabil:

1. **Patch toolchain & build system**
   - `build_files/cmake/platform/platform_android_toolchain.cmake`: tambah cabang `armeabi-v7a` (triple `armv7a-linux-androideabi`, API level target misal 28).
   - `platform_android.cmake`: tambah `LIBDIR_ANDROID = lib/android_armv7`, arch triple, dan jangan lupa **`ANDROID_ABI` per-target** (upstream baru bikin ini parametrik → tinggal diperluas).
   - `GNUMakefile`: tambah target `make android armv7` + opsi `ANDROID_ARM_NEON=TRUE`.
   - `release/android/app/build.gradle`: `abiFilters` per-flavor + skema digit ABI di `versionCode`.

2. **Build deps armv7 sendiri** (ini yang makan waktu)
   - Submodule `lib-android_arm64` / `lib-android_x64` **nggak ada** versi armv7 → lo harus `make deps android armv7` dan benerin resep yang gagal satu per satu (banyak resep autoconf yang punya cabang `ANDROID` yang nge-hardcode nilai AArch64 — sudah kejadian buat x86_64 juga, lihat commit "Fix per-ABI flags in autoconf based recipes").
   - Terima kenyataan: **matikan** Embree, OIDN, ISPC, USD (kalau bandel), video/FFmpeg. Itu fitur yang paling nggak realistis di 32-bit.

3. **CMake flag untuk profil Legacy**
   ```bash
   -DANDROID_ABI=armeabi-v7a -DANDROID_ARM_NEON=TRUE -DANDROID_ARM_MODE=arm \
   -DWITH_CYCLES_EMBREE=OFF -DWITH_OPENIMAGEDENOISE=OFF -DWITH_CYCLES_DEVICE_* =OFF \
   -DWITH_FFMPEG=OFF -DWITH_USD=OFF -DWITH_ALEMBIC=OFF \
   -DWITH_LTO=OFF            # LTO di 32-bit sering bikin masalah memori saat link
   ```
   (nama variabel di atas perlu diverifikasi lawan `CMakeLists.txt` versi branch yang lo pakai)

4. **Uji device minimum yang realistis:** Adreno 5xx/6xx, Mali-G51/G52/G7x dengan ROM 32-bit. Device Mali-400/Adreno 4xx ke bawah: **bilang terang-terangan nggak didukung**, jangan buang waktu.

5. **Kalau hasilnya jelek banget** (dan kemungkinan besar begitu): pivot yang lebih cerdas → naikin minSdk build 64-bit ke **Android 9 (API 28)** dan sediain **APK arm64 Lite**. Itu menjangkau jauh lebih banyak device nyata daripada armv7, dengan 1/10 kerjaannya. Ingat: mayoritas device 32-bit-only itu udah berumur >6 tahun.

---

## 7. Optimasi — daftar kerja nyata

### 7.1 Build-time (langsung terasa)

- **LTO + O3** buat user yang kuat: `-DWITH_LTO=ON` (uji dulu; LTO di build besar bisa naik 2–3× waktu link).
- **Tuning CPU per-tier:**
  - Profile **Generic** (kompatibel semua): `-march=armv8-a -O2` (default NDK).
  - Profile **Performance**: `-march=armv8.2-a+dotprod+fp16 -O3` — jangan asal: SoC lama (SD835/845 sebagian) bisa nggak punya dotprod. Karena Blender nggak banyak runtime CPU dispatch, lo harus rilis 2 varian atau tetap generic.
- **Ukuran & startup:** `-Oz` buat profil Lite, `-ffunction-sections -fdata-sections -Wl,--gc-sections`, `-Wl,--icf=all`, strip semua `.so` (`llvm-strip --strip-unneeded`), dan pastikan `-Wl,-z,max-page-size=16384`.
- **STL**: pilih `c++_shared` (satu salinan) atau static — jangan campur, kayak upstream.
- **Python**: jangan bawa seluruh stdlib. Pangkas modul yang nggak dipakai Blender (`test/`, `idlelib`, `tkinter`, `lib2to3`), precompile `.pyc`, hapus addon yang nggak perlu → APK mengecil **dan** startup lebih cepat.
- **CPU affinity / big.LITTLE**: jangan biarin thread numpuk di core kecil. Set thread count ke jumlah core besar (di `bpy`/Preferences → System → Threads, atau lewat default prefs di build lo). Ini bikin render Cycles lebih konsisten.
- **Allocator**: mimalloc/jemalloc (fork komunitas sudah mainan mimalloc) — menolong fragmentasi & scene besar.

### 7.2 GPU / render (ini yang paling kerasa di mobile)

- **Pipeline cache persistent** (`VkPipelineCache` yang di-save ke disk) — masalah nomor satu di mobile adalah stutter kompilasi shader saat pertama buka viewport/EEVEE.
- **Default yang ramah mobile**: EEVEE TAA samples turunin (16 → 8), motion blur & raytracing default mati, viewport resolution scale 0.75–0.85× dengan upscale, shadow/overlay lebih hemat.
- **Cycles = CPU-only di Android** (nggak ada CUDA/HIP/Metal/oneAPI). Jadi optimasinya: NEON, thread tuning, tile/progressive refine, denoise OIDN (kalau device 64-bit), plus preset "Fast GI" buat preview.
- **Jangan pakai Texture compression agresif** di .blend — itu urusan konten user, bukan build.

### 7.3 Startup & disk

- APK arm64 upstream ~194–276 MB dan unpack ~100 MB di launch pertama. Kurangi dengan: buang fitur yang nggak kepakai di device itu, kompresi asset yang tepat, dan kalau memungkinkan aktifkan `android:extractNativeLibs="false"` + lib ter-align halaman supaya install & launch lebih cepat.
- Cek juga: 1 APK 3 ABI = 500 MB+ → install lambat & makan storage. Ini alasan lain buat split per-ABI.

### 7.4 Termal & daya (sering dilupakan, tapi bikin pengalaman "kerasa lambat")

- SoC flagship bakal throttle 30–60 detik pertama. Ukur **sustained** FPS, bukan burst.
- Alat ukur: `perfetto` trace, `adb shell dumpsys thermalservice`, `gpuinfo`-style apps, plus benchmark scene tetap (buka file .blend yang sama, ukur time-to-first-frame + navigasi viewport FPS).
- Naikin `minSdk` dan tetapkan **budget panas**: misal default Cycles threads = 4 di phone, 6–8 di tablet.

### 7.5 Touch UI (ini yang bikin orang mau pakai, bukan cuma "jalan")

- Target besar buat jari, toolbar/header/properties dilebarin.
- Long-press tool = varian tool (Box/Circle/Lasso select).
- Stylus: tekanan + tilt (S-Pen jalan di port yang ada), gesture: 1 jari orbit, 2 jari pan, pinch zoom, undo gestur.
- Mode tablet + mouse/keyboard (DeX/desktop mode) **wajib** dites — keyboard shortcut adalah alasan utama orang nggak betah.
- Simpan layout khusus tablet dan khusus phone, plus panel shortcut keyboard virtual.

---

## 8. Milestone yang gw saranin

| M | Target | Definisi selesai |
|---|---|---|
| **M0** | Build arm64 sendiri jalan di mesin/GitHub Actions lo | APK arm64 hasil build sendiri, install, buka file .blend sederhana |
| **M1** | + x86_64 | Bisa dites di emulator, CI hijau buat dua ABI |
| **M2** | Optimasi & Lite profile | APK Lite (buang video/exchange), 16 KB align, startup < 10 s, angka benchmark terdokumentasi |
| **M3** | UI sentuh dari fork komunitas masuk | Tool variant, chrome besar, stylus pressure |
| **M4** | Spike 32-bit: toolchain + deps armv7 | `make deps android armv7` tembus (fitur dipotong), Blender nyala di minimal 1 device armv7 |
| **M5** | Rilis komunitas | GitHub Releases per-ABI, source GPL di-publish, catatan kompatibilitas device |

**Spike di M4 itu "gate" penting:** kalau setelah toolchain + deps jalan, Blender masih crash-nya nggak ketulungan di device asli, itu sinyal kuat buat berhenti di armv7 dan alihin energi ke "arm64 + Android 9+" (yang menjangkau lebih banyak orang nyata).

---

## 9. Risiko & jebakan

1. **GPL compliance** — publish patch + build script. Kalau nggak, komunitas (dan Blender Foundation) bakal ngamuk, dan lo bisa kena takedown.
2. **Jangan pakai nama/branding resmi seolah official** — cantumin jelas "unofficial port, not affiliated". Upstream udah bilang port komunitas nggak di-endorse.
3. **Driver GPU vendor-specific** — bug di driver Adreno/Mali/Xclipse itu nyata (port komunitas pernah nolak semua device Mali cuma karena 3 fitur yang bahkan nggak dipakai). Siapin mode "safe/compat" via env var/dev settings.
4. **Merge conflict dengan upstream** — makin lo ngubah file build system & GHOST, makin sering konflik. Disiplin: patch sekecil mungkin, sedetail mungkin, taruh di branch terpisah.
5. **Waktu & disk** — build penuh Blender + deps di CI: hitungan jam dan puluhan GB. Siapin cache & runner yang disknya lega.
6. **"Support all Android" itu klaim pemasaran, bukan fakta teknis** — selalu cantumin tier kompatibilitas (A: arm64 Android 12+ Vulkan 1.1; B: arm64 Android 9–11; C: armv7 Legacy Lite).

---

## 10. Referensi utama

- Roadmap resmi (Android Platform Support): https://www.blender.org/roadmap/
- PR upstream #164188 (Initial Platform Support): https://projects.blender.org/blender/blender/pulls/164188
- PR upstream #164424 (cross-compile + x86_64 ABI): https://projects.blender.org/blender/blender/pulls/164424
- Precompiled libs: repo `lib-android_arm64`, `lib-android_x64` di projects.blender.org
- Port komunitas + log teknis (baca semua update-nya, ini gold): https://blenderandroid.github.io/
- Fork CI-friendly (NDK + GH Actions): https://github.com/nuarted/BlenderForAndroid
- Isu 32-bit Blender: https://developer.blender.org/T67184
- Requirement GPU Blender: https://www.blender.org/download/requirements/
- NDK ABI: https://developer.android.com/ndk/guides/abis
- Aturan 64-bit Play: https://developer.android.com/google/play/requirements/64-bit
