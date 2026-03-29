#!/bin/bash

# Metron Grafana + Loki Observability Stack Startup Script
# Downloads and runs Loki, Promtail, and Grafana as native binaries.
# No Docker required.

set -euo pipefail

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Load .env if present
if [[ -f "$SCRIPT_DIR/.env" ]]; then
    set -a
    source "$SCRIPT_DIR/.env"
    set +a
fi

readonly GRAFANA_PORT="${GRAFANA_PORT:-3000}"
readonly LOKI_PORT="${LOKI_PORT:-3100}"
readonly BIN_DIR="$SCRIPT_DIR/.grafana-bin"
readonly DATA_DIR="$SCRIPT_DIR/.grafana-data"
readonly LOG_DIR="$SCRIPT_DIR/logs"

readonly LOKI_VERSION="3.5.0"
readonly PROMTAIL_VERSION="3.5.0"
readonly GRAFANA_VERSION="12.0.0"

readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly BLUE='\033[0;34m'
readonly CYAN='\033[0;36m'
readonly NC='\033[0m'

print_header()  { echo -e "${BLUE}╔════════════════════════════════════════╗${NC}"; echo -e "${BLUE}║ $1${NC}"; echo -e "${BLUE}╚════════════════════════════════════════╝${NC}"; }
print_info()    { echo -e "${CYAN}ℹ ${NC}$1"; }
print_success() { echo -e "${GREEN}✓ ${NC}$1"; }
print_warning() { echo -e "${YELLOW}⚠ ${NC}$1"; }
print_error()   { echo -e "${RED}✗ ${NC}$1" >&2; }
print_step()    { echo -e "\n${BLUE}→ $1${NC}"; }

# Track child PIDs for cleanup
PIDS=()

cleanup() {
    echo ""
    print_step "Shutting down..."
    for pid in "${PIDS[@]}"; do
        if kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null || true
        fi
    done
    wait 2>/dev/null || true
    print_success "All services stopped"
}
trap cleanup EXIT INT TERM

check_dependencies() {
    print_step "Checking dependencies"
    local missing=()
    for cmd in curl tar; do
        if ! command -v "$cmd" &> /dev/null; then
            missing+=("$cmd")
        fi
    done
    if [ ${#missing[@]} -gt 0 ]; then
        print_error "Missing required tools: ${missing[*]}"
        echo "Install them: sudo apt-get install ${missing[*]}"
        return 1
    fi
    print_success "All dependencies available"
}

detect_arch() {
    local arch
    arch=$(uname -m)
    case "$arch" in
        x86_64)  echo "amd64" ;;
        aarch64) echo "arm64" ;;
        arm64)   echo "arm64" ;;
        *)
            print_error "Unsupported architecture: $arch"
            exit 1
            ;;
    esac
}

detect_os() {
    if [[ "$OSTYPE" == "darwin"* ]]; then echo "darwin"
    elif [[ "$OSTYPE" == "linux-gnu"* ]] || [[ "$OSTYPE" == "linux"* ]]; then echo "linux"
    else
        print_error "Unsupported OS: $OSTYPE"
        exit 1
    fi
}

download_loki() {
    local os="$1" arch="$2"
    local binary="$BIN_DIR/loki"
    if [ -f "$binary" ]; then
        print_success "Loki already downloaded"
        return
    fi
    local url="https://github.com/grafana/loki/releases/download/v${LOKI_VERSION}/loki-${os}-${arch}.zip"
    print_info "Downloading Loki v${LOKI_VERSION}..."
    curl -fsSL "$url" -o "$BIN_DIR/loki.zip"
    python3 -c "import zipfile,sys; zipfile.ZipFile(sys.argv[1]).extractall(sys.argv[2])" \
        "$BIN_DIR/loki.zip" "$BIN_DIR"
    mv "$BIN_DIR/loki-${os}-${arch}" "$binary"
    chmod +x "$binary"
    rm -f "$BIN_DIR/loki.zip"
    print_success "Loki downloaded"
}

