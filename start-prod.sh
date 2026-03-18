#!/bin/bash

# Metron Production Gunicorn Server Startup Script
# This script sets up the environment and starts the production Gunicorn server

set -euo pipefail  # Exit on error, undefined vars, and pipe failures

# ============================================================================
# CONFIGURATION
# ============================================================================

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly VENV_DIR="${SCRIPT_DIR}/run_server"
readonly PYTHON_CMD="python3"
readonly MIN_PYTHON_VERSION="3.8"
readonly PORT="${PORT:-8000}"
readonly WORKERS="${WORKERS:-1}"

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
# HELPER FUNCTIONS
# ============================================================================

detect_os() {
    if [[ "$OSTYPE" == "darwin"* ]]; then
        echo "macos"
    elif [[ "$OSTYPE" == "linux-gnu"* ]] || [[ "$OSTYPE" == "linux"* ]]; then
        echo "linux"
    else
        echo "unknown"
    fi
}

get_distro() {
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        echo "$ID"
    else
        echo "unknown"
    fi
}

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

check_system_dependencies() {
    print_step "Checking system dependencies"
    
    local os=$(detect_os)
    
    case "$os" in
        macos)
            # macOS: check for Xcode Command Line Tools
            if xcode-select -p &> /dev/null; then
                print_success "Xcode Command Line Tools available"
            else
                print_warning "Xcode Command Line Tools not installed (optional)"
                echo "Some packages may need compilation. Install with:"
                echo "  xcode-select --install"
                echo "Proceeding without it - will fail if packages need compilation"
            fi
            ;;
        linux)
            # Linux: check for build tools (optional, many wheels are pre-built)
            if command -v gcc &> /dev/null; then
                print_success "Build tools available"
            else
                print_warning "Build tools not found (optional)"
                local distro=$(get_distro)
                case "$distro" in
                    ubuntu|debian)
                        echo "If pip fails, install with: sudo apt-get install build-essential python3-dev"
                        ;;
                    fedora|rhel|centos)
                        echo "If pip fails, install with: sudo yum install gcc python3-devel"
                        ;;
                    arch)
                        echo "If pip fails, install with: sudo pacman -S base-devel"
                        ;;
                    *)
                        echo "If pip fails, install your distro's build tools"
                        ;;
                esac
                echo "Proceeding without build tools - will fail if packages need compilation"
            fi
            ;;
        *)
            print_warning "Unknown OS detected"
            ;;
    esac
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
    
    # Check Python version meets minimum requirement
    # Using printf to compare as numbers (3.8 -> 308, 3.14 -> 314)
    local version_num=$(echo "$version" | awk -F. '{printf "%d%02d", $1, $2}')
    local min_version_num=$(echo "$MIN_PYTHON_VERSION" | awk -F. '{printf "%d%02d", $1, $2}')
    
    if [ "$version_num" -lt "$min_version_num" ]; then
        print_error "Python $version is installed, but $MIN_PYTHON_VERSION+ is required"
        return 1
    fi
}

check_pip_available() {
    print_step "Checking pip availability"
    
    if ! $PYTHON_CMD -m pip --version &> /dev/null; then
        print_warning "pip not found, attempting to install..."
        
        local os=$(detect_os)
        if [[ "$os" == "linux" ]]; then
            local distro=$(get_distro)
            case "$distro" in
                ubuntu|debian)
                    echo "Installing python3-pip via apt..."
                    sudo apt-get update
                    sudo apt-get install -y python3-pip
                    ;;
                fedora|rhel|centos)
                    echo "Installing python3-pip via yum..."
                    sudo yum install -y python3-pip
                    ;;
                arch)
                    echo "Installing python-pip via pacman..."
                    sudo pacman -S --noconfirm python-pip
                    ;;
                *)
                    echo "Trying ensurepip..."
                    $PYTHON_CMD -m ensurepip --default-pip
                    ;;
            esac
        else
            echo "Trying ensurepip..."
            $PYTHON_CMD -m ensurepip --default-pip
        fi
        
        if ! $PYTHON_CMD -m pip --version &> /dev/null; then
            print_error "Failed to install pip"
            return 1
        fi
    fi
    
    local version=$($PYTHON_CMD -m pip --version | awk '{print $2}')
    print_success "pip $version available"
}

