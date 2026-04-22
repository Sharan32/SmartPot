#!/usr/bin/env python3

"""
Quick Demo Guide for FirmPot Enhancements

This script shows all the new features and how to use them.
Run this after honeypot has been operational.
"""

import json
import os
import sqlite3
from datetime import datetime


def section(title):
    """Print section header"""
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}\n")


def subsection(title):
    """Print subsection header"""
    print(f"\n{title}")
    print(f"{'-'*50}")


def demo_1_run_all():
    """DEMO 1: Using run_all.py"""
    section("DEMO 1: ONE-COMMAND OPERATION")
    print("""
Quick Start:
    python3 run_all.py firmware.bin

What it does:
    1. ✓ Verifies firmware exists
    2. ✓ Runs auto.py (generates honeypot)
    3. ✓ Validates honeypot_instance/
    4. ✓ Starts honeypot server
    5. ✓ Logs everything to run_all.log

Output Files:
    - run_all.log           : Execution log with timestamps
    - logs/rl_agent.log     : RL decisions and rewards
    - logs/access.log       : Human-readable access log
    - logs/access_structured.json : Machine-readable JSON log

Stop the server:
    Press Ctrl+C

See what happened:
    tail -50 run_all.log
    """)


def demo_2_attack_detection():
    """DEMO 2: Attack Detection Examples"""
    section("DEMO 2: ATTACK DETECTION")
    print("""
Generate test traffic to see attack detection:

1. SQLi Attack:
   $ curl "http://localhost:8080/?id=1' OR '1'='1"
   
   → Detected as: sqli (confidence: 0.90)

2. XSS Attack:
   $ curl "http://localhost:8080/?msg=<script>alert('xss')</script>"
   
   → Detected as: xss (confidence: 0.85)

3. Brute Force:
   $ for i in {1..10}; do
       curl -X POST http://localhost:8080/login \\
            -d "username=admin&password=wrong$i"
     done
   
   → Detected as: brute_force (confidence: 0.90)

4. Scanner Activity:
   $ curl -H "User-Agent: nikto/2.1.5" http://localhost:8080/
   
   → Detected as: scanner (confidence: 0.95)

5. Normal Traffic:
   $ curl http://localhost:8080/
   
   → Detected as: normal (confidence: 0.95)

View detections in logs:
   $ tail -20 honeypot_instance/logs/access.log
   
   Format:
   [TIMESTAMP] IP SESSION_ID METHOD PATH -> STATUS | 
   Attack: TAG1,TAG2 (conf:0.XX) | RL_Ac: ACTION
    """)


def demo_3_session_tracking():
    """DEMO 3: Session Tracking (TASK 3)"""
    section("DEMO 3: SESSION TRACKING & LENGTH")
    print("""
Session Length = Number of Requests Per Session

How it works:
    - Each IP gets a session_id (32-char random)
    - Each request increments session['request_count']
    - Session expires after TTL (default: 3600s)
    - Metrics include: duration, request_count, attack_count

Example session tracking:

Session 1:
    IP: 192.168.1.100
    session_id: f4d3a8c2b1e9...
    requests_in_session: 5           ← SESSION LENGTH
    attacks_in_session: 2
    duration: 45 seconds
    profile: attacker

Session 2:
    IP: 10.0.0.5
    session_id: 2c8f1e9d4a3b...
    requests_in_session: 23          ← SESSION LENGTH
    attacks_in_session: 0
    duration: 312 seconds
    profile: attacker

View in logs:
    $ grep "session_id" honeypot_instance/logs/access_structured.json | \\
      python3 -m json.tool | head -20

Track sessions programmatically:
    from session_manager import SessionManager
    mgr = SessionManager()
    metrics = mgr.get_all_sessions_metrics()
    for session in metrics:
        print(f"Session {session['session_id'][:8]}: "
              f"{session['request_count']} requests")
    """)


