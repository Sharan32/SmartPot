import sqlite3
import random

class RLAgent:
    def __init__(self, db_path='rl.db', epsilon=0.1):
        self.db_path = db_path
        self.epsilon = epsilon
        self.conn = sqlite3.connect(db_path)
        self.create_table()

    def create_table(self):
        self.conn.execute('''CREATE TABLE IF NOT EXISTS rewards (
            context TEXT,
            action INTEGER,
            count INTEGER DEFAULT 0,
            total_reward REAL DEFAULT 0,
            PRIMARY KEY (context, action)
        )''')
        self.conn.commit()

    def select_response(self, context, candidates):
        if not candidates:
            return 0  # fallback
        context_str = f"{context[0]}|{context[1]}"  # path|method
        if random.random() < self.epsilon:
            return random.choice(candidates)
        else:
            max_avg = -1
            best_action = candidates[0]
            for action in candidates:
                row = self.conn.execute('SELECT count, total_reward FROM rewards WHERE context=? AND action=?', (context_str, action)).fetchone()
                if row:
                    count, total = row
                    if count > 0:
                        avg = total / count
                        if avg > max_avg:
                            max_avg = avg
                            best_action = action
            return best_action

    def update_reward(self, context, action, reward):
        context_str = f"{context[0]}|{context[1]}"
        row = self.conn.execute('SELECT count, total_reward FROM rewards WHERE context=? AND action=?', (context_str, action)).fetchone()
        if row:
            count, total = row
            count += 1
            total += reward
        else:
            count = 1
            total = reward
        self.conn.execute('INSERT OR REPLACE INTO rewards (context, action, count, total_reward) VALUES (?, ?, ?, ?)', (context_str, action, count, total))
        self.conn.commit()

    def close(self):
        self.conn.close()