cmake_minimum_required(VERSION 3.16)
project(SarifClangTidyDemo CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

add_executable(demo
    src/main.cpp
    src/Calculator.cpp
    src/Logger.cpp
)
