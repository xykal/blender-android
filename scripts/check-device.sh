#!/data/data/com.termux/files/usr/bin/bash
# check-device.sh — cek kesanggupan device SEBELUM mengunduh APK 200+ MB.
#
# Cara pakai (tanpa root, tanpa PC):
#   1. Install Termux (F-Droid, jangan Play Store — versi Play sudah usang).
#   2. Salin file ini ke device, lalu:
#        bash check-device.sh
#   Atau kalau tidak mau pakai Termux: pakai aplikasi AIDA64 / DevCheck dan
#   bandingkan sendiri dengan tabel di bawah.

set -u

echo "=============================================================="
echo " Blender for Android — pemeriksaan device"
echo "=============================================================="
echo

# --- Identitas dasar ---------------------------------------------------------
ANDROID_REL="$(getprop ro.build.version.release 2>/dev/null)"
SDK="$(getprop ro.build.version.sdk 2>/dev/null)"
ABI_LIST="$(getprop ro.product.cpu.abilist 2>/dev/null)"
ABI_PRIMARY="$(getprop ro.product.cpu.abi 2>/dev/null)"
SOC_MANUF="$(getprop ro.soc.manufacturer 2>/dev/null)"
SOC_MODEL="$(getprop ro.soc.model 2>/dev/null)"
BOARD="$(getprop ro.board.platform 2>/dev/null)"
EGL="$(getprop ro.hardware.egl 2>/dev/null)"
MODEL="$(getprop ro.product.model 2>/dev/null)"

echo "Model         : ${MODEL:-?}"
echo "Android       : ${ANDROID_REL:-?}  (API ${SDK:-?})"
echo "SoC           : ${SOC_MANUF:-?} ${SOC_MODEL:-?}  (board: ${BOARD:-?})"
echo "GPU (EGL)     : ${EGL:-?}"
echo "ABI utama     : ${ABI_PRIMARY:-?}"
echo "ABI didukung  : ${ABI_LIST:-?}"
echo

verdict_ok=1

# --- 1. ABI ------------------------------------------------------------------
echo "--------------------------------------------------------------"
echo "[1] Arsitektur CPU"
case "${ABI_PRIMARY:-}" in
  arm64-v8a)
    echo "  ✓ arm64-v8a → pakai APK arm64 (direkomendasikan)."
    ;;
  armeabi-v7a|armeabi)
    echo "  ! Device 32-bit. Butuh APK armv7 (Legacy Lite) — masih eksperimental,"
    echo "    dan wajib punya driver Vulkan."
    verdict_ok=0
    ;;
  x86_64)
    echo "  ✓ x86_64 → APK x64 (Chromebook/emulator)."
    ;;
  *)
    echo "  ✗ ABI tidak dikenali: ${ABI_PRIMARY:-?} — kemungkinan tidak didukung."
    verdict_ok=0
    ;;
esac
echo

# --- 2. Versi Android -------------------------------------------------------
echo "--------------------------------------------------------------"
echo "[2] Versi Android (minimum port ini: API 29 / Android 10)"
if [ -n "${SDK:-}" ] && [ "$SDK" -ge 29 ] 2>/dev/null; then
  echo "  ✓ API ${SDK} memenuhi syarat."
else
  echo "  ✗ API ${SDK:-?} < 29. Port ini tidak akan terpasang."
  echo "    (Bisa dipaksa dengan patch minSdk — lihat: apply-port-patches.py --minsdk 28)"
  verdict_ok=0
fi
echo

# --- 3. Driver Vulkan -------------------------------------------------------
echo "--------------------------------------------------------------"
echo "[3] Driver Vulkan  (WAJIB — tidak ada fallback OpenGL/GLES)"
found_vk=0
for p in /system/lib64/libvulkan.so /system/lib/libvulkan.so \
         /vendor/lib64/libvulkan.so /vendor/lib/libvulkan.so; do
  if [ -e "$p" ]; then
    echo "  ✓ ada: $p"
    found_vk=1
  fi
done
if [ "$found_vk" -eq 0 ]; then
  echo "  ✗ TIDAK ADA libvulkan.so di device ini."
  echo "    → Blender TIDAK BISA jalan, mau APK varian apa pun."
  echo "    → Satu-satunya harapan jangka panjang: backend GLES baru (docs/GLES-BACKEND.md)."
  verdict_ok=0
fi
echo

# --- 4. Daftar device Vulkan (kalau tool tersedia) --------------------------
if command -v vulkaninfo >/dev/null 2>&1; then
  echo "--------------------------------------------------------------"
  echo "[4] vulkaninfo (ringkas)"
  vulkaninfo --summary 2>/dev/null | head -n 25 | sed 's/^/  /'
  echo
fi

# --- Hasil ------------------------------------------------------------------
echo "=============================================================="
if [ "$verdict_ok" -eq 1 ]; then
  echo " HASIL: ✓ Device ini memenuhi syarat minimum."
  echo "        APK yang cocok: arm64 Full (atau Lite kalau RAM <= 6 GB)."
  echo "        Jangan lupa: launch pertama butuh ~1 menit (unpack ~100 MB)."
else
  echo " HASIL: ! Ada syarat yang tidak terpenuhi (lihat tanda ✗ di atas)."
  echo "        Kirim laporan lewat template 'Compatibility report'."
fi
echo "=============================================================="
echo
echo "Catatan: tanpa root, kita hanya bisa cek keberadaan libvulkan.so."
echo "Untuk baca versi Vulkan (1.1 / 1.3 / dst), pakai AIDA64 atau DevCheck,"
echo "atau dumpsys:  dumpsys SurfaceFlinger | grep -i vulkan"
