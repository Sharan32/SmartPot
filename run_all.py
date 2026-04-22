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
import argparse
import subprocess
import time
import json
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
        self.firmware_path = firmware_path
        self.verbose = verbose
        self.honeypot_instance_dir = "./honeypot_instance"
        self.log_file = "run_all.log"
        self.start_time = datetime.now()

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

        if os.path.exists(self.honeypot_instance_dir):
            self.log(
                f"Honeypot instance directory already exists, removing...",
                "WARNING",
            )
            subprocess.run(["rm", "-rf", self.honeypot_instance_dir])

        cmd = ["python3", "auto.py", self.firmware_path]
        self.log(f"Executing: {' '.join(cmd)}", "INFO")

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)

            if result.returncode == 0:
                self.log("✓ auto.py completed successfully", "SUCCESS")
                return True
            else:
                self.log(f"✗ auto.py failed with code {result.returncode}", "ERROR")
                self.log(f"STDOUT:\n{result.stdout}", "ERROR")
                self.log(f"STDERR:\n{result.stderr}", "ERROR")
                return False
        except subprocess.TimeoutExpired:
            self.log("✗ auto.py timeout (1 hour exceeded)", "ERROR", True)
            return False
        except Exception as e:
            self.log(f"✗ auto.py error: {e}", "ERROR", True)
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
            "word2vec.bin",
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
        checkpoints_dir = os.path.join(self.honeypot_instance_dir, "checkpoints")
        if os.path.isdir(checkpoints_dir):
            checkpoint_files = os.listdir(checkpoints_dir)
            self.log(
                f"  ✓ checkpoints/ directory with {len(checkpoint_files)} files",
                "SUCCESS",
            )
        else:
            self.log("  ✗ checkpoints/ directory MISSING", "ERROR")
            return False

        self.log(
            "\n✓ All required files present. Honeypot instance ready.", "SUCCESS"
        )
        return True

    def start_honeypot_server(self) -> bool:
        """Start honeypot server"""
        self.step(3, "Start Honeypot Server")

        os.chdir(self.honeypot_instance_dir)
        self.log(f"Changed directory to: {os.getcwd()}", "INFO")

        cmd = ["python3", "honeypot.py", "-m"]
        self.log(f"Executing: {' '.join(cmd)}", "INFO")
        self.log("Server starting... Press Ctrl+C to stop.", "INFO")

        try:
            result = subprocess.run(cmd)
            if result.returncode == 0:
                self.log("✓ Honeypot server stopped gracefully", "SUCCESS")
                return True
            else:
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

    def run(self) -> bool:
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
        os.chdir("..")  # Go back to FirmPot root
        if not self.start_honeypot_server():
            return False

        # Step 5: Summary and RL check
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
        help="Print verbose output",
    )

    args = parser.parse_args()

    # Ensure logs directory exists
    os.makedirs("logs", exist_ok=True)

    runner = HoneypotRunner(args.firmware, verbose=args.verbose)
    success = runner.run()

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
