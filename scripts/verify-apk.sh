#!/usr/bin/env bash
# verify-apk.sh — periksa isi APK hasil build sebelum dirilis.
#
# Pemakaian:
#   ./scripts/verify-apk.sh out/app-release.apk
#
# Yang dicek:
#   1. ABI apa saja yang ada di dalam APK (harus TEPAT SATU)
#   2. Ukuran lib native terbesar (indikasi APK kebawa debug/simbol)
#   3. Alignment page 16 KB (syarat Android 15+ / Play untuk app baru)
#   4. Apakah APK menyebut Vulkan (fitur wajib app ini)
#
# Exit code != 0 berarti ada masalah yang harus diperbaiki sebelum rilis.

set -uo pipefail

APK="${1:-}"
if [[ -z "$APK" || ! -f "$APK" ]]; then
  echo "Pemakaian: $0 <file.apk>" >&2
  exit 2
fi

fail=0
warn=0

echo "=============================================="
echo " Memeriksa: $APK"
echo " Ukuran   : $(du -h "$APK" | cut -f1)"
echo "=============================================="

# --- 1. ABI di dalam APK ---------------------------------------------------------------
echo
echo "[1] ABI di dalam APK"
mapfile -t ABIS < <(unzip -Z1 "$APK" 2>/dev/null \
  | grep -oE '^lib/[^/]+/' | sed 's|^lib/||; s|/$||' | sort -u)

if [[ ${#ABIS[@]} -eq 0 ]]; then
  echo "  ✗ Tidak ada lib/<abi>/ di APK. Ini bukan APK dengan native lib."
  fail=1
else
  printf '  · %s\n' "${ABIS[@]}"
  if [[ ${#ABIS[@]} -gt 1 ]]; then
    echo "  ! APK berisi lebih dari satu ABI → ukuran membengkak."
    echo "    Port ini pakai strategi satu-ABI-satu-APK (lihat docs/PLAN.md §3)."
    warn=1
  else
    echo "  ✓ Tepat satu ABI."
  fi
fi

# --- 2. Ukuran lib native --------------------------------------------------------------
echo
echo "[2] Ukuran lib native"
unzip -l "$APK" 2>/dev/null | grep -E 'lib/.*\.so$' | sort -k1 -n -r | head -n 5 \
  | awk '{printf "  %10.1f MB  %s\n", $1/1048576, $4}'
echo "  (lib utama Blender di atas 150 MB = normal untuk profil Full.)"

# --- 3. Alignment 16 KB ---------------------------------------------------------------
echo
echo "[3] Alignment page 16 KB (syarat Android 15+ / Play untuk app baru)"
TMPDIR_LIB="$(mktemp -d)"
unzip -q -o "$APK" "lib/*" -d "$TMPDIR_LIB" 2>/dev/null || true

BIGGEST="$(find "$TMPDIR_LIB" -name '*.so' -printf '%s %p\n' 2>/dev/null | sort -n | tail -n1 | cut -d' ' -f2-)"
if [[ -n "$BIGGEST" ]] && command -v readelf >/dev/null 2>&1; then
  # Cari LOAD segment dengan alignment terkecil.
  MIN_ALIGN="$(readelf -lW "$BIGGEST" 2>/dev/null | awk '/LOAD/ {print $NF}' | sort -u | head -n1)"
  echo "  File  : $(basename "$BIGGEST")"
  echo "  Align : ${MIN_ALIGN:-tidak terdeteksi}"
  if [[ "${MIN_ALIGN:-0}" == "0x4000" || "${MIN_ALIGN:-0}" == "0x10000" ]]; then
    echo "  ✓ Sudah kompatibel 16 KB."
  else
    echo "  ! Alignment terdeteksi '${MIN_ALIGN:-?}'. Tambahkan link flag:"
    echo "      -Wl,-z,max-page-size=16384"
    warn=1
  fi
else
  echo "  (readelf tidak tersedia / lib tidak ditemukan — dilewati)"
fi

# zipalign bisa mengonfirmasi juga, kalau ada (dari Android build-tools):
if command -v zipalign >/dev/null 2>&1; then
  echo "  zipalign -c -P 16 -v 4:"
  zipalign -c -P 16 -v 4 "$APK" 2>&1 | tail -n 3 | sed 's/^/    /'
fi

rm -rf "$TMPDIR_LIB"

# --- 4. Vulkan ------------------------------------------------------------------------
echo
echo "[4] Dukungan Vulkan (wajib untuk app ini)"
if command -v aapt2 >/dev/null 2>&1; then
  if aapt2 dump badging "$APK" 2>/dev/null | grep -qi 'vulkan'; then
    echo "  ✓ Manifest menyatakan kebutuhan fitur Vulkan."
  else
    echo "  ! Manifest tidak menyebut Vulkan. Pastikan memang disengaja"
    echo "    (device tanpa Vulkan tetap tidak bisa menjalankan app ini)."
    warn=1
  fi
else
  echo "  (aapt2 tidak tersedia — dilewati; bisa dicek manual di AndroidManifest.xml)"
fi

# --- Ringkasan -----------------------------------------------------------------------
echo
echo "=============================================="
if [[ $fail -eq 1 ]]; then
  echo " HASIL: ✗ ADA MASALAH — jangan dirilis dulu."
elif [[ $warn -eq 1 ]]; then
  echo " HASIL: ! Ada peringatan. Periksa di atas sebelum rilis."
else
  echo " HASIL: ✓ Siap dirilis."
fi
echo "=============================================="
exit $fail
