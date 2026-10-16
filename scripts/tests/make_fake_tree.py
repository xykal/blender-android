#!/usr/bin/env python3
"""
make_fake_tree.py — bikin pohon file TIRUAN yang berisi teks anchor asli upstream.

Tujuannya: menguji `apply-port-patches.py` (logika anchor, idempotensi, jalur gagal)
TANPA meng-clone atau meng-compile Blender. Kalau upstream mengubah file-file ini,
anchor di sini harus diperbarui bersama `docs/UPSTREAM-NOTES.md`.

Semua kutipan di bawah diambil dari branch `android` upstream per 16 Oktober 2026.
"""

from __future__ import annotations

import sys
from pathlib import Path

# --------------------------------------------------------------------------------------

TOOLCHAIN = """set(NDK_TOOLCHAIN_FILE "${ANDROID_NDK_ROOT}/build/cmake/android.toolchain.cmake")

# ----------------------------------------------------------------------------
# Android ABI

# Supported ABIs are arm64-v8a (default) and x86_64.
# 32-bit ABIs (armeabi-v7a, x86) are not supported.
if(NOT ANDROID_ABI)
  set(ANDROID_ABI arm64-v8a)
endif()

if(NOT (ANDROID_ABI STREQUAL "arm64-v8a" OR ANDROID_ABI STREQUAL "x86_64"))
  message(FATAL_ERROR
    "Unsupported Android ABI \\"${ANDROID_ABI}\\", expected one of: arm64-v8a, x86_64."
  )
endif()

message(STATUS "Using Android ABI: ${ANDROID_ABI}")

# ----------------------------------------------------------------------------
# Android platform / minimum SDK version.

# Set to API level 29, minimum set to Android 10. See https://apilevels.com.

# - Used to be 23 (min Android 6.0), bumped to 28 to support C11 aligned_alloc required by OpenJPH.
#   It might be possible to lower it back down by patching OpenJPH.
# - Used to be 28 (min Android 9.0), bumped to 29 to support timespec_get for BLI's uuid.cc.
#   It should be possible to lower it back down by adding an ifdef switch in uuid.cc

set(ANDROID_PLATFORM android-29)

# ----------------------------------------------------------------------------
# Android STL type (static/shared)

set(ANDROID_STL c++_shared)
"""

GRADLE_CMAKE = """set(_apk_version_name "${BLENDER_VERSION}.${BLENDER_VERSION_PATCH}-${BLENDER_VERSION_CYCLE}")

if(ANDROID_ABI STREQUAL "arm64-v8a")
  set(_abi_prefix 1)
elseif(ANDROID_ABI STREQUAL "x86_64")
  set(_abi_prefix 4)
else()
  message(FATAL_ERROR "Unsupported ANDROID_ABI: ${ANDROID_ABI}")
endif()

if(ANDROID_ABI STREQUAL "arm64-v8a")
  set(_android_arch_triple "aarch64-linux-android")
elseif(ANDROID_ABI STREQUAL "x86_64")
  set(_android_arch_triple "x86_64-linux-android")
else()
  message(FATAL_ERROR "Unsupported Android ABI \\"${ANDROID_ABI}\\".")
endif()
"""

PLATFORM_UNIX = """# Libraries configuration for any *nix system including Linux and Unix (excluding APPLE).

if(NOT WITH_LIBS_PRECOMPILED)
  unset(LIBDIR)
else()
  if(NOT DEFINED LIBDIR AND ANDROID)
    # Map the Android ABI onto Blender's own architecture naming conventions,
    # matching the directory the dependency builder harvests into.
    if(ANDROID_ABI STREQUAL "arm64-v8a")
      set(LIBDIR_ANDROID ${CMAKE_SOURCE_DIR}/lib/android_arm64)
    elseif(ANDROID_ABI STREQUAL "x86_64")
      set(LIBDIR_ANDROID ${CMAKE_SOURCE_DIR}/lib/android_x64)
    else()
      message(FATAL_ERROR "Unsupported Android ABI \\"${ANDROID_ABI}\\".")
    endif()

    file(GLOB LIBDIR_RESULT ${LIBDIR_ANDROID}/*)
"""

