"""
Detached framework generation worker.

Started by BookManager when ``wait=False`` so the job survives parent CLI exit.
Do not invoke directly unless debugging.
"""

from __future__ import annotations

import argparse
import logging
import sys


def _bootstrap() -> None:
    from dotenv import load_dotenv

    from src.core.app_config import load_json_into_env

    load_dotenv()
    load_json_into_env()
    logging.basicConfig(
        level=logging.INFO,
        format="%(name)s %(levelname)s: %(message)s",
        stream=sys.stderr,
    )


def _cmd_run(args: argparse.Namespace) -> int:
    _bootstrap()
    from src.core.book_manager import BookManager

    mc = args.max_chunks if args.max_chunks and args.max_chunks > 0 else None
    bm = BookManager()
    try:
        bm._execute_framework_generation_job(
            args.book_id,
            args.framework_id,
            args.name,
            mc,
            None,
        )
    except Exception:
        logging.getLogger(__name__).exception(
            "Detached framework job failed (framework_id=%s)", args.framework_id
        )
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m src.cli.job_runner")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("run", help="Run one framework generation job")
    p.add_argument("book_id", type=int)
    p.add_argument("framework_id", type=int)
    p.add_argument("name")
    p.add_argument("--max-chunks", type=int, default=0)
    p.set_defaults(func=_cmd_run)
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
