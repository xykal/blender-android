# NOTICE — lisensi & merek dagang

## 1. Kode ini GPL

Blender adalah perangkat lunak bebas berlisensi **GNU GPL v3 (atau lebih baru)**.
Karena repo ini berisi modifikasi dan skrip build untuk Blender, **seluruh patch dan skrip
di repo ini juga tunduk pada GPLv3 atau lebih baru.**

## 2. Artinya kalau kamu membagikan APK

Setiap kali kamu **mengdistribusikan** APK hasil build (GitHub Releases, Google Drive,
grup Telegram, apa pun), GPLv3 mewajibkan kamu menyertakan **source code lengkap yang
sesuai (corresponding source)** — yaitu versi Blender yang kamu build, termasuk semua
modifikasi kamu, dalam bentuk yang bisa dikompilasi ulang.

Cara paling simpul memenuhinya (dan yang dipakai CI ini):

1. Push repo ini sebagai **repo publik** — script patch + konfigurasi build sudah termasuk.
2. Simpan patch hasil CI (`porting-<abi>.patch`) dan commit upstream yang dipakai
   (`upstream-commit-<abi>.txt`) **di setiap rilis**. CI sudah menghasilkan dua file itu
   sebagai artifact otomatis.
3. Cantumkan di deskripsi rilis: versi Blender, commit upstream, dan link ke source.

Kalau kamu mengubah Blender langsung (bukan lewat script ini), perubahan itu juga wajib
dipublikasikan. Jangan ragu: ini bukan beban, ini justru yang membuat orang lain bisa
memverifikasi dan ikut memperbaiki port.

## 3. Merek dagang & afiliasi

- **Proyek ini UNOFFICIAL.** Tidak berafiliasi, tidak disponsori, dan tidak di-endorse oleh
  Blender Foundation.
- Jangan gunakan nama resmi atau logo resmi Blender dengan cara yang menyiratkan ini produk
  resmi. Sebutkan selalu: *"unofficial community port of Blender for Android"*.
- Nama paket `org.blender.blender` diwarisi dari skeleton Gradle upstream; kalau kamu
  merilis luas, pertimbangkan menggantinya dengan namespace komunitas sendiri.

## 4. Tanggung jawab

Build di repo ini adalah **alpha eksperimental** di atas port yang belum stabil. Selalu
ingatkan pengguna: cadangkan file kerja mereka, dan jangan pakai untuk produksi.