download_promtail() {
    local os="$1" arch="$2"
    local binary="$BIN_DIR/promtail"
    if [ -f "$binary" ]; then
        print_success "Promtail already downloaded"
        return
    fi
    local url="https://github.com/grafana/loki/releases/download/v${PROMTAIL_VERSION}/promtail-${os}-${arch}.zip"
    print_info "Downloading Promtail v${PROMTAIL_VERSION}..."
    curl -fsSL "$url" -o "$BIN_DIR/promtail.zip"
    python3 -c "import zipfile,sys; zipfile.ZipFile(sys.argv[1]).extractall(sys.argv[2])" \
        "$BIN_DIR/promtail.zip" "$BIN_DIR"
    mv "$BIN_DIR/promtail-${os}-${arch}" "$binary"
    chmod +x "$binary"
    rm -f "$BIN_DIR/promtail.zip"
    print_success "Promtail downloaded"
}

download_grafana() {
    local os="$1" arch="$2"
    local grafana_dir="$BIN_DIR/grafana"
    if [ -d "$grafana_dir/bin" ]; then
        print_success "Grafana already downloaded"
        return
    fi
    local ext="tar.gz"
    local url="https://dl.grafana.com/oss/release/grafana-${GRAFANA_VERSION}.${os}-${arch}.${ext}"
    print_info "Downloading Grafana v${GRAFANA_VERSION}..."
    curl -fsSL "$url" -o "$BIN_DIR/grafana.tar.gz"
    tar -xzf "$BIN_DIR/grafana.tar.gz" -C "$BIN_DIR"
    mv "$BIN_DIR/grafana-v${GRAFANA_VERSION}" "$grafana_dir" 2>/dev/null \
        || mv "$BIN_DIR/grafana-${GRAFANA_VERSION}" "$grafana_dir" 2>/dev/null \
        || true
    rm -f "$BIN_DIR/grafana.tar.gz"
    print_success "Grafana downloaded"
}

generate_loki_config() {
    # Derive local config from the Docker loki-config.yml by rewriting paths
    sed \
        -e "s|/loki|${DATA_DIR}/loki|g" \
        "$SCRIPT_DIR/grafana/loki-config.yml" > "$DATA_DIR/loki-local.yml"
}

generate_promtail_config() {
    # Derive local config from the Docker promtail-config.yml:
    #  - rewrite Loki URL from Docker service name to localhost
    #  - rewrite log path from Docker mount to local logs dir
    #  - rewrite positions file path
    #  - strip the Docker-only scrape job (docker_sd_configs section)
    sed \
        -e "s|http://loki:${LOKI_PORT}|http://localhost:${LOKI_PORT}|g" \
        -e "s|/var/log/metron|${LOG_DIR}|g" \
        -e "s|/tmp/positions.yaml|${DATA_DIR}/promtail-positions.yaml|g" \
        -e '/# 2\. Docker container logs/,$d' \
        "$SCRIPT_DIR/grafana/promtail-config.yml" > "$DATA_DIR/promtail-local.yml"
}

generate_grafana_provisioning() {
    # Copy provisioning files and rewrite Loki URL for local run
    local prov_dir="$DATA_DIR/provisioning/datasources"
    mkdir -p "$prov_dir"
    sed \
        -e "s|http://loki:3100|http://localhost:${LOKI_PORT}|g" \
        "$SCRIPT_DIR/grafana/provisioning/datasources/loki.yml" > "$prov_dir/loki.yml"

    # Copy dashboard provisioning with path rewritten for local run
    local dash_prov_dir="$DATA_DIR/provisioning/dashboards"
    mkdir -p "$dash_prov_dir"
    sed \
        -e "s|/etc/grafana/provisioning/dashboards/json|${SCRIPT_DIR}/grafana/provisioning/dashboards/json|g" \
        "$SCRIPT_DIR/grafana/provisioning/dashboards/dashboards.yml" > "$dash_prov_dir/dashboards.yml"
}

check_port_available() {
    local port="$1" name="$2"
    if ss -tuln 2>/dev/null | grep -q ":${port} " || \
       lsof -Pi ":${port}" -sTCP:LISTEN -t >/dev/null 2>&1; then
        print_error "Port ${port} (${name}) is already in use"
        return 1
    fi
    print_success "Port ${port} (${name}) is available"
}

