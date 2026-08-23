"""codecheck: pluggable project-specific coding-rule checker, SARIF 2.1.0 output.

Public building blocks (also usable directly by rule plugins that need
more control than the plugin contract exposes):
    sarif_common   -- SARIF construction helpers, resource-dir detection
    plugin_runner  -- CheckContext + rule-plugin discovery/execution
    sarif_merge    -- combine this tool's SARIF with any other tool's
"""

__version__ = "0.1.0"
