"""Spawn detached framework generation jobs (survives CLI parent exit)."""

from __future__ import annotations

import logging
import subprocess
import sys
from typing import Optional

from .app_config import project_root

log = logging.getLogger(__name__)


def spawn_detached_framework_job(
    book_id: int,
    framework_id: int,
    name: str,
    max_chunks: Optional[int] = None,
) -> None:
    """
    Run framework generation in a separate process.

    Required when the caller returns immediately (``wait=False``); daemon threads
    are killed if the parent CLI process exits during interpreter shutdown.
    """
    root = project_root()
    cmd = [
        sys.executable,
        "-m",
        "src.cli.job_runner",
        "run",
        str(book_id),
        str(framework_id),
        name,
    ]
    if max_chunks is not None and max_chunks > 0:
        cmd.extend(["--max-chunks", str(max_chunks)])

    kwargs: dict = {
        "cwd": str(root),
        "stdin": subprocess.DEVNULL,
    }
    if sys.platform == "win32":
        # Detached so ``python -m src.cli frameworks generate`` can return while job runs.
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        kwargs["creationflags"] = flags
        kwargs["stdout"] = subprocess.DEVNULL
        kwargs["stderr"] = subprocess.DEVNULL
    else:
        kwargs["start_new_session"] = True
        kwargs["stdout"] = subprocess.DEVNULL
        kwargs["stderr"] = subprocess.DEVNULL

    log.info(
        "Spawning detached framework job book_id=%s framework_id=%s",
        book_id,
        framework_id,
    )
    subprocess.Popen(cmd, **kwargs)
