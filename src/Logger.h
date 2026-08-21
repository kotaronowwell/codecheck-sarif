#pragma once

#include <string>

/// Sends diagnostic text to whatever sink the platform provides.
///
/// This class exists purely to exercise the custom
/// require_doxygen_for_public_methods.py rule: one public method is
/// documented (should pass), the other isn't (should be flagged).
class Logger {
public:
    /// Writes a single line to the log sink, unmodified.
    void logLine(const std::string& text);

    // Intentionally missing a Doxygen comment, to trigger the custom rule.
    void setLevel(int level);

private:
    int m_level = 0;
};
