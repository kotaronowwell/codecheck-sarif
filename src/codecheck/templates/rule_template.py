# Copy this file into your rules directory, rename it (anything not
# starting with '_' is auto-discovered), and fill in the three pieces
# below. `codecheck init-rule <name>` does the copying for you.
#
# CONTRACT (see plugin_runner.py for the full explanation):
#   RULE_ID           stable id, becomes the SARIF ruleId. Namespace it
#                     with your project/team so it can't collide with
#                     someone else's rule of the same short name.
#   RULE_DESCRIPTION  one-line human description (SARIF shortDescription).
#   RULE_HELP_URI     optional -- link to your team's wiki/coding-standard
#                     page for this rule. Delete the line if you don't
#                     have one yet.
#   check(ctx, file_path)
#                     return a list of ctx.result(...) values, or
#                     [] / None if file_path is clean.
#
# `ctx` gives you:
#   ctx.parse(file_path)          -> a libclang TranslationUnit, with
#                                     compile flags already resolved from
#                                     compile_commands.json (or a sane
#                                     C/C++ default if there's no entry).
#                                     Cheap to call: every rule looking at
#                                     this file shares one parse. Don't
#                                     keep the TU or its Cursors past the
#                                     end of check() -- they're freed when
#                                     the run moves to the next file.
#   ctx.in_project(node)          -> False for anything pulled in from a
#                                     system header or another library
#   ctx.result(file_path, line, col, message, level="warning")
#                                  -> a properly-shaped SARIF result dict

RULE_ID = "myproj/example-rule"
RULE_DESCRIPTION = "describe in one line what this rule enforces and why"
RULE_HELP_URI = "https://internal.wiki/rules/myproj-example-rule"


def check(ctx, file_path):
    import clang.cindex as cindex

    findings = []
    tu = ctx.parse(file_path)

    for node in tu.cursor.walk_preorder():
        if not ctx.in_project(node):
            continue  # skip anything from #include'd system/third-party headers

        # --- replace this example with your real condition -------------
        # Example: flag every function named exactly "TODO_rename_me".
        if node.kind == cindex.CursorKind.FUNCTION_DECL and node.spelling == "TODO_rename_me":
            findings.append(
                ctx.result(
                    file_path,
                    node.location.line,
                    node.location.column,
                    f"function '{node.spelling}' still has its placeholder name",
                )
            )
        # -----------------------------------------------------------------

    return findings
