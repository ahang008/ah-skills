#!/usr/bin/env python3
"""Validate a single Gemini answer and extract its complete script, not its facts."""
import argparse
import json
from pathlib import Path
import re
import sys


def extract_script(text, task_id, revision, min_chars=1, max_chars=None):
    if not re.fullmatch(r"[A-Za-z0-9_-]+", task_id):
        raise ValueError("invalid task_id")
    if revision < 1 or min_chars < 1 or (max_chars is not None and max_chars < min_chars):
        raise ValueError("invalid revision or character limits")
    text = text.strip()
    suffix = f"task_id={task_id} revision={revision}"
    done = f"REPLY_DONE {suffix}"
    if not text.endswith(done):
        raise ValueError("missing or mismatched final completion marker")
    markers = re.findall(r"SCRIPT_BEGIN|SCRIPT_END|REPLY_DONE|NEEDS_INPUT", text)
    if "NEEDS_INPUT" in markers:
        raise ValueError("Gemini requests missing input; no complete script")
    if markers != ["SCRIPT_BEGIN", "SCRIPT_END", "REPLY_DONE"]:
        raise ValueError("duplicate, missing, or out-of-order markers")
    begin = f"SCRIPT_BEGIN {suffix}"
    end = f"SCRIPT_END {suffix}"
    lines = text.splitlines()
    if lines[0] != begin or end not in lines or lines[-1] != done:
        raise ValueError("mismatched task/revision or invalid boundary")
    end_index = lines.index(end)
    script = "\n".join(lines[1:end_index]).strip()
    if not script:
        raise ValueError("empty script")
    if re.search(r"SCRIPT_BEGIN|SCRIPT_END|REPLY_DONE|NEEDS_INPUT", script):
        raise ValueError("protocol text leaked into script")
    count = len(re.sub(r"\s+", "", script))
    if count < min_chars or (max_chars is not None and count > max_chars):
        raise ValueError(f"script length {count} is outside requested bounds")
    return script, count


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--response", type=Path, required=True)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--revision", type=int, required=True)
    parser.add_argument("--min-chars", type=int, default=1)
    parser.add_argument("--max-chars", type=int)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        script, count = extract_script(args.response.read_text(encoding="utf-8"), args.task_id,
                                       args.revision, args.min_chars, args.max_chars)
        if args.out.exists() or args.out.is_symlink():
            raise ValueError("output exists; use a new revision path")
        if not args.out.parent.is_dir():
            raise ValueError("output parent does not exist")
        with args.out.open("x", encoding="utf-8") as output:
            output.write(script + "\n")
    except (OSError, ValueError) as error:
        print(json.dumps({"status": "FAIL", "error": str(error)}, ensure_ascii=False))
        return 1
    print(json.dumps({"status": "PASS", "chars_without_whitespace": count,
                      "facts_reviewed": False, "model_verified": False}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
