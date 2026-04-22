"""
Structured Logger: Logs honeypot events in structured format
"""

import json
import os
from datetime import datetime
from typing import Dict, Any


class StructuredLogger:
    """
    Logs honeypot events in both JSON and text formats.
    Tracks: requests, responses, attacks, sessions, RL decisions
    """

    def __init__(
        self, log_dir: str, json_log_filename: str, text_log_filename: str
    ):
        """
        Initialize logger
        
        Args:
            log_dir: Directory for log files
            json_log_filename: JSON log file name
            text_log_filename: Text log file name
        """
        self.log_dir = log_dir
        self.json_log_path = os.path.join(log_dir, json_log_filename)
        self.text_log_path = os.path.join(log_dir, text_log_filename)

        # Ensure log directory exists
        os.makedirs(log_dir, exist_ok=True)

    def log_event(self, event: Dict[str, Any]):
        """
        Log a structured event
        
        Args:
            event: Event dict containing:
                - src_ip: source IP
                - method: HTTP method
                - path: request path
                - query: query string
                - body: request body
                - headers: request headers
                - status: response status
                - attack_tags: detected attack types
                - confidence: attack confidence
                - rl_action_id: RL action chosen
                - profile: session profile
                - session_id: session identifier
        """
        # Add timestamp
        event["timestamp"] = datetime.now().isoformat()

        # JSON log
        try:
            with open(self.json_log_path, "a") as f:
                f.write(json.dumps(event, default=str) + "\n")
        except Exception as e:
            print(f"[!] Error writing JSON log: {e}")

        # Text log (human-readable)
        try:
            log_line = self._format_text_log(event)
            with open(self.text_log_path, "a") as f:
                f.write(log_line + "\n")
        except Exception as e:
            print(f"[!] Error writing text log: {e}")

    def _format_text_log(self, event: Dict) -> str:
        """Format event as human-readable log line"""
        timestamp = event.get("timestamp", "?")
        src_ip = event.get("src_ip", "?")
        method = event.get("method", "?")
        path = event.get("path", "?")
        status = event.get("status", "?")
        attack_tags = ",".join(event.get("attack_tags", ["normal"]))
        confidence = event.get("confidence", 0.0)
        rl_action = event.get("rl_action_id", "?")
        session_id = event.get("session_id", "?")[:8]

        return (
            f"[{timestamp}] {src_ip} {session_id} "
            f"{method} {path} -> {status} | "
            f"Attack: {attack_tags} (conf:{confidence:.2f}) | "
            f"RL_Ac: {rl_action}"
        )

    def log_attack(self, src_ip: str, path: str, attack_type: str, confidence: float):
        """Log an attack event"""
        self.log_event(
            {
                "src_ip": src_ip,
                "event_type": "attack",
                "method": "UNKNOWN",
                "path": path,
                "query": "",
                "body": "",
                "headers": {},
                "status": 0,
                "attack_tags": [attack_type],
                "confidence": confidence,
                "rl_action_id": 0,
                "profile": "attacker",
                "session_id": src_ip,
            }
        )

    def log_rl_decision(
        self, state: tuple, action: int, reward: float, q_value: float
    ):
        """Log RL decision (for learning verification)"""
        with open(
            os.path.join(self.log_dir, "rl_decisions.log"), "a"
        ) as f:
            timestamp = datetime.now().isoformat()
            f.write(
                f"[{timestamp}] State: {state} -> Action: {action} | "
                f"Reward: {reward:.2f} | Q-value: {q_value:.4f}\n"
            )

    def get_log_stats(self) -> Dict[str, Any]:
        """Get statistics from log files"""
        stats = {
            "json_log_path": self.json_log_path,
            "text_log_path": self.text_log_path,
            "json_log_exists": os.path.exists(self.json_log_path),
            "text_log_exists": os.path.exists(self.text_log_path),
        }

        if os.path.exists(self.json_log_path):
            try:
                with open(self.json_log_path, "r") as f:
                    stats["json_log_lines"] = sum(1 for _ in f)
            except:
                stats["json_log_lines"] = 0

        if os.path.exists(self.text_log_path):
            try:
                with open(self.text_log_path, "r") as f:
                    stats["text_log_lines"] = sum(1 for _ in f)
            except:
                stats["text_log_lines"] = 0

        return stats
