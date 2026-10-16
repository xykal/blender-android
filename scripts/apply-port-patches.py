#!/usr/bin/env python3
"""
apply-port-patches.py — terapkan patch port Android ke checkout source Blender.

Dipakai dari CI (lihat .github/workflows/android-build.yml) DAN bisa dipakai manual:

    python3 scripts/apply-port-patches.py --blender ./blender --abi arm64            # no-op (upstream penuh)
    python3 scripts/apply-port-patches.py --blender ./blender --abi armv7            # patch ABI 32-bit
    python3 scripts/apply-port-patches.py --blender ./blender --minsdk 28            # turunkan minSdk ke Android 9
    python3 scripts/apply-port-patches.py --blender ./blender --abi armv7 --dry-run  # cek tanpa menulis

Prinsip:
  * IDEMPOTEN — jalan dua kali tidak merusak apa pun (dicek lewat marker "PORT PATCH").
  * AMAN — kalau anchor teks upstream tidak ketemu, script TIDAK menebak; dia lapor dan
    keluar dengan exit code != 0 untuk rule wajib, supaya CI gagal dengan pesan jelas.
  * MINIMAL — patch sesedikit mungkin biar merge dengan upstream tetap gampang.

Semua anchor diverifikasi terhadap branch `android` upstream per 16 Oktober 2026.
Lihat docs/UPSTREAM-NOTES.md kalau ada yang gagal (kemungkinan upstream refactor).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# --------------------------------------------------------------------------------------
# Util

OK = "\033[92m✓\033[0m"
WARN = "\033[93m!\033[0m"
FAIL = "\033[91m✗\033[0m"

report: list[tuple[str, str, str]] = []


def log(level: str, path: str, message: str) -> None:
    icon = {"ok": OK, "warn": WARN, "fail": FAIL}[level]
    print(f"  {icon} {path}: {message}")
    report.append((level, path, message))


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def replace_once(
    root: Path,
    rel_path: str,
    marker: str,
    old: str,
    new: str,
    *,
    required: bool,
    dry_run: bool,
) -> bool:
    """Ganti `old` -> `new` tepat sekali, dengan marker idempotensi."""
    path = root / rel_path
    if not path.exists():
        log("fail" if required else "warn", rel_path, "file tidak ada (upstream berubah?)")
        return not required

    text = read(path)

    if marker in text:
        log("ok", rel_path, "sudah dipatch sebelumnya (skip)")
        return True

    count = text.count(old)
    if count == 0:
        log("fail" if required else "warn",
            rel_path, "anchor teks tidak ditemukan — upstream mungkin refactor, cek manual")
        return not required
    if count > 1:
        log("fail", rel_path, f"anchor muncul {count}× (harus tepat 1) — batalkan")
        return False

    if dry_run:
        log("ok", rel_path, "DRY-RUN: akan dipatch")
        return True

    write(path, text.replace(old, new, 1))
    log("ok", rel_path, "dipatch")
    return True


# --------------------------------------------------------------------------------------
# Rule 1: toolchain — allowlist ABI 32-bit + NEON

TOOLCHAIN = "build_files/cmake/platform/platform_android_toolchain.cmake"

TOOLCHAIN_OLD = """# Supported ABIs are arm64-v8a (default) and x86_64.
# 32-bit ABIs (armeabi-v7a, x86) are not supported.
if(NOT ANDROID_ABI)
  set(ANDROID_ABI arm64-v8a)
endif()

if(NOT (ANDROID_ABI STREQUAL "arm64-v8a" OR ANDROID_ABI STREQUAL "x86_64"))
  message(FATAL_ERROR
    "Unsupported Android ABI \\"${ANDROID_ABI}\\", expected one of: arm64-v8a, x86_64."
  )
endif()
"""

TOOLCHAIN_NEW = """# Supported ABIs are arm64-v8a (default) and x86_64.
# 32-bit ABIs (armeabi-v7a, x86) are not supported.
# PORT PATCH: armeabi-v7a (32-bit) ditambahkan oleh port ini. Upstream belum
# mendukungnya, dan build 32-bit jauh lebih rapuh (batas 4 GB address space,
# tanpa Embree/OIDN/ISPC). Lihat docs/PLAN.md bagian 32-bit.
if(NOT ANDROID_ABI)
  set(ANDROID_ABI arm64-v8a)
