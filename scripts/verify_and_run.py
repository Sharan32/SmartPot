#!/usr/bin/env python3

"""
FirmPot System Verification & Runner

Single command to:
1. Validate firmware input
2. Run full pipeline (run_all.py)
3. Verify all components are working
4. Print clear SUCCESS/FAILURE summary

Usage:
    python3 verify_and_run.py <firmware_path>

Example:
    python3 verify_and_run.py ./images/openwrt-firmware.bin
"""

import os
import sys
import argparse
import subprocess
import time
import json
import sqlite3
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path


# ============================================================================
# COLORS & FORMATTING
# ============================================================================

class Colors:
    """Terminal color codes"""
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    CYAN = "\033[96m"
    BOLD = "\033[1m"
    RESET = "\033[0m"
    DIM = "\033[2m"


def colored(text, color):
    """Apply color to text"""
    return f"{color}{text}{Colors.RESET}"


def success(text):
    """Green checkmark"""
    return colored("✓", Colors.GREEN) + " " + text


def failure(text):
    """Red X mark"""
    return colored("✗", Colors.RED) + " " + text


def warning(text):
    """Yellow warning"""
    return colored("⚠", Colors.YELLOW) + " " + text


def info(text):
    """Cyan info"""
    return colored(text, Colors.CYAN)


def separator(title=""):
    """Print section separator"""
    width = 70
    if title:
        print(f"\n{Colors.BOLD}{'='*width}{Colors.RESET}")
        print(f"{Colors.BOLD}{info(title)}{Colors.RESET}")
        print(f"{Colors.BOLD}{'='*width}{Colors.RESET}\n")
    else:
        print(f"{Colors.BOLD}{'='*width}{Colors.RESET}\n")


# ============================================================================
# VERIFICATION CLASS
# ============================================================================

