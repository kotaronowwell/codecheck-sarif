#!/usr/bin/env python3
"""Convert clang-tidy's plain-text diagnostic output into a SARIF 2.1.0 log.

clang-tidy has no native SARIF exporter, so this script parses its normal
stdout diagnostic lines:

    /path/to/file.cpp:12:5: warning: message text [check-name]

and turns them into a SARIF run, one rule per distinct check-name, with a
best-effort helpUri pointing at the official clang-tidy documentation page
for that check.

Usage:
    clang-tidy -p build src/*.cpp 2> clang-tidy-output.txt
    python3 tools/clang_tidy_to_sarif.py --root . clang-tidy-output.txt > results.sarif

    # or piped directly:
    clang-tidy -p build src/*.cpp 2>&1 | python3 tools/clang_tidy_to_sarif.py --root . > results.sarif

Only the Python standard library is used, so no extra pip install is needed.
"""
import argparse
import json
import os
import re
import sys

# Matches: <file>:<line>:<col>: <level>: <message>
DIAG_RE = re.compile(
    r'^(?P<file>.+?):(?P<line>\d+):(?P<col>\d+):\s+'
    r'(?P<level>warning|error|note):\s+(?P<message>.*)$'
)
# Pulls a trailing " [check-name]" off the message, if present.
CHECK_RE = re.compile(r'^(?P<msg>.*)\s\[(?P<check>[\w][\w\-.,]*)\]$')

LEVEL_MAP = {"warning": "warning", "error": "error", "note": "note"}


def parse_diagnostics(lines):
    """Pull structured diagnostics out of clang-tidy's text output.

    Everything that isn't a "file:line:col: level: message" line (source
    snippets, caret/underline art, the "N warnings generated" banner, the
    "Suppressed N warnings" footer, etc.) is silently skipped.
    """
    diagnostics = []
    for raw_line in lines:
        m = DIAG_RE.match(raw_line.rstrip("\n"))
        if not m:
            continue
        message = m.group("message")
        check = None
        cm = CHECK_RE.match(message)
        if cm:
            message = cm.group("msg")
            check = cm.group("check")
        diagnostics.append(
            {
                "file": m.group("file"),
                "line": int(m.group("line")),
                "col": int(m.group("col")),
                "level": m.group("level"),
                "message": message,
                "check": check,
            }
        )
    return diagnostics


def help_uri_for(check):
    """Best-effort link to https://clang.llvm.org/extra/clang-tidy/checks/..."""
    if not check or "-" not in check:
        return None
    group, name = check.split("-", 1)
    return f"https://clang.llvm.org/extra/clang-tidy/checks/{group}/{name}.html"


def build_sarif(diagnostics, root_abspath):
    rules = {}
    results = []

    for d in diagnostics:
        rel = os.path.relpath(d["file"], root_abspath).replace(os.sep, "/")
        check_id = d["check"] or "clang-tidy/note"

        if check_id not in rules:
            rule = {"id": check_id, "shortDescription": {"text": check_id}}
            uri = help_uri_for(d["check"])
            if uri:
                rule["helpUri"] = uri
            rules[check_id] = rule

        results.append(
            {
                "ruleId": check_id,
                "level": LEVEL_MAP.get(d["level"], "warning"),
                "message": {"text": d["message"]},
                "locations": [
                    {
                        "physicalLocation": {
                            "artifactLocation": {"uri": rel, "uriBaseId": "SRCROOT"},
                            "region": {
                                "startLine": d["line"],
                                "startColumn": d["col"],
                            },
                        }
                    }
                ],
            }
        )

    return {
        "$schema": "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "clang-tidy",
                        "informationUri": "https://clang.llvm.org/extra/clang-tidy/",
                        "rules": sorted(rules.values(), key=lambda r: r["id"]),
                    }
                },
                "originalUriBaseIds": {
                    "SRCROOT": {"uri": "file://" + root_abspath.rstrip("/") + "/"}
                },
                "results": results,
            }
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "input",
        nargs="?",
        type=argparse.FileType("r"),
        default=sys.stdin,
        help="clang-tidy text output file (default: stdin)",
    )
    parser.add_argument(
        "--root",
        default=".",
        help="project root used to compute relative artifact URIs (default: current directory)",
    )
    args = parser.parse_args()

    root_abspath = os.path.abspath(args.root)
    diagnostics = parse_diagnostics(args.input.readlines())
    sarif = build_sarif(diagnostics, root_abspath)

    json.dump(sarif, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")

    unique_rules = len({d["check"] for d in diagnostics if d["check"]})
    print(
        f"# converted {len(diagnostics)} diagnostics across {unique_rules} rule(s)",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
