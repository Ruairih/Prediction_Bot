#!/bin/bash
#
# Run this script ON YOUR HOST MACHINE (not inside the container)
# It sets up Tailscale to expose your dashboards externally
#

set -e

echo "=== Tailscale Dashboard Setup ==="
echo ""

# Check if tailscale is available
if ! command -v tailscale &> /dev/null; then
    echo "ERROR: Tailscale not installed on this machine"
    echo "Install from: https://tailscale.com/download"
    exit 1
fi

# Check if logged in
if ! tailscale status &> /dev/null; then
    echo "ERROR: Tailscale not running. Run: sudo tailscale up"
    exit 1
fi

HOSTNAME=$(tailscale status --json 2>/dev/null | jq -r '.Self.DNSName' | sed 's/\.$//')
echo "Your Tailscale hostname: $HOSTNAME"
echo ""

# Define ports
declare -A PORTS=(
    [3004]="Market Explorer Frontend"
    [8000]="Market Explorer API"
    [3000]="Trading Dashboard (React)"
    [9050]="Trading Dashboard (Flask)"
)

case "${1:-status}" in
    start)
        echo "Starting Tailscale serves..."
        for port in "${!PORTS[@]}"; do
            echo -n "  ${PORTS[$port]} (port $port): "
            if curl -s -o /dev/null -w "" --connect-timeout 1 http://127.0.0.1:$port 2>/dev/null; then
                sudo tailscale serve --bg --https=$port http://127.0.0.1:$port 2>/dev/null && echo "OK" || echo "already configured"
            else
                echo "SKIPPED (service not running)"
            fi
        done
        echo ""
        echo "Access URLs:"
        for port in "${!PORTS[@]}"; do
            echo "  ${PORTS[$port]}: https://$HOSTNAME:$port"
        done
        ;;

    stop)
        echo "Stopping Tailscale serves..."
        for port in "${!PORTS[@]}"; do
            sudo tailscale serve --https=$port off 2>/dev/null || true
        done
        echo "Done"
        ;;

    status|*)
        echo "Checking services on localhost..."
        for port in "${!PORTS[@]}"; do
            echo -n "  ${PORTS[$port]} (port $port): "
            if curl -s -o /dev/null -w "" --connect-timeout 1 http://127.0.0.1:$port 2>/dev/null; then
                echo "RUNNING"
            else
                echo "NOT RUNNING"
            fi
        done
        echo ""
        echo "Tailscale serve status:"
        tailscale serve status 2>/dev/null || echo "  No serves configured"
        echo ""
        echo "To start: $0 start"
        echo "To stop:  $0 stop"
        ;;
esac
