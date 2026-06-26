# -*- mode: python ; coding: utf-8 -*-
from __future__ import annotations

import importlib.util
import os
from pathlib import Path

from PyInstaller.building.api import COLLECT, EXE, PYZ
from PyInstaller.building.build_main import Analysis
from PyInstaller.utils.hooks import collect_all, collect_dynamic_libs

# NOTE: PyInstaller evaluates `.spec` files via `exec` — `__file__` is NOT guaranteed to exist.
def _spec_dir(ns: dict) -> Path:
    spec = ns.get("SPEC")
    if spec:
        return Path(str(spec)).resolve().parent
    sp = ns.get("SPECPATH")
    if sp:
        p = Path(str(sp))
        return p.parent if p.is_file() else p
    return Path(os.getcwd())


_ROOT_DIR = _spec_dir(globals())
_COMMON_PATH = _ROOT_DIR / "packaging" / "pyinstaller_spec_common.py"
_spec = importlib.util.spec_from_file_location("pta_pyinstaller_spec_common", str(_COMMON_PATH))
_common = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_common)

ROOT = _common.repo_root(globals())
ENTRY = ROOT / "mcp_entry.py"


def _merge_hiddenimports(names: tuple[str, ...]) -> None:
    _common.merge_hiddenimports(hiddenimports, names)


def _merge_dynamic_libs(names: tuple[str, ...]) -> None:
    _common.merge_dynamic_libs(binaries, names)


datas: list[tuple[str, str]] = []
binaries: list[tuple[str, str]] = []
hiddenimports: list[str] = []

# Torch (tooling can trigger embeddings)
_d, _b, _h = _common.torch_collect_all()
datas += _d
binaries += _b
hiddenimports += _h

_merge_hiddenimports(("sentence_transformers", "transformers", "tokenizers", "safetensors"))
_merge_dynamic_libs(("sentence_transformers", "transformers", "tokenizers", "safetensors"))

_merge_hiddenimports(("chromadb", "chromadb_rust_bindings"))
_merge_dynamic_libs(("chromadb", "chromadb_rust_bindings", "onnxruntime"))

_merge_dynamic_libs(("numpy",))

# Qt is required for PDF export (`src/ui/pdf_export.py` uses Qt print stack).
try:
    d, b, h = collect_all("PyQt6")
    datas += d
    binaries += b
    hiddenimports += h
except Exception:
    pass

_merge_hiddenimports(
    (
        "PyQt6.QtCore",
        "PyQt6.QtGui",
        "PyQt6.QtWidgets",
        "PyQt6.QtPrintSupport",
    )
)

try:
    binaries += collect_dynamic_libs("torch")
except Exception:
    pass

dotenv_path = ROOT / ".env"
if dotenv_path.is_file():
    datas += [(str(dotenv_path), ".")]

hiddenimports = sorted(
    set(
        hiddenimports
        + [
            # MCP server implementation
            "mcp",
            "mcp.server",
            "mcp.server.fastmcp",
            # DOCX export path
            "docx",
            "docx.enum.text",
            "docx.oxml",
            "docx.oxml.ns",
            "docx.shared",
        ]
    )
)

binaries = _common.filter_qt6_bin_msvc_runtime_dupes(binaries)

a = Analysis(
    [str(ENTRY)],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[str(ROOT / "packaging" / "hooks")],
    hooksconfig={},
    runtime_hooks=[str(ROOT / "packaging" / "runtime_hook_torch_dll_dirs.py")],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=None)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ProperThinkingAI_MCP",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    # MCP stdio transport requires real OS stdin/stdout handles. A windowed (`console=False`)
    # build makes `sys.stdin`/`sys.stdout` None and FastMCP crashes accessing `.buffer`.
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="ProperThinkingAI_MCP",
)
