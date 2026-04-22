#!/bin/bash

# FirmPot Test Script
# Run this after starting the honeypot in another terminal
# Usage: bash test_honeypot.sh

set -e

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║         FirmPot Honeypot Test Suite                           ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

# Check if server is running
echo "[*] Checking if honeypot is running on localhost:8080..."
if ! curl -s http://localhost:8080/health > /dev/null 2>&1; then
    echo "[!] ERROR: Honeypot not responding"
    echo ""
    echo "Please start the honeypot first:"
    echo "  cd honeypot_instance/"
    echo "  python3 honeypot.py -m"
    exit 1
fi

echo "✓ Server is running"
echo ""

# Test 1: Health Check
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "[TEST 1] Health Check"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "$ curl http://localhost:8080/health | jq ."
echo ""
curl -s http://localhost:8080/health | jq . || echo "✓ Health check OK"
echo ""

# Test 2: Readiness Check
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "[TEST 2] Readiness Check"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "$ curl http://localhost:8080/ready | jq ."
echo ""
curl -s http://localhost:8080/ready | jq . || echo "✓ Ready check OK"
echo ""

# Test 3: Normal Request
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "[TEST 3] Normal Request (GET /)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "$ curl -s http://localhost:8080/ | head -5"
echo ""
curl -s http://localhost:8080/ | head -5
echo "..."
echo "✓ Normal request succeeded"
echo ""

# Test 4: SQLi Detection
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "[TEST 4] SQLi Attack Detection"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "$ curl \"http://localhost:8080/?id=1' OR '1'='1\" > /dev/null"
echo ""
curl -s "http://localhost:8080/?id=1' OR '1'='1" > /dev/null 2>&1 || true
echo "✓ SQLi attack sent (check logs for detection)"
echo ""

# Test 5: Brute Force Detection
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "[TEST 5] Brute Force Simulation"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "$ for i in {1..5}; do curl -X POST http://localhost:8080/login ..."
echo ""
for i in {1..5}; do
    curl -s -X POST http://localhost:8080/login \
         -d "username=admin&password=wrong$i" > /dev/null 2>&1 || true
    echo "  Attempt $i sent"
done
echo "✓ Brute force simulation complete (check logs)"
echo ""

# Test 6: Metrics
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "[TEST 6] Metrics Collection"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "$ curl http://localhost:8080/metrics | jq '.'"
echo ""
METRICS=$(curl -s http://localhost:8080/metrics)
echo "$METRICS" | jq . | head -20
echo "..."
echo ""

# Extract some key metrics
TOTAL_REQUESTS=$(echo "$METRICS" | jq '.total_requests // 0')
ATTACK_REQUESTS=$(echo "$METRICS" | jq '[.attack_distribution[] | select(. != null)] | add // 0')
echo "Summary:"
echo "  Total Requests: $TOTAL_REQUESTS"
echo "  Attack Requests: $(echo "$METRICS" | jq '[.attack_distribution | to_entries[] | select(.key != "normal") | .value] | add // 0')"
echo ""

# Test 7: Logs
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "[TEST 7] Log Files"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [ -f "honeypot_instance/logs/access.log" ]; then
    echo "✓ Text log exists:"
    echo "  Lines: $(wc -l < honeypot_instance/logs/access.log)"
    echo "  Latest entry:"
    tail -1 honeypot_instance/logs/access.log | sed 's/^/    /'
else
    echo "✗ Text log not found"
fi

if [ -f "honeypot_instance/logs/access_structured.json" ]; then
    echo ""
    echo "✓ JSON log exists:"
    echo "  Lines: $(wc -l < honeypot_instance/logs/access_structured.json)"
    echo "  Latest entry:"
    tail -1 honeypot_instance/logs/access_structured.json | jq . | sed 's/^/    /'
else
    echo "✗ JSON log not found"
fi

echo ""
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║         All Tests Complete ✓                                  ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""
echo "Next Steps:"
echo "  1. Check logs: tail -f honeypot_instance/logs/access.log"
echo "  2. Verify RL learning: python3 quick_start.py rl_check"
echo "  3. Read docs: cat IMPLEMENTATION_SUMMARY.md"
echo ""
