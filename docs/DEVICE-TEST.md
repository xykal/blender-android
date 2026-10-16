# DEVICE-TEST — ngetes cuma pakai HP (tanpa PC)

Prinsip: **HP lo = device lab.** Nggak butuh ADB, nggak butuh laptop. Semua langkah di bawah bisa dilakukan dari HP.

---

## 1. Cek dulu: HP lo sanggup nggak?

Tiga syarat mutlak (kalau salah satu gagal, Blender nggak akan nyala sama sekali):

| Syarat | Cara cek tanpa PC |
|---|---|
| **CPU 64-bit (arm64-v8a)** | Install APK arm64. Kalau muncul error "App not installed" / "aplikasi tidak terpasang" padahal Android lo 10+, kemungkinan ROM-nya 32-bit. |
| **Android 10+ (API 29)** | Setelan → Tentang ponsel → Versi Android. (Upstream set `ANDROID_PLATFORM android-29`.) |
| **GPU punya driver Vulkan 1.1** | Aplikasi **AIDA64** atau **DevCheck** → bagian GPU → cari "Vulkan" + versinya. Kalau kosong → nggak ada Vulkan → Blender nggak bisa jalan (nggak ada fallback OpenGL). |

Catatan: mayoritas HP keluaran 2019+ (Snapdragon 6-series ke atas / Adreno 6xx ke atas) aman. HP lama dengan Mali-400 / Adreno 3xx–4xx: jangan berharap.

## 2. Pasang APK hasil build sendiri

1. Unduh artifact dari GitHub Actions (atau rilis).
2. Buka File Manager → tap APK → Android minta izin **"Install unknown apps"** → izinkan untuk app yang lo pakai (browser / Files).
3. **Launch pertama bakal lama** (puluhan detik sampai ~1 menit, cuma splash). App lagi unpack ~100 MB runtime ke storage privatnya. **Jangan di-force close** — nanti keulang dari awal.

Kalau gagal install dengan "App not installed":
- APK armv7 dicoba di HP 64-bit-only (Pixel 7+, sebagian flagship baru) → memang nggak bisa, itu wajar.
- Tanda tangan beda dengan versi sebelumnya → uninstall dulu yang lama.

## 3. Checklist tes (jalanin berurutan, catat yang gagal)

Untuk setiap APK yang mau lo rilis:

1. **Startup** — sampai viewport tampil. Berapa detik?
2. **File** — New scene, hapus cube, simpan ke storage, tutup, buka lagi. (Kalau app mati: interogasi **File → Recover → Auto Save**.)
3. **Navigasi viewport** — orbit, pan, zoom. Berapa FPS kira-kira (nyaman / patah-patah / nggak bisa dipakai)?
4. **Modeling ringan** — tambah cube, subdivide 2×, masuk Sculpt, beberapa tarikan brush. (Ini yang paling sering nge-crash di 32-bit karena batas memori.)
5. **Material** — Principled BSDF + satu texture. (Bug yang pernah ada: material render jadi hampir hitam → tandai kalau kejadian, dulu itu bug khusus Android.)
6. **EEVEE** — render 1 frame sederhana, resolusi 50%. Berhasil? Berapa detik?
7. **Cycles** — 32 sample, resolusi 25%, CPU only. Berapa detik? (Cycles GPU nggak ada di Android.)
8. **Audio** (kalau ada) — timeline playback, pastikan nggak crash.
9. **Termal / sustained** — pakai 10 menit nonstop. HP panas? Kerasa throttle (FPS drop)? Masuk catatan.
10. **Stylus** (kalau ada) — tekanan terasa? (S-Pen: cek Sculpt brush size sensitivity.)

## 4. Protokol laporan

**Cara paling gampang: buka issue pakai template "Compatibility report".** Isi:

- Model HP + SoC (misal: Redmi Note 13 / Snapdragon 685)
- Versi Android
- Versi Vulkan (dari AIDA64/DevCheck)
- Varian APK (arm64 full / arm64 lite / armv7 / x64)
- Hasil tiap langkah checklist di atas (boleh singkat: ✅ / ❌ / "patah-patah")
- Kalau app mati: apakah kejadian di langkah nomor berapa, dan apakah **Auto Save** masih ada isinya

**Soal log:** tanpa PC, ngambil `logcat` susah (app logcat non-root nggak boleh baca log sistem). Karena itu **M2 di roadmap** memasang tombol **"Share startup log"** di dalam app yang nulis log ke file yang bisa di-share dari HP. Sampai itu ada, laporan deskriptif sudah cukup berguna.

## 5. Tips hemat waktu

- Setelah ubah default viewport/EEVEE, **simpan sebagai startup file** di app, biar nggak setel ulang tiap buka (HP bukan tempat ngutak-atik preferensi 50 kali).
- Scene uji harus **tetap**: satu file .blend kecil (cube + sphere + material + 1 light) buat benchmark antar build. Simpan di Downloads.
- Screenshot itu bukti tercepat: satu screenshot error lebih berguna daripada 3 paragraf.
- Test **satu hal berubah per build**. Kalau lo ganti 10 hal lalu crash, lo nggak tahu penyebabnya.
- Backup selalu. Ini alpha; APK yang crash bisa nggak bisa dibuka sama sekali.