endif()

if(NOT (ANDROID_ABI STREQUAL "arm64-v8a" OR ANDROID_ABI STREQUAL "x86_64"
        OR ANDROID_ABI STREQUAL "armeabi-v7a"))
  message(FATAL_ERROR
    "Unsupported Android ABI \\"${ANDROID_ABI}\\", expected one of: arm64-v8a, x86_64, armeabi-v7a."
  )
endif()

# PORT PATCH: untuk 32-bit, NEON wajib secara praktik (didukung semua CPU Android
# modern). Mode 'arm' dipilih karena sebagian hot-path Blender lebih cepat tanpa
# Thumb-2; sesuaikan kalau ada masalah.
if(ANDROID_ABI STREQUAL "armeabi-v7a")
  set(ANDROID_ARM_NEON ON)
  set(ANDROID_ARM_MODE arm)
endif()
"""


def patch_toolchain(root: Path, dry_run: bool) -> bool:
    print(f"\n[1] {TOOLCHAIN}")
    return replace_once(root, TOOLCHAIN, "PORT PATCH: armeabi-v7a",
                        TOOLCHAIN_OLD, TOOLCHAIN_NEW, required=True, dry_run=dry_run)


# --------------------------------------------------------------------------------------
# Rule 2: Gradle bridge — digit versionCode + arch triple

GRADLE_CMAKE = "build_files/cmake/platform/platform_android_gradle.cmake"

VERSIONCODE_ANCHOR = """elseif(ANDROID_ABI STREQUAL "x86_64")
  set(_abi_prefix 4)
"""
VERSIONCODE_ADD = """elseif(ANDROID_ABI STREQUAL "armeabi-v7a")
  # PORT PATCH: digit terendah supaya device yang mendukung keduanya memilih build
  # 64-bit, dan APK armv7 tidak bisa menimpa APK arm64 (terdeteksi sebagai downgrade).
  set(_abi_prefix 0)
"""

TRIPLE_ANCHOR = """elseif(ANDROID_ABI STREQUAL "x86_64")
  set(_android_arch_triple "x86_64-linux-android")
"""
TRIPLE_ADD = """elseif(ANDROID_ABI STREQUAL "armeabi-v7a")
  # PORT PATCH: direktorat sysroot NDK untuk 32-bit ARM bernama 'arm-linux-androideabi'
  # (BUKAN 'armv7a-linux-androideabi' — itu prefix compiler-nya).
  # Cek dengan: ls $ANDROID_NDK_ROOT/toolchains/llvm/prebuilt/*/sysroot/usr/lib/
  set(_android_arch_triple "arm-linux-androideabi")
"""


def patch_gradle_cmake(root: Path, dry_run: bool) -> bool:
    print(f"\n[2] {GRADLE_CMAKE}")
    ok1 = replace_once(root, GRADLE_CMAKE, "_abi_prefix 0",
                       VERSIONCODE_ANCHOR, VERSIONCODE_ANCHOR + VERSIONCODE_ADD,
                       required=True, dry_run=dry_run)
    ok2 = replace_once(root, GRADLE_CMAKE, "arm-linux-androideabi",
                       TRIPLE_ANCHOR, TRIPLE_ANCHOR + TRIPLE_ADD,
                       required=True, dry_run=dry_run)
    return ok1 and ok2


# --------------------------------------------------------------------------------------
# Rule 3: LIBDIR_ANDROID — direktori precompiled lib armv7 (platform_unix.cmake)

UNIX_CMAKE = "build_files/cmake/platform/platform_unix.cmake"

LIBDIR_OLD = """    if(ANDROID_ABI STREQUAL "arm64-v8a")
      set(LIBDIR_ANDROID ${CMAKE_SOURCE_DIR}/lib/android_arm64)
    elseif(ANDROID_ABI STREQUAL "x86_64")
      set(LIBDIR_ANDROID ${CMAKE_SOURCE_DIR}/lib/android_x64)
    else()
      message(FATAL_ERROR "Unsupported Android ABI \\"${ANDROID_ABI}\\".")
    endif()
