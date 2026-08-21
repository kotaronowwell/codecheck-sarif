#include "Logger.h"

#include <iostream>

void Logger::logLine(const std::string& text) {
    std::cout << text << std::endl;
}

void Logger::setLevel(int level) {
    m_level = level;
}
