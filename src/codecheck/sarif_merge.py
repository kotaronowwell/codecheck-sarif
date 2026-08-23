#!/usr/bin/env python3
"""Merge this tool's SARIF output with SARIF produced by ANY other tool
(cppcheck, PVS-Studio, Coverity, a vendor's static analyzer, a second
codecheck run, ...) into one multi-run log.

SARIF's top-level "runs" is an array precisely so this is a supported,
not a hacky, thing to do -- GitHub Code Scanning, VS Code's SARIF Viewer,
and friends all understand a log with several runs from different tools.

This merger is deliberately forgiving about *where* the SARIF comes from:

  * Inputs can be individual .sarif files, or directories -- a directory
    is scanned recursively for "*.sarif" files, so "point it at your CI
    artifacts folder" just works.
  * A file that isn't valid JSON, or is JSON but has no "runs" array, is
    skipped with a warning instead of aborting the whole merge -- one
    malformed upload from a flaky third-party tool shouldn't block the
    rest.
  * --rebase OLD=NEW rewrites path prefixes inside artifactLocation.uri
    and originalUriBaseIds.*.uri. This solves the single most common
    friction point when merging in someone else's SARIF: their tool ran
    in a different checkout path (a CI container, a colleague's machine)
    than the one you're merging on, so the paths otherwise don't line up
    with your working copy. Pass it as many times as you need.
  * --dedupe drops results that are byte-for-byte identical (same rule,
    file, line, column, and message) across merged runs. Off by default
    -- usually you *want* to see that two independent tools agree.
"""
import argparse
import glob as globmod
import json
import os
import sys

from .sarif_common import SARIF_SCHEMA


def find_sarif_files(inputs):
    files = []
    for item in inputs:
        if os.path.isdir(item):
            found = sorted(globmod.glob(os.path.join(item, "**", "*.sarif"), recursive=True))
            if not found:
                print(f"# warning: no *.sarif files found under directory {item}", file=sys.stderr)
            files.extend(found)
        else:
            files.append(item)
    return files


def load_runs(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            log = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"# warning: skipping {path}: not readable/valid JSON ({e})", file=sys.stderr)
        return []

    runs = log.get("runs")
    if not isinstance(runs, list):
        print(f"# warning: skipping {path}: no top-level 'runs' array (not a SARIF log?)", file=sys.stderr)
        return []
    return runs


def _rewrite_uri(uri, rebase_pairs):
    for old, new in rebase_pairs:
        if uri.startswith(old):
            return new + uri[len(old):]
    return uri


def rebase_run(run, rebase_pairs):
    if not rebase_pairs:
        return run
    for base in run.get("originalUriBaseIds", {}).values():
        if "uri" in base:
            base["uri"] = _rewrite_uri(base["uri"], rebase_pairs)
    for result in run.get("results", []):
        for loc in result.get("locations", []):
            art = loc.get("physicalLocation", {}).get("artifactLocation", {})
            if "uri" in art:
                art["uri"] = _rewrite_uri(art["uri"], rebase_pairs)
    return run


def _result_fingerprint(run_name, result):
    loc = (result.get("locations") or [{}])[0].get("physicalLocation", {})
    art = loc.get("artifactLocation", {})
    region = loc.get("region", {})
    return (
        result.get("ruleId"),
        art.get("uri"),
        region.get("startLine"),
        region.get("startColumn"),
        result.get("message", {}).get("text"),
    )


def dedupe_runs(runs):
    seen = set()
    for run in runs:
        kept = []
        for result in run.get("results", []):
            fp = _result_fingerprint(run.get("tool", {}).get("driver", {}).get("name"), result)
            if fp in seen:
                continue
            seen.add(fp)
            kept.append(result)
        run["results"] = kept
    return runs


def merge(inputs, rebase_pairs=None, dedupe=False):
    rebase_pairs = rebase_pairs or []
    runs = []
    for path in find_sarif_files(inputs):
        for run in load_runs(path):
            runs.append(rebase_run(run, rebase_pairs))
    if dedupe:
        runs = dedupe_runs(runs)
    return {"$schema": SARIF_SCHEMA, "version": "2.1.0", "runs": runs}


def _parse_rebase_arg(raw):
    if "=" not in raw:
        raise argparse.ArgumentTypeError(f"--rebase expects OLD=NEW, got: {raw!r}")
    old, new = raw.split("=", 1)
    return (old, new)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("inputs", nargs="+", help=".sarif files and/or directories to merge")
    ap.add_argument(
        "--rebase",
        action="append",
        type=_parse_rebase_arg,
        default=[],
        metavar="OLD=NEW",
        help="rewrite this path prefix in every merged artifactLocation.uri (repeatable)",
    )
    ap.add_argument("--dedupe", action="store_true", help="drop exact-duplicate results across merged runs")
    ap.add_argument("--out", default=None, help="write merged SARIF here instead of stdout")
    args = ap.parse_args()

    merged = merge(args.inputs, rebase_pairs=args.rebase, dedupe=args.dedupe)

    out = open(args.out, "w", encoding="utf-8") if args.out else sys.stdout
    try:
        json.dump(merged, out, ensure_ascii=False, indent=2)
        out.write("\n")
    finally:
        if args.out:
            out.close()

    total_results = sum(len(r.get("results", [])) for r in merged["runs"])
    print(f"# merged {len(merged['runs'])} run(s), {total_results} result(s) total", file=sys.stderr)


if __name__ == "__main__":
    main()
