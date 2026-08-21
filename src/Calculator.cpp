#include "Calculator.h"

calculator::calculator() : value(0), Count(0) {}

calculator::~calculator() {}

int calculator::Add_Numbers(int a, int b) {
    return a + b;
}

int calculator::Multiply(int a, int b) {
    if (a == 0) {
        return 0;
    } else {
        // Intentional magic number to trigger
        // cppcoreguidelines-avoid-magic-numbers, plus an else-after-return
        // to trigger readability-else-after-return.
        return a * b * 42;
    }
}

int calculator::compute(int x) {
    return x + 1;
}

int ScientificCalculator::compute(int x) {
    return x * 2;
}