def demo_4_rl_learning():
    """DEMO 4: RL Learning Verification (TASK 2)"""
    section("DEMO 4: RL AGENT LEARNING VERIFICATION")
    print("""
Verify that RL Agent is learning:

Quick Check:
    python3 << 'EOF'
    from rl_agent import RLAgent
    agent = RLAgent('./honeypot_instance/rl.db')
    report = agent.verify_rl_learning()
    
    print(f"Is Learning: {report['is_learning']}")
    print(f"States: {report['total_unique_states']}")
    print(f"Q-values: {len(report['sample_q_table'])}")
    print(f"Recommendation: {report['recommendation']}")
    
    agent.close()
    EOF

What you should see:
    Is Learning: True
    States: 12-50 (varies with traffic)
    Q-values: Multiple state-action pairs
    Recommendation: ✓ RL Agent is LEARNING...

Detailed Report:
    python3 << 'EOF'
    import json
    from rl_agent import RLAgent
    
    agent = RLAgent('./honeypot_instance/rl.db')
    report = agent.verify_rl_learning()
    print(json.dumps(report, indent=2))
    agent.close()
    EOF

Output includes:
    - is_learning: Boolean status
    - total_unique_states: Number of distinct state-actions seen
    - sample_q_table: Top 10 learned state-action pairs
    - action_distribution: How many times each action was taken
    - exploration_rate: % of random vs learned decisions
    - recommendation: Human interpretation

Example Q-table entry:
    {
        "state": "/login|POST|brute_force",
        "action": 1,        # DELAY_ERROR action
        "q_value": 0.8234,  # Average reward for this
        "visits": 12,       # Times this was encountered
        "total_reward": 9.88
    }

RL Agent Actions:
    0 = NORMAL          (show fake homepage)
    1 = DELAY_ERROR     (500 error with delay)
    2 = FAKE_SUCCESS    (trick with fake data)
    3 = REDIRECT        (redirect to /login)
    4 = EXPOSE_DATA     (show honeypot trap data)

Check Training Progress:
    $ tail -10 honeypot_instance/logs/rl_agent.log
    
    Entries show:
    - EXPLORATION: random action (learning phase)
    - EXPLOITATION: best known action (using learned policy)
    - REWARD_UPDATE: Q-value changes
    """)


def demo_5_metrics():
    """DEMO 5: Performance Metrics Collection"""
    section("DEMO 5: METRICS & STATISTICS")
    print("""
Get comprehensive metrics:

1. Via HTTP Endpoint (while server running):
   $ curl http://localhost:8080/metrics | python3 -m json.tool
   
   Returns:
   {
       "uptime_seconds": 3600,
       "total_requests": 1523,
       "requests_per_second": 0.42,
       "attack_distribution": {
           "normal": 1400,
           "sqli": 45,
           "xss": 23,
           "brute_force": 55
       },
       "rl_action_distribution": {
           "0": 1200,
           "1": 180,
           "2": 92,
           "3": 45,
           "4": 6
       },
       "average_reward": 0.18,
       "top_attacking_ips": [
           {"ip": "192.168.1.1", "requests": 234},
           {"ip": "10.0.0.5", "requests": 156}
       ],
       "top_attacked_paths": [
           {"path": "/login", "requests": 456},
           {"path": "/", "requests": 234}
       ]
   }

2. Health Check:
   $ curl http://localhost:8080/health | python3 -m json.tool
   
   {
       "status": "healthy",
       "uptime": 3600.45,
       "timestamp": "2024-01-15T10:30:45.123"
   }

3. Readiness Check:
   $ curl http://localhost:8080/ready | python3 -m json.tool
   
   {
       "ready": true,
       "detector": true,
       "session_mgr": true,
       "response_engine": true,
       "rl_agent": true,
       "logger": true
   }

Key Metrics:
    - Total Requests: Traffic volume
    - RPS: Real-time throughput
    - Attack Distribution: What attacks detected
    - RL Actions: Which responses chosen
    - Top IPs: Primary attackers
    - Top Paths: Most targeted endpoints
    """)


