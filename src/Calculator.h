#pragma once

// NOTE: This class intentionally violates the project's naming convention
// (class names should be PascalCase, member variables should use the m_
// prefix, functions should be camelBack) so clang-tidy has something to
// report in this demo.
class calculator {
public:
    calculator();
    virtual ~calculator();

    int Add_Numbers(int a, int b);
    int Multiply(int a, int b);

    virtual int compute(int x);

private:
    int value;
    int Count;
};

class ScientificCalculator : public calculator {
public:
    // Intentionally missing 'override' to trigger modernize-use-override.
    int compute(int x);
};
