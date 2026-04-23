#!/usr/bin/env python3

"""
Lightweight analytics dashboard for FirmPot.

Exposes:
  /dashboard -> HTML overview
  /api/stats -> JSON payload for the dashboard
"""

import argparse
import json
import os
import sqlite3
from collections import Counter

from flask import Flask, jsonify, render_template_string


DASHBOARD_HTML = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>FirmPot Dashboard</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <style>
    body { font-family: Arial, sans-serif; margin: 0; background: #f4f6f8; color: #15202b; }
    .wrap { max-width: 1200px; margin: 0 auto; padding: 24px; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px; margin-bottom: 24px; }
    .card { background: white; border-radius: 12px; padding: 18px; box-shadow: 0 8px 24px rgba(0,0,0,0.06); }
    h1 { margin-top: 0; }
    h3 { margin: 0 0 8px 0; font-size: 15px; color: #52606d; }
    .value { font-size: 30px; font-weight: bold; }
    .charts { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 16px; }
    table { width: 100%; border-collapse: collapse; }
    th, td { text-align: left; padding: 8px; border-bottom: 1px solid #e5e7eb; }
  </style>
</head>
<body>
  <div class="wrap">
    <h1>FirmPot Analytics Dashboard</h1>
    <div class="grid">
      <div class="card"><h3>Total Requests</h3><div class="value" id="total_requests">0</div></div>
      <div class="card"><h3>Total Attacks</h3><div class="value" id="total_attacks">0</div></div>
      <div class="card"><h3>Active Sessions</h3><div class="value" id="active_sessions">0</div></div>
      <div class="card"><h3>RL Decisions</h3><div class="value" id="rl_total_decisions">0</div></div>
    </div>
    <div class="charts">
      <div class="card"><canvas id="attackTypes"></canvas></div>
      <div class="card"><canvas id="topIps"></canvas></div>
      <div class="card"><canvas id="topEndpoints"></canvas></div>
      <div class="card"><canvas id="attackFrequency"></canvas></div>
    </div>
    <div class="charts" style="margin-top: 16px;">
      <div class="card">
        <h3>Session Lengths</h3>
        <table id="sessionTable">
          <thead><tr><th>Session</th><th>IP</th><th>Requests</th><th>Attacks</th><th>Duration (s)</th></tr></thead>
          <tbody></tbody>
        </table>
      </div>
      <div class="card">
        <h3>RL Summary</h3>
        <table id="rlTable">
          <tbody></tbody>
        </table>
      </div>
    </div>
  </div>
  <script>
    let charts = {};
    function renderBar(id, labels, values, label) {
      if (charts[id]) charts[id].destroy();
      charts[id] = new Chart(document.getElementById(id), {
        type: 'bar',
        data: { labels, datasets: [{ label, data: values, backgroundColor: '#2f855a' }] },
        options: { responsive: true, maintainAspectRatio: false }
      });
    }
    function renderLine(id, labels, values, label) {
      if (charts[id]) charts[id].destroy();
      charts[id] = new Chart(document.getElementById(id), {
        type: 'line',
        data: { labels, datasets: [{ label, data: values, borderColor: '#1d4ed8', fill: false }] },
        options: { responsive: true, maintainAspectRatio: false }
      });
    }
    async function refresh() {
      const stats = await fetch('/api/stats').then(r => r.json());
      document.getElementById('total_requests').textContent = stats.total_requests;
      document.getElementById('total_attacks').textContent = stats.total_attacks;
      document.getElementById('active_sessions').textContent = stats.session_count;
      document.getElementById('rl_total_decisions').textContent = stats.rl.total_decisions;

      renderBar('attackTypes', Object.keys(stats.attack_type_distribution), Object.values(stats.attack_type_distribution), 'Attack Types');
      renderBar('topIps', stats.top_attacker_ips.map(x => x.ip), stats.top_attacker_ips.map(x => x.requests), 'Top Attacker IPs');
      renderBar('topEndpoints', stats.top_endpoints.map(x => x.path), stats.top_endpoints.map(x => x.requests), 'Top Endpoints');
      renderLine('attackFrequency', Object.keys(stats.attack_frequency), Object.values(stats.attack_frequency), 'Attack Frequency');

      const sessionRows = stats.sessions.map(s =>
        `<tr><td>${s.session_id}</td><td>${s.ip}</td><td>${s.request_count}</td><td>${s.attack_count}</td><td>${s.duration_seconds}</td></tr>`
      ).join('');
      document.querySelector('#sessionTable tbody').innerHTML = sessionRows || '<tr><td colspan="5">No sessions yet</td></tr>';

      const rlRows = [
        ['Total Decisions', stats.rl.total_decisions],
        ['Average Reward', stats.rl.average_reward],
        ['Recent Average Reward', stats.rl.recent_average_reward],
        ['Learned States', stats.rl.learned_states],
        ['Trend', stats.rl.trend]
      ].map(row => `<tr><td>${row[0]}</td><td>${row[1]}</td></tr>`).join('');
      document.querySelector('#rlTable tbody').innerHTML = rlRows;
    }
    refresh();
    setInterval(refresh, 5000);
  </script>
</body>
</html>
"""


def load_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return default


def read_rl_stats(rl_db_path):
    if not os.path.exists(rl_db_path):
        return {
            "total_decisions": 0,
            "average_reward": 0,
            "recent_average_reward": 0,
            "learned_states": 0,
            "trend": "idle",
        }

    conn = sqlite3.connect(rl_db_path)
    try:
        rows = conn.execute(
            "SELECT context, action, count, total_reward FROM rewards WHERE count > 0"
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        return {
            "total_decisions": 0,
            "average_reward": 0,
            "recent_average_reward": 0,
            "learned_states": 0,
            "trend": "idle",
        }

    total_decisions = sum(row[2] for row in rows)
    rewards = []
    for _, _, count, total_reward in rows:
        rewards.extend([total_reward / count] * count)
    average_reward = round(sum(rewards) / len(rewards), 4) if rewards else 0
    recent = rewards[-50:] if rewards else []
    recent_average = round(sum(recent) / len(recent), 4) if recent else 0

    return {
        "total_decisions": total_decisions,
        "average_reward": average_reward,
        "recent_average_reward": recent_average,
        "learned_states": len({row[0] for row in rows}),
        "trend": "improving" if recent_average >= average_reward else "stable",
    }


def build_stats(log_dir, honeypot_dir):
    attack_data_path = os.path.join(log_dir, "attack_data.json")
    structured_path = os.path.join(log_dir, "access_structured.json")
    attack_data = load_json(
        attack_data_path,
        {
            "total_requests": 0,
            "total_attacks": 0,
            "attack_type_distribution": {},
            "top_attacker_ips": {},
            "top_endpoints": {},
            "attack_frequency": {},
            "sessions": {},
        },
    )

    if not attack_data["attack_type_distribution"] and os.path.exists(structured_path):
        per_type = Counter()
        per_ip = Counter()
        per_path = Counter()
        with open(structured_path, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                event = json.loads(line)
                per_ip[event.get("src_ip", "unknown")] += 1
                per_path[event.get("path", "/")] += 1
                for tag in event.get("attack_tags", []):
                    if tag != "normal":
                        per_type[tag] += 1
        attack_data["attack_type_distribution"] = dict(per_type)
        attack_data["top_attacker_ips"] = dict(per_ip)
        attack_data["top_endpoints"] = dict(per_path)

    sessions = []
    for session_id, session in attack_data.get("sessions", {}).items():
        sessions.append(
            {
                "session_id": session_id[:8],
                "ip": session.get("ip", "unknown"),
                "request_count": session.get("request_count", 0),
                "attack_count": session.get("attack_count", 0),
                "duration_seconds": session.get("duration_seconds", 0),
            }
        )
    sessions.sort(key=lambda item: item["request_count"], reverse=True)

    top_ips = sorted(
        attack_data.get("top_attacker_ips", {}).items(),
        key=lambda item: item[1],
        reverse=True,
    )[:10]
    top_endpoints = sorted(
        attack_data.get("top_endpoints", {}).items(),
        key=lambda item: item[1],
        reverse=True,
    )[:10]

    return {
        "total_requests": attack_data.get("total_requests", 0),
        "total_attacks": attack_data.get("total_attacks", 0),
        "attack_type_distribution": attack_data.get("attack_type_distribution", {}),
        "top_attacker_ips": [{"ip": ip, "requests": requests} for ip, requests in top_ips],
        "top_endpoints": [{"path": path, "requests": requests} for path, requests in top_endpoints],
        "attack_frequency": attack_data.get("attack_frequency", {}),
        "sessions": sessions[:10],
        "session_count": len(sessions),
        "rl": read_rl_stats(os.path.join(honeypot_dir, "rl.db")),
    }


def create_app(log_dir, honeypot_dir):
    app = Flask(__name__)

    @app.route("/api/stats")
    def api_stats():
        return jsonify(build_stats(log_dir, honeypot_dir))

    @app.route("/dashboard")
    def dashboard():
        return render_template_string(DASHBOARD_HTML)

    @app.route("/")
    def index():
        return jsonify({"dashboard": "/dashboard", "api": "/api/stats"})

    return app


def main():
    parser = argparse.ArgumentParser(description="FirmPot analytics dashboard")
    parser.add_argument(
        "--log-dir",
        default=os.path.join("honeypot_instance", "logs"),
        help="Directory containing honeypot log files",
    )
    parser.add_argument(
        "--honeypot-dir",
        default="honeypot_instance",
        help="Honeypot instance directory containing rl.db",
    )
    parser.add_argument("--port", type=int, default=5000, help="Dashboard port")
    args = parser.parse_args()

    app = create_app(args.log_dir, args.honeypot_dir)
    app.run(host="0.0.0.0", port=args.port, debug=False)


if __name__ == "__main__":
    main()
