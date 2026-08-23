#!/usr/bin/env python3
"""Plugin engine for project-specific coding-rule scripts.

THE PLUGIN CONTRACT
--------------------
Any *.py file dropped into a "rules directory" (not starting with '_') is
auto-discovered as a rule plugin. It must define:

    RULE_ID           str   -- stable SARIF rule id, e.g. "myproj/no-goto"
    RULE_DESCRIPTION  str   -- one-line human description
    RULE_HELP_URI     str   -- optional: link to your team's wiki page

    def check(ctx, file_path):
        '''Return a list of ctx.result(...) dicts for violations found in
        file_path (an absolute path). Return [] / None if the file is
        clean. Exceptions are caught per-file and logged to stderr --
        one broken plugin never aborts the whole run.'''
        ...

`ctx` (a CheckContext) hides all the libclang boilerplate: it already knows
this project's compile_commands.json (if any), how to fall back to a
sensible default when a file isn't in it, and which resource-dir fixes
"stddef.h not found" errors from the pip 'libclang' wheel. A minimal
plugin is just:

    RULE_ID = "myproj/no-goto"
    RULE_DESCRIPTION = "goto is banned; restructure with a loop instead"

    def check(ctx, file_path):
        findings = []
        tu = ctx.parse(file_path)
        for node in tu.cursor.walk_preorder():
            if node.kind.name == "GOTO_STMT" and ctx.in_project(node):
                findings.append(ctx.result(file_path, node.location.line,
                                            node.location.column,
                                            "goto is banned"))
        return findings

See templates/rule_template.py (shipped with this package -- `codecheck
init-rule` copies it for you) for a fuller, more heavily annotated starter.
"""
import glob
import importlib.util
import os
import sys

from .sarif_common import build_sarif, make_result, make_rule, relative_uri, default_clang_args

import clang.cindex as cindex

REQUIRED_ATTRS = ("RULE_ID", "RULE_DESCRIPTION", "check")

LANG_DEFAULTS = {
    "c": ("c11", "c"),
    "c++": ("c++17", "c++"),
}
C_EXTENSIONS = {".c"}
CXX_EXTENSIONS = {".cpp", ".cc", ".cxx", ".c++", ".hpp", ".hh", ".hxx"}


class PluginError(Exception):
    """A rule plugin file is missing something the contract requires."""


def _clean_compdb_args(raw_args, file_abspath):
    """Turn a compile_commands.json entry's argv into flags libclang can
    take directly: drop the compiler executable, -o/-c and their values,
    and the source file path itself (Index.parse() takes that separately).
    Everything else -- -std, -I, -D, -target, -mcpu, sysroot flags, all of
    it -- passes through untouched, so a real embedded cross-compiler
    invocation (arm-none-eabi-gcc, etc.) is respected as-is."""
    args = list(raw_args)[1:]  # drop argv[0], the compiler executable
    cleaned = []
    skip_next = False
    for a in args:
        if skip_next:
            skip_next = False
            continue
        if a in ("-o", "-c"):
            skip_next = a == "-o"
            continue
        if os.path.isabs(a) and os.path.abspath(a) == file_abspath:
            continue
        cleaned.append(a)
    return cleaned


def guess_fallback_args(file_abspath, default_lang):
    """Best-effort parse args for a file with no compile_commands.json
    entry (a lone header, or a project with no compdb at all)."""
    ext = os.path.splitext(file_abspath)[1].lower()
    if ext in C_EXTENSIONS:
        lang = "c"
    elif ext in CXX_EXTENSIONS:
        lang = "c++"
    else:
        lang = default_lang  # ambiguous (.h) or unknown extension
    std, xlang = LANG_DEFAULTS[lang]
    return default_clang_args(std=std, extra=["-x", xlang])


