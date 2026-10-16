# GLES-BACKEND — rencana backend OpenGL ES native untuk modul GPU Blender

**Status: proyek riset. Jangan dijanjikan ke siapa pun sebelum ada spike yang jalan.**

Ini satu-satunya jalan supaya device **tanpa Vulkan** bisa menjalankan Blender 5.x di Android. Semua jalur lain (Vulkan vendor, Turnip, Zink, Freedreno, lavapipe) tetap butuh Vulkan atau GPU desktop-class. Kalau lo serius mau "yang nggak bisa dilakukan orang lain", ini dia — tapi harganya nyata: hitungan bulan, dan hasilnya pun cuma sampai "bisa dipakai untuk modeling ringan".

---

## 1. Masalahnya dalam satu tabel

Blender (modul `gpu`) punya kontrak: **OpenGL 4.3 core** + dua extension wajib. GLES 3.2 punya sebagian besar fitur modern, tapi ada lubang spesifik yang harus diakali.

| Kebutuhan Blender | GLES 3.2 | Catatan / strategi |
|---|---|---|
| Shader storage buffer (SSBO) | ✅ ES 3.1 | Aman |
| Compute shader | ✅ ES 3.1 | Aman (dipakai compositor/EEVEE) |
| Image load/store (`imageLoad/Store`) | ✅ ES 3.1 | Aman |
| Immutable texture storage (`glTexStorage*`) | ✅ ES 3.0 | Aman |
| sRGB framebuffer | ✅ ES 3.0 | Aman |
| Instanced draw | ✅ ES 3.0 | Aman |
| `baseVertex` draw | 🟡 ES 3.2 core / `EXT_draw_elements_base_vertex` | Pakai extension di ES 3.0/3.1 |
| `baseInstance` draw | 🟡 `EXT_base_instance` | Umum tersedia; kalau tidak, emulasi lewat atribut offset |
| Multi-draw indirect | 🟡 `EXT_multi_draw_indirect` | Bisa dimatikan → satu draw per panggilan (lebih lambat, tetap benar) |
| Depth clamp | ✅ ES 3.2 | Aman |
| Transform feedback | ✅ ES 3.0 | Aman |
| Occlusion query, sync/fence | ✅ ES 3.0 | Aman |
| Multisample texture | ✅ ES 3.1 | Aman |
| **`ARB_shader_draw_parameters`** (`gl_DrawID`, `gl_BaseVertex`, `gl_BaseInstance`) | ❌ | **Ini lubang terbesar.** Emulasi: (a) matikan jalur "GPU-driven batching" Blender dan gambar per-draw, atau (b) suntik uniform per draw (`glUniform1i` + `glDrawID` buatan sendiri), atau (c) trik instancing. Semua ada harga performa/kompleksitas di draw manager. |
| **`ARB_clip_control`** (`GL_ZERO_TO_ONE`, `GL_LOWER_LEFT`) | ❌ | Emulasi: ubah konvensi kedalaman di shader (`z' = z*0.5 + w*0.5`) + balik fungsi depth + konsistenkan seluruh state depth. Ini menyentuh banyak tempat dan gampang bikin bug halus (shadow, wireframe, kedalaman terbalik). |
| Geometry shader | ❌ | Audit dulu: Blender 5.x masih pakai geometry shader di beberapa path (mis. ekspansi garis/curtain). Harus diganti compute+SSBO atau CPU. |
| Tessellation shader | ❌ | Sama — audit; kemungkinan jarang dipakai di viewport. |
| `glPolygonMode` (wireframe solid) | ❌ | Blender punya jalur wireframe berbasis shader; audit apakah jalur itu cukup. |
| Double precision (`dvec`, `gl_Position` double) | ❌ | Audit — sebagian besar GPU Blender pakai float, tapi sisir `source/blender/gpu/**` untuk `dvec`/`double` di shader. |
| Vertex attrib binding (`glBindVertexBuffer`) | 🟡 `EXT_vertex_attrib_binding` | Umum ada di ES 3.1+; kalau tidak, fallback ke path lama. |
| Dual-source blending | 🟡 `EXT_blend_func_extended` | Cek dukungan; sebagian shader EEVEE mengandalkannya. |
| Texture buffer object | 🟡 ES 3.2 / `EXT_texture_buffer` | Sering ada; kalau tidak, fallback ke SSBO. |

**Kesimpulan teknis:** GLES 3.1/3.2 sebenarnya **cukup mampu**; yang jadi masalah bukan fitur rendering modern, tapi **dua extension lama** (`shader_draw_parameters`, `clip_control`) plus beberapa jalur shader khusus. Itu kabar bagus: kerjaannya berat di "menyesuaikan", bukan di "mustahil".

