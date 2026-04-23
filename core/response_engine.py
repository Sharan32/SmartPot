"""
Response Engine: Generates realistic honeypot responses to requests
"""

import random
import time
from typing import Dict


class ResponseEngine:
    """Generates realistic HTTP responses to deceive attackers"""

    def __init__(self, config: Dict):
        """Initialize response engine with config"""
        self.config = config
        self.response_cache = {}

    def _delay(self) -> float:
        """Add realistic delay to responses"""
        return random.uniform(0.1, 0.5)

    def fake_status_page(self, session: Dict, attack_info: Dict) -> str:
        """Generate fake status/home page"""
        html = """<!DOCTYPE html>
<html>
<head>
    <title>Device Configuration</title>
    <style>
        body { font-family: Arial; margin: 20px; }
        .status { color: green; }
    </style>
</head>
<body>
    <h1>Device Status</h1>
    <p class='status'>System is operational</p>
    <p>Uptime: """ + str(random.randint(1, 365)) + """ days</p>
    <p>Last reboot: """ + self._fake_date() + """</p>
</body>
</html>"""
        return html.encode()

    def fake_error_page(self, error_msg: str) -> bytes:
        """Generate fake error page"""
        html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Error</title>
</head>
<body>
    <h1>Error</h1>
    <p>{error_msg}</p>
</body>
</html>"""
        return html.encode()

    def login_page(self) -> bytes:
        """Generate fake login page"""
        html = """<!DOCTYPE html>
<html>
<head>
    <title>Login</title>
    <style>
        body { font-family: Arial; display: flex; justify-content: center; margin-top: 50px; }
        .login-box { border: 1px solid #ccc; padding: 20px; width: 300px; }
        input { width: 100%; padding: 8px; margin: 5px 0; }
    </style>
</head>
<body>
    <div class='login-box'>
        <h2>Login</h2>
        <form method='POST' action='/login'>
            <input type='text' name='username' placeholder='Username' required>
            <input type='password' name='password' placeholder='Password' required>
            <input type='submit' value='Login'>
        </form>
    </div>
</body>
</html>"""
        return html.encode()

    def fake_login_result(
        self, username: str, password: str, success: bool, page_name: str
    ) -> bytes:
        """Generate fake login result page"""
        if success:
            html = """<!DOCTYPE html>
<html>
<body>
    <h1>Login Successful</h1>
    <p>Welcome, """ + username + """!</p>
    <p><a href='/'>Return to home</a></p>
</body>
</html>"""
        else:
            html = """<!DOCTYPE html>
<html>
<body>
    <h1>Login Failed</h1>
    <p>Invalid credentials. Please try again.</p>
    <p><a href='/login'>Back to login</a></p>
</body>
</html>"""
        return html.encode()

    def fake_sensitive_data(self) -> bytes:
        """Generate fake sensitive data expose"""
        data = {
            "database_host": "db.internal.local",
            "db_user": "admin",
            "api_key": "sk_" + "".join(random.choices("0123456789abcdef", k=32)),
            "logs": [
                f"[{self._fake_timestamp()}] User {self._fake_username()} logged in",
                f"[{self._fake_timestamp()}] Database backup completed",
                f"[{self._fake_timestamp()}] Memory usage: {random.randint(50, 90)}%",
            ],
        }
        html = f"""<!DOCTYPE html>
<html>
<head><title>Debug Info</title></head>
<body>
    <h1>Debug Information</h1>
    <pre>{str(data)}</pre>
</body>
</html>"""
        return html.encode()

    def redirect_to(self, path: str) -> bytes:
        """Generate redirect response"""
        html = f"""<!DOCTYPE html>
<html>
<head>
    <meta http-equiv='refresh' content='0;url={path}'>
</head>
<body>
    <p>Redirecting to <a href='{path}'>{path}</a></p>
</body>
</html>"""
        return html.encode()

    def _fake_date(self) -> str:
        """Generate fake date string"""
        return f"2024-{random.randint(1,12):02d}-{random.randint(1,28):02d}"

    def _fake_timestamp(self) -> str:
        """Generate fake timestamp"""
        return (
            f"2024-{random.randint(1,12):02d}-{random.randint(1,28):02d} "
            f"{random.randint(0,23):02d}:{random.randint(0,59):02d}:{random.randint(0,59):02d}"
        )

    def _fake_username(self) -> str:
        """Generate fake username"""
        names = ["root", "admin", "user", "guest", "operator"]
        return random.choice(names)
