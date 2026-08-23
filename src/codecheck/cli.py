#!/usr/bin/env python3
"""codecheck: pluggable project-specific coding-rule checker for C/C++,
emitting SARIF 2.1.0.

Subcommands:
    convert-clang-tidy   turn clang-tidy's text output into a SARIF run
    run-rules            run every plugin in a rules directory, emit SARIF
    merge                combine any number of SARIF logs into one
    init-rule             copy the starter rule template to a new file

A typical CI step for a project (C or C++, any build system that can
produce compile_commands.json):

    clang-tidy -p build src/*.c > clang-tidy-output.txt
    codecheck convert-clang-tidy --root . clang-tidy-output.txt > ct.sarif
    codecheck run-rules --root . --compile-commands build \\
        --rules-dir tools/rules.d --lang c src/*.c > rules.sarif
    codecheck merge ct.sarif rules.sarif path/to/external-tool-results/ \\
        --rebase /builds/ci/project=$(pwd) \\
        --out results-combined.sarif
"""
import argparse
import json
import os
import sys

from . import clang_tidy_convert, plugin_runner, sarif_merge


def _cmd_convert_clang_tidy(args):
    root_abspath = os.path.abspath(args.root)
    lines = args.input.readlines()
    sarif, diagnostics = clang_tidy_convert.convert(lines, root_abspath)
    _dump(sarif, args.out)
    unique_rules = len({d["check"] for d in diagnostics if d["check"]})
    print(f"# converted {len(diagnostics)} diagnostics across {unique_rules} rule(s)", file=sys.stderr)


def _cmd_run_rules(args):
    try:
        sarif, plugins = plugin_runner.run(
            root=args.root,
            rules_dir=args.rules_dir,
            files=args.files,
            compile_commands_dir=args.compile_commands,
            default_lang=args.lang,
            tool_name=args.tool_name,
        )
    except plugin_runner.PluginError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)

    _dump(sarif, args.out)
    total = len(sarif["runs"][0]["results"])
    names = ", ".join(m.RULE_ID for m in plugins)
    print(f"# ran {len(plugins)} rule plugin(s) [{names}] over {len(args.files)} file(s): {total} finding(s)", file=sys.stderr)


def _cmd_merge(args):
    rebase_pairs = []
    for raw in args.rebase:
        if "=" not in raw:
            print(f"error: --rebase expects OLD=NEW, got: {raw!r}", file=sys.stderr)
            sys.exit(1)
        old, new = raw.split("=", 1)
        rebase_pairs.append((old, new))
    merged = sarif_merge.merge(args.inputs, rebase_pairs=rebase_pairs, dedupe=args.dedupe)
    _dump(merged, args.out)
    total = sum(len(r.get("results", [])) for r in merged["runs"])
    print(f"# merged {len(merged['runs'])} run(s), {total} result(s) total", file=sys.stderr)


def _cmd_init_rule(args):
    import shutil

    template = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates", "rule_template.py")
    dest = args.dest
    if os.path.exists(dest) and not args.force:
        print(f"error: {dest} already exists (use --force to overwrite)", file=sys.stderr)
        sys.exit(1)
    os.makedirs(os.path.dirname(os.path.abspath(dest)) or ".", exist_ok=True)
    shutil.copy(template, dest)
    print(f"# wrote {dest} -- edit RULE_ID / RULE_DESCRIPTION / check() and drop it in your rules directory")


def _dump(obj, out_path):
    out = open(out_path, "w", encoding="utf-8") if out_path else sys.stdout
    try:
        json.dump(obj, out, ensure_ascii=False, indent=2)
        out.write("\n")
    finally:
        if out_path:
            out.close()


def build_parser():
    ap = argparse.ArgumentParser(prog="codecheck", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)

    p = sub.add_parser("convert-clang-tidy", help="convert clang-tidy text output to SARIF")
    p.add_argument("input", nargs="?", type=argparse.FileType("r"), default=sys.stdin)
    p.add_argument("--root", default=".")
    p.add_argument("--out", default=None)
    p.set_defaults(func=_cmd_convert_clang_tidy)

    p = sub.add_parser("run-rules", help="run rules-directory plugins over the given files")
    p.add_argument("files", nargs="+", help="C/C++ source files to check")
    p.add_argument("--root", default=".")
    p.add_argument("--rules-dir", required=True, help="directory of *.py rule plugins")
    p.add_argument("--compile-commands", default=None, help="directory containing compile_commands.json")
    p.add_argument("--lang", choices=["c", "c++"], default="c++", help="fallback language for files with no compdb entry (e.g. lone headers)")
    p.add_argument("--tool-name", default="project-custom-rules", help="SARIF tool.driver.name for this run")
    p.add_argument("--out", default=None)
    p.set_defaults(func=_cmd_run_rules)

    p = sub.add_parser("merge", help="merge SARIF logs (yours and/or any external tool's) into one")
    p.add_argument("inputs", nargs="+", help=".sarif files and/or directories")
    p.add_argument("--rebase", action="append", default=[], metavar="OLD=NEW", help="rewrite this path prefix (repeatable)")
    p.add_argument("--dedupe", action="store_true")
    p.add_argument("--out", default=None)
    p.set_defaults(func=_cmd_merge)

    p = sub.add_parser("init-rule", help="copy the starter rule template to a new file")
    p.add_argument("dest", help="destination path, e.g. tools/rules.d/no_goto.py")
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=_cmd_init_rule)

    return ap


def main(argv=None):
    args = build_parser().parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
