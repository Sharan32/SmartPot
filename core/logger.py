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
        self.attack_data_path = os.path.join(log_dir, "attack_data.json")

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

        try:
            self._update_attack_data(event)
        except Exception as e:
            print(f"[!] Error updating attack data: {e}")

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

    def _update_attack_data(self, event: Dict[str, Any]):
        """Maintain a compact aggregate JSON file for dashboards and demo reporting."""
        if os.path.exists(self.attack_data_path):
            with open(self.attack_data_path, "r") as f:
                data = json.load(f)
        else:
            data = {
                "total_requests": 0,
                "total_attacks": 0,
                "attack_type_distribution": {},
                "top_attacker_ips": {},
                "top_endpoints": {},
                "attack_frequency": {},
                "sessions": {},
                "last_updated": None,
            }

        src_ip = event.get("src_ip", "unknown")
        path = event.get("path", "/")
        tags = event.get("attack_tags", ["normal"])
        session_id = event.get("session_id", "unknown")
        timestamp = event.get("timestamp", datetime.now().isoformat())
        minute_bucket = timestamp[:16]

        data["total_requests"] += 1
        data["top_attacker_ips"][src_ip] = data["top_attacker_ips"].get(src_ip, 0) + 1
        data["top_endpoints"][path] = data["top_endpoints"].get(path, 0) + 1
        data["attack_frequency"][minute_bucket] = data["attack_frequency"].get(minute_bucket, 0) + 1

        session_entry = data["sessions"].setdefault(
            session_id,
            {
                "ip": src_ip,
                "request_count": 0,
                "attack_count": 0,
                "attack_types": {},
                "endpoints": {},
                "started_at": timestamp,
                "last_seen": timestamp,
                "duration_seconds": 0,
            },
        )
        session_entry["request_count"] += 1
        session_entry["last_seen"] = timestamp
        session_entry["endpoints"][path] = session_entry["endpoints"].get(path, 0) + 1
        started = datetime.fromisoformat(session_entry["started_at"])
        current = datetime.fromisoformat(timestamp)
        session_entry["duration_seconds"] = max(
            0, int((current - started).total_seconds())
        )

        attack_tags = [tag for tag in tags if tag != "normal"]
        if attack_tags:
            data["total_attacks"] += 1
            for tag in attack_tags:
                data["attack_type_distribution"][tag] = (
                    data["attack_type_distribution"].get(tag, 0) + 1
                )
                session_entry["attack_types"][tag] = (
                    session_entry["attack_types"].get(tag, 0) + 1
                )
            session_entry["attack_count"] += 1

        data["last_updated"] = timestamp

        with open(self.attack_data_path, "w") as f:
            json.dump(data, f, indent=2)

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