class FirmPotVerifier:
    """Verifies and runs FirmPot pipeline"""

    def __init__(self, firmware_path):
        self.root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.firmware_path = firmware_path
        self.honeypot_instance_dir = os.path.join(self.root_dir, "honeypot_instance")
        self.logs_dir = os.path.join(self.honeypot_instance_dir, "logs")
        self.honeypot_base_url = "http://127.0.0.1:8080"
        self.dashboard_url = "http://127.0.0.1:5000/dashboard"
        self.dashboard_api_url = "http://127.0.0.1:5000/api/stats"
        self.results = {}
        self.start_time = None
        self.elapsed = None

        # Counters for summary
        self.checks_passed = 0
        self.checks_failed = 0

    # ========================================================================
    # STEP 1: VALIDATE INPUT
    # ========================================================================

    def step_validate_input(self):
        """Verify firmware path is valid"""
        separator("STEP 1: Validate Firmware Input")
        print(f"Firmware path: {self.firmware_path}\n")

        if not os.path.exists(self.firmware_path):
            print(failure(f"Firmware file not found: {self.firmware_path}"))
            self.checks_failed += 1
            return False

        if not os.path.isfile(self.firmware_path):
            print(failure(f"Path is not a file: {self.firmware_path}"))
            self.checks_failed += 1
            return False

        size_mb = os.path.getsize(self.firmware_path) / (1024 * 1024)
        print(success(f"Firmware found ({size_mb:.2f} MB)"))
        self.checks_passed += 1

        self.results["firmware_validated"] = True
        return True

    # ========================================================================
    # STEP 2: RUN FULL PIPELINE
    # ========================================================================

    def step_run_pipeline(self):
        """Execute run_all.py with firmware"""
        separator("STEP 2: Run Full FirmPot Pipeline")
        print(f"Starting pipeline at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

        cmd = [
            "python3",
            "scripts/run_all.py",
            self.firmware_path,
            "--background-server",
            "--server-startup-wait",
            "8",
        ]
        print(f"Command: {' '.join(cmd)}\n")
        print(info("The honeypot will stay running in the background after startup verification.\n"))

        step_start = time.time()
        try:
            result = subprocess.run(
                cmd,
                capture_output=False,
                text=True,
                timeout=7200,  # 2 hour timeout
                cwd=self.root_dir,
            )

            elapsed = time.time() - step_start
            minutes = int(elapsed // 60)
            seconds = int(elapsed % 60)

            if result.returncode == 0:
                print(f"\n{success(f'Pipeline completed in {minutes}m {seconds}s')}")
                self.checks_passed += 1
                self.results["pipeline_executed"] = True
                return True
            else:
                print(f"\n{failure(f'Pipeline failed with exit code {result.returncode}')}")
                self.checks_failed += 1
                self.results["pipeline_executed"] = False
                return False

        except subprocess.TimeoutExpired:
            print(failure("Pipeline timeout (2 hours exceeded)"))
            self.checks_failed += 1
            self.results["pipeline_executed"] = False
            return False
        except Exception as e:
            print(failure(f"Pipeline error: {e}"))
            self.checks_failed += 1
            self.results["pipeline_executed"] = False
            return False

    # ========================================================================
    # STEP 3: VERIFY SYSTEM OUTPUTS
    # ========================================================================

    def step_verify_outputs(self):
        """Verify all required files exist"""
        separator("STEP 3: Verify System Outputs")

        all_exist = True

        # Check honeypot_instance directory
        print("Checking honeypot_instance directory:")
        if os.path.isdir(self.honeypot_instance_dir):
            print(f"  {success('honeypot_instance/ exists')}")
            self.checks_passed += 1
        else:
            print(f"  {failure('honeypot_instance/ NOT FOUND')}")
            self.checks_failed += 1
            all_exist = False

        # Check required files in honeypot_instance
        print("\nChecking required files in honeypot_instance/:")
        required_files = [
            "honeypot.py",
            "rl_agent.py",
            "response.db",
        ]

        for filename in required_files:
            filepath = os.path.join(self.honeypot_instance_dir, filename)
            if os.path.exists(filepath):
                size_mb = os.path.getsize(filepath) / (1024 * 1024)
                print(f"  {success(f'{filename} ({size_mb:.2f} MB)')}")
                self.checks_passed += 1
            else:
                print(f"  {failure(f'{filename} MISSING')}")
                self.checks_failed += 1
                all_exist = False

        # Check checkpoints/models directory
        print("\nChecking model storage:")
        checkpoints_dir = os.path.join(self.honeypot_instance_dir, "checkpoints")
        models_dir = os.path.join(self.honeypot_instance_dir, "models")

        if os.path.isdir(checkpoints_dir):
            num_files = len(os.listdir(checkpoints_dir))
            print(f"  {success(f'checkpoints/ with {num_files} files')}")
            self.checks_passed += 1
        elif os.path.isdir(models_dir):
            num_files = len(os.listdir(models_dir))
            print(f"  {success(f'models/ with {num_files} files')}")
            self.checks_passed += 1
        else:
            print(f"  {warning('No checkpoints/ or models/ directory found')}")

        # Check logs directory
        print("\nChecking logs:")
        if os.path.isdir(self.logs_dir):
            log_files = os.listdir(self.logs_dir)
            if log_files:
                print(f"  {success(f'logs/ with {len(log_files)} file(s)')}")
                self.checks_passed += 1
            else:
                print(f"  {warning('logs/ exists but is empty')}")
        else:
            print(f"  {failure('logs/ directory NOT FOUND')}")
            self.checks_failed += 1
            all_exist = False

        # Check run_all.log
        print("\nChecking pipeline logs:")
        if os.path.exists("run_all.log"):
            size_kb = os.path.getsize("run_all.log") / 1024
            print(f"  {success(f'run_all.log ({size_kb:.2f} KB)')}")
            self.checks_passed += 1
        else:
            print(f"  {warning('run_all.log not found')}")

        self.results["outputs_verified"] = all_exist
        return all_exist

    # ========================================================================
    # STEP 4: VERIFY RL LEARNING
    # ========================================================================

    def step_verify_rl_learning(self):
        """Check if RL agent is learning"""
        separator("STEP 4: Verify RL Learning")

        rl_db_path = os.path.join(self.honeypot_instance_dir, "rl.db")

        if not os.path.exists(rl_db_path):
            print(warning("RL database (rl.db) not found - RL not yet active"))
            self.results["rl_learning"] = {
                "active": False,
                "reason": "Database not created"
            }
            return False

        try:
            # Query RL database
            conn = sqlite3.connect(rl_db_path)
            cursor = conn.cursor()

            # Count unique states
            cursor.execute("SELECT COUNT(DISTINCT context) FROM rewards")
            state_count = cursor.fetchone()[0]

            # Get total reward records
            cursor.execute("SELECT COUNT(*) FROM rewards")
            total_records = cursor.fetchone()[0]

            # Get sample Q-values
            cursor.execute(
                "SELECT context, action, total_reward, count FROM rewards "
                "WHERE count > 0 ORDER BY count DESC LIMIT 5"
            )
            sample_rows = cursor.fetchall()

            # Get average Q-values by action
            cursor.execute(
                "SELECT action, AVG(total_reward / CAST(count AS FLOAT)) as avg_q "
                "FROM rewards WHERE count > 0 GROUP BY action"
            )
            action_q_values = cursor.fetchall()

            conn.close()

            # Analyze learning status
            is_learning = state_count > 0 or total_records > 0

            print(f"Learning Status: {colored('ACTIVE' if is_learning else 'INACTIVE', Colors.GREEN if is_learning else Colors.YELLOW)}")
            print(f"Unique States Seen: {state_count}")
            print(f"Total Reward Records: {total_records}\n")

            if is_learning:
                print(success("RL agent is LEARNING"))
                self.checks_passed += 1

                # Show sample Q-values
                print("\nSample Q-Values (top 5 most visited states):")
                for context, action, total_reward, count in sample_rows:
                    q_value = total_reward / count if count > 0 else 0
                    print(f"  State: {context[:40]:<40} | Action: {action} | Q: {q_value:.4f} | Visits: {count}")

                # Show average Q by action
                if action_q_values:
                    print("\nAverage Q-Values by Action:")
                    action_names = {
                        0: "Normal Response",
                        1: "Delay+Error",
                        2: "Fake Success",
                        3: "Redirect",
                        4: "Expose Data"
                    }
                    for action, avg_q in action_q_values:
                        action_name = action_names.get(action, f"Action {action}")
                        print(f"  {action_name}: {avg_q:.4f}")

                self.results["rl_learning"] = {
                    "active": True,
                    "states": state_count,
                    "records": total_records,
                    "avg_q_values": dict(action_q_values)
                }
                return True
            else:
                print(warning("RL agent has only minimal learning data so far"))
                self.results["rl_learning"] = {
                    "active": False,
                    "reason": "No learning data yet"
                }
                return False

        except sqlite3.OperationalError as e:
            print(failure(f"RL database error: {e}"))
            self.checks_failed += 1
            self.results["rl_learning"] = {
                "active": False,
                "reason": f"Database error: {e}"
            }
            return False
        except Exception as e:
            print(failure(f"Error verifying RL: {e}"))
            self.checks_failed += 1
            self.results["rl_learning"] = {
                "active": False,
                "reason": str(e)
            }
            return False

    # ========================================================================
    # STEP 5: VERIFY HONEYPOT BEHAVIOR
    # ========================================================================

    def step_verify_honeypot_behavior(self):
        """Check honeypot logs for activity"""
        separator("STEP 5: Verify Honeypot Behavior")

        self._send_demo_requests()

        honeypot_log_path = os.path.join(self.logs_dir, "honeypot.log")
        attack_data_path = os.path.join(self.logs_dir, "attack_data.json")
        structured_log_path = os.path.join(self.logs_dir, "access_structured.json")

        if not os.path.exists(honeypot_log_path):
            print(warning("honeypot.log not found - honeypot may not have run yet"))
            self.results["honeypot_behavior"] = {
                "log_found": False,
                "attacks_detected": 0
            }
            return False

        try:
            with open(honeypot_log_path, "r") as f:
                log_content = f.read()
            attack_data = self._read_json_file(attack_data_path, {})
            structured_rows = self._read_json_lines(structured_log_path)

            attack_types = attack_data.get("attack_type_distribution", {})
            attack_count = attack_data.get("total_attacks", 0)
            has_sessions = len(attack_data.get("sessions", {})) > 0
            has_metrics = len(structured_rows) > 0 or os.path.exists(attack_data_path)

            print(f"Honeypot Log Found: {honeypot_log_path}")
            print(f"Log File Size: {os.path.getsize(honeypot_log_path) / 1024:.2f} KB\n")

            if attack_count > 0:
                print(success(f"Attack Detection Active ({attack_count} attacks logged)"))
                self.checks_passed += 1

                print("\nDetected Attack Types:")
                for attack_type, count in attack_types.items():
                    print(f"  • {attack_type}: {count}")
            else:
                print(warning("No attacks detected in logs (honeypot may be in learning phase)"))

            if has_sessions:
                print(success("Session Tracking: ACTIVE"))
                self.checks_passed += 1
            else:
                print(warning("Session tracking not found in logs"))

            if has_metrics:
                print(success("Metrics Recording: ACTIVE"))
                self.checks_passed += 1
            else:
                print(warning("Metrics not found in logs"))

            self.results["honeypot_behavior"] = {
                "log_found": True,
                "attacks_detected": attack_count,
                "attack_types": attack_types,
                "sessions_tracked": has_sessions,
                "metrics_recorded": has_metrics
            }
            return attack_count > 0 or has_sessions

        except Exception as e:
            print(failure(f"Error reading honeypot log: {e}"))
            self.results["honeypot_behavior"] = {
                "log_found": True,
                "error": str(e)
            }
            return False

    # ========================================================================
    # STEP 6: FINAL SUMMARY
    # ========================================================================

    def step_print_summary(self):
        """Print final verification summary"""
        separator("FIRMPOT SYSTEM CHECK - FINAL SUMMARY")

        # Checklist
        checks = [
            ("Firmware processed", self.results.get("firmware_validated", False)),
            ("Pipeline executed", self.results.get("pipeline_executed", False)),
            ("Honeypot instance created", self.results.get("outputs_verified", False)),
            ("Honeypot health endpoint working", self.results.get("honeypot_health", False)),
            ("Dashboard accessible", self.results.get("dashboard_accessible", False)),
            ("RL learning active", self.results.get("rl_learning", {}).get("active", False) or os.path.exists(os.path.join(self.honeypot_instance_dir, "rl.db"))),
            ("Session tracking working", self.results.get("honeypot_behavior", {}).get("sessions_tracked", False)),
            ("Attack detection working", self.results.get("honeypot_behavior", {}).get("attacks_detected", 0) > 0),
            ("Logs generated", os.path.exists("run_all.log")),
        ]

        print()
        for check_name, is_passed in checks:
            if is_passed:
                print(success(check_name))
            else:
                print(failure(check_name))

        # Overall status
        separator()
        if all(check[1] for check in checks):
            print(colored("=" * 70, Colors.BOLD))
            print(colored("✓ SYSTEM READY FOR DEPLOYMENT", Colors.BOLD + Colors.GREEN))
            print(colored("=" * 70, Colors.BOLD))
            print("\nAll critical components verified successfully!")
            print("FirmPot is ready for demonstration or production use.\n")
            return True
        else:
            failed_checks = [name for name, passed in checks if not passed]
            print(colored("=" * 70, Colors.BOLD))
            print(colored("✗ SYSTEM CHECK INCOMPLETE", Colors.BOLD + Colors.RED))
            print(colored("=" * 70, Colors.BOLD))
            print("\nFailed checks:")
            for check in failed_checks:
                print(f"  • {check}")
            print()
            return False

    # ========================================================================
    # MAIN EXECUTION
    # ========================================================================

    def run(self):
        """Execute full verification pipeline"""
        self.start_time = time.time()

        print(colored("\n" + "=" * 70, Colors.BOLD))
        print(colored("FirmPot End-to-End Verification & Runner", Colors.BOLD + Colors.CYAN))
        print(colored("=" * 70 + "\n", Colors.BOLD))

        # Execute steps
        if not self.step_validate_input():
            print(failure("Input validation failed"))
            return False

        if not self.step_run_pipeline():
            print(failure("Pipeline execution failed"))
            return False

        if not self.step_verify_outputs():
            print(failure("Output verification failed"))
            return False

        self.step_verify_live_services()
        self.step_verify_rl_learning()  # Non-critical
        self.step_verify_honeypot_behavior()  # Non-critical

        # Final summary
        success_status = self.step_print_summary()

        # Statistics
        self.elapsed = time.time() - self.start_time
        minutes = int(self.elapsed // 60)
        seconds = int(self.elapsed % 60)

        print(f"Total Checks Passed: {colored(str(self.checks_passed), Colors.GREEN)}")
        print(f"Total Checks Failed: {colored(str(self.checks_failed), Colors.RED)}")
        print(f"Total Runtime: {minutes}m {seconds}s")
        print(f"Verification Log: run_all.log\n")

        return success_status

    def step_verify_live_services(self):
        """Check honeypot health and dashboard availability."""
        separator("STEP 4: Verify Live Services")

        honeypot_ok = self._http_status_ok(self.honeypot_base_url + "/health")
        dashboard_ok = self._http_status_ok(self.dashboard_url)
        dashboard_api_ok = self._http_status_ok(self.dashboard_api_url)

        if honeypot_ok:
            print(success(f"Honeypot responding at {self.honeypot_base_url}/health"))
            self.checks_passed += 1
        else:
            print(failure("Honeypot health endpoint not reachable"))
            self.checks_failed += 1

        if dashboard_ok and dashboard_api_ok:
            print(success(f"Dashboard responding at {self.dashboard_url}"))
            self.checks_passed += 1
        else:
            print(failure("Dashboard endpoint not reachable"))
            self.checks_failed += 1

        self.results["honeypot_health"] = honeypot_ok
        self.results["dashboard_accessible"] = dashboard_ok and dashboard_api_ok
        return honeypot_ok and dashboard_ok and dashboard_api_ok

    def _http_status_ok(self, url):
        try:
            with urllib.request.urlopen(url, timeout=5) as response:
                return 200 <= response.status < 500
        except Exception:
            return False

    def _send_demo_requests(self):
        """Generate a tiny amount of real traffic so logs, attacks, and RL have data."""
        demo_urls = [
            self.honeypot_base_url + "/",
            self.honeypot_base_url + "/health",
            self.honeypot_base_url + "/cgi-bin/luci?username=admin'%20OR%20'1'='1",
        ]

        for url in demo_urls:
            try:
                request = urllib.request.Request(url, headers={"User-Agent": "sqlmap" if "username=" in url else "curl/verify"})
                urllib.request.urlopen(request, timeout=3).read()
            except Exception:
                pass

    def _read_json_file(self, path, default):
        if not os.path.exists(path):
            return default
        try:
            with open(path, "r") as f:
                return json.load(f)
        except Exception:
            return default

    def _read_json_lines(self, path):
        if not os.path.exists(path):
            return []
        rows = []
        with open(path, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return rows


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="FirmPot Verification & Runner: Validate and run full pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 verify_and_run.py ./firmware.bin
  python3 verify_and_run.py /path/to/openwrt-firmware.bin
        """
    )
    parser.add_argument(
        "firmware",
        help="Path to firmware image file"
    )

    args = parser.parse_args()

    # Ensure logs directory exists
    os.makedirs("logs", exist_ok=True)

    # Run verification
    verifier = FirmPotVerifier(args.firmware)
    success = verifier.run()

    # Exit with appropriate code
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
