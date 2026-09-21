#!/usr/bin/env python3
"""Check local runtime requirements without contacting Douyin."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sys


def build_report() -> dict:
    library = Path.home() / "Desktop" / "抖音无水印视频"
    python_ok = sys.version_info >= (3, 9)
    curl = shutil.which("curl")
    ffprobe = shutil.which("ffprobe")
    return {
        "status": "ok" if python_ok and curl else "needs_attention",
        "python": {
            "version": ".".join(str(part) for part in sys.version_info[:3]),
            "minimum": "3.9",
            "ok": python_ok,
        },
        "curl": {"path": curl, "required": True, "ok": bool(curl)},
        "ffprobe": {
            "path": ffprobe,
            "required": False,
            "ok": bool(ffprobe),
            "fallback": "mp4_header_only" if not ffprobe else None,
        },
        "default_output": str(library),
        "default_output_exists": library.exists(),
        "network_checked": False,
        "paid_api_required": False,
    }


def format_text(report: dict) -> str:
    lines = [
        f"status: {report['status']}",
        f"python: {report['python']['version']} ({'ok' if report['python']['ok'] else 'too old'})",
        f"curl: {report['curl']['path'] or 'missing'}",
        f"ffprobe: {report['ffprobe']['path'] or 'missing; MP4 header fallback will be used'}",
        f"default output: {report['default_output']}",
        "network checked: no",
        "paid API required: no",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Check the local downloader environment.")
    parser.add_argument("--format", choices=("json", "text"), default="json")
    args = parser.parse_args()
    report = build_report()
    if args.format == "text":
        print(format_text(report))
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
