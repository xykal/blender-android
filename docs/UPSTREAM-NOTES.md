# UPSTREAM-NOTES — hasil riset source (biar nggak riset dua kali)

Catatan ini dari branch `android` di `projects.blender.org/blender/blender`, dicek **16 Oktober 2026**.
Kalau patch lo nggak nyantol, kemungkinan besar upstream sudah refactor — cek ulang file-nya.

---

## 1. `build_files/cmake/platform/platform_android_toolchain.cmake`

Toolchain wrapper di atas NDK. Isi penting:

- **NDK discovery:** kalau `ANDROID_NDK_ROOT` di-set, dipakai. Kalau nggak, dia nebak dari `$ANDROID_HOME/ndk/*` (ambil versi terbaru).
  → **Di CI: selalu set `ANDROID_NDK_ROOT` eksplisit.** Lebih deterministik.
- **Allowlist ABI (yang harus lo patch buat armv7):**
  ```cmake
  # Supported ABIs are arm64-v8a (default) and x86_64.
  # 32-bit ABIs (armeabi-v7a, x86) are not supported.
  if(NOT ANDROID_ABI)
    set(ANDROID_ABI arm64-v8a)
  endif()

  if(NOT (ANDROID_ABI STREQUAL "arm64-v8a" OR ANDROID_ABI STREQUAL "x86_64"))
    message(FATAL_ERROR
      "Unsupported Android ABI \"${ANDROID_ABI}\", expected one of: arm64-v8a, x86_64."
    )
  endif()
  ```
- **`set(ANDROID_PLATFORM android-29)`** → artinya **minSdk = 29 = Android 10**. Ini yang dipass ke Gradle sebagai `blenderMinSdk`.
  Komentar aslinya menyebut alasan historis:
  - pernah 23 (Android 6) → dinaikin ke **28** karena `aligned_alloc` (C11) yang dibutuhkan **OpenJPH** → "mungkin bisa diturunkan lagi dengan patch OpenJPH"
  - 28 (Android 9) → **29** karena `timespec_get` yang dipakai `uuid.cc` di BLI → "bisa diturunkan dengan `#ifdef` di `uuid.cc`"

  👉 **Ini peta jalan buat "support Android lama" tanpa nyentuh 32-bit:**
  - API 29 (Android 10) → gratis, default.
  - API 28 (Android 9) → butuh ifdef di `source/blender/blenlib/intern/uuid.cc`.
  - API ≤ 27 → tambahan patch OpenJPH (atau matikan OpenJPH).
- `set(ANDROID_STL c++_shared)` — STL dibagi sebagai shared lib.
- `set(ANDROID_USE_LEGACY_TOOLCHAIN ON)` — pakai toolchain CMake NDK "legacy" (yang justru didukung).
- Ada workaround Yasm khusus host macOS arm64.

## 2. `release/android/app/build.gradle`

Skeleton Gradle yang cuma ngemas + nge-sign. Isi penting:

- `namespace` / `applicationId` = **`org.blender.blender`**
- `compileSdkVersion = 36`, `targetSdkVersion = 36`
- `versionCode`, `versionName`, `minSdkVersion`, `abiFilters` semuanya **dilempar dari CMake** lewat properti: `blenderVersionCode`, `blenderVersionName`, `blenderMinSdk`, `blenderAbi`
- `packaging { jniLibs { useLegacyPackaging = true } }` → lib disimpan terkompresi & di-extract saat install (APK jadi ~2× lebih kecil)
- `buildTypes.release`: **ditandatangani pakai `signingConfigs.debug`** dan `debuggable = true` → jadi **nggak butuh keystore rahasia buat bikin APK yang bisa di-install**. (Untuk rilis serius, ganti ke keystore sendiri nanti.)
- Ada komentar: filter asset default terlalu agresif → `ignoreAssetsPattern = ''`

## 3. `build_files/cmake/platform/platform_android_gradle.cmake`

Jembatan CMake → Gradle. Isi penting:

- **Target:** `gradle_stage` (install Blender + staging project Gradle ke `${CMAKE_BINARY_DIR}/gradle`), `gradle_assemble` (panggil Gradle → APK), plus utilitas ADB: `android_upload`, `android_run`, `android_kill`, `android_clean`.
  → `android_upload` = `adb install -r <apk>`; `android_run` = `am start -n org.blender.blender/.BlenderActivity`.
