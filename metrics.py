"""
Metrics: Tracks honeypot performance and learning metrics
"""

import time
from typing import Dict, List
from collections import defaultdict


class Metrics:
    """Collects and reports honeypot metrics"""

    def __init__(self):
        """Initialize metrics tracking"""
        self.start_time = time.time()

        # Request metrics
        self.request_count = 0
        self.requests_by_attack_type = defaultdict(int)
        self.requests_by_status = defaultdict(int)
        self.requests_by_ip = defaultdict(int)
        self.requests_by_path = defaultdict(int)
        self.requests_by_method = defaultdict(int)

        # RL metrics
        self.rl_actions = defaultdict(int)  # action_id -> count
        self.rl_rewards = []  # list of rewards
        self.rl_states = defaultdict(list)  # state -> list of [action, reward, q_value]

        # Response time tracking
        self.response_times = []

        # Session metrics
        self.active_sessions = set()
        self.total_sessions = 0

    def record_request(
        self,
        attack_tags: List[str],
        status_code: int,
        response_time: float,
        client_ip: str,
        path: str = "",
        method: str = "GET",
        rl_action: int = 0,
    ):
        """Record a request"""
        self.request_count += 1

        # Attack type tracking
        for tag in attack_tags:
            self.requests_by_attack_type[tag] += 1

        # Status tracking
        self.requests_by_status[status_code] += 1

        # IP tracking
        self.requests_by_ip[client_ip] += 1

        # Path and method tracking
        if path:
            self.requests_by_path[path] += 1
        if method:
            self.requests_by_method[method] += 1

        # Response time
        self.response_times.append(response_time)

        # RL action tracking
        self.rl_actions[rl_action] += 1

    def record_rl_action(
        self, state: tuple, action: int, reward: float, q_value: float
    ):
        """Record RL learning event"""
        self.rl_rewards.append(reward)
        self.rl_states[state].append(
            {"action": action, "reward": reward, "q_value": q_value}
        )

    def record_session(self, session_id: str):
        """Record session activity"""
        if session_id not in self.active_sessions:
            self.active_sessions.add(session_id)
            self.total_sessions += 1

    def get_metrics_snapshot(self) -> Dict:
        """Get current metrics snapshot"""
        uptime = time.time() - self.start_time
        avg_response_time = (
            sum(self.response_times) / len(self.response_times)
            if self.response_times
            else 0
        )
        avg_reward = (
            sum(self.rl_rewards) / len(self.rl_rewards) if self.rl_rewards else 0
        )

        # Top IPs attacking
        top_ips = sorted(
            self.requests_by_ip.items(), key=lambda x: x[1], reverse=True
        )[:5]

        # Top attacked paths
        top_paths = sorted(
            self.requests_by_path.items(), key=lambda x: x[1], reverse=True
        )[:5]

        # Attack type distribution
        attack_distribution = dict(self.requests_by_attack_type)

        # RL action distribution
        action_distribution = dict(self.rl_actions)

        return {
            "uptime_seconds": uptime,
            "total_requests": self.request_count,
            "requests_per_second": self.request_count / uptime if uptime > 0 else 0,
            "average_response_time_ms": avg_response_time * 1000,
            "active_sessions": len(self.active_sessions),
            "total_sessions": self.total_sessions,
            "attack_distribution": attack_distribution,
            "status_code_distribution": dict(self.requests_by_status),
            "method_distribution": dict(self.requests_by_method),
            "top_attacking_ips": [{"ip": ip, "requests": count} for ip, count in top_ips],
            "top_attacked_paths": [
                {"path": path, "requests": count} for path, count in top_paths
            ],
            "rl_action_distribution": action_distribution,
            "rl_average_reward": avg_reward,
            "rl_total_decisions": len(self.rl_rewards),
            "rl_learned_states": len(self.rl_states),
        }

    def get_rl_learning_summary(self) -> Dict:
        """Get summary of RL learning progress"""
        if not self.rl_rewards:
            return {
                "status": "no_learning_yet",
                "total_decisions": 0,
                "message": "No RL decisions recorded yet",
            }

        avg_reward = sum(self.rl_rewards) / len(self.rl_rewards)
        recent_rewards = self.rl_rewards[-100:] if len(self.rl_rewards) > 100 else self.rl_rewards
        recent_avg = sum(recent_rewards) / len(recent_rewards)

        return {
            "total_decisions": len(self.rl_rewards),
            "average_reward": avg_reward,
            "recent_average_reward": recent_avg,
            "learned_states": len(self.rl_states),
            "action_distribution": dict(self.rl_actions),
            "trend": "improving" if recent_avg > avg_reward * 0.5 else "stable",
        }

    def get_attack_summary(self) -> Dict:
        """Get summary of detected attacks"""
        total_attacks = sum(
            count for tag, count in self.requests_by_attack_type.items() if tag != "normal"
        )

        return {
            "total_requests": self.request_count,
            "total_attack_requests": total_attacks,
            "attack_percentage": (
                (total_attacks / self.request_count * 100)
                if self.request_count > 0
                else 0
            ),
            "attack_types": dict(self.requests_by_attack_type),
            "normal_requests": self.requests_by_attack_type.get("normal", 0),
        }


def get_metrics() -> Metrics:
    """Factory function to create metrics instance"""
    return Metrics()