"""
LIBDIR_NEW = """    if(ANDROID_ABI STREQUAL "arm64-v8a")
      set(LIBDIR_ANDROID ${CMAKE_SOURCE_DIR}/lib/android_arm64)
    elseif(ANDROID_ABI STREQUAL "x86_64")
      set(LIBDIR_ANDROID ${CMAKE_SOURCE_DIR}/lib/android_x64)
    elseif(ANDROID_ABI STREQUAL "armeabi-v7a")
      # PORT PATCH: upstream tidak menyediakan submodule precompiled lib untuk armv7.
      # Direktori ini harus hasil `make deps android armv7` milikmu sendiri
      # (DEPS_INSTALL_DIR di GNUmakefile otomatis mengarah ke lib/android_armv7).
      set(LIBDIR_ANDROID ${CMAKE_SOURCE_DIR}/lib/android_armv7)
    else()
      message(FATAL_ERROR "Unsupported Android ABI \\"${ANDROID_ABI}\\".")
    endif()
"""


def patch_platform_unix(root: Path, dry_run: bool) -> bool:
    print(f"\n[3] {UNIX_CMAKE}")
    return replace_once(root, UNIX_CMAKE, "lib/android_armv7",
                        LIBDIR_OLD, LIBDIR_NEW, required=True, dry_run=dry_run)


# --------------------------------------------------------------------------------------
# Rule 4: GNUmakefile — routing arch 'armv7'
# (indentasi file ini memakai TAB — anchor di bawah memakai \t eksplisit)

GNUMakefile = "GNUmakefile"

GNU_CPU_OLD = "\tTARGET_CPU:=$(strip $(filter arm64 x64, $(MAKECMDGOALS)))\n"
GNU_CPU_NEW = "\tTARGET_CPU:=$(strip $(filter arm64 x64 armv7, $(MAKECMDGOALS)))\n"

GNU_ABI_OLD = """\tifeq ($(TARGET_CPU),arm64)
\t\tANDROID_ABI:=arm64-v8a
\telse
\t\tANDROID_ABI:=x86_64
\tendif
"""
GNU_ABI_NEW = """\tifeq ($(TARGET_CPU),arm64)
\t\tANDROID_ABI:=arm64-v8a
\telseif ($(TARGET_CPU),armv7)
\t\tANDROID_ABI:=armeabi-v7a
\telse
\t\tANDROID_ABI:=x86_64
\tendif
"""

GNU_GOALS_OLD = """arm64: .FORCE
x64: .FORCE
"""
GNU_GOALS_NEW = """arm64: .FORCE
x64: .FORCE
armv7: .FORCE
"""

GNU_HELP_OLD = "   * x64:           Target the 64-bit x86 architecture (Android ABI 'x86_64').\n"
GNU_HELP_NEW = ("   * x64:           Target the 64-bit x86 architecture (Android ABI 'x86_64').\n"
                "   * armv7:         Target the 32-bit ARM architecture (Android ABI 'armeabi-v7a'). EXPERIMENTAL.\n")


def patch_gnumakefile(root: Path, dry_run: bool) -> bool:
    print(f"\n[4] {GNUMakefile}")
    ok = replace_once(root, GNUMakefile, "filter arm64 x64 armv7",
                      GNU_CPU_OLD, GNU_CPU_NEW, required=True, dry_run=dry_run)
    ok &= replace_once(root, GNUMakefile, "ANDROID_ABI:=armeabi-v7a",
                       GNU_ABI_OLD, GNU_ABI_NEW, required=True, dry_run=dry_run)
    ok &= replace_once(root, GNUMakefile, "armv7: .FORCE",
                       GNU_GOALS_OLD, GNU_GOALS_NEW, required=True, dry_run=dry_run)
    ok &= replace_once(root, GNUMakefile, "Android ABI 'armeabi-v7a'",
                       GNU_HELP_OLD, GNU_HELP_NEW, required=False, dry_run=dry_run)
    return ok


# --------------------------------------------------------------------------------------
# Rule 5: untuk armv7, lewati library deps yang tidak praktis di ARM 32-bit
#
# Kenapa perlu: `make deps` TIDAK membaca config Blender (blender_lite.cmake), jadi
# walau Blender-nya dibangun dengan goal `lite` (WITH_EMBREE/OIDN/USD/OFF), dependency
# builder tetap mencoba membangun semuanya dan gagal di library yang butuh ARM64/SIMD 128-bit.
#
# Pasangannya: bangun Blender dengan goal `lite`, mis. `make android armv7 lite`
# → blender_lite.cmake mematikan fitur yang sama di sisi Blender.

DEPS_CMAKE = "build_files/build_environment/CMakeLists.txt"

DEPS_GUARD_ANCHOR = 'project("BlenderDependencies")\n'
DEPS_GUARD_ADD = """
# PORT PATCH: profil deps "Lite" untuk ARM 32-bit (armv7).
# Library yang dilewati di bawah ini butuh SIMD 128-bit / hanya tersedia untuk ARM64,
# dan padanannya sudah dimatikan di sisi Blender oleh build_files/cmake/config/blender_lite.cmake.
if(ANDROID AND ANDROID_ABI STREQUAL "armeabi-v7a")
  set(BLENDER_ANDROID_ARMV7_LITE ON)
  message(STATUS "PORT PATCH: profil deps armv7 Lite aktif — melewati Embree/OIDN/USD/MaterialX/OpenVDB/Alembic")