check_venv_available() {
    print_step "Checking virtual environment support"
    
    if ! $PYTHON_CMD -m venv --help &> /dev/null; then
        print_warning "venv module not available, attempting to install..."
        
        local os=$(detect_os)
        if [[ "$os" == "linux" ]]; then
            local distro=$(get_distro)
            case "$distro" in
                ubuntu|debian)
                    echo "Installing python3-venv via apt..."
                    sudo apt-get install -y python3-venv
                    ;;
                fedora|rhel|centos)
                    echo "Installing python3-venv via yum..."
                    sudo yum install -y python3-venv
                    ;;
                arch)
                    echo "Installing python-venv via pacman..."
                    sudo pacman -S --noconfirm python-venv
                    ;;
                *)
                    echo "Cannot install venv - install your distro's python3-venv package"
                    return 1
                    ;;
            esac
        fi
        
        if ! $PYTHON_CMD -m venv --help &> /dev/null; then
            print_error "Failed to install venv support"
            return 1
        fi
    fi
    
    print_success "Virtual environment support available"
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
    
    # Verify activation was successful
    if [[ -z "${VIRTUAL_ENV:-}" ]]; then
        print_error "Failed to activate virtual environment"
        return 1
    fi
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
        print_info "Upgrading pip, setuptools, wheel..."
        if ! pip install --upgrade pip setuptools wheel 2>&1; then
            print_error "Failed to upgrade pip"
            return 1
        fi
        
        # Install requirements without cache to avoid corruption issues
        print_info "Installing requirements from requirements.txt..."
        if ! pip install --no-cache-dir -r "$SCRIPT_DIR/requirements.txt" 2>&1; then
            print_error "Failed to install requirements"
            echo ""
            local os=$(detect_os)
            echo "Troubleshooting tips:"
            echo "  1. Check Python version: $PYTHON_CMD --version"
            if [[ "$os" == "macos" ]]; then
                echo "  2. Install Xcode tools: xcode-select --install"
            elif [[ "$os" == "linux" ]]; then
                local distro=$(get_distro)
                case "$distro" in
                    ubuntu|debian)
                        echo "  2. Install build tools: sudo apt-get install build-essential python3-dev"
                        ;;
                    fedora|rhel|centos)
                        echo "  2. Install build tools: sudo yum install gcc python3-devel"
                        ;;
                    arch)
                        echo "  2. Install build tools: sudo pacman -S base-devel"
                        ;;
                esac
            fi
            echo "  3. Try manually: pip install --no-cache-dir -r requirements.txt"
            return 1
        fi
        print_success "Dependencies installed"
    else
        return 1
    fi
}

check_gunicorn_available() {
    print_step "Checking Gunicorn availability"
    
    if ! python -c "import gunicorn" 2>/dev/null; then
        print_error "Gunicorn is not installed in the virtual environment"
        print_info "It should be in requirements.txt"
        return 1
    fi
    
    local version=$(pip show gunicorn | grep Version | awk '{print $2}')
    print_success "Gunicorn $version available"
}

check_port_available() {
    print_step "Checking port $PORT availability"
    
    local os=$(detect_os)
    
    # Check if port is in use
    if [[ "$os" == "macos" ]]; then
        if lsof -Pi :$PORT -sTCP:LISTEN -t >/dev/null 2>&1; then
            print_error "Port $PORT is already in use"
            echo "Finding process on port $PORT:"
            lsof -i :$PORT
            echo ""
            echo "To kill the process: kill -9 <PID>"
            echo "Or use a different port: PORT=8001 ./start-prod.sh"
            return 1
        fi
    elif [[ "$os" == "linux" ]]; then
        if ss -tuln 2>/dev/null | grep -q ":$PORT "; then
            print_error "Port $PORT is already in use"
            echo "Finding process on port $PORT:"
            ss -tuln | grep :$PORT
            echo ""
            echo "To kill the process: sudo lsof -i :$PORT | awk 'NR!=1 {print $2}' | xargs kill -9"
            echo "Or use a different port: PORT=8001 ./start-prod.sh"
            return 1
        fi
    fi
    
    print_success "Port $PORT is available"
}

start_production_server() {
    print_step "Starting production Gunicorn server"
    
    # Validate required files
    if ! check_required_file "gunicorn.conf.py" "gunicorn.conf.py"; then
        return 1
    fi
    if ! check_required_file "wsgi.py" "wsgi.py"; then
        return 1
    fi
    
    echo ""
    print_success "All checks passed! Starting Gunicorn server..."
    echo -e "${CYAN}Server binding: 0.0.0.0:${PORT}${NC}"
    echo -e "${CYAN}Workers: ${WORKERS}${NC}"
    echo -e "${YELLOW}Press Ctrl+C to stop${NC}\n"
    
    cd "$SCRIPT_DIR"
    
    # Set METRON_UI_PORT to match the port Gunicorn will bind to
    export METRON_UI_PORT="${PORT}"
    
    # Start Gunicorn with configuration file
    gunicorn \
        --config gunicorn.conf.py \
        --bind "0.0.0.0:${PORT}" \
        --workers "${WORKERS}" \
        wsgi:app
}

# ============================================================================
# MAIN EXECUTION
# ============================================================================

main() {
    print_header " Metron Production Gunicorn Server Startup "
    
    local os=$(detect_os)
    if [[ "$os" == "unknown" ]]; then
        print_warning "Running on unknown OS (trying to proceed anyway)"
    else
        print_info "Detected OS: $os"
    fi
    echo ""
    
    # Run all checks
    check_system_dependencies
    check_python_installed || exit 1
    check_pip_available || exit 1
    check_venv_available || exit 1
    load_env_file
    create_or_verify_venv || exit 1
    activate_venv || exit 1
    install_dependencies || exit 1
    check_gunicorn_available || exit 1
    check_port_available || exit 1
    
    # Start the production server
    start_production_server
}

# Run main function
main "$@"