class CheckContext:
    """Passed into every plugin's check(ctx, file_path). Owns the libclang
    Index (reused across files/plugins for speed) and knows how to resolve
    compile args for a given file, C or C++, compdb or not."""

    def __init__(self, root_abspath, compdb=None, default_lang="c++"):
        self.root = root_abspath
        self.compdb = compdb
        self.default_lang = default_lang
        self._index = cindex.Index.create()
        self.current_rule_id = None  # set by run_plugins() before each plugin runs

    def compile_args(self, file_path):
        file_abspath = os.path.abspath(file_path)
        if self.compdb is not None:
            commands = self.compdb.getCompileCommands(file_abspath)
            if commands:
                return _clean_compdb_args(commands[0].arguments, file_abspath)
        return guess_fallback_args(file_abspath, self.default_lang)

    def parse(self, file_path):
        file_abspath = os.path.abspath(file_path)
        return self._index.parse(file_abspath, args=self.compile_args(file_abspath))

    def in_project(self, cursor_or_location):
        """True if this AST node's location is inside --root (i.e. not a
        system header or unrelated third-party file pulled in via #include)."""
        loc = getattr(cursor_or_location, "location", cursor_or_location)
        if loc is None or loc.file is None:
            return False
        return os.path.abspath(loc.file.name).startswith(self.root)

    def relative_uri(self, file_path):
        return relative_uri(os.path.abspath(file_path), self.root)

    def result(self, file_path, line, col, message, level="warning", end_line=None, end_col=None):
        if self.current_rule_id is None:
            raise RuntimeError(
                "ctx.result() was called outside of a plugin's check() -- this is a codecheck bug"
            )
        return make_result(
            self.current_rule_id, level, message, self.relative_uri(file_path), line, col, end_line, end_col
        )


def discover_plugins(rules_dir):
    if not os.path.isdir(rules_dir):
        raise PluginError(f"rules directory not found: {rules_dir}")

    plugins = []
    for path in sorted(glob.glob(os.path.join(rules_dir, "*.py"))):
        name = os.path.basename(path)
        if name.startswith("_"):
            continue  # convention: leading underscore = template/helper, not a rule

        mod_name = f"codecheck_rule_{os.path.splitext(name)[0]}"
        spec = importlib.util.spec_from_file_location(mod_name, path)
        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
        except Exception as e:
            raise PluginError(f"{path}: failed to import: {e}") from e

        missing = [a for a in REQUIRED_ATTRS if not hasattr(module, a)]
        if missing:
            raise PluginError(f"{path}: missing required attribute(s): {missing}")

        module._codecheck_source_path = path
        plugins.append(module)
    return plugins


def run_plugins(plugins, files, ctx):
    rules = []
    results = []
    abs_files = [os.path.abspath(f) for f in files]

    for mod in plugins:
        rules.append(make_rule(mod.RULE_ID, mod.RULE_DESCRIPTION, getattr(mod, "RULE_HELP_URI", None)))
        ctx.current_rule_id = mod.RULE_ID
        for f in abs_files:
            try:
                found = mod.check(ctx, f) or []
            except Exception as e:
                print(f"# [{mod.RULE_ID}] raised on {f}: {e!r}", file=sys.stderr)
                continue
            results.extend(found)

    ctx.current_rule_id = None
    return rules, results


def run(root, rules_dir, files, compile_commands_dir=None, default_lang="c++", tool_name="project-custom-rules"):
    """One-shot convenience: discover plugins, run them over `files`,
    return a ready-to-dump SARIF log. Importable directly, so a bigger
    Python build script can call this instead of shelling out to the CLI."""
    root_abspath = os.path.abspath(root)

    compdb = None
    if compile_commands_dir:
        try:
            compdb = cindex.CompilationDatabase.fromDirectory(compile_commands_dir)
        except cindex.CompilationDatabaseError:
            print(f"# warning: no compile_commands.json found in {compile_commands_dir}", file=sys.stderr)

    plugins = discover_plugins(rules_dir)
    ctx = CheckContext(root_abspath, compdb, default_lang)
    rules, results = run_plugins(plugins, files, ctx)
    sarif = build_sarif(tool_name, None, rules, results, root_abspath)
    return sarif, plugins