- **Nama build type:** `Debug` → `assembleDebug`, selain itu → `assembleRelease`.
- **Output APK:** `<build_dir>/gradle/app/build/outputs/apk/<type>/app-<type>.apk`
- **Skema versionCode** (wajib lo mengerti sebelum nambah ABI):
  ```
  [digit ABI][major][minor][patch][increment]
  ABI: arm64-v8a = 1, x86_64 = 4
  contoh: 5.4.1 arm64 → 105040100 ; 5.4.1 x86_64 → 405040100
  ```
  Alasan digit besar buat x86_64: "arm64-v8a sering didukung platform lain lewat emulasi, jadi angka tertinggi harus dikasih ke ABI lain."
  → Buat **armeabi-v7a pakai digit `0`**: artinya kalau device bisa dua-duanya, dia milih 64-bit, dan APK armv7 nggak akan bisa "menimpa" APK arm64 (ke-deteksi sebagai downgrade).
- **Triple arch** (dipakai staging buat ngambil libc++ dari sysroot NDK):
  - `arm64-v8a` → `aarch64-linux-android`
  - `x86_64` → `x86_64-linux-android`
  - ⚠️ buat armv7: **compiler prefix**-nya `armv7a-linux-androideabi<API>-clang`, tapi **direktori sysroot**-nya `arm-linux-androideabi`. Untuk nilai di file ini, pakai **`arm-linux-androideabi`** (dicek dulu di `$NDK/toolchains/llvm/prebuilt/<host>/sysroot/usr/lib/`, karena staging-nya nyari libc++ di sana).
- Kode ini **`FATAL_ERROR`** kalau ABI bukan kedua itu → jadi 2 blok yang harus dipatch (allowlist + triple).

## 4. `build_files/build_environment/` (dependency builder)

