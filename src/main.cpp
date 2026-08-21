#include <iostream>
#include <string>

#include "Calculator.h"

// Intentional violation of google-build-using-namespace.
using namespace std;

// 'data' is unused (misc-unused-parameters) and passed by value where a
// const reference would do (performance-unnecessary-value-param).
int process(std::string data) {
    return 0;
}

int main() {
    calculator calc;
    std::cout << calc.Add_Numbers(3, 4) << std::endl;
    std::cout << calc.Multiply(2, 5) << std::endl;
    return 0;
}
