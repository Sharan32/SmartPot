"""
Detection Module: Identifies and tags attack attempts in honeypot traffic
"""

import re
from typing import Dict, List, Tuple


class AttackDetector:
    """
    Simple attack detection using pattern matching and heuristics.
    Tags requests as: normal, sqli, xss, brute_force, scanner, command_injection, path_traversal
    """

    def __init__(self):
        self.sqli_patterns = [
            r"(?i)\b(or|and)\b\s+['\"]?\d+['\"]?\s*=\s*['\"]?\d+['\"]?",
            r"(?i)\b(or|and)\b\s+['\"][^'\"]+['\"]\s*=\s*['\"][^'\"]+['\"]",
            r"(?i)\bunion\b.+\bselect\b",
            r"('|\"|;|\s)(\s)??(or|and)(\s)??('|\"|\d)",
            r"(\s)??(union|select|insert|update|delete|drop)(\s)??(from|into|table)",
            r"(--|\#|\/\*|\*\/)",
            r"xp_|sp_",
        ]
        self.xss_patterns = [
            r"<script[^>]*>.*?</script>",
            r"javascript:",
            r"on\w+\s*=",
            r"<iframe",
            r"<object",
            r"<embed",
        ]
        self.path_traversal_patterns = [
            r"\.\./",
            r"\.\.",
            r"%2e%2e",
        ]
        self.command_injection_patterns = [
            r"[;&|`$()]",
            r"\$\{",
            r"<\(",
            r"(?i)\b(cat|wget|curl|nc|bash|sh)\b",
        ]
        self.brute_force_threshold = 5  # requests per session for brute force detection
        self.scanner_patterns = [
            r"nikto|nmap|masscan|sqlmap|metasploit|burp|zaproxy|acunetix",
            r"nessus|openvas|qualys",
        ]
        self.path_attack_map = {
            "config_exposure": ["/.git", "/config", "/env", "/web-inf", "/wp-config", "/.svn"],
            "key_exfiltration": ["/id_rsa", ".key", ".pem", ".p12", ".pfx", "authorized_keys"],
            "web_probe": ["/phpinfo", "/adminer", "/server-status", "/actuator", "/debug", "/solr"],
        }

        self.ip_failed_logins = {}  # Track failed logins per IP
        self.ip_request_count = {}  # Track request count per IP

    def detect(
        self,
        method: str,
        path: str,
        query: str,
        body: str,
        headers: Dict,
        client_ip: str,
        user_agent: str,
    ) -> Dict:
        """
        Detect attacks in the request.
        
        Returns:
        {
            'tags': ['normal'] or list of attack types,
            'confidence': 0.0 - 1.0,
            'details': explanation
        }
        """
        tags = []
        confidence = 0.0

        # SQLi detection
        if self._check_sqli(query + " " + body):
            tags.append("sqli")
            confidence = 0.9

        # XSS detection
        if self._check_xss(query + " " + body):
            tags.append("xss")
            confidence = 0.85

        # Command Injection detection
        if self._check_command_injection(query + " " + body):
            tags.append("command_injection")
            confidence = 0.8

        # Path Traversal detection
        if self._check_path_traversal(path):
            tags.append("path_traversal")
            confidence = 0.85

        # Scanner detection
        if self._check_scanner(user_agent):
            tags.append("scanner")
            confidence = 0.95

        # Path-based probe classification
        path_tag = self._classify_path_probe(path)
        if path_tag:
            tags.append(path_tag)
            confidence = max(confidence, 0.85)

        # Brute force/credential stuffing detection
        if path == "/login" and method == "POST":
            if client_ip not in self.ip_failed_logins:
                self.ip_failed_logins[client_ip] = 0
            self.ip_failed_logins[client_ip] += 1
            if self.ip_failed_logins[client_ip] > self.brute_force_threshold:
                tags.append("brute_force")
                confidence = 0.9

        # Request frequency detection
        if client_ip not in self.ip_request_count:
            self.ip_request_count[client_ip] = 0
        self.ip_request_count[client_ip] += 1
        if self.ip_request_count[client_ip] > 50:  # More than 50 requests
            if "scanner" not in tags and path_tag is None:
                tags.append("scanner")
            confidence = max(confidence, 0.7)

        if not tags:
            tags = ["normal"]
            confidence = 0.95

        return {
            "tags": tags,
            "confidence": confidence,
            "details": f"Detected: {', '.join(tags)}",
        }

    def _check_sqli(self, payload: str) -> bool:
        """Check for SQL injection patterns"""
        payload_lower = payload.lower()
        for pattern in self.sqli_patterns:
            if re.search(pattern, payload_lower, re.IGNORECASE):
                return True
        return False

    def _check_xss(self, payload: str) -> bool:
        """Check for XSS patterns"""
        for pattern in self.xss_patterns:
            if re.search(pattern, payload, re.IGNORECASE):
                return True
        return False

    def _check_command_injection(self, payload: str) -> bool:
        """Check for command injection patterns"""
        for pattern in self.command_injection_patterns:
            if re.search(pattern, payload):
                return True
        return False

    def _check_path_traversal(self, path: str) -> bool:
        """Check for path traversal patterns"""
        for pattern in self.path_traversal_patterns:
            if re.search(pattern, path, re.IGNORECASE):
                return True
        return False

    def _check_scanner(self, user_agent: str) -> bool:
        """Check for scanner signatures"""
        for pattern in self.scanner_patterns:
            if re.search(pattern, user_agent, re.IGNORECASE):
                return True
        return False

    def _classify_path_probe(self, path: str) -> str:
        path_lower = (path or "").lower()
        for tag, indicators in self.path_attack_map.items():
            for indicator in indicators:
                if indicator in path_lower:
                    return tag
        return ""

    def reset_ip_stats(self, client_ip: str):
        """Reset stats for an IP (e.g., on new session)"""
        if client_ip in self.ip_failed_logins:
            self.ip_failed_logins[client_ip] = 0
        if client_ip in self.ip_request_count:
            self.ip_request_count[client_ip] = 0

    def get_stats(self) -> Dict:
        """Get detection statistics"""
        return {
            "tracked_ips": len(self.ip_request_count),
            "high_frequency_ips": sum(
                1 for count in self.ip_request_count.values() if count > 50
            ),
            "brute_force_ips": len(self.ip_failed_logins),
        }
