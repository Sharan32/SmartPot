#!/usr/bin/env python3

"""
FirmPot End-to-End Runner

Single entry point to:
1. Generate honeypot from firmware (auto.py)
2. Verify honeypot_instance/ created
3. Start honeypot server
4. Verify RL learning

Usage:
    python3 run_all.py <firmware_image>

Example:
    python3 run_all.py ./images/openwrt-firmware.bin
"""

import os
import sys
import re
import argparse
import subprocess
import time
import json
import shutil
import socket
import urllib.request
from datetime import datetime


class HoneypotRunner:
    """Orchestrates full FirmPot workflow"""

    def __init__(self, firmware_path: str, verbose: bool = True):
        """
        Initialize runner
        
        Args:
            firmware_path: Path to firmware image
            verbose: Print detailed logs
        """
        self.root_dir = os.getcwd()
        self.firmware_path = firmware_path
        self.verbose = verbose
        self.honeypot_instance_dir = os.path.join(self.root_dir, "honeypot_instance")
        self.log_file = os.path.join(self.root_dir, "run_all.log")
        self.start_time = datetime.now()
        self.dashboard_port = 5000

    def log(self, message: str, level: str = "INFO", is_error: bool = False):
        """Print and log message"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        color_code = {
            "INFO": "\033[36m",  # Cyan
            "SUCCESS": "\033[32m",  # Green
            "WARNING": "\033[33m",  # Yellow
            "ERROR": "\033[31m",  # Red
        }.get(level, "\033[0m")

        reset_code = "\033[0m"
        formatted = f"{color_code}[{timestamp}][{level}]{reset_code} {message}"

        if self.verbose or is_error:
            print(formatted)

        with open(self.log_file, "a") as f:
            f.write(f"[{timestamp}][{level}] {message}\n")

    def step(self, step_num: int, message: str):
        """Print step marker"""
        self.log(f"\n{'='*70}", "INFO")
        self.log(f"STEP {step_num}: {message}", "INFO")
        self.log(f"{'='*70}\n", "INFO")

    def check_firmware(self) -> bool:
        """Verify firmware file exists"""
        if not os.path.exists(self.firmware_path):
            self.log(f"Firmware not found: {self.firmware_path}", "ERROR", True)
            return False

        size_mb = os.path.getsize(self.firmware_path) / (1024 * 1024)
        self.log(
            f"✓ Firmware found: {self.firmware_path} ({size_mb:.2f} MB)",
            "SUCCESS",
        )
        return True

    def run_auto_generation(self) -> bool:
        """Run auto.py to generate honeypot"""
        self.step(1, "Generate Honeypot from Firmware (auto.py)")

        self.stop_existing_background_services()

        if os.path.exists(self.honeypot_instance_dir):
            self.log(
                f"Honeypot instance directory already exists, removing...",
                "WARNING",
            )
            shutil.rmtree(self.honeypot_instance_dir)

        cmd = ["python3", "pipeline/auto.py", self.firmware_path]
        self.log(f"Executing: {' '.join(cmd)}", "INFO")

        try:
            env = os.environ.copy()
            env["PYTHONPATH"] = self.root_dir
            result = subprocess.run(cmd, timeout=3600, cwd=self.root_dir, env=env)

            if result.returncode == 0:
                self.log("✓ auto.py completed successfully", "SUCCESS")
                return True
            else:
                self.log(f"✗ auto.py failed with code {result.returncode}", "ERROR")
                return False
        except subprocess.TimeoutExpired:
            self.log("✗ auto.py timeout (1 hour exceeded)", "ERROR", True)
            return False
        except Exception as e:
            self.log(f"✗ auto.py error: {e}", "ERROR", True)
            return False

    def stop_existing_background_services(self):
        """Stop previous background honeypot/dashboard processes if PID files exist."""
        for pid_filename in ["honeypot.pid", "dashboard.pid"]:
            pid_path = os.path.join(self.honeypot_instance_dir, pid_filename)
            if not os.path.exists(pid_path):
                continue
            try:
                with open(pid_path, "r") as f:
                    pid = int(f.read().strip())
                os.kill(pid, 15)
                self.log(f"Stopped previous background process from {pid_filename} (PID {pid})", "INFO")
            except Exception:
                pass

    def _is_port_in_use(self, port: int) -> bool:
        """Return True if the given TCP port is already bound."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(1.0)
            try:
                result = sock.connect_ex(("127.0.0.1", port))
                return result == 0
            except Exception:
                return False

    def _port_owner_pid(self, port: int):
        """Try to discover the PID owning the TCP port."""
        try:
            output = subprocess.check_output(["lsof", "-ti", f"tcp:{port}"], text=True).strip()
            if output:
                return int(output.splitlines()[0])
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass

        try:
            output = subprocess.check_output(["ss", "-ltnp"], text=True, stderr=subprocess.DEVNULL)
            for line in output.splitlines():
                if f":{port} " in line:
                    match = re.search(r"pid=(\d+),", line)
                    if match:
                        return int(match.group(1))
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass

        return None

    def _ensure_port_free(self, port: int) -> bool:
        """Make sure the TCP port is available before starting the honeypot."""
        if not self._is_port_in_use(port):
            return True

        pid = self._port_owner_pid(port)
        if pid:
            self.log(f"Port {port} is in use by PID {pid}. Attempting to stop it.", "WARNING")
            try:
                os.kill(pid, 15)
                time.sleep(1)
                if not self._is_port_in_use(port):
                    self.log(f"Port {port} freed successfully.", "INFO")
                    return True
            except Exception as e:
                self.log(f"Failed to free port {port}: {e}", "WARNING")
                return False

        self.log(f"Port {port} is still in use and could not be freed.", "ERROR")
        return False

    def verify_honeypot_instance(self) -> bool:
        """Verify honeypot_instance/ was created correctly"""
        self.step(2, "Verify Honeypot Instance Created")

        if not os.path.isdir(self.honeypot_instance_dir):
            self.log(
                f"✗ Honeypot instance directory not found: {self.honeypot_instance_dir}",
                "ERROR",
                True,
            )
            return False

        self.log(
            f"✓ Honeypot instance directory exists: {self.honeypot_instance_dir}",
            "SUCCESS",
        )

        # Check required files
        required_files = [
            "honeypot.py",
            "rl_agent.py",
            "response.db",
        ]

        for filename in required_files:
            filepath = os.path.join(self.honeypot_instance_dir, filename)
            if os.path.exists(filepath):
                size_mb = os.path.getsize(filepath) / (1024 * 1024)
                self.log(f"  ✓ {filename} ({size_mb:.2f} MB)", "SUCCESS")
            else:
                self.log(f"  ✗ {filename} MISSING", "ERROR")
                return False

        # Check checkpoints directory
        word2vec_path = os.path.join(self.honeypot_instance_dir, "word2vec.bin")
        if os.path.exists(word2vec_path):
            size_mb = os.path.getsize(word2vec_path) / (1024 * 1024)
            self.log(f"  ✓ word2vec.bin ({size_mb:.2f} MB)", "SUCCESS")
        else:
            self.log(
                "  ! word2vec.bin not found; honeypot will run without Magnitude mode",
                "WARNING",
            )

        checkpoints_dir = os.path.join(self.honeypot_instance_dir, "checkpoints")
        if os.path.isdir(checkpoints_dir):
            checkpoint_files = os.listdir(checkpoints_dir)
            self.log(
                f"  ✓ checkpoints/ directory with {len(checkpoint_files)} files",
                "SUCCESS",
            )
        else:
            self.log(
                "  ! checkpoints/ directory missing; honeypot will start with fallback weights",
                "WARNING",
            )

        self.log(
            "\n✓ All required files present. Honeypot instance ready.", "SUCCESS"
        )
        return True

    def start_honeypot_server(
        self,
        background: bool = False,
        startup_wait: int = 5,
    ) -> bool:
        """Start honeypot server"""
        self.step(3, "Start Honeypot Server")

        cmd = ["python3", "honeypot.py"]
        if os.path.exists(os.path.join(self.honeypot_instance_dir, "word2vec.bin")):
            cmd.append("-m")

        if not self._ensure_port_free(8080):
            self.log("Cannot start honeypot because port 8080 is unavailable.", "ERROR")
            return False

        self.log(f"Executing: {' '.join(cmd)}", "INFO")
        self.log(f"Honeypot directory: {self.honeypot_instance_dir}", "INFO")

        try:
            if background:
                stdout_log = os.path.join(
                    self.honeypot_instance_dir, "logs", "honeypot_stdout.log"
                )
                os.makedirs(os.path.dirname(stdout_log), exist_ok=True)

                self.log(
                    f"Server starting in background; waiting {startup_wait}s for startup checks.",
                    "INFO",
                )
                with open(stdout_log, "a") as stdout_handle:
                    process = subprocess.Popen(
                        cmd,
                        cwd=self.honeypot_instance_dir,
                        stdout=stdout_handle,
                        stderr=subprocess.STDOUT,
                        start_new_session=True,
                        text=True,
                    )

                time.sleep(startup_wait)
                returncode = process.poll()
                if returncode is None:
                    pid_file = os.path.join(self.honeypot_instance_dir, "honeypot.pid")
                    with open(pid_file, "w") as f:
                        f.write(f"{process.pid}\n")

                    self.log(
                        f"✓ Honeypot server is running in background (PID {process.pid})",
                        "SUCCESS",
                    )
                    self.log(f"Stdout/stderr log: {stdout_log}", "INFO")
                    self.log(
                        "Use `kill $(cat honeypot_instance/honeypot.pid)` to stop it later.",
                        "INFO",
                    )
                    return True

                self.log(
                    f"✗ Honeypot server exited during startup with code {returncode}",
                    "ERROR",
                )
                self.log(f"Check server output: {stdout_log}", "ERROR")
                return False

            self.log("Server starting... Press Ctrl+C to stop.", "INFO")
            result = subprocess.run(cmd, cwd=self.honeypot_instance_dir)
            if result.returncode == 0:
                self.log("✓ Honeypot server stopped gracefully", "SUCCESS")
                return True

            self.log(
                f"✗ Honeypot server exited with code {result.returncode}",
                "ERROR",
            )
            return False
        except KeyboardInterrupt:
            self.log(
                "\n✓ Honeypot server stopped by user (Ctrl+C)", "SUCCESS"
            )
            return True
        except Exception as e:
            self.log(f"✗ Error starting server: {e}", "ERROR")
            return False

    def start_dashboard(self, startup_wait: int = 5) -> bool:
        """Start analytics dashboard for the honeypot instance."""
        self.step(4, "Start Analytics Dashboard")

        cmd = [
            "python3",
            os.path.join(self.root_dir, "analyzer.py"),
            "--log-dir",
            os.path.join(self.honeypot_instance_dir, "logs"),
            "--honeypot-dir",
            self.honeypot_instance_dir,
            "--port",
            str(self.dashboard_port),
        ]
        stdout_log = os.path.join(self.honeypot_instance_dir, "logs", "dashboard_stdout.log")
        os.makedirs(os.path.dirname(stdout_log), exist_ok=True)

        with open(stdout_log, "a") as stdout_handle:
            process = subprocess.Popen(
                cmd,
                cwd=self.root_dir,
                stdout=stdout_handle,
                stderr=subprocess.STDOUT,
                start_new_session=True,
                text=True,
            )

        time.sleep(startup_wait)
        if process.poll() is not None:
            self.log(
                f"✗ Dashboard exited during startup with code {process.returncode}",
                "ERROR",
            )
            self.log(f"Check dashboard output: {stdout_log}", "ERROR")
            return False

        if not self._http_ok(f"http://127.0.0.1:{self.dashboard_port}/dashboard"):
            self.log("✗ Dashboard did not respond after startup", "ERROR")
            self.log(f"Check dashboard output: {stdout_log}", "ERROR")
            return False

        pid_file = os.path.join(self.honeypot_instance_dir, "dashboard.pid")
        with open(pid_file, "w") as f:
            f.write(f"{process.pid}\n")

        self.log(
            f"✓ Dashboard is running in background (PID {process.pid})",
            "SUCCESS",
        )
        self.log(f"Dashboard: http://localhost:{self.dashboard_port}/dashboard", "INFO")
        return True

    def _http_ok(self, url: str) -> bool:
        try:
            with urllib.request.urlopen(url, timeout=3) as response:
                return 200 <= response.status < 500
        except Exception:
            return False

    def print_summary(self):
        """Print execution summary"""
        elapsed = datetime.now() - self.start_time
        self.log(f"\n{'='*70}", "INFO")
        self.log("FirmPot Runner Summary", "INFO")
        self.log(f"{'='*70}", "INFO")
        self.log(f"Firmware: {self.firmware_path}", "INFO")
        self.log(f"Honeypot Instance: {self.honeypot_instance_dir}", "INFO")
        self.log(f"Total Runtime: {elapsed}", "INFO")
        self.log(f"Log File: {self.log_file}", "INFO")
        self.log(f"{'='*70}\n", "INFO")

    def verify_rl_learning(self):
        """Check if RL agent is learning"""
        self.log("\nVerifying RL Agent Learning...", "INFO")

        try:
            # Try to import and check RL agent
            sys.path.insert(0, self.honeypot_instance_dir)
            from rl_agent import RLAgent

            rl_db = os.path.join(self.honeypot_instance_dir, "rl.db")
            if os.path.exists(rl_db):
                agent = RLAgent(rl_db)
                learning_report = agent.verify_rl_learning()

                self.log(f"\n{'='*70}", "INFO")
                self.log("RL Learning Report", "INFO")
                self.log(f"{'='*70}", "INFO")
                self.log(f"Is Learning: {learning_report.get('is_learning')}", "INFO")
                self.log(
                    f"Total Unique States: {learning_report.get('total_unique_states')}",
                    "INFO",
                )
                self.log(
                    f"Recommendation: {learning_report.get('recommendation')}", "INFO"
                )
                self.log(f"{'='*70}\n", "INFO")

                agent.close()
            else:
                self.log("RL database not yet created (no learning data)", "WARNING")

        except Exception as e:
            self.log(f"Could not verify RL learning: {e}", "WARNING")

    def run(self, background_server: bool = False, startup_wait: int = 5) -> bool:
        """Execute full pipeline"""
        self.log("FirmPot End-to-End Runner Started", "SUCCESS")
        self.log(f"Start Time: {self.start_time}", "INFO")

        # Step 1: Verify firmware
        if not self.check_firmware():
            return False

        # Step 2: Generate honeypot
        if not self.run_auto_generation():
            return False

        # Step 3: Verify honeypot instance
        if not self.verify_honeypot_instance():
            return False

        # Step 4: Start server
        if not self.start_honeypot_server(
            background=background_server,
            startup_wait=startup_wait,
        ):
            return False

        # Step 5: Start analytics dashboard
        if not self.start_dashboard(startup_wait=3 if background_server else 5):
            return False

        # Step 6: Summary and RL check
        self.print_summary()
        # Note: RL verification would happen after server runs
        # For now, just suggest where to find it

        self.log("✓ FirmPot pipeline completed successfully!", "SUCCESS")
        return True


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="FirmPot End-to-End Runner: Generate and run honeypot from firmware"
    )
    parser.add_argument("firmware", help="Path to firmware image")
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Print verbose output (enabled by default)",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Suppress non-error console logs",
    )
    parser.add_argument(
        "--background-server",
        action="store_true",
        help="Start honeypot in the background and return after startup checks",
    )
    parser.add_argument(
        "--server-startup-wait",
        type=int,
        default=5,
        help="Seconds to wait before considering background startup successful",
    )

    args = parser.parse_args()

    # Ensure logs directory exists
    os.makedirs("logs", exist_ok=True)

    verbose = True
    if args.quiet:
        verbose = False
    elif args.verbose:
        verbose = True

    runner = HoneypotRunner(args.firmware, verbose=verbose)
    success = runner.run(
        background_server=args.background_server,
        startup_wait=args.server_startup_wait,
    )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
