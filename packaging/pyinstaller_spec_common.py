"""
Shared helpers for PyInstaller `.spec` files in this repo.

PyInstaller evaluates `.spec` files as Python scripts with some injected globals.
Importing this module keeps the desktop and MCP specs aligned on tricky Windows
packaging rules (Torch + MSVC runtime collisions with Qt).
"""

from __future__ import annotations

import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_dynamic_libs, collect_submodules

Binaries = list[tuple[str, str]]


def repo_root(spec_globals: dict) -> Path:
    """
    Resolve the repository root directory.

    PyInstaller injects `SPECPATH` (folder containing the spec) when evaluating specs.
    """
    root = spec_globals.get("SPECPATH") or spec_globals.get("SPEC")
    if root:
        p = Path(str(root))
        return p.parent if p.is_file() else p
    return Path(os.getcwd())


def merge_hiddenimports(hiddenimports: list[str], names: tuple[str, ...]) -> None:
    for n in names:
        try:
            hiddenimports += collect_submodules(n)
        except Exception:
            pass


def merge_dynamic_libs(binaries: Binaries, names: tuple[str, ...]) -> None:
    for n in names:
        try:
            binaries += collect_dynamic_libs(n)
        except Exception:
            pass


def filter_qt6_bin_msvc_runtime_dupes(binaries: Binaries) -> Binaries:
    """
    Remove MSVC runtime DLLs shipped under `PyQt6/Qt6/bin`.

    PyQt6 wheels often include older `msvcp140.dll` / `vcruntime140*.dll` copies.
    When bundled next to newer copies from Torch/Sklearn/etc., Windows can bind
    the wrong CRT first and Torch's `c10.dll` initialization fails (WinError 1114).
    """
    if os.name != "nt":
        return binaries

    blocked = {
        "msvcp140.dll",
        "vcruntime140.dll",
        "vcruntime140_1.dll",
        "concrt140.dll",
        "msvcp140_1.dll",
        "msvcp140_2.dll",
        "msvcp140_atomic_wait.dll",
        "msvcp140_codecvt_ids.dll",
        "vccorlib140.dll",
        "vcomp140.dll",
    }

    def is_blocked(entry: tuple[str, str]) -> bool:
        src, dest = entry
        dest_l = dest.replace("/", "\\").lower()
        if "pyqt6\\qt6\\bin\\" not in dest_l:
            return False
        return os.path.basename(src).lower() in blocked

    return [e for e in binaries if not is_blocked(e)]


def torch_collect_all() -> tuple[list[tuple[str, str]], Binaries, list[str]]:
    from PyInstaller.utils.hooks import collect_all

    datas: list[tuple[str, str]] = []
    binaries: Binaries = []
    hiddenimports: list[str] = []
    try:
        d, b, h = collect_all("torch")
        datas += d
        binaries += b
        hiddenimports += h
    except Exception:
        pass
    return datas, binaries, hiddenimports
