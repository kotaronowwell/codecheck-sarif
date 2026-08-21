#!/usr/bin/env python3
"""Merge several SARIF 2.1.0 logs (one per tool) into a single log with
multiple runs. SARIF's top-level 'runs' is an array precisely so a
clang-tidy run and a custom libclang-checker run can live side by side in
one file -- most viewers (GitHub Code Scanning, VS Code's SARIF Viewer,
etc.) handle multi-run logs natively.

Usage:
    python3 tools/merge_sarif.py results.sarif results-doxygen-check.sarif \
        > results-combined.sarif
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sarif_common import SARIF_SCHEMA


def main():
    if len(sys.argv) < 2:
        print(f"usage: {sys.argv[0]} <sarif-file> [<sarif-file> ...]", file=sys.stderr)
        sys.exit(1)

    runs = []
    for path in sys.argv[1:]:
        with open(path, "r", encoding="utf-8") as f:
            log = json.load(f)
        runs.extend(log.get("runs", []))

    merged = {"$schema": SARIF_SCHEMA, "version": "2.1.0", "runs": runs}
    json.dump(merged, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    print(f"# merged {len(sys.argv) - 1} file(s) into {len(runs)} run(s)", file=sys.stderr)


if __name__ == "__main__":
    main()
