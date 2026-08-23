#!/usr/bin/env python3
"""Small shared helpers for building SARIF 2.1.0 logs.

Both clang_tidy_to_sarif.py (wraps clang-tidy's text output) and
require_doxygen_for_public_methods.py (a from-scratch libclang checker)
import this module, so every tool in this project emits results in the
exact same shape and can be merged into one SARIF log later with
merge_sarif.py.
"""
import os
import shutil
import subprocess

SARIF_SCHEMA = (
    "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/"
    "Schemata/sarif-schema-2.1.0.json"
)


def make_rule(rule_id, description, help_uri=None):
    rule = {"id": rule_id, "shortDescription": {"text": description}}
    if help_uri:
        rule["helpUri"] = help_uri
    return rule


def make_result(rule_id, level, message, uri, line, col, end_line=None, end_col=None):
    region = {"startLine": line, "startColumn": col}
    if end_line is not None:
        region["endLine"] = end_line
    if end_col is not None:
        region["endColumn"] = end_col
    return {
        "ruleId": rule_id,
        "level": level,
        "message": {"text": message},
        "locations": [
            {
                "physicalLocation": {
                    "artifactLocation": {"uri": uri, "uriBaseId": "SRCROOT"},
                    "region": region,
                }
            }
        ],
    }


def relative_uri(abs_path, root_abspath):
    return os.path.relpath(abs_path, root_abspath).replace(os.sep, "/")


def detect_resource_dir():
    """The pip 'libclang' wheel ships only libclang.so -- no bundled
    'lib/clang/<ver>/include' resource directory with builtin headers like
    stddef.h. Point it at the system clang's resource dir (if one is
    installed) so parsing doesn't fail on '#include <stddef.h>' etc."""
    clang_bin = shutil.which("clang") or shutil.which("clang-18") or shutil.which("clang-tidy")
    if not clang_bin:
        return None
    try:
        out = subprocess.run(
            [clang_bin, "-print-resource-dir"], capture_output=True, text=True, check=True
        )
        return out.stdout.strip() or None
    except (OSError, subprocess.CalledProcessError):
        return None


def default_clang_args(std="c++17", extra=None):
    """A reasonable default arg list for Index.parse() on a standalone
    file that isn't in any compile_commands.json (a snippet, a header)."""
    args = [f"-std={std}"]
    resource_dir = detect_resource_dir()
    if resource_dir:
        args += ["-resource-dir", resource_dir]
    if extra:
        args += list(extra)
    return args


def build_sarif(tool_name, tool_info_uri, rules, results, root_abspath):
    """Wrap one tool's rules+results into a single-run SARIF log."""
    driver = {"name": tool_name, "rules": sorted(rules, key=lambda r: r["id"])}
    if tool_info_uri:
        driver["informationUri"] = tool_info_uri
    return {
        "$schema": SARIF_SCHEMA,
        "version": "2.1.0",
        "runs": [
            {
                "tool": {"driver": driver},
                "originalUriBaseIds": {
                    "SRCROOT": {"uri": "file://" + root_abspath.rstrip("/") + "/"}
                },
                "results": results,
            }
        ],
    }
