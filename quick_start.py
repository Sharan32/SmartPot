#!/usr/bin/env python3

"""
Quick Start Helper for FirmPot

This script helps you get the honeypot running quickly.
It checks your setup and provides options to start the server.
"""

import os
import subprocess
import sys

from rl_agent import RLAgent


DEFAULT_PORT = int(os.getenv("FIRMPOT_PORT", "8080"))


def check_setup():
    """Check if honeypot_instance is ready"""
    print("[*] Checking FirmPot setup...\n")
    
    checks = {
        "honeypot_instance/": os.path.isdir("honeypot_instance"),
        "honeypot_instance/honeypot.py": os.path.isfile("honeypot_instance/honeypot.py"),
        "honeypot_instance/rl_agent.py": os.path.isfile("honeypot_instance/rl_agent.py"),
        "config.json": os.path.isfile("config.json"),
    }
    
    all_good = True
    for check, result in checks.items():
        status = "✓" if result else "✗"
        print(f"  {status} {check}")
        if not result:
            all_good = False
    
    print()
    return all_good


def start_honeypot():
    """Start the honeypot server"""
    print("[*] Starting FirmPot Honeypot Server...\n")
    
    cwd = os.path.join(os.getcwd(), "honeypot_instance")
    
    try:
        os.chdir(cwd)
        print(f"[*] Working directory: {cwd}")
        print("[*] Starting: python3 honeypot.py -m\n")
        print("=" * 70)
        print(f"Server is running on http://localhost:{DEFAULT_PORT}")
        print("Press Ctrl+C to stop\n")
        print("Test commands (in another terminal):")
        print(f"  curl http://localhost:{DEFAULT_PORT}/")
        print(f"  curl http://localhost:{DEFAULT_PORT}/health | jq .")
        print(f"  curl http://localhost:{DEFAULT_PORT}/metrics | jq .")
        print("=" * 70 + "\n")
        
        subprocess.run(["python3", "honeypot.py", "-m"])
    except KeyboardInterrupt:
        print("\n\n[*] Server stopped by user")
    except Exception as e:
        print(f"[!] Error: {e}")
        sys.exit(1)


def show_options():
    """Show available options"""
    print("\n" + "=" * 70)
    print("FirmPot Quick Start Options:")
    print("=" * 70)
    
    print("\n1. START HONEYPOT SERVER (Recommended)")
    print("   $ python3 quick_start.py start")
    print(f"   Starts the honeypot on http://localhost:{DEFAULT_PORT}")
    
    print("\n2. TEST HONEYPOT (Run in another terminal)")
    print(f"   $ curl http://localhost:{DEFAULT_PORT}/")
    print(f"   $ curl http://localhost:{DEFAULT_PORT}/metrics | jq .")

    print("\n3. VIEW DOCUMENTATION")
    print("   $ cat QUICKSTART.md")
    print("   $ cat IMPLEMENTATION_SUMMARY.md")
    print("   $ python3 DEMO_GUIDE.py")

    print("\n4. VERIFY RL LEARNING")
    print("   $ python3 quick_start.py rl_check")

    print("\n5. GENERATE NEW HONEYPOT (If you have firmware)")
    print("   $ python3 run_all.py /path/to/firmware.bin")
    
    print("\n" + "=" * 70 + "\n")


def main():
    if len(sys.argv) <= 1:
        show_options()
        return

    if sys.argv[1] == "start":
        if check_setup():
            start_honeypot()
        else:
            print("[!] Setup incomplete. Please run from FirmPot root directory.")
            sys.exit(1)
        return

    if sys.argv[1] == "rl_check":
        rl_db = os.path.join("honeypot_instance", "rl.db")
        if not os.path.exists(rl_db):
            print("[!] RL database not found. Start the honeypot and generate some traffic first.")
            sys.exit(1)

        agent = RLAgent(rl_db)
        try:
            report = agent.verify_rl_learning()
            print(report["recommendation"])
            print(f"Unique states: {report['total_unique_states']}")
            print(f"Total Q entries: {report['total_q_entries']}")
        finally:
            agent.close()
        return

    show_options()


if __name__ == "__main__":
    main()
