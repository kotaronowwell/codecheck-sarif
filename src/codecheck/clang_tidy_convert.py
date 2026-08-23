#!/usr/bin/env python3
"""Convert clang-tidy's plain-text diagnostic output into a SARIF 2.1.0 run.

clang-tidy has no native SARIF exporter, so this parses its normal stdout
diagnostic lines:

    /path/to/file.cpp:12:5: warning: message text [check-name]

into one rule per distinct check-name, with a best-effort helpUri pointing
at the official clang-tidy documentation page for that check.
"""
import os
import re

from .sarif_common import build_sarif, make_result, make_rule, relative_uri

DIAG_RE = re.compile(
    r'^(?P<file>.+?):(?P<line>\d+):(?P<col>\d+):\s+'
    r'(?P<level>warning|error|note):\s+(?P<message>.*)$'
)
CHECK_RE = re.compile(r'^(?P<msg>.*)\s\[(?P<check>[\w][\w\-.,]*)\]$')
LEVEL_MAP = {"warning": "warning", "error": "error", "note": "note"}


def parse_diagnostics(lines):
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
    if not check or "-" not in check:
        return None
    group, name = check.split("-", 1)
    return f"https://clang.llvm.org/extra/clang-tidy/checks/{group}/{name}.html"


def diagnostics_to_sarif(diagnostics, root_abspath):
    rules = {}
    results = []
    for d in diagnostics:
        rel = relative_uri(d["file"], root_abspath)
        check_id = d["check"] or "clang-tidy/note"
        if check_id not in rules:
            rules[check_id] = make_rule(check_id, check_id, help_uri_for(d["check"]))
        results.append(
            make_result(check_id, LEVEL_MAP.get(d["level"], "warning"), d["message"], rel, d["line"], d["col"])
        )
    return build_sarif("clang-tidy", "https://clang.llvm.org/extra/clang-tidy/", list(rules.values()), results, root_abspath)


def convert(text_lines, root):
    root_abspath = os.path.abspath(root)
    diagnostics = parse_diagnostics(text_lines)
    return diagnostics_to_sarif(diagnostics, root_abspath), diagnostics
