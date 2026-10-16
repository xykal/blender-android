# patches/

Patch ke source Blender dikelola di sini, **satu topik = satu rule**.

## Kenapa tidak file `.patch`/`.diff` statis?

Karena repo ini bukan fork penuh — setiap build mengambil branch `android` upstream secara fresh, lalu menempelkan patch. Diff statis gampang ditolak `git apply` saat konteks berubah, dan CI jadi rusak tanpa penjelasan. Karena itu patch di sini berbentuk **anchor-based** (lihat `scripts/apply-port-patches.py`):

- idempoten (marker `PORT PATCH:` dicek dulu),
- kalau anchor hilang → **gagal dengan pesan jelas**, bukan diam-diam tidak dipatch,
- rule wajib → `exit 1` (CI berhenti, tidak menghasilkan APK cacat).

## Isi saat ini

| Rule | File upstream | Status anchor | Wajib? | Kapan aktif |
|---|---|---|---|---|
| Allowlist ABI 32-bit + NEON | `platform_android_toolchain.cmake` | ✅ terverifikasi | ya | `--abi armv7` |
| Digit `versionCode` ABI (`_abi_prefix 0`) | `platform_android_gradle.cmake` | ✅ terverifikasi | ya | `--abi armv7` |
| Arch triple sysroot (`arm-linux-androideabi`) | `platform_android_gradle.cmake` | ✅ terverifikasi | ya | `--abi armv7` |
| `LIBDIR_ANDROID` → `lib/android_armv7` | `platform_unix.cmake` | ✅ terverifikasi | ya | `--abi armv7` |
| Routing arch `armv7` di Makefile | `GNUmakefile` (3 anchor + 1 help text) | ✅ terverifikasi | ya/cosmetic | `--abi armv7` |
| `ANDROID_PLATFORM android-28` | `platform_android_toolchain.cmake` | ✅ terverifikasi | ya | `--minsdk 28` |
| `timespec_get` → `clock_gettime` (API < 29) | `source/blender/blenlib/intern/uuid.cc` | ✅ terverifikasi | ya | `--minsdk <29` |

## Belum ada patch (kerja manual, lihat output script + `docs/ROADMAP.md`)

| Topik | File yang kemungkinan disentuh | Catatan |
|---|---|---|
| Resep deps armv7 (embree/OIDN/ISPC/USD) | `build_files/build_environment/cmake/*.cmake` | Harus iterasi lawan error build, tidak bisa ditebak dari jauh |
| `BLENDER_PLATFORM_ARM` untuk armv7 | `build_files/build_environment/cmake/options.cmake` | Cek apakah armv7 ikut memicu sse2neon |
| OpenJPH `aligned_alloc` (API ≤ 27) | `build_environment/cmake/openjph.cmake` | Atau cukup matikan OpenJPH |
| Runtime renderer selector | `release/android/.../Activity`, `GHOST_Context*.{cc,hh}` | Desain: `docs/RENDERERS.md` §3 |
| Bundling Turnip / Zink | build Mesa + packaging `jniLibs`/`assets` | `docs/RENDERERS.md` R2/R3 |
| Backend GLES | `source/blender/gpu/gles/**` (baru) | `docs/GLES-BACKEND.md` |

## Menambah patch baru

1. Ambil anchor **persis** dari source upstream (`docs/UPSTREAM-NOTES.md` punya perintah `grep`-nya).
2. Tambah satu fungsi rule di `scripts/apply-port-patches.py`, daftarkan di `main()`.
3. Set `required=True` kalau build **harus** gagal saat anchor hilang.
4. Uji `--dry-run` di checkout (atau pohon file tiruan).
5. Update tabel di atas + catat di `docs/UPSTREAM-NOTES.md` bagian mana yang disentuh.

## Catatan GPL

Patch di repo ini ikut lisensi **GPLv3** (modifikasi dari kode GPL). CI juga men-generate `porting-<abi>.patch` berisi diff lengkap tiap build — itu yang dipakai memenuhi kewajiban source code saat APK dirilis.
