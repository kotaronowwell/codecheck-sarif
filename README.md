# c-code-checker-sarif
C/C++ code checker with clang output by SARIF (Static Analysis Results Interchange Format)

## Setup

Install tools

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
pip install libclang
```

Install by pip, not need to sudo.  
The pip version of libclang bundles libclang.so itself, so it’s self-contained and works even if it doesn’t match the system’s clang version.

Install vscode extension SARIF Viewer.

## Run

```bash
cmake -S . -B build -DCMAKE_EXPORT_COMPILE_COMMANDS=ON
clang-tidy -p build src/main.cpp src/Calculator.cpp > clang-tidy-output.txt
python3 tools/clang_tidy_to_sarif.py --root . clang-tidy-output.txt > results.sarif
```