---

## 2. Arsitektur yang gw usulkan

### 2.1 Backend baru, bukan tambalan di GL

```
source/blender/gpu/
├── opengl/        (GL 4.3 — tetap apa adanya)
├── vulkan/
├── metal/
└── gles/          ← BARU: backend GLES 3.1/3.2
    ├── gles_backend.cc      (inisialisasi, deteksi fitur, extension allowlist)
    ├── gles_capabilities.cc (GCaps versi GLES)
    ├── gles_shader.cc       (kompilasi ESSL)
    └── gles_draw.cc         (draw path + emulasi draw parameters)
```

Blender sudah punya abstraksi `GPU_BACKEND_*` (dipakai untuk memilih Vulkan/Metal/GL). Menambah `GPU_BACKEND_GLES` mengikuti pola yang sama. Titik masuknya: `gpu_backend_create()`, `GPU_backend_type_selection_set()`, dan `gpu::GPU_backend_get_type()`.

### 2.2 Pipeline shader: GLSL 4.x → ESSL 3.1/3.2

Blender menulis shader dengan "meta-language" (shader_tool) yang bisa ditargetkan ke GLSL desktop, SPIR-V (Vulkan), dan MSL (Metal). Untuk GLES, ada dua opsi:

- **Opsi A (disarankan):** tambah target ES di `shader_tool` → emit **ESSL 310/320** langsung dari sumber yang sudah ada (atur `#version`, eksplisitkan binding, ganti `layout` yang tidak ada, ganti built-in yang tidak ada).
- **Opsi B:** lewat SPIR-V lalu **SPIRV-Cross → ESSL**. Lebih "aman" secara sistematis (semua transformasi di satu tempat), tapi menambah satu tool + satu lapisan yang bisa salah. Kalau `shader_tool` sudah punya infrastruktur cross-compile, opsi A lebih hemat.

Yang harus ditangani di kedua opsi: `layout(binding=...)` untuk UBO/SSBO/texture (canonical di ES 3.1 tapi sering butuh kompatibilitas), `gl_ClipDistance` (butuh `#extension GL_EXT_clip_cull_distance`), `gl_Layer` (ES 3.2), integer texture formats, dan presisi (`precision highp float;` wajib di ES — MSL/Vulkan tidak butuh itu).

### 2.3 Emulasi dua extension wajib

**a) `clip_control` → konvensi kedalaman.**

Blender memakai `glClipControl(GL_LOWER_LEFT, GL_ZERO_TO_ONE)` untuk menyamakan konvensi depth dengan Vulkan. Di GLES:

- Tambahkan transform di vertex shader: `gl_Position.z = gl_Position.z * 0.5 + gl_Position.w * 0.5;`
- Ubah `glDepthFunc` dan nilai clear depth supaya konsisten.
- Sisir semua tempat yang menulis `gl_FragDepth` (pemetaan mundur yang sama).

Ini mirip dengan yang dilakukan backend Vulkan/Metal Blender saat menyesuaikan clip space — jadi ada preseden di kodebase sendiri. Risikonya: setiap tempat yang lupa disesuaikan akan kelihatan sebagai artefak z-fighting / objek hilang.

**b) `shader_draw_parameters` → jalur draw.**

Tiga strategi, dari paling murah ke paling mahal:

1. **Matikan batching GPU-driven.** Blender punya jalur "single draw" dan jalur batched. Paksa jalur sederhana: satu `glDrawElements` per group, `gl_BaseVertex`-nya nol. Paling gampang, paling lambat (draw call naik banyak di scene kompleks).
2. **Uniform per draw.** Sebelum tiap draw, `glUniform1ui(gl_DrawID_loc, i)`. Butuh penyesuaian di shader (ganti `gl_DrawID` → `uniform uint gl_DrawID;`) dan di draw manager.
3. **Instancing trick / atribut sintetis.** Cuma kalau 1 & 2 tidak cukup.

Untuk versi pertama: **pakai strategi 1**. Targetkan "berfungsi", bukan "cepat". Optimasi setelahnya.

### 2.4 Yang harus dimatikan / diturunkan di profil GLES

- Workbench: tetap (target utama pertama, paling sederhana).
- EEVEE: matikan fitur yang bergantung pada geometry/tessellation shader dan virtual texturing; turunkan kualitas default.
- Cycles: tetap CPU (di Android memang CPU-only).
- Compositor GPU: tunda; awalnya jalan pakai CPU compositor.
- Grease Pencil: audit (shader-nya relatif sederhana, kemungkinan jalan lebih mudah dari EEVEE).