def demo_6_logs():
    """DEMO 6: Structured Logging"""
    section("DEMO 6: STRUCTURED LOGGING")
    print("""
Two log formats are generated:

1. TEXT LOG (logs/access.log) - Human readable:
   
   [2024-01-15 10:30:45] 192.168.1.100 f4d3a8c2 POST /login -> 200 | 
   Attack: brute_force (conf:0.90) | RL_Ac: 1

   View:
   $ tail -20 honeypot_instance/logs/access.log

2. JSON LOG (logs/access_structured.json) - Machine parseable:

   {
       "timestamp": "2024-01-15T10:30:45.123456",
       "src_ip": "192.168.1.100",
       "method": "POST",
       "path": "/login",
       "query": "",
       "status": 200,
       "attack_tags": ["brute_force"],
       "confidence": 0.9,
       "rl_action_id": 1,
       "session_id": "f4d3a8c2b1e9...",
       "profile": "attacker"
   }

   View:
   $ tail -5 honeypot_instance/logs/access_structured.json | \\
     python3 -m json.tool

Parse JSON logs:
   python3 << 'EOF'
   import json
   
   with open('honeypot_instance/logs/access_structured.json') as f:
       for line in f:
           event = json.loads(line)
           print(f"{event['timestamp']} {event['src_ip']}: "
                 f"{event['attack_tags']} -> Action {event['rl_action_id']}")
   EOF

Analyze Attack Trends:
   python3 << 'EOF'
   import json
   from collections import Counter
   
   attacks = Counter()
   with open('honeypot_instance/logs/access_structured.json') as f:
       for line in f:
           event = json.loads(line)
           for tag in event.get('attack_tags', []):
               attacks[tag] += 1
   
   for attack, count in attacks.most_common():
       print(f"{attack}: {count} times")
   EOF
    """)


def demo_7_backwards_compat():
    """DEMO 7: Backwards Compatibility"""
    section("DEMO 7: BACKWARDS COMPATIBILITY")
    print("""
Old workflows still work without modification:

Manual Pipeline (Old Way):
   $ python3 booter.py firmware.bin
   $ python3 scanner.py -i 172.17.0.2
   $ python3 learner.py
   $ python3 manager.py --create
   $ cd honeypot_instance/
   $ python3 honeypot.py -m
   
   ✓ Works exactly as before
   ✓ New features automatically integrated
   ✓ No code changes needed

Auto Pipeline (Old Way):
   $ python3 auto.py firmware.bin
   $ cd honeypot_instance/
   $ python3 honeypot.py -m
   
   ✓ Works exactly as before
   ✓ New features automatically integrated

New Way (Simplified):
   $ python3 run_all.py firmware.bin
   
   ✓ Does all of the above in one command
   ✓ Same output
   ✓ Better logging
   ✓ More user-friendly
    """)


def main():
    """Run all demos"""
    section("FIRMPOT DEMO GUIDE")
    print("""
This guide shows all new features added to FirmPot.

Features implemented:
    ✓ TASK 1: Single entry point (run_all.py)
    ✓ TASK 2: RL learning verification
    ✓ TASK 3: Session tracking with request count
    ✓ TASK 4: Honeypot behavior (detection + tracing)
    ✓ TASK 5: Code cleanup
    ✓ TASK 6: Backwards compatibility
    """)

    demo_1_run_all()
    demo_2_attack_detection()
    demo_3_session_tracking()
    demo_4_rl_learning()
    demo_5_metrics()
    demo_6_logs()
    demo_7_backwards_compat()

    section("SUMMARY")
    print("""
Next Steps:

1. Try it yourself:
   python3 run_all.py firmware.bin

2. Generate test traffic:
   curl http://localhost:8080/
   curl "http://localhost:8080/?id=1' OR '1'='1"

3. Check logs while running:
   tail -f honeypot_instance/logs/access.log

4. Verify learning after run:
   python3 << 'EOF'
   from rl_agent import RLAgent
   agent = RLAgent('./honeypot_instance/rl.db')
   print(agent.verify_rl_learning()['recommendation'])
   EOF

5. Analyze metrics:
   curl http://localhost:8080/metrics | python3 -m json.tool

Documentation:
   - Read: ENHANCEMENTS.md (detailed documentation)
   - Read: det.txt (workflow overview)
    """)


if __name__ == "__main__":
    main()
