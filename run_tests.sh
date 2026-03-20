#!/bin/bash

################################################################################
# Test Runner Script for Metron
#
# Usage:
#   ./run_tests.sh [options]
#
# Options:
#   --unit              Run only unit tests
#   --integration       Run only integration tests
#   --coverage          Run with coverage report (default)
#   --no-coverage       Run without coverage
#   --verbose           Verbose output
#   --clean             Clean up coverage files before running
#   --html              Generate HTML coverage report
#   --help              Show this help message
################################################################################

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
MAGENTA='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m'
BOLD='\033[1m'

RUN_COVERAGE=true
RUN_UNIT=true
RUN_INTEGRATION=true
VERBOSE=false
CLEAN=false
HTML_REPORT=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --unit)         RUN_INTEGRATION=false; shift ;;
        --integration)  RUN_UNIT=false; shift ;;
        --coverage)     RUN_COVERAGE=true; shift ;;
        --no-coverage)  RUN_COVERAGE=false; shift ;;
        --verbose)      VERBOSE=true; shift ;;
        --clean)        CLEAN=true; shift ;;
        --html)         HTML_REPORT=true; RUN_COVERAGE=true; shift ;;
        --help)
            echo "Usage: ./run_tests.sh [options]"
            echo ""
            echo "Options:"
            echo "  --unit              Run only unit tests"
            echo "  --integration       Run only integration tests"
            echo "  --coverage          Run with coverage report (default)"
            echo "  --no-coverage       Run without coverage"
            echo "  --verbose           Verbose output"
            echo "  --clean             Clean up coverage files before running"
            echo "  --html              Generate HTML coverage report"
            echo "  --help              Show this help message"
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

echo ""
echo -e "${BOLD}${CYAN}════════════════════════════════════════════════════════════════${NC}"
echo -e "${BOLD}${CYAN}  Metron - Test Suite Runner${NC}"
echo -e "${BOLD}${CYAN}════════════════════════════════════════════════════════════════${NC}"
echo ""

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

print_status()  { echo -e "${BLUE}[INFO]${NC} $1"; }
print_success() { echo -e "${GREEN}[✓]${NC} $1"; }
print_error()   { echo -e "${RED}[✗]${NC} $1"; }
print_warning() { echo -e "${YELLOW}[!]${NC} $1"; }
print_section() {
    echo ""
    echo -e "${BOLD}${MAGENTA}▶ $1${NC}"
    echo -e "${MAGENTA}────────────────────────────────────────────────────────${NC}"
}

print_section "1. Checking uv installation"
if ! command -v uv &> /dev/null; then
    print_error "uv is not installed"
    echo "Install it from: https://docs.astral.sh/uv/"
    exit 1
fi
print_success "$(uv --version) installed"

print_section "2. Installing Dependencies"
print_status "Running uv sync --group dev..."
uv sync --group dev
print_success "Dependencies ready"

if [ "$CLEAN" = true ]; then
    print_section "3. Cleaning Coverage Files"
    rm -rf htmlcov/ .coverage coverage.xml .pytest_cache/
    print_success "Coverage files cleaned"
fi

print_section "Running Tests"

if [ "$RUN_UNIT" = true ] && [ "$RUN_INTEGRATION" = true ]; then
    print_status "Running all tests (unit + integration)"
    TEST_PATTERN="tests/"
elif [ "$RUN_UNIT" = true ]; then
    print_status "Running unit tests only"
    TEST_PATTERN="tests/test_utils.py tests/test_api_services.py tests/test_api_clients.py tests/test_constants.py tests/test_server.py"
else
    print_status "Running integration tests only"
    TEST_PATTERN="tests/test_integration.py"
fi

TEST_CMD="uv run pytest $TEST_PATTERN"

if [ "$RUN_COVERAGE" = true ]; then
    TEST_CMD="$TEST_CMD --cov=app --cov-report=term-missing"
    if [ "$HTML_REPORT" = true ]; then
        TEST_CMD="$TEST_CMD --cov-report=html"
    fi
fi

if [ "$VERBOSE" = true ]; then
    TEST_CMD="$TEST_CMD -v"
fi

echo ""
echo -e "${CYAN}Command: ${NC}$TEST_CMD"
echo ""
echo -e "${BOLD}${CYAN}════════════════════════════════════════════════════════════════${NC}"
echo ""

eval "$TEST_CMD"
RESULT=$?

if [ $RESULT -eq 0 ]; then
    echo ""
    echo -e "${BOLD}${CYAN}════════════════════════════════════════════════════════════════${NC}"
    echo -e "${BOLD}${GREEN}✓ All tests passed!${NC}"
    echo -e "${BOLD}${CYAN}════════════════════════════════════════════════════════════════${NC}"
    if [ "$HTML_REPORT" = true ] && [ -d "htmlcov" ]; then
        echo ""
        print_success "HTML coverage report generated"
        echo -e "${CYAN}Open: ${NC}htmlcov/index.html"
    fi
    echo ""
    exit 0
else
    echo ""
    echo -e "${BOLD}${CYAN}════════════════════════════════════════════════════════════════${NC}"
    echo -e "${BOLD}${RED}✗ Tests failed!${NC}"
    echo -e "${BOLD}${CYAN}════════════════════════════════════════════════════════════════${NC}"
    echo ""
    exit 1
fi
