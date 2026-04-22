#!/bin/bash

# FirmPot Startup Helper
# This script provides easy commands to start and test the honeypot

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ $# -eq 0 ]; then
    cat << 'EOF'

╔════════════════════════════════════════════════════════════════════════════╗
║                  FirmPot Honeypot - Getting Started                       ║
╚════════════════════════════════════════════════════════════════════════════╝

QUICK START COMMANDS:

1. START HONEYPOT SERVER:
   $ ./start.sh

2. TEST HONEYPOT (in another terminal):
   $ bash test_honeypot.sh

3. VIEW DOCUMENTATION:
   $ cat QUICKSTART.md
   $ cat IMPLEMENTATION_SUMMARY.md
   $ python3 DEMO_GUIDE.py

4. CHECK RL LEARNING:
   python3 << 'PYEOF'
   from rl_agent import RLAgent
   agent = RLAgent('./honeypot_instance/rl.db')
   print(agent.verify_rl_learning()['recommendation'])
   agent.close()
   PYEOF

5. MONITOR LOGS:
   $ tail -f honeypot_instance/logs/access.log
   $ tail -f honeypot_instance/logs/access_structured.json | jq .

════════════════════════════════════════════════════════════════════════════

EXAMPLES:

Test normal request:
   $ curl http://localhost:8080/

Trigger SQLi detection:
   $ curl "http://localhost:8080/?id=1' OR '1'='1"

Check server health:
   $ curl http://localhost:8080/health | jq .

View metrics:
   $ curl http://localhost:8080/metrics | jq '.total_requests'

════════════════════════════════════════════════════════════════════════════

For more info, run:
   $ python3 quick_start.py

════════════════════════════════════════════════════════════════════════════

EOF
    exit 0
fi

case "$1" in
    "start")
        echo "[*] Starting FirmPot Honeypot..."
        cd honeypot_instance/
        python3 honeypot.py -m
        ;;
    "test")
        bash test_honeypot.sh
        ;;
    "logs")
        tail -f honeypot_instance/logs/access.log
        ;;
    "json")
        tail -f honeypot_instance/logs/access_structured.json | jq .
        ;;
    "metrics")
        while true; do
            clear
            echo "FirmPot Metrics (updating every 2 seconds)..."
            echo ""
            curl -s http://localhost:8080/metrics | jq '.
                | {
                  uptime: .uptime_seconds,
                  total_requests: .total_requests,
                  rps: .requests_per_second,
                  attacks: (.attack_distribution | keys),
                  top_ips: .top_attacking_ips,
                  rl_actions: .rl_action_distribution
                }'
            sleep 2
        done
        ;;
    *)
        echo "Unknown command: $1"
        echo ""
        echo "Available commands:"
        echo "  start    - Start honeypot server"
        echo "  test     - Run test suite"
        echo "  logs     - Tail access logs"
        echo "  json     - Tail JSON logs"
        echo "  metrics  - Watch metrics (updates every 2s)"
        exit 1
        ;;
esac
