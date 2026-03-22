#!/bin/bash

# Metron Development Server Startup Script

set -euo pipefail

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly MIN_PYTHON_VERSION="3.12"

readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly BLUE='\033[0;34m'
readonly CYAN='\033[0;36m'
readonly NC='\033[0m'

print_header() {
    echo -e "${BLUE}╔════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║ $1${NC}"
    echo -e "${BLUE}╚════════════════════════════════════════╝${NC}"
}
print_info()    { echo -e "${CYAN}ℹ ${NC}$1"; }
print_success() { echo -e "${GREEN}✓ ${NC}$1"; }
print_warning() { echo -e "${YELLOW}⚠ ${NC}$1"; }
print_error()   { echo -e "${RED}✗ ${NC}$1" >&2; }
print_step()    { echo -e "\n${BLUE}→ $1${NC}"; }

detect_os() {
    if [[ "$OSTYPE" == "darwin"* ]]; then echo "macos"
    elif [[ "$OSTYPE" == "linux-gnu"* ]] || [[ "$OSTYPE" == "linux"* ]]; then echo "linux"
    else echo "unknown"
    fi
}

check_uv_installed() {
    print_step "Checking uv installation"
    if ! command -v uv &> /dev/null; then
        print_error "uv is not installed"
        echo ""
        echo "Install uv:"
        echo "  curl -LsSf https://astral.sh/uv/install.sh | sh"
        echo "  or: brew install uv  (macOS)"
        return 1
    fi
    local version
    version=$(uv --version 2>&1)
    print_success "$version installed"
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
    print_info "Running uv sync --group dev..."
    if ! uv sync --group dev 2>&1; then
        print_error "Failed to install dependencies"
        return 1
    fi
    print_success "Dependencies installed"
}

check_port_available() {
    print_step "Checking development port availability"
    local dev_port=8000
    local os
    os=$(detect_os)
    if [[ "$os" == "macos" ]]; then
        if lsof -Pi :$dev_port -sTCP:LISTEN -t >/dev/null 2>&1; then
            print_warning "Port $dev_port is already in use"
            lsof -i :$dev_port
            return 1
        fi
    elif [[ "$os" == "linux" ]]; then
        if ss -tuln 2>/dev/null | grep -q ":$dev_port "; then
            print_warning "Port $dev_port is already in use"
            return 1
        fi
    fi
    print_success "Development port $dev_port is available"
}

run_linters() {
    print_step "Running linters"

    local failed=0

    print_info "Checking Python (ruff)..."
    if ! uv run ruff check . 2>&1; then
        print_error "ruff found issues — fix with: uv run ruff check . --fix"
        failed=1
    else
        print_success "ruff: OK"
    fi

    print_info "Checking Python types (pyrefly)..."
    if ! uv run pyrefly check 2>&1; then
        print_error "pyrefly found type errors — fix with: uv run pyrefly check"
        failed=1
    else
        print_success "pyrefly: OK"
    fi

    print_info "Checking HTML templates (djlint)..."
    if ! uv run djlint app/templates/ --check 2>&1; then
        print_error "djlint found issues — fix with: uv run djlint app/templates/ --reformat"
        failed=1
    else
        print_success "djlint: OK"
    fi

    if command -v npx &> /dev/null; then
        print_info "Checking JavaScript (eslint)..."
        if ! npx --no-install eslint app/static/js/ 2>&1; then
            print_error "eslint found issues — fix with: npx eslint app/static/js/ --fix"
            failed=1
        else
            print_success "eslint: OK"
        fi

        print_info "Checking CSS (stylelint)..."
        if ! npx --no-install stylelint "app/static/css/**/*.css" 2>&1; then
            print_error "stylelint found issues — fix with: npx stylelint app/static/css/**/*.css --fix"
            failed=1
        else
            print_success "stylelint: OK"
        fi
    else
        print_info "npx not found — skipping JS/CSS linting"
    fi

    if [[ $failed -eq 1 ]]; then
        print_error "Linting errors found. Fix them before starting the server."
        return 1
    fi

    print_success "All linters passed"
}

start_server() {
    print_step "Starting development server"
    if [ ! -f "$SCRIPT_DIR/main.py" ]; then
        print_error "main.py not found at $SCRIPT_DIR/main.py"
        return 1
    fi
    check_port_available || return 1
    echo ""
    print_success "All checks passed! Starting server..."
    echo -e "${YELLOW}Press Ctrl+C to stop${NC}\n"
    cd "$SCRIPT_DIR"
    export METRON_UI_PORT=8000
    export LOG_LEVEL=DEBUG
    uv run python3 main.py
}

main() {
    print_header " Metron Development Server Startup "
    local os
    os=$(detect_os)
    if [[ "$os" == "unknown" ]]; then
        print_warning "Running on unknown OS (trying to proceed anyway)"
    else
        print_info "Detected OS: $os"
    fi
    echo ""
    check_uv_installed || exit 1
    load_env_file
    install_dependencies || exit 1
    run_linters || exit 1
    start_server
}

main "$@"
