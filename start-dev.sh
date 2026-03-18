#!/bin/bash

# Metron Development Server Startup Script
# This script sets up the environment and starts the development server with graceful error handling

set -euo pipefail  # Exit on error, undefined vars, and pipe failures

# ============================================================================
# CONFIGURATION
# ============================================================================

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly VENV_DIR="${SCRIPT_DIR}/run_server"
readonly PYTHON_CMD="python3"
readonly MIN_PYTHON_VERSION="3.8"

# Color codes
readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly BLUE='\033[0;34m'
readonly CYAN='\033[0;36m'
readonly NC='\033[0m'  # No Color

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

print_header() {
    echo -e "${BLUE}╔════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║ $1${NC}"
    echo -e "${BLUE}╚════════════════════════════════════════╝${NC}"
}

print_info() {
    echo -e "${CYAN}ℹ ${NC}$1"
}

print_success() {
    echo -e "${GREEN}✓ ${NC}$1"
}

print_warning() {
    echo -e "${YELLOW}⚠ ${NC}$1"
}

print_error() {
    echo -e "${RED}✗ ${NC}$1" >&2
}

print_step() {
    echo -e "\n${BLUE}→ $1${NC}"
}

cleanup() {
    local exit_code=$?
    if [ $exit_code -ne 0 ]; then
        echo ""
        print_error "Script failed with exit code $exit_code"
    fi
    # Deactivate virtual environment if active
    if [[ -n "${VIRTUAL_ENV:-}" ]]; then
        deactivate
    fi
    exit $exit_code
}

trap cleanup EXIT

# ============================================================================
# VALIDATION FUNCTIONS
# ============================================================================

check_required_file() {
    local file=$1
    local description=$2
    
    if [ ! -f "$SCRIPT_DIR/$file" ]; then
        print_error "$description not found at $SCRIPT_DIR/$file"
        return 1
    fi
}

check_python_installed() {
    print_step "Checking Python installation"
    
    if ! command -v $PYTHON_CMD &> /dev/null; then
        print_error "Python 3 is not installed"
        echo ""
        echo "Please install Python 3:"
        if [[ "$OSTYPE" == "darwin"* ]]; then
            echo "  macOS: brew install python3"
        elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
            echo "  Ubuntu/Debian: sudo apt-get install python3 python3-pip python3-venv"
            echo "  Fedora/CentOS: sudo yum install python3 python3-pip"
        else
            echo "  Visit: https://www.python.org/downloads/"
        fi
        return 1
    fi
    
    local version=$($PYTHON_CMD --version 2>&1 | awk '{print $2}')
    print_success "Python $version installed"
}

check_pip_available() {
    print_step "Checking pip availability"
    
    if ! $PYTHON_CMD -m pip --version &> /dev/null; then
        print_warning "pip not found, attempting to install..."
        if ! $PYTHON_CMD -m ensurepip --default-pip &> /dev/null; then
            print_error "Failed to install pip"
            return 1
        fi
    fi
    
    local version=$($PYTHON_CMD -m pip --version | awk '{print $2}')
    print_success "pip $version available"
}

create_or_verify_venv() {
    print_step "Setting up virtual environment"
    
    if [ ! -d "$VENV_DIR" ]; then
        print_info "Creating virtual environment at $VENV_DIR..."
        if ! $PYTHON_CMD -m venv "$VENV_DIR" 2>/dev/null; then
            print_error "Failed to create virtual environment"
            return 1
        fi
        print_success "Virtual environment created"
    else
        print_info "Virtual environment already exists"
    fi
    
    # Verify pip exists in venv
    if [ ! -f "$VENV_DIR/bin/pip" ]; then
        print_warning "Virtual environment corrupted, recreating..."
        rm -rf "$VENV_DIR"
        if ! $PYTHON_CMD -m venv "$VENV_DIR" 2>/dev/null; then
            print_error "Failed to recreate virtual environment"
            return 1
        fi
    fi
}

activate_venv() {
    print_step "Activating virtual environment"
    
    local activate_script="$VENV_DIR/bin/activate"
    if [ ! -f "$activate_script" ]; then
        print_error "Activation script not found"
        return 1
    fi
    
    # shellcheck disable=SC1090
    source "$activate_script"
    print_success "Virtual environment activated"
}

load_env_file() {
    print_step "Loading environment configuration"
    
    if [ -f "$SCRIPT_DIR/.env" ]; then
        set -a
        # shellcheck disable=SC1090
        source "$SCRIPT_DIR/.env"
        set +a
        print_success ".env file loaded"
    else
        print_info "No .env file found, using system environment"
    fi
}

install_dependencies() {
    print_step "Installing dependencies"
    
    if check_required_file "requirements.txt" "requirements.txt"; then
        # Upgrade pip first
        pip install --upgrade pip setuptools wheel --quiet 2>/dev/null || {
            print_error "Failed to upgrade pip"
            return 1
        }
        
        # Install requirements with progress output
        if ! pip install -r "$SCRIPT_DIR/requirements.txt" --quiet; then
            print_error "Failed to install requirements"
            return 1
        fi
        print_success "Dependencies installed"
    else
        return 1
    fi
}

start_server() {
    print_step "Starting development server"
    
    if ! check_required_file "main.py" "main.py"; then
        return 1
    fi
    
    echo ""
    print_success "All checks passed! Starting server..."
    echo -e "${YELLOW}Press Ctrl+C to stop${NC}\n"
    
    cd "$SCRIPT_DIR"
    "$PYTHON_CMD" main.py
}

# ============================================================================
# MAIN EXECUTION
# ============================================================================

main() {
    print_header " Metron Development Server Startup "
    
    # Run all checks
    check_python_installed || exit 1
    check_pip_available || exit 1
    load_env_file
    create_or_verify_venv || exit 1
    activate_venv || exit 1
    install_dependencies || exit 1
    
    # Start the server
    start_server
}

# Run main function
main "$@"