start_services() {
    print_step "Starting Loki on port ${LOKI_PORT}"
    mkdir -p "$DATA_DIR/loki/chunks" "$DATA_DIR/loki/rules" "$DATA_DIR/loki/compactor"
    "$BIN_DIR/loki" -config.file="$DATA_DIR/loki-local.yml" \
        > "$LOG_DIR/loki.log" 2>&1 &
    PIDS+=($!)
    print_success "Loki started (PID ${PIDS[-1]})"

    # Wait for Loki to become ready (including ingester ring)
    print_info "Waiting for Loki to be ready..."
    for i in $(seq 1 45); do
        if curl -sf "http://localhost:${LOKI_PORT}/ready" >/dev/null 2>&1; then
            # Also verify the ingester ring is accepting writes
            local test_push
            test_push=$(curl -s -o /dev/null -w "%{http_code}" \
                -X POST "http://localhost:${LOKI_PORT}/loki/api/v1/push" \
                -H "Content-Type: application/json" \
                -d '{"streams":[{"stream":{"job":"healthcheck"},"values":[["'$(date +%s)000000000'","loki ready"]]}]}' 2>/dev/null)
            if [ "$test_push" = "204" ]; then
                print_success "Loki is ready and accepting writes"
                break
            fi
        fi
        if [ "$i" -eq 45 ]; then
            print_error "Loki failed to start — check logs/loki.log"
            exit 1
        fi
        sleep 1
    done

    print_step "Starting Promtail"
    "$BIN_DIR/promtail" -config.file="$DATA_DIR/promtail-local.yml" \
        > "$LOG_DIR/promtail.log" 2>&1 &
    PIDS+=($!)
    print_success "Promtail started (PID ${PIDS[-1]})"

    print_step "Starting Grafana on port ${GRAFANA_PORT}"
    local grafana_dir="$BIN_DIR/grafana"
    GF_PATHS_DATA="$DATA_DIR/grafana" \
    GF_PATHS_LOGS="$LOG_DIR" \
    GF_PATHS_PROVISIONING="$DATA_DIR/provisioning" \
    GF_SERVER_HTTP_PORT="${GRAFANA_PORT}" \
    GF_SECURITY_ADMIN_USER="${GRAFANA_ADMIN_USER:-admin}" \
    GF_SECURITY_ADMIN_PASSWORD="${GRAFANA_ADMIN_PASSWORD:-metron}" \
    GF_AUTH_ANONYMOUS_ENABLED="false" \
    GF_EXPLORE_ENABLED="true" \
    "$grafana_dir/bin/grafana" server \
        --homepath "$grafana_dir" \
        > "$LOG_DIR/grafana.log" 2>&1 &
    PIDS+=($!)
    print_success "Grafana started (PID ${PIDS[-1]})"

    echo ""
    print_success "All services running!"
    echo -e "${CYAN}Grafana UI:  http://localhost:${GRAFANA_PORT}${NC}"
    print_info "Default login — admin / metron"
    print_info "Logs in ${LOG_DIR}/ (loki.log, promtail.log, grafana.log)"
    echo -e "${YELLOW}Press Ctrl+C to stop all services${NC}"

    # Wait for any child to exit
    wait
}

main() {
    print_header " Metron Grafana + Loki Startup        "
    echo ""

    local os arch
    os=$(detect_os)
    arch=$(detect_arch)
    print_info "Detected: ${os}/${arch}"

    mkdir -p "$BIN_DIR" "$DATA_DIR" "$LOG_DIR"

    check_dependencies || exit 1

    print_step "Checking ports"
    check_port_available "$LOKI_PORT" "Loki" || exit 1
    check_port_available "$GRAFANA_PORT" "Grafana" || exit 1

    print_step "Downloading binaries (if needed)"
    download_loki "$os" "$arch"
    download_promtail "$os" "$arch"
    download_grafana "$os" "$arch"

    print_step "Generating local configs"
    generate_loki_config
    generate_promtail_config
    generate_grafana_provisioning
    print_success "Configs written to $DATA_DIR/"

    start_services
}

main
