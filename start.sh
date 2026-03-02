#!/bin/bash

# Metron Startup Script
# This script sets up the environment and starts the server

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo -e "${BLUE}=== Metron Startup ===${NC}\n"

# Function to print colored messages
print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if config.json exists and is properly configured
print_info "Checking configuration..."
if [ ! -f "config/config.json" ]; then
    print_error "config/config.json not found!"
    echo ""
    echo "Please create a config.json file with your account details."
    echo "See config/config.json.example for the required structure."
    exit 1
fi

# Validate config.json structure using the application's own validation
if ! python3 -c "
import json
import sys

try:
    with open('config/config.json', 'r') as f:
        config = json.load(f)

    # Basic structure check — accounts are now stored per-user in Firebase,
    # so we only validate that the JSON is parseable and has server settings.
    if 'server' not in config:
        print('WARNING: config.json is missing \"server\" section, defaults will be used')

    print('Configuration validation passed')

except json.JSONDecodeError as e:
    print(f'ERROR: config.json is not valid JSON: {e}')
    sys.exit(1)
except Exception as e:
    print(f'ERROR: Failed to validate config.json: {e}')
    sys.exit(1)
" 2>&1; then
    print_error "Configuration validation failed!"
    exit 1
fi

print_success "Configuration validated"

# Check if Python 3 is installed
print_info "Checking Python installation..."
if ! command -v python3 &> /dev/null; then
    print_error "Python 3 is not installed!"
    echo ""
    echo "Please install Python 3 using one of these methods:"
    echo ""
    if [[ "$OSTYPE" == "darwin"* ]]; then
        echo "On macOS:"
        echo "  1. Using Homebrew: brew install python3"
        echo "  2. Download from: https://www.python.org/downloads/"
    elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
        echo "On Linux:"
        echo "  Ubuntu/Debian: sudo apt-get update && sudo apt-get install python3 python3-pip python3-venv"
        echo "  Fedora/CentOS: sudo yum install python3 python3-pip"
    else
        echo "Download from: https://www.python.org/downloads/"
    fi
    exit 1
fi

PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
print_success "Python $PYTHON_VERSION found"

# Check if pip is available
print_info "Checking pip installation..."
if ! python3 -m pip --version &> /dev/null; then
    print_warning "pip not found, attempting to install..."
    if [[ "$OSTYPE" == "darwin"* ]] || [[ "$OSTYPE" == "linux-gnu"* ]]; then
        python3 -m ensurepip --default-pip || {
            print_error "Failed to install pip. Please install it manually."
            exit 1
        }
    else
        print_error "pip not found. Please install pip manually."
        exit 1
    fi
fi
print_success "pip is available"

# Create virtual environment if it doesn't exist
VENV_DIR="run_server"
if [ ! -d "$VENV_DIR" ]; then
    print_info "Creating virtual environment..."
    python3 -m venv "$VENV_DIR" || {
        print_error "Failed to create virtual environment"
        exit 1
    }
    print_success "Virtual environment created"
else
    print_info "Virtual environment already exists"
fi

# Activate virtual environment
print_info "Activating virtual environment..."
source "$VENV_DIR/bin/activate" || {
    print_error "Failed to activate virtual environment"
    exit 1
}
print_success "Virtual environment activated"

# Verify pip is available in venv
if ! command -v pip &> /dev/null; then
    print_error "pip not found in virtual environment"
    print_info "Attempting to reinstall virtual environment..."
    rm -rf "$VENV_DIR"
    python3 -m venv "$VENV_DIR" || {
        print_error "Failed to recreate virtual environment"
        exit 1
    }
    source "$VENV_DIR/bin/activate" || {
        print_error "Failed to activate virtual environment"
        exit 1
    }
fi

# Upgrade pip in virtual environment
print_info "Upgrading pip..."
python -m pip install --upgrade pip --quiet

# Install requirements
print_info "Installing/updating requirements..."
if [ ! -f "requirements.txt" ]; then
    print_error "requirements.txt not found!"
    exit 1
fi

python -m pip install -r requirements.txt --quiet || {
    print_error "Failed to install requirements"
    deactivate
    exit 1
}
print_success "Requirements installed"

# Check if main.py exists
if [ ! -f "main.py" ]; then
    print_error "main.py not found!"
    deactivate
    exit 1
fi

echo ""
print_success "All checks passed! Starting server..."
echo ""
echo -e "${YELLOW}Press Ctrl+C to stop the server${NC}"
echo ""

# Start the server
python3 main.py

# Deactivate virtual environment on exit
deactivate