else()
  set(BLENDER_ANDROID_ARMV7_LITE OFF)
endif()
"""

# (baris include, indentasi di file asli)
DEPS_SKIP_LIBS = [
    ("include(cmake/embree.cmake)", 2),
    ("include(cmake/openimagedenoise.cmake)", 4),
    ("include(cmake/usd.cmake)", 0),
    ("include(cmake/materialx.cmake)", 0),
    ("include(cmake/openvdb.cmake)", 0),
    ("include(cmake/alembic.cmake)", 0),
]


def patch_deps_armv7_lite(root: Path, dry_run: bool) -> bool:
    print(f"\n[5] {DEPS_CMAKE}  (profil deps armv7 Lite)")

    ok = replace_once(root, DEPS_CMAKE, "BLENDER_ANDROID_ARMV7_LITE ON",
                      DEPS_GUARD_ANCHOR, DEPS_GUARD_ANCHOR + DEPS_GUARD_ADD,
                      required=False, dry_run=dry_run)

    for line, indent in DEPS_SKIP_LIBS:
        lib = line.split("cmake/")[1].replace(".cmake)", "")
        marker = f"# PORT PATCH armv7-lite: {lib}"
        old = " " * indent + line + "\n"
        new = (
            " " * indent + "if(NOT BLENDER_ANDROID_ARMV7_LITE)\n"
            + " " * (indent + 2) + line + f"  {marker}\n"
            + " " * indent + "endif()\n"
        )
        ok &= replace_once(root, DEPS_CMAKE, marker, old, new,
                           required=False, dry_run=dry_run)
    return ok


# --------------------------------------------------------------------------------------
# Rule 6: minSdk lebih rendah (opsional, lewat --minsdk)
#
# Kenapa ini terpisah dari armv7: "jangkau Android lama" itu masalah yang BEDA
# dengan "jangkau CPU 32-bit". Menurunkan minSdk ke 28 (Android 9) untuk build
# arm64 jauh lebih murah daripada membangun armv7, dan menjangkau lebih banyak
# device nyata. Lihat docs/RENDERERS.md dan docs/PLAN.md.

_ANDROID_VERSIONS = {
    21: "5.0", 22: "5.1", 23: "6", 24: "7.0", 25: "7.1", 26: "8.0", 27: "8.1",
    28: "9", 29: "10", 30: "11", 31: "12", 32: "12L", 33: "13", 34: "14",
    35: "15", 36: "16",
}


def android_version_name(api: int) -> str:
    return _ANDROID_VERSIONS.get(api, f"API {api}")


def patch_minsdk(root: Path, minsdk: int, dry_run: bool) -> bool:
    print(f"\n[6] minSdk -> API {minsdk} (Android {android_version_name(minsdk)})")

    if minsdk >= 29:
        log("warn", TOOLCHAIN, f"minSdk {minsdk} >= 29: sudah jadi default upstream, tidak ada yang dipatch")
        return True

    # 5a. Toolchain: ANDROID_PLATFORM
    platform_old = "set(ANDROID_PLATFORM android-29)\n"
    platform_new = (
        f"# PORT PATCH: minSdk diturunkan ke API {minsdk} (Android {android_version_name(minsdk)}).\n"
        f"# Lihat docs/PLAN.md & docs/RENDERERS.md. Catatan upstream: 29 dibutuhkan untuk\n"
        f"# timespec_get() di source/blender/blenlib/intern/uuid.cc (sudah dipatch script ini).\n"
        f"set(ANDROID_PLATFORM android-{minsdk})\n"
    )
    ok = replace_once(root, TOOLCHAIN, f"PORT PATCH: minSdk diturunkan",
                      platform_old, platform_new, required=True, dry_run=dry_run)

    # 5b. uuid.cc: timespec_get() hanya ada sejak API 29
    uuid_old = """    timespec ts;
    timespec_get(&ts, TIME_UTC);
