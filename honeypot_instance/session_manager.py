"""
Session Manager: Tracks user sessions and per-session metrics
"""

import time
import random
import string
from typing import Dict, List
from datetime import datetime


class SessionManager:
    """
    Manages honeypot user sessions.
    Tracks session-level metrics: requests per session, session duration, etc.
    """

    def __init__(self, ttl_seconds: int = 3600):
        """
        Initialize session manager
        
        Args:
            ttl_seconds: Session time-to-live in seconds
        """
        self.ttl_seconds = ttl_seconds
        self.sessions = {}  # session_id -> session_data
        self.ip_to_session = {}  # ip -> session_id mapping
        self.session_request_count = {}  # session_id -> count
        self.session_start_time = {}  # session_id -> timestamp

    def get_session(self, client_ip: str, headers: Dict) -> Dict:
        """
        Get or create session for client
        
        Returns session dict with:
            - id: unique session identifier
            - ip: client IP
            - start_time: session creation time
            - request_count: number of requests in session
            - profile: user behavior profile
        """
        # Check for existing session cookie
        cookie_header = headers.get("Cookie", "")
        session_id = self._extract_session_id(cookie_header)

        if session_id and session_id in self.sessions:
            # Validate session TTL
            if (
                time.time() - self.session_start_time.get(session_id, 0)
                > self.ttl_seconds
            ):
                # Session expired
                self._cleanup_session(session_id)
                session_id = None

        if not session_id:
            # Create new session
            session_id = self._generate_session_id()
            self.sessions[session_id] = {
                "id": session_id,
                "ip": client_ip,
                "created_at": datetime.now().isoformat(),
                "last_activity": time.time(),
                "profile": "attacker" if client_ip.startswith("192.168") else "remote",
                "attack_count": 0,
                "requests": [],
            }
            self.ip_to_session[client_ip] = session_id
            self.session_start_time[session_id] = time.time()
            self.session_request_count[session_id] = 0

        session = self.sessions[session_id]
        session["last_activity"] = time.time()
        session["request_count"] = self.session_request_count.get(session_id, 0)

        return session

    def update_session(
        self, session: Dict, request_info: Dict, attack_info: Dict, response_info: Dict
    ):
        """
        Update session with new request data
        
        Args:
            session: Session dict
            request_info: Request details {method, path}
            attack_info: Attack detection {tags, confidence}
            response_info: Response details {status, rl_action, login_success}
        """
        session_id = session["id"]

        if session_id not in self.sessions:
            return

        # Increment request count
        self.session_request_count[session_id] = (
            self.session_request_count.get(session_id, 0) + 1
        )

        # Track attack patterns
        if "normal" not in attack_info.get("tags", ["normal"]):
            self.sessions[session_id]["attack_count"] += 1

        # Record request
        self.sessions[session_id]["requests"].append(
            {
                "timestamp": time.time(),
                "method": request_info.get("method"),
                "path": request_info.get("path"),
                "attack_tags": attack_info.get("tags", []),
                "status": response_info.get("status"),
                "rl_action": response_info.get("rl_action"),
            }
        )

        # Limit stored requests to avoid memory bloat
        if len(self.sessions[session_id]["requests"]) > 100:
            self.sessions[session_id]["requests"] = (
                self.sessions[session_id]["requests"][-50:]
            )

    def get_session_metrics(self, session_id: str) -> Dict:
        """Get metrics for a session"""
        if session_id not in self.sessions:
            return {}

        session = self.sessions[session_id]
        duration = time.time() - self.session_start_time.get(session_id, time.time())

        return {
            "session_id": session_id,
            "ip": session.get("ip"),
            "request_count": self.session_request_count.get(session_id, 0),
            "attack_count": session.get("attack_count", 0),
            "duration_seconds": duration,
            "created_at": session.get("created_at"),
            "profile": session.get("profile"),
        }

    def get_all_sessions_metrics(self) -> List[Dict]:
        """Get metrics for all active sessions"""
        metrics = []
        for session_id in list(self.sessions.keys()):
            session_metric = self.get_session_metrics(session_id)
            if session_metric:
                metrics.append(session_metric)
        return metrics

    def build_cookie_header(self, session: Dict) -> str:
        """Build Set-Cookie header value"""
        return f"session_id={session['id']}; Path=/; Max-Age={self.ttl_seconds}"

    def _extract_session_id(self, cookie_header: str) -> str:
        """Extract session_id from cookie header"""
        if not cookie_header:
            return None
        cookies = cookie_header.split(";")
        for cookie in cookies:
            cookie = cookie.strip()
            if cookie.startswith("session_id="):
                return cookie.split("=")[1]
        return None

    def _generate_session_id(self) -> str:
        """Generate unique session ID"""
        return "".join(random.choices(string.ascii_letters + string.digits, k=32))

    def _cleanup_session(self, session_id: str):
        """Clean up expired session"""
        if session_id in self.sessions:
            ip = self.sessions[session_id].get("ip")
            if ip and self.ip_to_session.get(ip) == session_id:
                del self.ip_to_session[ip]
            del self.sessions[session_id]
        if session_id in self.session_start_time:
            del self.session_start_time[session_id]
        if session_id in self.session_request_count:
            del self.session_request_count[session_id]

    def cleanup_expired_sessions(self):
        """Clean up all expired sessions"""
        current_time = time.time()
        expired_sessions = [
            sid
            for sid, start_time in self.session_start_time.items()
            if current_time - start_time > self.ttl_seconds
        ]
        for session_id in expired_sessions:
            self._cleanup_session(session_id)

    def get_stats(self) -> Dict:
        """Get session manager statistics"""
        self.cleanup_expired_sessions()
        return {
            "active_sessions": len(self.sessions),
            "total_requests": sum(self.session_request_count.values()),
            "avg_requests_per_session": (
                sum(self.session_request_count.values()) / len(self.sessions)
                if self.sessions
                else 0
            ),
            "tracked_ips": len(self.ip_to_session),
        }
