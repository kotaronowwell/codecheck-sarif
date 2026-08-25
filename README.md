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

Works on both C and C++ sources, with or without a `compile_commands.json`.

## Using this in your project

This repo is meant to be depended on, not copy-pasted into every project
that wants it. Pick whichever of the two fits your project's setup.

### Option A: git submodule (recommended)

Vendor the source in under a `vendor/` (or similar) directory. This is
the right call when your project already tracks its build tooling in-repo,
when your CI has no access to a package registry, or when you just want
the exact source you're running to be reviewable in your own tree.

```bash
git submodule add https://github.com/kotaronowwell/codecheck-sarif.git vendor/codecheck-sarif
git commit -m "Add codecheck-sarif as a submodule"
```

Then install it as an editable package from that path:

```bash
pip install -e vendor/codecheck-sarif
```

Anyone else cloning your project needs one extra step to pull the
submodule in:

```bash
git clone --recurse-submodules <your-repo-url>
# or, if already cloned:
git submodule update --init --recursive
```

To bump the vendored version later:

```bash
cd vendor/codecheck-sarif
git fetch origin
git checkout v0.1.0        # a tag, not a branch -- see Versioning below
cd ../..
git add vendor/codecheck-sarif
git commit -m "chore: bump vendored codecheck-sarif to v0.1.0"
```

See [sarif-clang-tidy-demo](https://github.com/kotaronowwell/sarif-clang-tidy-demo)
for a full worked example of a project set up exactly this way.

### Option B: pip install directly from a git tag

If your project already manages its Python tooling with `pip`/`requirements.txt`
and doesn't want a submodule, install straight from a tagged commit:

```bash
pip install "git+https://github.com/kotaronowwell/codecheck-sarif.git@v0.1.0"
```

Or in `requirements.txt`:

```
codecheck-sarif @ git+https://github.com/kotaronowwell/codecheck-sarif.git@v0.1.0
```

Note the URL shape: `git+https://github.com/<user>/<repo>.git@<tag>` -- a
slash between the host and the path, not a colon. The scp-style shorthand
(`git@github.com:user/repo.git`) that `git clone` accepts does **not**
work directly after `git+ssh://`; if you need SSH auth (a private repo),
write it as `git+ssh://git@github.com/<user>/<repo>.git@<tag>`, still with
a slash. HTTPS (as above) needs no auth for a public repo and is the
simpler default.

Either option pulls in the `libclang` pip wheel, which bundles its own
`libclang.so`, so it works even if it doesn't match the system's installed
clang/clang-tidy version.

**A gotcha you will likely hit:** on modern Debian/Ubuntu (Python 3.12+,
PEP 668), a bare `pip install` outside a virtual environment fails with
`error: externally-managed-environment`. Fix it one of these ways, in
order of preference:

```bash
# 1. a virtual environment (cleanest)
python3 -m venv .venv && source .venv/bin/activate
pip install -e vendor/codecheck-sarif

# 2. pipx, if you only want the `codecheck` command, not the Python API
pipx install "git+https://github.com/kotaronowwell/codecheck-sarif.git@v0.1.0"

# 3. last resort -- installs into the system Python, at your own risk
pip install -e vendor/codecheck-sarif --break-system-packages
```

## Working on this repo itself

The rest of this README is for hacking on `codecheck-sarif` itself, or
running its own examples. If you just want to *use* it, see above.

Install the OS toolchain (Debian/Ubuntu package names -- adjust for other
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

```bash
pip install -e .
```

Also install the **SARIF Viewer** VS Code extension
(`MS-SarifVSCode.sarif-viewer`) to browse `.sarif` output with clickable,
in-editor results instead of raw JSON.

`examples/embedded-c-demo/` is a small, dependency-free plain-C fixture
(no `compile_commands.json` needed) that exercises the `--lang c` path and
the `merge --rebase` flow against a fabricated third-party tool's SARIF --
run through it to see the whole pipeline end to end.

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
(via a submodule, or `pip install` against a git ref).

**Always pin consumers to a tag or commit, never to `@main`** -- a change
here should never silently change what a consumer's CI does on its next
`git submodule update` or `pip install --upgrade`. If no tag exists yet
when you read this, that's the next thing to fix here (`git tag v0.1.0 &&
git push --tags`) before anyone else takes a real dependency on `main`.