"""
    uuid_new = """    timespec ts;
#if defined(__ANDROID__) && (__ANDROID_API__ < 29)
    /* PORT PATCH: timespec_get() baru tersedia sejak Android 10 (API 29).
     * clock_gettime() ada sejak API 21 dan setara untuk TIME_UTC.
     * Kalau compiler mengeluh tidak menemukan deklarasi, tambahkan #include <time.h>. */
    clock_gettime(CLOCK_REALTIME, &ts);
#else
    timespec_get(&ts, TIME_UTC);
#endif
"""
    ok &= replace_once(root, "source/blender/blenlib/intern/uuid.cc",
                       "PORT PATCH: timespec_get()", uuid_old, uuid_new,
                       required=True, dry_run=dry_run)

    if minsdk <= 27:
        log("warn", TOOLCHAIN,
            f"minSdk {minsdk} <= 27: OpenJPH butuh aligned_alloc() (C11, API 28). "
            "Patch OpenJPH atau bangun dengan -DWITH_OPENJPH=OFF.")

    return ok


# --------------------------------------------------------------------------------------
# Bagian manual (belum bisa diotomatiskan — butuh iterasi lawan device)

MANUAL = """
================================================================================
PATCH MANUAL / KERJA LANJUTAN (lihat docs/ROADMAP.md)
================================================================================

a) RESEP DEPS UNTUK armv7 — `make deps android armv7` akan gagal di sebagian resep:
     build_files/build_environment/cmake/{embree,openimagedenoise,ispc,usd}.cmake
   Urutan kerja yang disarankan:
     1. Jalankan `make deps android armv7` dan catat library pertama yang gagal.
     2. Matikan dulu fiturnya di sisi Blender (mis. -DWITH_CYCLES_EMBREE=OFF,
        -DWITH_OPENIMAGEDENOISE=OFF, -DWITH_USD=OFF), biarkan build tembus.
     3. Baru hidupkan satu-satu; tiap satu library = satu patch terpisah.
   Referensi pola fix: commit upstream "Deps: Android: Fix per-ABI flags in autoconf
   based recipes" (resep autoconf gampang sekali nge-hardcode nilai AArch64).

b) BLENDER_PLATFORM_ARM — cek apakah armv7 ikut terdeteksi:
     grep -rn "BLENDER_PLATFORM_ARM" build_files/build_environment/cmake/options.cmake
   Variabel ini mengaktifkan resep sse2neon; kalau hanya di-set untuk arm64,
   armv7 mungkin butuh perlakuan serupa.

c) FINGERPRINT ABI — cari semua tempat yang masih hanya menyebut dua ABI:
     grep -rn "arm64-v8a\\|x86_64" --include='*.cmake' --include='*.gradle' \\
       --include='GNUmakefile' build_files release GNUmakefile

