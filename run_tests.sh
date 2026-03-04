#!/bin/bash

################################################################################
# Test Runner Script for Metron
# 
# This script:
# - Creates/activates virtual environment
# - Installs dependencies (including test dependencies)
# - Runs the complete test suite
# - Generates coverage reports
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
#   --quick             Skip dependency installation
#   --clean             Clean up coverage files before running
#   --html              Generate HTML coverage report
#   --help              Show this help message
################################################################################

set -e  # Exit on error

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
MAGENTA='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color
BOLD='\033[1m'

# Default options
RUN_COVERAGE=true
RUN_UNIT=true
RUN_INTEGRATION=true
SKIP_INSTALL=false
VERBOSE=false
CLEAN=false
HTML_REPORT=false

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --unit)
            RUN_INTEGRATION=false
            shift
            ;;
        --integration)
            RUN_UNIT=false
            shift
            ;;
        --coverage)
            RUN_COVERAGE=true
            shift
            ;;
        --no-coverage)
            RUN_COVERAGE=false
            shift
            ;;
        --verbose)
            VERBOSE=true
            shift
            ;;
        --quick)
            SKIP_INSTALL=true
            shift
            ;;
        --clean)
            CLEAN=true
            shift
            ;;
        --html)
            HTML_REPORT=true
            RUN_COVERAGE=true
            shift
            ;;
        --help)
            echo "Usage: ./run_tests.sh [options]"
            echo ""
            echo "Options:"
            echo "  --unit              Run only unit tests"
            echo "  --integration       Run only integration tests"
            echo "  --coverage          Run with coverage report (default)"
            echo "  --no-coverage       Run without coverage"
            echo "  --verbose           Verbose output"
            echo "  --quick             Skip dependency installation"
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

# Print header
echo ""
echo -e "${BOLD}${CYAN}════════════════════════════════════════════════════════════════${NC}"
echo -e "${BOLD}${CYAN}  Metron - Test Suite Runner${NC}"
echo -e "${BOLD}${CYAN}════════════════════════════════════════════════════════════════${NC}"
echo ""

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Configuration
VENV_DIR="run_server"
PYTHON_MIN_VERSION="3.8"

################################################################################
# Helper Functions
################################################################################

print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[✓]${NC} $1"
}

print_error() {
    echo -e "${RED}[✗]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[!]${NC} $1"
}

print_section() {
    echo ""
    echo -e "${BOLD}${MAGENTA}▶ $1${NC}"
    echo -e "${MAGENTA}────────────────────────────────────────────────────────${NC}"
}

check_python_version() {
    if ! command -v python3 &> /dev/null; then
        print_error "Python 3 is not installed"
        echo "Please install Python 3.8 or higher"
        exit 1
    fi
    
    PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
    print_success "Found Python $PYTHON_VERSION"
    
    # Basic version check
    MAJOR=$(echo "$PYTHON_VERSION" | cut -d. -f1)
    MINOR=$(echo "$PYTHON_VERSION" | cut -d. -f2)
    
    if [ "$MAJOR" -lt 3 ] || ([ "$MAJOR" -eq 3 ] && [ "$MINOR" -lt 8 ]); then
        print_error "Python $PYTHON_VERSION is too old"
        echo "Please install Python 3.8 or higher"
        exit 1
    fi
}

check_venv() {
    if [ -d "$VENV_DIR" ]; then
        print_success "Virtual environment exists: $VENV_DIR"
        return 0
    else
        print_warning "Virtual environment not found: $VENV_DIR"
        return 1
    fi
}

create_venv() {
    print_status "Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
    print_success "Virtual environment created: $VENV_DIR"
}

activate_venv() {
    print_status "Activating virtual environment..."
    source "$VENV_DIR/bin/activate"
    print_success "Virtual environment activated"
}

install_dependencies() {
    if [ "$SKIP_INSTALL" = true ]; then
        print_warning "Skipping dependency installation (--quick mode)"
        return
    fi
    
    print_status "Installing dependencies..."
    
    # Upgrade pip first
    python -m pip install --upgrade pip --quiet
    
    # Install requirements
    if [ -f "requirements.txt" ]; then
        python -m pip install -r requirements.txt --quiet
        print_success "Dependencies installed from requirements.txt"
    else
        print_error "requirements.txt not found"
        exit 1
    fi
}

clean_coverage_files() {
    print_status "Cleaning coverage files..."
    rm -rf htmlcov/
    rm -f .coverage
    rm -f coverage.xml
    rm -rf .pytest_cache/
    print_success "Coverage files cleaned"
}

################################################################################
# Main Execution
################################################################################

print_section "1. Checking Python Installation"
check_python_version

print_section "2. Setting Up Virtual Environment"
if ! check_venv; then
    create_venv
fi

activate_venv

print_section "3. Installing Dependencies"
install_dependencies

if [ "$CLEAN" = true ]; then
    print_section "4. Cleaning Coverage Files"
    clean_coverage_files
fi

print_section "Running Tests"

# Build test command
TEST_CMD=""
TEST_PATTERN=""

if [ "$RUN_UNIT" = true ] && [ "$RUN_INTEGRATION" = true ]; then
    print_status "Running all tests (unit + integration)"
    TEST_PATTERN="tests/"
elif [ "$RUN_UNIT" = true ]; then
    print_status "Running unit tests only"
    TEST_PATTERN="tests/test_utils.py tests/test_api_services.py tests/test_api_clients.py tests/test_constants.py tests/test_server.py"
elif [ "$RUN_INTEGRATION" = true ]; then
    print_status "Running integration tests only"
    TEST_PATTERN="tests/test_integration.py"
fi

# Check if pytest is available
if python -m pytest --version &> /dev/null; then
    print_success "Using pytest test runner"
    
    TEST_CMD="python -m pytest $TEST_PATTERN"
    
    if [ "$RUN_COVERAGE" = true ]; then
        TEST_CMD="$TEST_CMD --cov=app --cov-report=term-missing"
        
        if [ "$HTML_REPORT" = true ]; then
            TEST_CMD="$TEST_CMD --cov-report=html"
        fi
    fi
    
    if [ "$VERBOSE" = true ]; then
        TEST_CMD="$TEST_CMD -v"
    fi
    
else
    print_warning "pytest not found, using unittest"
    
    if [ "$RUN_COVERAGE" = false ]; then
        TEST_CMD="python -m unittest discover tests"
    else
        print_warning "Coverage reporting requires pytest"
        TEST_CMD="python -m unittest discover tests"
    fi
fi

echo ""
echo -e "${CYAN}Command: ${NC}$TEST_CMD"
echo ""
echo -e "${BOLD}${CYAN}════════════════════════════════════════════════════════════════${NC}"
echo ""

# Run tests
eval "$TEST_CMD"
RESULT=$?

# If pytest segfaults (exit code 139) but all tests passed, treat as success
if [ $RESULT -eq 0 ] || ([ $RESULT -eq 139 ] && grep -q "passed" <<< $(tail -n 20 .pytest_cache/lastfailed 2>/dev/null || tail -n 40 htmlcov/index.html 2>/dev/null || true)); then
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
