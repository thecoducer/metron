#!/bin/bash

# Metron Cloudflare Tunnel Startup Script
# This script manages the Cloudflare tunnel for the Metron application

set -euo pipefail  # Exit on error, undefined vars, and pipe failures

# ============================================================================
# CONFIGURATION
# ============================================================================

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly TUNNEL_NAME="metron-tunnel"
readonly CONFIG_DIR="${HOME}/.cloudflared"
readonly CONFIG_FILE="${SCRIPT_DIR}/config.yml"
readonly LOCAL_PORT="${LOCAL_PORT:-8000}"

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
    exit $exit_code
}

trap cleanup EXIT

# ============================================================================
# INSTALLATION FUNCTIONS
# ============================================================================

install_cloudflared() {
    print_step "Installing cloudflared"
    
    if [[ "$OSTYPE" == "darwin"* ]]; then
        # macOS
        if ! command -v brew &> /dev/null; then
            print_error "Homebrew is required but not installed"
            echo "Visit: https://brew.sh to install Homebrew"
            return 1
        fi
        print_info "Installing via Homebrew..."
        brew install cloudflare/cloudflare/cloudflared || {
            print_error "Failed to install cloudflared"
            return 1
        }
    elif [[ "$OSTYPE" == "linux-gnu"* ]] || [[ "$OSTYPE" == "linux"* ]]; then
        # Linux - detect distro and use appropriate package manager
        if [ -f /etc/os-release ]; then
            . /etc/os-release
            DISTRO="$ID"
        else
            DISTRO="unknown"
        fi
        
        case "$DISTRO" in
            ubuntu|debian)
                print_info "Installing via apt..."
                sudo apt-get update
                sudo apt-get install -y cloudflared || {
                    print_error "Failed to install cloudflared"
                    return 1
                }
                ;;
            fedora|rhel|centos)
                print_info "Installing via yum..."
                sudo yum install -y cloudflared || {
                    print_error "Failed to install cloudflared"
                    return 1
                }
                ;;
            arch)
                print_info "Installing via pacman..."
                sudo pacman -S --noconfirm cloudflare-warp || {
                    print_error "Failed to install cloudflared"
                    return 1
                }
                ;;
            alpine)
                print_info "Installing via apk..."
                sudo apk add --no-cache cloudflare-warp || {
                    print_error "Failed to install cloudflared"
                    return 1
                }
                ;;
            *)
                print_error "Unsupported distro: $DISTRO"
                echo "Please install cloudflared manually:"
                echo "Visit: https://developers.cloudflare.com/cloudflare-one/connections/connect-applications/install-and-setup/installation/"
                return 1
                ;;
        esac
    else
        print_error "Unsupported OS. Please install cloudflared manually:"
        echo "Visit: https://developers.cloudflare.com/cloudflare-one/connections/connect-applications/install-and-setup/installation/"
        return 1
    fi
    
    print_success "cloudflared installed"
}

check_cloudflared_installed() {
    print_step "Checking cloudflared installation"
    
    if ! command -v cloudflared &> /dev/null; then
        print_warning "cloudflared is not installed"
        install_cloudflared || return 1
    fi
    
    local version=$(cloudflared --version 2>&1 | head -n 1)
    print_success "$version installed"
}

setup_cloudflare_credentials() {
    print_step "Setting up Cloudflare credentials"
    
    # Create config directory if it doesn't exist
    if [ ! -d "$CONFIG_DIR" ]; then
        print_info "Creating configuration directory at $CONFIG_DIR..."
        mkdir -p "$CONFIG_DIR"
        print_success "Configuration directory created"
    fi
    
    # Check for credentials
    local cert_file="$CONFIG_DIR/cert.pem"
    if [ ! -f "$cert_file" ]; then
        print_warning "Cloudflare credentials not found at $cert_file"
        echo ""
        echo "Please authenticate with Cloudflare by running:"
        echo -e "${YELLOW}  cloudflared tunnel login${NC}"
        echo ""
        echo "This will open a browser window to authenticate."
        echo "After authentication, the cert.pem file will be created."
        echo ""
        
        # Attempt to run login
        if cloudflared tunnel login; then
            print_success "Cloudflare authentication successful"
        else
            print_error "Cloudflare authentication failed"
            return 1
        fi
    else
        print_success "Cloudflare credentials found"
    fi
}

check_tunnel_exists() {
    print_step "Checking if tunnel '$TUNNEL_NAME' exists"
    
    # List tunnels (this requires authentication)
    if cloudflared tunnel list 2>/dev/null | grep -q "^${TUNNEL_NAME}"; then
        print_success "Tunnel '$TUNNEL_NAME' exists"
        return 0
    else
        print_warning "Tunnel '$TUNNEL_NAME' not found"
        return 1
    fi
}

create_tunnel() {
    print_step "Creating tunnel '$TUNNEL_NAME'"
    
    if cloudflared tunnel create "$TUNNEL_NAME" 2>/dev/null; then
        print_success "Tunnel '$TUNNEL_NAME' created"
    else
        print_error "Failed to create tunnel"
        return 1
    fi
}

setup_config_file() {
    print_step "Setting up tunnel configuration"
    
    # Check if config.yml exists in project directory
    if [ ! -f "$CONFIG_FILE" ]; then
        print_info "Creating config.yml at $CONFIG_FILE..."
        
        cat > "$CONFIG_FILE" << 'EOF'
# Metron Cloudflare Tunnel Configuration
# This file routes traffic from Cloudflare to your local application

tunnel: metron-tunnel
credentials-file: ~/.cloudflared/metron-tunnel.json

ingress:
  # Example: Change "yourdomain.com" to your actual domain
  - hostname: yourdomain.com
    service: http://localhost:8000
  
  # Catch-all for any other hostname
  - service: http_status:404
EOF
        
        print_success "config.yml created at $CONFIG_FILE"
        print_warning "Please update the hostname in $CONFIG_FILE with your actual domain"
    else
        print_info "config.yml already exists at $CONFIG_FILE"
    fi
}

start_tunnel() {
    print_step "Starting Cloudflare tunnel"
    
    if [ ! -f "$CONFIG_FILE" ]; then
        print_error "config.yml not found at $CONFIG_FILE"
        return 1
    fi
    
    echo ""
    print_success "All checks passed! Starting Cloudflare tunnel..."
    echo -e "${CYAN}Tunnel name: ${TUNNEL_NAME}${NC}"
    echo -e "${CYAN}Config file: ${CONFIG_FILE}${NC}"
    echo -e "${CYAN}Local service: http://localhost:${LOCAL_PORT}${NC}"
    echo -e "${YELLOW}Press Ctrl+C to stop${NC}\n"
    
    # Start the tunnel
    cloudflared tunnel run --config "$CONFIG_FILE" "$TUNNEL_NAME"
}

# ============================================================================
# MAIN EXECUTION
# ============================================================================

main() {
    print_header " Metron Cloudflare Tunnel Startup "
    
    # Install cloudflared if needed (for new computers)
    check_cloudflared_installed || exit 1
    
    # Tunnel is already created, just run it
    echo ""
    print_success "Starting existing tunnel: $TUNNEL_NAME"
    echo -e "${CYAN}Local service: http://localhost:${LOCAL_PORT}${NC}"
    echo -e "${YELLOW}Press Ctrl+C to stop${NC}\n"
    
    cloudflared tunnel run "$TUNNEL_NAME"
}

# Run main function
main "$@"