- Resep per-library: `build_files/build_environment/cmake/*.cmake` (aom, alembic, blosc, brotli, bzip2, ceres, cython, draco, ...).
- Ada `android_meson_crossfile.txt.in` → cross-file Meson di-parameterisasi per ABI (dari PR #164424).
- Commit terkait yang wajib dibaca kalau armv7 gagal:
  - `Deps: Android: Fix per-ABI flags in autoconf based recipes` — "beberapa resep autoconf nge-hardcode nilai AArch64 di cabang Android, atau malah ambil cabang x86_64 desktop" → resep armv7 bakal kena masalah serupa.
  - `Deps: Exclude compute backends from Android builds` — HIP-RT & DPC++ nggak ada di Android.
  - `Deps: ISPC: Support building Android cross-targets on Linux hosts` — ISPC dipakai OpenImageDenoise.
- **Precompiled libs:** submodule `lib/android_arm64` dan `lib/android_x64` (repo `lib-android_arm64` / `lib-android_x64`).
  → **nggak ada versi armv7.** Jadi armv7 = build deps sendiri = bagian tersulit M4.

## 5. `GNUmakefile` (target convenience) — anchor persis

Nama filenya **`GNUmakefile`** (huruf 'm' kecil!). Struktur penting, dikutip persis:

```makefile
ifneq "$(findstring android, $(MAKECMDGOALS))" ""
	TARGET_OS:=Android
	TARGET_OS_NCASE:=android
	IS_CROSSCOMPILING:=1

	# Target architecture selection, defaults to 64-bit ARM when no architecture goal is given.
	TARGET_CPU:=$(strip $(filter arm64 x64, $(MAKECMDGOALS)))
	ifeq ($(TARGET_CPU),)
		TARGET_CPU:=arm64
	endif

	# Map the target architecture onto its Android ABI name, passed to the toolchain file below.
	# See https://developer.android.com/ndk/guides/abis for the list of Android ABI names.
	ifeq ($(TARGET_CPU),arm64)
		ANDROID_ABI:=arm64-v8a
	else
		ANDROID_ABI:=x86_64
	endif
	...
	ANDROID_TOOLCHAIN_FILE:=$(BLENDER_DIR)/build_files/cmake/platform/platform_android_toolchain.cmake
	CMAKE_CROSSCOMPILE_CONFIG_ARGS:=-DCMAKE_TOOLCHAIN_FILE=$(ANDROID_TOOLCHAIN_FILE) \
									-DANDROID_ABI=$(ANDROID_ABI)
endif
```

Dan blok target di bagian bawah:

```makefile
# Cross-compilation targets

android: .FORCE
	@echo "Building for Android $(ANDROID_ABI) from host $(HOST_OS)."

# Target architecture selection goals, only meaningful combined with a cross-compilation
# target such as `android`.
arm64: .FORCE
x64: .FORCE
```

Konsekuensi yang enak untuk armv7:
- `HOST_DEPS_BUILD_DIR` = `build_$(HOST_OS_NCASE)/deps_$(HOST_CPU)` (host tools saat cross-compile).
- **`DEPS_BUILD_DIR` = `build_android/deps_$(TARGET_CPU)`** dan **`DEPS_INSTALL_DIR` = `lib/$(OS_LIBDIR)_$(TARGET_CPU)`** → begitu `armv7` diterima sebagai TARGET_CPU, direktori deps otomatis jadi `deps_armv7` dan hasil harvest otomatis ke **`lib/android_armv7`**. Tidak ada perubahan lain yang diperlukan untuk penamaan.
- `deps:` mengekspor `SOURCE_DATE_EPOCH` (build reproducible).

## 6. Kenapa x86_64 relevan buat lo

- Emulator Android (AVD) biasanya **x86_64** → build x64 = lo bisa ngetes cepat di emulator tanpa HP.
- Chromebook & Googlebook kelas baru = x86_64 (dan arm64).
- Ini juga alasan upstream nambah ABI ini (PR #164424).

---

## 7. `build_files/cmake/platform/platform_unix.cmake` — rumah `LIBDIR_ANDROID`

Jerat yang harus diketahui: memilih ABI saja **tidak cukup** — Blender juga harus diberi tahu di mana library precompiled-nya berada. Blok persisnya (dikutip):

```cmake
  if(NOT DEFINED LIBDIR AND ANDROID)
    # Map the Android ABI onto Blender's own architecture naming conventions,
    # matching the directory the dependency builder harvests into.
    if(ANDROID_ABI STREQUAL "arm64-v8a")
      set(LIBDIR_ANDROID ${CMAKE_SOURCE_DIR}/lib/android_arm64)
    elseif(ANDROID_ABI STREQUAL "x86_64")
      set(LIBDIR_ANDROID ${CMAKE_SOURCE_DIR}/lib/android_x64)
    else()
      message(FATAL_ERROR "Unsupported Android ABI \"${ANDROID_ABI}\".")
    endif()
```

Tanpa cabang `armeabi-v7a` di sini, build armv7 akan mati dengan `FATAL_ERROR` **walaupun** toolchain-nya sudah dipatch. Ini rule wajib di `apply-port-patches.py`.

Temuan lain dari file yang sama:
- Saat `ANDROID`, `LIBDIR` di-prepend ke `CMAKE_FIND_ROOT_PATH` (karena toolchain NDK mengunci `ROOT_PATH_MODE_PACKAGE=ONLY`).
- `WITH_VULKAN_BACKEND` untuk Android: **loader Vulkan TIDAK diambil dari LIBDIR** — "Android provides its own Vulkan Loader", yang diambil dari LIBDIR hanya header SPIR-V (untuk name injection shader, PR !162006). Jadi jangan bingung mencari `libvulkan.so` di paket deps.
- Ada `add_bundled_libraries(vulkan/lib)` dan penanganan `shaderc` — shaderc tetap wajib ada di LIBDIR.

## 8. `source/blender/blenlib/intern/uuid.cc` — penghalang minSdk

Satu-satunya alasan `ANDROID_PLATFORM` dinaikkan dari 28 → 29 (Android 9 → 10) ada di file ini:

```cpp
    timespec ts;
    timespec_get(&ts, TIME_UTC);
```

`timespec_get()` baru ada di bionic sejak API 29. Untuk menurunkan minSdk ke 28, ganti dengan `clock_gettime(CLOCK_REALTIME, &ts)` (ada sejak API 21). Rule ini sudah diotomatiskan di `apply-port-patches.py --minsdk 28`.

Alasan historis lain (ada di komentar `platform_android_toolchain.cmake`): 23 → 28 karena `aligned_alloc()` (C11) yang dipakai **OpenJPH**. Jadi kalau mau API ≤ 27, patch OpenJPH atau bangun dengan `-DWITH_OPENJPH=OFF`.

## 9. GHOST di branch android — windowing SDL, GPU context VK/EGL

Isi `intern/ghost/intern/` (branch `android`) yang relevan:

- `GHOST_ContextSDL.cc/.hh` — windowing Android (SDL3), termasuk lifecycle surface.
- `GHOST_ContextVK.cc/.hh` — konteks **Vulkan** (jalur aktif; ada commit "Fix: SDL: Broken Vulkan rendering after Android app resume", Sep 2026).
- `GHOST_ContextEGL.cc/.hh` — konteks **EGL** ada di tree. Ini titik masuk paling mungkin untuk jalur **desktop GL via Mesa/Zink** (harus diarahkan ke `libEGL` bundel + `EGL_OPENGL_API`, bukan `EGL_OPENGL_ES_API` sistem).
- ❌ **Tidak ada** `GHOST_SystemAndroid.cc` / `GHOST_WindowAndroid.cc` di upstream. Nama file itu berasal dari fork komunitas lain (epai / port SDL pihak ketiga) — jangan dicari di upstream.

Commit upstream yang relevan (branch `android`, Sep–Okt 2026):
- `Vulkan: Lower requirements to support Vulkan 1.1 devices.` — inilah yang membuat kelas mobile (driver Vulkan 1.1) bisa masuk.
- `Android: Lower base DPI override to 240`, `UI: Use Android immersive mode...`, `Android: Allow external file browsers to open .blend files`, `Fix: SDL: Broken Vulkan rendering after Android app resume`.

## 10. Modul GPU & syarat renderer (untuk rencana multi-renderer)

- Backend Blender: `source/blender/gpu/{opengl,vulkan,metal}`. Dokumen resmi: "GPU Module Overview" + "GLSL Cross Compilation" + "Blender Shader Language".
- Syarat minimum (resmi, Blender 5.x): **OpenGL 4.3** dengan **wajib** `GL_ARB_shader_draw_parameters` + `GL_ARB_clip_control`; **Vulkan 1.3**, dan 5.3 menurunkannya ke **1.1** untuk Android/device lama. Kalau Vulkan tidak ada → Blender mundur ke OpenGL.
- `--gpu-backend vulkan|metal|opengl` adalah argumen CLI yang **sudah ada** → ini kunci untuk runtime selection tanpa mengubah kode Blender banyak-banyak.
- Zink memberi GL 4.6 di atas Vulkan; kopper menyediakan jalur EGL/WSI-nya. Bukti di Android: laporan `zink Vulkan 1.4 (Adreno ... MESA_TURNIP)` / "OpenGL 4.6 core profile" di lingkungan Termux, dan Winlator yang mengirim Mesa (Turnip/Zink/VirGL) di APK native.
- **VirGL bukan opsi untuk Blender**: tabel fitur `vrend_renderer.c` menandai `clip_control` butuh host GL 4.5 dan `draw_parameters` butuh GL 4.6 — host Android-nya GLES, jadi dua extension wajib itu tidak akan ada.
- Rencana lengkapnya: `docs/RENDERERS.md` (matriks + selector) dan `docs/GLES-BACKEND.md` (proyek backend GLES).

---

## Perintah cek cepat (dijalankan di checkout Blender lo, di CI/terminal)

```bash
# 1. Konfirmasi allowlist ABI & platform API
grep -n "ANDROID_ABI\|ANDROID_PLATFORM" build_files/cmake/platform/platform_android_toolchain.cmake

# 2. Konfirmasi blok triple + versionCode
grep -n "_android_arch_triple\|_abi_prefix" build_files/cmake/platform/platform_android_gradle.cmake

# 3. Konfirmasi LIBDIR_ANDROID (ini yang sering kelewat)
grep -n "LIBDIR_ANDROID\|arm64-v8a\|x86_64" build_files/cmake/platform/platform_unix.cmake | head

# 4. Routing arch di makefile (nama file: GNUmakefile, bukan GNUMakefile)
grep -n "TARGET_CPU\|ANDROID_ABI\|arm64: \.FORCE" GNUmakefile | head -n 20

# 5. Semua tempat yang masih hanya menyebut dua ABI (daftar kerja lengkap buat armv7)
grep -rn "arm64-v8a\|x86_64" --include="*.cmake" --include="GNUmakefile" --include="*.gradle" \
  build_files release GNUmakefile | grep -v "^Binary"

# 6. Versi NDK yang diminta
grep -rn "NDK" build_files/build_environment/cmake/check_software.cmake

# 7. Backend GL ikut dikompilasi? (prasyarat rencana Zink/GL)
ls source/blender/gpu/opengl/ | head
grep -rn "WITH_VULKAN_BACKEND\|GPU_BACKEND_OPENGL" build_files/cmake/options.cmake | head -n 20

# 8. Titik pemilihan backend saat runtime
grep -rn "gpu-backend" source/blender/creator/*.cc | head
grep -rn "EGL_OPENGL_API\|EGL_OPENGL_ES_API" intern/ghost/intern/GHOST_ContextEGL.cc | head
```