---

## 3. Rencana spike (yang harus dibuktikan lebih dulu, berurutan)

| # | Spike | Kriteria lulus |
|---|---|---|
| S1 | **Inisialisasi GLES + deteksi fitur** | Binary Android bisa membuat EGL/GLES 3.1 context lewat GHOST dan mencetak `GL_VERSION`/`GL_RENDERER` + semua extension |
| S2 | **Workbench satu objek** | Satu kubus + grid ter-render benar lewat backend GLES (termasuk kedalaman & sRGB) |
| S3 | **UI Blender** | IMM/draw manager menggambar UI (font, widget, icon) — di sini *clip_control* emulation mulai diuji |
| S4 | **Clipping & selection** | Clip plane, selection outline, anti-alias benar |
| S5 | **Workbench scene nyata** | Scene 100k–500k tri, navigasi viewport, hasil visual dibandingkan dengan GL desktop (pixel diff) |
| S6 | **EEVEE minimal** | Satu frame EEVEE dengan material sederhana, tanpa fitur lanjutan |
| S7 | **Grease Pencil / object mode umum** | Operasi harian nggak crash |

**Gate keputusan:** kalau S2–S3 tembus, proyek ini layak dilanjutkan (artinya konsepnya benar). Kalau S3 tersangkut lebih dari ~2 bulan, hentikan — dan alihkan ke jalur "Blender 2.79 + GL4ES" untuk device lama (lihat `docs/RENDERERS.md` §7).

---

## 4. Perkiraan biaya (jujur)

| Aspek | Perkiraan |
|---|---|
| Skill minimum | 1 orang yang paham render pipeline + GLSL/ESSL + sudah pernah menyentuh draw manager Blender |
| Waktu sampai "bisa dibuka & modeling ringan" (S1–S5) | 3–6 bulan paruh waktu intensif, atau 2–3 bulan full time — **dengan asumsi banyak dibantu diskusi dengan dev Blender** |
| Waktu sampai "bisa dipakai harian" | +6 bulan lagi (bug halus di kedalaman, blending, AA, driver vendor yang beda-beda) |
| Risiko utama | (1) `clip_control` emulation menimbulkan bug visual sulit dilacak; (2) driver Mali/Adreno berbeda perilaku di ESSL; (3) merge conflict terus-menerus dengan upstream karena sentuhan di `gpu/` besar |

Yang paling penting: **jangan publikasikan estimasi waktu ke publik.** Umumkan sebagai "riset, tanpa jadwal".

---

## 5. Cara memulai besok (kalau nekat)

1. Clone branch `android`, build arm64 sampai APK jalan (M0). Jangan mulai GLES tanpa ini.
2. Baca `source/blender/gpu/opengl/gl_backend.cc` **seluruhnya**. Pahami `detect_workarounds()`, `GPU_backend_init_once()`, GCaps.
3. Buat `gpu/gles/` yang **cuma** menginisialisasi GLES context + mencetak capability (S1). Jangan sentuh apa pun lagi.
4. Cari cara termurah mencetak itu dari app: bikin jalur "diagnostic mode" di Activity yang memanggil fungsi ini dan menulis hasilnya ke file log. Dari sini semua debugging jadi mungkin tanpa PC.
5. Kirim hasil S1 ke thread "Issues porting Blender to Android tablets" di devtalk Blender. Kalau ada dev yang tertarik, proyek ini naik kelas dari "spike sendirian" jadi "upstream-adjacent" — itu pengali terbesar untuk keberhasilan.

---

## 6. Kalau tidak nekat (pilihan rasional)

- Device tanpa Vulkan **mayoritas juga lambat**: bahkan kalau backend GLES-nya selesai, scene yang bisa dibuka sangat terbatas (RAM kecil, GPU kelas entry, sering 32-bit).
- Energy yang sama, kalau dialihkan ke: **R1 (selector)** + **R2 (Turnip)** + **R3 (Zink/GL)** + **minSdk 28**, akan menyenangkan **jauh lebih banyak** pengguna nyata — karena itu menyasar device 2019+ yang punya Vulkan tapi driver-nya bermasalah.
- Jadi: GLES backend = "legacy/ideologis", bukan prioritas pengguna. Kerjakan kalau memang tujuannya *menjadi yang pertama*, bukan kalau tujuannya *paling banyak dipakai*.
