#!/usr/bin/env python3
"""Custom project rule implemented directly on libclang (no clang-tidy
plugin involved): every public method, constructor, and destructor must be
preceded by a Doxygen-style comment (///, //!, /** ... */, /*! ... */).

This is the kind of project-specific convention that's awkward to express
as a stock clang-tidy check, but simple with the Python bindings: walk each
class's member cursors, keep the ones with access_specifier == PUBLIC, and
read cursor.raw_comment. libclang already recognizes Doxygen-style comment
markers and associates the nearest one with the declaration -- an ordinary
"//" comment sitting right above a declaration does NOT count, which is
exactly the distinction a project style guide usually wants.

Usage:
    python3 tools/require_doxygen_for_public_methods.py \
        --root . --compile-commands build src/main.cpp src/Calculator.cpp src/Logger.cpp \
        > results-doxygen-check.sarif

Requires the 'libclang' pip package (bundles its own prebuilt shared
library, so it does not need to match the system clang/clang-tidy version):
    pip install libclang
"""
import argparse
import json
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sarif_common import build_sarif, make_result, make_rule, relative_uri

import clang.cindex as cindex


def _detect_resource_dir():
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
        path = out.stdout.strip()
        return path or None
    except (OSError, subprocess.CalledProcessError):
        return None


RESOURCE_DIR = _detect_resource_dir()

RULE_ID = "eudc/require-doxygen-public-methods"
RULE_DESC = "public methods, constructors, and destructors must have a Doxygen comment"
RULE_HELP_URI = "https://internal.wiki/rules/eudc-require-doxygen-public-methods"

TARGET_KINDS = {
    cindex.CursorKind.CXX_METHOD,
    cindex.CursorKind.CONSTRUCTOR,
    cindex.CursorKind.DESTRUCTOR,
}


def compile_args_for(compdb, file_path):
    """Look up this file's real compiler flags in compile_commands.json, or
    fall back to a plain C++17 parse for headers / files with no entry."""
    if compdb is not None:
        commands = compdb.getCompileCommands(file_path)
        if commands:
            args = list(commands[0].arguments)[1:]  # drop the compiler executable
            cleaned = []
            skip_next = False
            for a in args:
                if skip_next:
                    skip_next = False
                    continue
                if a in ("-o", "-c"):
                    skip_next = a == "-o"
                    continue
                if os.path.abspath(a) == file_path:
                    continue
                cleaned.append(a)
            args = cleaned
        else:
            args = ["-std=c++17", "-x", "c++"]
    else:
        args = ["-std=c++17", "-x", "c++"]

    if RESOURCE_DIR:
        args = args + ["-resource-dir", RESOURCE_DIR]
    return args


def check_file(index, compdb, file_path, root_abspath, seen, findings):
    args = compile_args_for(compdb, file_path)
    tu = index.parse(file_path, args=args)

    for diag in tu.diagnostics:
        if diag.severity >= cindex.Diagnostic.Error:
            print(f"# clang parse error in {file_path}: {diag}", file=sys.stderr)

    for node in tu.cursor.walk_preorder():
        if node.kind not in TARGET_KINDS:
            continue
        if node.access_specifier != cindex.AccessSpecifier.PUBLIC:
            continue
        if node != node.canonical:
            continue  # only the in-class declaration, not an out-of-line definition

        loc = node.location
        if loc.file is None:
            continue
        decl_path = os.path.abspath(loc.file.name)
        if not decl_path.startswith(root_abspath):
            continue  # skip system / third-party headers pulled in via #include

        if node.raw_comment:
            continue  # documented -- nothing to report

        key = (decl_path, loc.line, loc.column, node.spelling)
        if key in seen:
            continue
        seen.add(key)

        class_name = node.semantic_parent.spelling if node.semantic_parent else "?"
        findings.append(
            make_result(
                RULE_ID,
                "warning",
                f"public member '{class_name}::{node.spelling}' has no Doxygen comment",
                relative_uri(decl_path, root_abspath),
                loc.line,
                loc.column,
            )
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("files", nargs="+", help="C/C++ source files to check (headers are picked up via #include)")
    parser.add_argument("--root", default=".", help="project root used for relative artifact URIs")
    parser.add_argument("--compile-commands", default=None, help="directory containing compile_commands.json")
    args = parser.parse_args()

    root_abspath = os.path.abspath(args.root)

    compdb = None
    if args.compile_commands:
        try:
            compdb = cindex.CompilationDatabase.fromDirectory(args.compile_commands)
        except cindex.CompilationDatabaseError:
            print(f"# warning: no compile_commands.json found in {args.compile_commands}", file=sys.stderr)

    index = cindex.Index.create()
    seen = set()
    findings = []
    for f in args.files:
        check_file(index, compdb, os.path.abspath(f), root_abspath, seen, findings)

    rules = [make_rule(RULE_ID, RULE_DESC, RULE_HELP_URI)]
    sarif = build_sarif(
        "require-doxygen-public-methods.py",
        RULE_HELP_URI,
        rules,
        findings,
        root_abspath,
    )

    json.dump(sarif, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    print(f"# found {len(findings)} undocumented public member(s)", file=sys.stderr)


if __name__ == "__main__":
    main()