d) RUNTIME RENDERER SELECTION (Vulkan/Turnip/OpenGL-Zink) — lihat docs/RENDERERS.md.
   Titik sentuh yang perlu dibaca di checkout:
     - release/android/app/src/main/java/org/blender/blender/  (Activity, tempat argumen dikirim)
     - intern/ghost/intern/GHOST_ContextSDL.* , GHOST_ContextVK.* , GHOST_ContextEGL.*
     - source/blender/creator/  (parsing argumen, termasuk --gpu-backend)
   Blender sudah punya argo CLI `--gpu-backend vulkan|opengl|metal`. Langkah pertama
   yang paling murah: baca preferensi dari file dan suntikkan argumen itu saat launch.

e) Device tanpa Vulkan = TIDAK BISA JALAN dengan port ini.
   Tidak ada jalur OpenGL/GLES native di port ini (desktop GL tidak ada di Android).
   Jalur yang mungkin: bundel Zink (GL di atas Vulkan) — tetap butuh Vulkan;
   atau tulis backend GLES baru di modul gpu Blender (proyek riset, docs/GLES-BACKEND.md).
"""


# --------------------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description="Patch Blender source untuk port Android.")
    ap.add_argument("--blender", required=True, help="path ke checkout source Blender (branch android)")
    ap.add_argument("--abi", default="arm64", choices=["arm64", "x64", "armv7"],
                    help="ABI target; 'arm64'/'x64' = tidak ada patch ABI yang perlu diterapkan")
    ap.add_argument("--minsdk", type=int, default=None,
                    help="turunkan minSdk ke API level ini (mis. 28 = Android 9)")
    ap.add_argument("--dry-run", action="store_true", help="jangan tulis apa pun")
    args = ap.parse_args()

    root = Path(args.blender).resolve()
    if not (root / "build_files").is_dir():
        print(f"{FAIL} '{root}' bukan checkout Blender (folder build_files tidak ada).")
        return 2

    print("=" * 80)
    print(f"apply-port-patches  ·  blender={root}  ·  abi={args.abi}"
          f"  ·  minsdk={args.minsdk if args.minsdk else '-'}"
          f"{'  · DRY-RUN' if args.dry_run else ''}")
    print("=" * 80)

    if args.abi in ("arm64", "x64") and args.minsdk is None:
        print(f"\n{OK} ABI '{args.abi}' didukung upstream penuh — tidak ada patch yang perlu diterapkan.")
        print("    (Kalau ingin minSdk lebih rendah, tambahkan: --minsdk 28)")
        return 0

    ok = True

    if args.abi == "armv7":
        ok &= patch_toolchain(root, args.dry_run)
        ok &= patch_gradle_cmake(root, args.dry_run)
        ok &= patch_platform_unix(root, args.dry_run)
        ok &= patch_gnumakefile(root, args.dry_run)
        ok &= patch_deps_armv7_lite(root, args.dry_run)

    if args.minsdk is not None:
        ok &= patch_minsdk(root, args.minsdk, args.dry_run)

    print(MANUAL)

    failures = [r for r in report if r[0] == "fail"]
    print("=" * 80)
    if failures:
        print(f"{FAIL} {len(failures)} rule GAGAL. CI sebaiknya berhenti di sini.")
        print("   Anchor tidak ketemu → kemungkinan upstream berubah.")
        print("   Jalankan perintah di docs/UPSTREAM-NOTES.md bagian 'Perintah cek cepat'.")
        return 1

    if args.abi == "armv7":
        print(f"{OK} Semua rule armv7 berhasil diterapkan.")
        print("   Lanjut (pakai goal 'lite', pasangan dari profil deps armv7):")
        print("     make deps android armv7")
        print("     make android armv7 lite")
        print("   Catatan: hasilnya masuk ke build_android_armv7_lite/, bukan build_android_armv7/.")
    if args.minsdk is not None:
        print(f"{OK} minSdk diturunkan ke API {args.minsdk}. Jangan lupa uji di device lama sungguhan.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
