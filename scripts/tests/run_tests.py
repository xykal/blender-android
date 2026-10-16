#!/usr/bin/env python3
"""
run_tests.py — uji perilaku `scripts/apply-port-patches.py` tanpa Blender.

Menguji:
  T1  arm64 / x64  → no-op (tidak menyentuh file)
  T2  --abi armv7  → semua rule wajib terterap, exit 0
  T3  idempoten    → jalan 2×, tidak ada duplikasi, exit 0
  T4  --minsdk 28  → ANDROID_PLATFORM turun + timespec_get diganti, exit 0
  T5  kombinasi armv7 + minsdk
  T6  anchor hilang → exit code 1 (CI berhenti, bukan lanjut diam-diam)
  T7  --dry-run    → tidak menulis apa pun
  T8  label versi Android benar (API 28 = Android 9)

Jalankan:  python3 scripts/tests/run_tests.py
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from make_fake_tree import make_tree  # noqa: E402

SCRIPT = HERE.parent / "apply-port-patches.py"

passed: list[str] = []
failed: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        passed.append(name)
        print(f"  \033[92mPASS\033[0m {name}")
    else:
        failed.append(name)
        print(f"  \033[91mFAIL\033[0m {name} {detail}")


def run(tree: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--blender", str(tree), *args],
        capture_output=True, text=True,
    )


def fresh(tmp: Path) -> Path:
    tree = tmp / "blender"
    if tree.exists():
        shutil.rmtree(tree)
    return make_tree(tree)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="blender-port-test-") as td:
        tmp = Path(td)

        print("\nT1: arm64 harus no-op")
        tree = fresh(tmp)
        before = {p: p.read_text() for p in tree.rglob("*") if p.is_file()}
        r = run(tree, "--abi", "arm64")
        after = {p: p.read_text() for p in tree.rglob("*") if p.is_file()}
        check("T1 exit 0", r.returncode == 0, f"exit={r.returncode}")
        check("T1 tidak mengubah file", before == after)

        print("\nT2: armv7 menerapkan semua rule wajib")
        tree = fresh(tmp)
        r = run(tree, "--abi", "armv7")
        check("T2 exit 0", r.returncode == 0, f"exit={r.returncode}")
        g = (tree / "GNUmakefile").read_text()
        check("T2 filter arch armv7", "filter arm64 x64 armv7" in g)
        check("T2 ABI armeabi-v7a", "ANDROID_ABI:=armeabi-v7a" in g)
        check("T2 goal armv7", "armv7: .FORCE" in g)
        check("T2 help text armv7", "Android ABI 'armeabi-v7a'" in g)
        u = (tree / "build_files/cmake/platform/platform_unix.cmake").read_text()
        check("T2 LIBDIR_ANDROID armv7", "lib/android_armv7" in u)
        t = (tree / "build_files/cmake/platform/platform_android_toolchain.cmake").read_text()
        check("T2 allowlist toolchain", "OR ANDROID_ABI STREQUAL \"armeabi-v7a\"" in t)
        check("T2 NEON aktif", "set(ANDROID_ARM_NEON ON)" in t)
        gc = (tree / "build_files/cmake/platform/platform_android_gradle.cmake").read_text()
        check("T2 versionCode digit 0", "set(_abi_prefix 0)" in gc)
        check("T2 arch triple sysroot", "arm-linux-androideabi" in gc)

        print("\nT3: idempoten (jalan kedua tidak menduplikasi)")
        r2 = run(tree, "--abi", "armv7")
        g2 = (tree / "GNUmakefile").read_text()
        check("T3 exit 0", r2.returncode == 0, f"exit={r2.returncode}")
        check("T3 tidak ada duplikasi goal", g2.count("armv7: .FORCE") == 1)
        check("T3 tidak ada duplikasi ABI", g2.count("ANDROID_ABI:=armeabi-v7a") == 1)
        check("T3 melaporkan skip", "sudah dipatch sebelumnya" in r2.stdout)

        print("\nT4: --minsdk 28")
        tree = fresh(tmp)
        r = run(tree, "--minsdk", "28")
        t = (tree / "build_files/cmake/platform/platform_android_toolchain.cmake").read_text()
        uuid = (tree / "source/blender/blenlib/intern/uuid.cc").read_text()
        check("T4 exit 0", r.returncode == 0, f"exit={r.returncode}")
        check("T4 ANDROID_PLATFORM android-28", "set(ANDROID_PLATFORM android-28)" in t)
        check("T4 android-29 tidak tersisa", "set(ANDROID_PLATFORM android-29)" not in t)
        check("T4 clock_gettime dipakai", "clock_gettime(CLOCK_REALTIME, &ts);" in uuid)
        check("T4 ifdef API 29 ada", "(__ANDROID_API__ < 29)" in uuid)
        check("T4 label versi benar (API 28 = Android 9)", "Android 9" in r.stdout, r.stdout[:200])

        print("\nT5: kombinasi armv7 + minsdk 28")
        tree = fresh(tmp)
        r = run(tree, "--abi", "armv7", "--minsdk", "28")
        check("T5 exit 0", r.returncode == 0, f"exit={r.returncode}")
        check("T5 armv7 terpatch",
              "ANDROID_ABI:=armeabi-v7a" in (tree / "GNUmakefile").read_text())
        check("T5 minsdk terpatch",
              "set(ANDROID_PLATFORM android-28)" in
              (tree / "build_files/cmake/platform/platform_android_toolchain.cmake").read_text())

        print("\nT6: anchor hilang → exit 1 (jangan lanjut diam-diam)")
        tree = fresh(tmp)
        g = tree / "GNUmakefile"
        g.write_text(g.read_text().replace("arm64: .FORCE", "arm64_v8a: .FORCE", 1))
        r = run(tree, "--abi", "armv7")
        check("T6 exit 1", r.returncode == 1, f"exit={r.returncode}")
        check("T6 pesan jelas", "GAGAL" in r.stdout and "anchor" in r.stdout)

        print("\nT7: --dry-run tidak menulis apa pun")
        tree = fresh(tmp)
        before = {p: p.read_text() for p in tree.rglob("*") if p.is_file()}
        r = run(tree, "--abi", "armv7", "--minsdk", "28", "--dry-run")
        after = {p: p.read_text() for p in tree.rglob("*") if p.is_file()}
        check("T7 exit 0", r.returncode == 0, f"exit={r.returncode}")
        check("T7 tidak ada perubahan file", before == after)

        print("\nT8: bukan checkout Blender → exit 2")
        empty = tmp / "kosong"
        empty.mkdir(exist_ok=True)
        r = run(empty, "--abi", "armv7")
        check("T8 exit 2", r.returncode == 2, f"exit={r.returncode}")

        print("\nT9: semua file .yml repo valid (GitHub Actions menolak YAML rusak)")
        try:
            import yaml  # noqa: PLC0415
        except ImportError:
            check("T9 pyyaml tersedia", False, "jalankan: pip install pyyaml")
        else:
            repo_root = HERE.parent.parent
            for path in sorted(repo_root.rglob("*.yml")):
                try:
                    yaml.safe_load(path.read_text())
                    check(f"T9 {path.relative_to(repo_root)}", True)
                except Exception as exc:  # noqa: BLE001
                    check(f"T9 {path.relative_to(repo_root)}", False, str(exc).splitlines()[0])

        print("\nT10: armv7 melewati deps berat (profil Lite)")
        tree = fresh(tmp)
        r = run(tree, "--abi", "armv7")
        deps = (tree / "build_files/build_environment/CMakeLists.txt").read_text()
        check("T10 exit 0", r.returncode == 0, f"exit={r.returncode}")
        check("T10 guard variable dibuat", "BLENDER_ANDROID_ARMV7_LITE ON" in deps)
        for lib in ("embree", "openimagedenoise", "usd", "materialx", "openvdb", "alembic"):
            check(f"T10 {lib} dibungkus guard",
                  f"# PORT PATCH armv7-lite: {lib}" in deps,
                  f"marker {lib} tidak ada")
        check("T10 jumlah endif() wajar", deps.count("if(NOT BLENDER_ANDROID_ARMV7_LITE)") == 6,
              f"count={deps.count('if(NOT BLENDER_ANDROID_ARMV7_LITE)')}")
        # library penting yang TIDAK boleh dilewati
        for lib in ("python", "openimageio", "openexr", "tbb"):
            check(f"T10 {lib} tetap dibangun",
                  f"# PORT PATCH armv7-lite: {lib}" not in deps)

        print("\nT11: arm64 tidak menyentuh deps sama sekali")
        tree = fresh(tmp)
        deps_before = (tree / "build_files/build_environment/CMakeLists.txt").read_text()
        run(tree, "--abi", "arm64")
        deps_after = (tree / "build_files/build_environment/CMakeLists.txt").read_text()
        check("T11 deps tidak berubah", deps_before == deps_after)
        check("T11 tidak ada marker armv7", "PORT PATCH armv7-lite" not in deps_after)

    print("\n" + "=" * 60)
    print(f"Hasil: {len(passed)} pass, {len(failed)} fail")
    for name in failed:
        print(f"  \033[91m✗\033[0m {name}")
    print("=" * 60)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
