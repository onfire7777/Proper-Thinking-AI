"""
PyInstaller runtime hook (runs very early, before user code imports).

Goal: make Windows DLL resolution for PyTorch as close as possible to a normal
`python main.py` launch when running a frozen app from `_internal/`.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _ensure_standard_streams() -> None:
    """
    In windowed PyInstaller apps (`console=False`), stdio streams can be `None`.
    Some ML dependencies (e.g. tqdm via transformers/sentence-transformers) call
    `.isatty()` on stderr/stdout and crash if the stream object is missing.
    """
    if getattr(sys, "stderr", None) is None:
        try:
            sys.stderr = open(os.devnull, "w", encoding="utf-8", buffering=1)
        except Exception:
            pass
    # IMPORTANT:
    # - For MCP stdio servers, stdout must remain a real pipe to the host process.
    # - In windowed GUI apps, stdin/stdout are typically both None; routing stdout
    #   to devnull is OK there, but would break MCP if applied blindly.
    if getattr(sys, "stdout", None) is None and getattr(sys, "stdin", None) is None:
        try:
            sys.stdout = open(os.devnull, "w", encoding="utf-8", buffering=1)
        except Exception:
            pass


def _candidate_torch_lib_dirs() -> list[Path]:
    roots: list[Path] = []

    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        roots.append(Path(meipass))

    # onedir fallback
    roots.append(Path(sys.executable).resolve().parent)

    out: list[Path] = []
    for r in roots:
        p = r / "torch" / "lib"
        if p.is_dir():
            out.append(p)
    # de-dupe while preserving order
    seen: set[str] = set()
    uniq: list[Path] = []
    for p in out:
        key = str(p.resolve())
        if key in seen:
            continue
        seen.add(key)
        uniq.append(p)
    return uniq


if sys.platform == "win32":
    _ensure_standard_streams()

    # Keep behavior aligned with `main.py` (helps some OpenMP duplicate scenarios).
    os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
    os.environ.setdefault("TQDM_DISABLE", "1")
    os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")

    for lib in _candidate_torch_lib_dirs():
        try:
            os.add_dll_directory(str(lib))
        except Exception:
            # Extremely old Python builds / unusual environments
            pass

        # Some native stacks still consult PATH during probing.
        try:
            os.environ["PATH"] = str(lib) + os.pathsep + os.environ.get("PATH", "")
        except Exception:
            pass
