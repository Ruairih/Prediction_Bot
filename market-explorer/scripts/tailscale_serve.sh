#!/bin/bash
#
# Tailscale Serve Setup - Run on HOST machine
#

PORTS="3004 8000 3000 9050"

case "${1:-start}" in
    start)
        echo "Starting Tailscale serves..."
        for port in $PORTS; do
            echo -n "  Port $port: "
            sudo tailscale serve --bg --https=$port http://localhost:$port 2>/dev/null && echo "OK" || echo "skipped"
        done
        echo ""
        echo "Access URLs:"
        HOSTNAME=$(tailscale status --json | jq -r '.Self.DNSName' | sed 's/\.$//')
        for port in $PORTS; do
            echo "  https://$HOSTNAME:$port"
        done
        ;;
    stop)
        echo "Stopping Tailscale serves..."
        for port in $PORTS; do
            sudo tailscale serve --https=$port off 2>/dev/null
        done
        ;;
    status)
        tailscale serve status
        ;;
    *)
        echo "Usage: $0 {start|stop|status}"
        ;;
esac
