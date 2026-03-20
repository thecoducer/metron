#!/bin/bash

# Metron Production Gunicorn Server Startup Script

set -euo pipefail

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly PORT="${PORT:-8000}"
readonly WORKERS="${WORKERS:-1}"

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

check_required_file() {
    if [ ! -f "$SCRIPT_DIR/$1" ]; then
        print_error "$2 not found at $SCRIPT_DIR/$1"
        return 1
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
    print_info "Running uv sync --group prod --no-dev..."
    if ! uv sync --group prod --no-dev 2>&1; then
        print_error "Failed to install dependencies"
        return 1
    fi
    print_success "Dependencies installed"
}

check_port_available() {
    print_step "Checking port $PORT availability"
    local os
    os=$(detect_os)
    if [[ "$os" == "macos" ]]; then
        if lsof -Pi :$PORT -sTCP:LISTEN -t >/dev/null 2>&1; then
            print_error "Port $PORT is already in use"
            lsof -i :$PORT
            echo "Or use a different port: PORT=8001 ./start-prod.sh"
            return 1
        fi
    elif [[ "$os" == "linux" ]]; then
        if ss -tuln 2>/dev/null | grep -q ":$PORT "; then
            print_error "Port $PORT is already in use"
            echo "Or use a different port: PORT=8001 ./start-prod.sh"
            return 1
        fi
    fi
    print_success "Port $PORT is available"
}

start_production_server() {
    print_step "Starting production Gunicorn server"
    check_required_file "gunicorn.conf.py" "gunicorn.conf.py" || return 1
    check_required_file "wsgi.py" "wsgi.py" || return 1
    echo ""
    print_success "All checks passed! Starting Gunicorn server..."
    echo -e "${CYAN}Server binding: 0.0.0.0:${PORT}${NC}"
    echo -e "${CYAN}Workers: ${WORKERS}${NC}"
    echo -e "${YELLOW}Press Ctrl+C to stop${NC}\n"
    cd "$SCRIPT_DIR"
    export METRON_UI_PORT="${PORT}"
    uv run gunicorn \
        --config gunicorn.conf.py \
        --bind "0.0.0.0:${PORT}" \
        --workers "${WORKERS}" \
        wsgi:app
}

main() {
    print_header " Metron Production Gunicorn Server Startup "
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
    check_port_available || exit 1
    start_production_server
}

main "$@"