# PENTING: file ini memakai TAB untuk indentasi.
GNUMAKEFILE = (
    'ifneq "$(findstring android, $(MAKECMDGOALS))" ""\n'
    "\tTARGET_OS:=Android\n"
    "\tTARGET_OS_NCASE:=android\n"
    "\tIS_CROSSCOMPILING:=1\n"
    "\n"
    "\t# Target architecture selection, defaults to 64-bit ARM when no architecture goal is given.\n"
    "\tTARGET_CPU:=$(strip $(filter arm64 x64, $(MAKECMDGOALS)))\n"
    "\tifeq ($(TARGET_CPU),)\n"
    "\t\tTARGET_CPU:=arm64\n"
    "\tendif\n"
    "\n"
    "\t# Map the target architecture onto its Android ABI name, passed to the toolchain file below.\n"
    "\t# See https://developer.android.com/ndk/guides/abis for the list of Android ABI names.\n"
    "\tifeq ($(TARGET_CPU),arm64)\n"
    "\t\tANDROID_ABI:=arm64-v8a\n"
    "\telse\n"
    "\t\tANDROID_ABI:=x86_64\n"
    "\tendif\n"
    "\n"
    "\t# Use our own Android CMake toolchain file wrapper.\n"
    "\tANDROID_TOOLCHAIN_FILE:=$(BLENDER_DIR)/build_files/cmake/platform/platform_android_toolchain.cmake\n"
    "endif\n"
    "\n"
    "# Cross-compilation targets\n"
    "\n"
    "android: .FORCE\n"
    '\t@echo "Building for Android $(ANDROID_ABI) from host $(HOST_OS)."\n'
    "\n"
    "# Target architecture selection goals, only meaningful combined with a cross-compilation\n"
    "# target such as `android`.\n"
    "arm64: .FORCE\n"
    "x64: .FORCE\n"
    "\n"
    "define HELP_TEXT\n"
    "Cross-Compilation Targets\n"
    "   * android:       Build for Android via cross-compilation, applies to regular Blender builds and `deps` dependency builds.\n"
    "\n"
    "   * arm64:         Target the 64-bit ARM architecture (Android ABI 'arm64-v8a').\n"
    "   * x64:           Target the 64-bit x86 architecture (Android ABI 'x86_64').\n"
    "endef\n"
)

UUID_CC = """#include "BLI_assert.hh"
#include "BLI_uuid.hh"

#include <ctime>
#include <random>

namespace blender {

bUUID BLI_uuid_generate_random()
{
  static std::mt19937_64 rng = []() {
    std::mt19937_64 rng;

    timespec ts;
    timespec_get(&ts, TIME_UTC);
    /* XOR the nanosecond and second fields, just in case the clock only has seconds resolution. */
    uint64_t seed = ts.tv_nsec;
    seed ^= ts.tv_sec;
    rng.seed(seed);

    return rng;
  }();
}
}  // namespace blender
"""

DEPS_CMAKELISTS = """# SPDX-FileCopyrightText: 2023 Blender Authors
# SPDX-License-Identifier: GPL-2.0-or-later

cmake_minimum_required(VERSION 3.10)
project("BlenderDependencies")
if(POLICY CMP0135)
  cmake_policy(SET CMP0135 NEW)
endif()
include(ExternalProject)

include(cmake/options.cmake)
include(cmake/versions.cmake)
include(cmake/download.cmake)
include(cmake/macros.cmake)
include(cmake/ssl.cmake)
include(cmake/zlib.cmake)
include(cmake/png.cmake)
include(cmake/jpeg.cmake)
include(cmake/openexr.cmake)
include(cmake/freetype.cmake)
include(cmake/alembic.cmake)
include(cmake/opensubdiv.cmake)
include(cmake/sdl.cmake)
include(cmake/tbb.cmake)
include(cmake/python.cmake)
include(cmake/llvm.cmake)
include(cmake/openimageio.cmake)
include(cmake/usd.cmake)
include(cmake/materialx.cmake)
include(cmake/openvdb.cmake)
include(cmake/potrace.cmake)
include(cmake/harfbuzz.cmake)
include(cmake/fmt.cmake)
include(cmake/openjph.cmake)
include(cmake/thorvg.cmake)
include(cmake/webp.cmake)

if(NOT WIN32 OR ENABLE_MSYS2)
  include(cmake/gmp.cmake)
  include(cmake/openjpeg.cmake)
  include(cmake/sqlite.cmake)
  include(cmake/aom.cmake)
  if(NOT WIN32 OR BUILD_MODE STREQUAL Release)
    include(cmake/openimagedenoise.cmake)
    include(cmake/lame.cmake)
    include(cmake/ogg.cmake)
    include(cmake/ffmpeg.cmake)
    include(cmake/sndfile.cmake)
  endif()
endif()

if(BLENDER_PLATFORM_WINDOWS_ARM)
  include(cmake/embree_windows_arm.cmake)
else()
  include(cmake/embree.cmake)
endif()

include(cmake/shaderc.cmake)
include(cmake/vulkan.cmake)
include(cmake/spirv-reflect.cmake)
include(cmake/eigen.cmake)
include(cmake/draco.cmake)
include(cmake/meshoptimizer.cmake)
"""

FILES = {
    "build_files/cmake/platform/platform_android_toolchain.cmake": TOOLCHAIN,
    "build_files/cmake/platform/platform_android_gradle.cmake": GRADLE_CMAKE,
    "build_files/cmake/platform/platform_unix.cmake": PLATFORM_UNIX,
    "build_files/build_environment/CMakeLists.txt": DEPS_CMAKELISTS,
    "GNUmakefile": GNUMAKEFILE,
    "source/blender/blenlib/intern/uuid.cc": UUID_CC,
}


def make_tree(dest: Path) -> Path:
    for rel, text in FILES.items():
        p = dest / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    return dest


if __name__ == "__main__":
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/blender-fake-tree")
    make_tree(out)
    print(f"Pohon tiruan dibuat di: {out}")
    for rel in FILES:
        print(f"  - {rel}")
