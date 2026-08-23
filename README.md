# codecheck-sarif

Pluggable project-specific coding-rule checker for C/C++, emitting SARIF
(Static Analysis Results Interchange Format) 2.1.0.

It wraps three things behind one `codecheck` CLI:

- clang-tidy's text output, converted to SARIF (clang-tidy has no native
  SARIF exporter).
- Your own project-specific coding rules, written as small Python/libclang
  scripts dropped into a `rules.d/` directory -- no clang-tidy plugin
  build required.
- Merging with SARIF produced by any other tool (cppcheck, PVS-Studio,
  Coverity, a vendor analyzer, another codecheck run, ...) into one log.

Works on both C and C++ sources. See
[sarif-clang-tidy-demo](../sarif-clang-tidy-demo) for a full worked example
(a small C++ project with a `.clang-tidy` config, a `rules.d/` of sample
rules, and a plain-C fixture proving the C path).

## Setup

Install the toolchain (Debian/Ubuntu package names -- adjust for other
distros):

```bash
sudo apt-get update
sudo apt-get install -y \
    clang \
    clang-tidy \
    cmake \
    build-essential \
    python3 \
    python3-pip
```

Install this package itself. Do this with `pip`, not `sudo` -- it pulls in
the `libclang` wheel, which bundles its own `libclang.so`, so it's
self-contained and works even if it doesn't match the system clang/clang-tidy
version:

```bash
pip install -e .
# or, from another repo that depends on this one:
pip install "git+ssh://git@github.com:kotaronowwell/sarif-clang-tidy-demo.git@v0.1.0"
```

This installs the `codecheck` command (and `python -m codecheck` works
too, without a separate install, if you're running from a checkout).

Also install the **SARIF Viewer** VS Code extension
(`MS-SarifVSCode.sarif-viewer`) to browse `.sarif` output with clickable,
in-editor results instead of raw JSON.

## Usage

### 1. clang-tidy -> SARIF

```bash
cmake -S . -B build -DCMAKE_EXPORT_COMPILE_COMMANDS=ON
clang-tidy -p build src/main.cpp src/Calculator.cpp > clang-tidy-output.txt
codecheck convert-clang-tidy --root . clang-tidy-output.txt > clang-tidy.sarif
```

### 2. Your own coding rules (`rules.d/`)

Any `*.py` file in a rules directory (not starting with `_`) is
auto-discovered. It must define `RULE_ID`, `RULE_DESCRIPTION`, and a
`check(ctx, file_path)` function:

```python
# rules.d/no_goto.py
RULE_ID = "myproj/no-goto"
RULE_DESCRIPTION = "goto is banned; restructure with a loop instead"

def check(ctx, file_path):
    import clang.cindex as cindex
    findings = []
    tu = ctx.parse(file_path)          # compile flags + resource-dir resolved for you
    for node in tu.cursor.walk_preorder():
        if node.kind == cindex.CursorKind.GOTO_STMT and ctx.in_project(node):
            findings.append(ctx.result(file_path, node.location.line,
                                        node.location.column, "goto is banned"))
    return findings
```

Scaffold a new one from the annotated starter template:

```bash
codecheck init-rule rules.d/no_goto.py
```

Run every rule in the directory over your sources:

```bash
codecheck run-rules --root . --compile-commands build \
    --rules-dir rules.d src/main.cpp src/Calculator.cpp > rules.sarif
```

For a file with no `compile_commands.json` entry (a lone header, or a
project with no compilation database at all), pass `--lang c` or
`--lang c++` to pick the fallback parse args; the default is `c++`.

### 3. Merging with other tools' SARIF

```bash
codecheck merge clang-tidy.sarif rules.sarif ci-artifacts/ \
    --rebase /builds/ci/project=$(pwd) \
    --dedupe \
    --out results-combined.sarif
```

- Inputs can be individual `.sarif` files or directories (scanned
  recursively for `*.sarif`).
- A file that isn't valid SARIF is skipped with a warning instead of
  aborting the whole merge.
- `--rebase OLD=NEW` (repeatable) rewrites path prefixes in
  `artifactLocation.uri` -- the fix for "the other tool ran in a CI
  container with a different checkout path than mine."
- `--dedupe` drops exact-duplicate results across merged runs.

The result is one SARIF log with one `run` per tool, which GitHub Code
Scanning, VS Code's SARIF Viewer, and similar consumers all understand
natively.

## Library use

Everything above is also importable directly, for a build script that
wants tighter integration than shelling out to the CLI:

```python
from codecheck import plugin_runner, sarif_merge

sarif, plugins = plugin_runner.run(
    root=".", rules_dir="rules.d", files=["src/main.cpp"],
    compile_commands_dir="build", default_lang="c++",
)
```

## Versioning

Treat the `check(ctx, file_path)` plugin contract and the `codecheck`
CLI's subcommands/flags as a public interface: bump the major version on
any breaking change, since other repositories depend on this one directly
(via pip against a git tag, or a submodule). Don't move a consuming
project's pin to an untagged branch (`@main`) -- pin to a tag or commit so
a change here can't silently break someone else's CI.
