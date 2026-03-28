#!/bin/bash

# Metron SigNoz Observability Stack Startup Script
# Starts only the SigNoz components (ClickHouse, ZooKeeper, SigNoz, OTEL Collector)
# via docker compose for standalone observability use.

set -euo pipefail

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly SIGNOZ_PORT="${SIGNOZ_PORT:-8080}"

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

check_docker() {
    print_step "Checking Docker"
    if ! command -v docker &> /dev/null; then
        print_error "Docker is not installed"
        return 1
    fi
    if ! docker info &> /dev/null; then
        print_error "Docker daemon is not running"
        return 1
    fi
    print_success "Docker is running"
}

check_port_available() {
    print_step "Checking port $SIGNOZ_PORT availability"
    if ss -tuln 2>/dev/null | grep -q ":$SIGNOZ_PORT "; then
        print_error "Port $SIGNOZ_PORT is already in use"
        echo "Stop the existing service or set SIGNOZ_PORT to a different value"
        return 1
    fi
    print_success "Port $SIGNOZ_PORT is available"
}

start_signoz() {
    print_step "Starting SigNoz observability stack"
    echo ""
    print_success "All checks passed! Starting SigNoz..."
    echo -e "${CYAN}UI:  http://localhost:${SIGNOZ_PORT}${NC}"
    echo -e "${YELLOW}Press Ctrl+C to stop${NC}\n"

    cd "$SCRIPT_DIR"
    docker compose up --build zookeeper clickhouse signoz-migrator signoz signoz-otel-collector
}

main() {
    print_header " Metron SigNoz Observability Startup "
    echo ""
    check_docker || exit 1
    check_port_available || exit 1
    start_signoz
}

main "$@"
