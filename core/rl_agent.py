"""
RL Agent: Reinforcement Learning agent for honeypot response selection

Implements Q-learning to learn optimal responses based on attack types and contexts.
Tracks Q-values per state-action pair and updates them based on rewards.
"""

import sqlite3
import random
import logging
from typing import Tuple, List, Dict, Optional


class RLAgent:
    """
    Q-Learning based agent for selecting honeypot responses.
    
    State: (path, method, attack_type)
    Actions: 0=normal, 1=delay_error, 2=fake_success, 3=redirect, 4=expose_data
    """

    def __init__(
        self,
        db_path: str = "rl.db",
        epsilon: float = 0.1,
        discount_gamma: float = 0.99,
        learning_rate: float = 0.01,
        enable_logging: bool = True,
    ):
        """
        Initialize RL Agent
        
        Args:
            db_path: Path to SQLite database for Q-table storage
            epsilon: Exploration rate (0.1 = 10% random actions)
            discount_gamma: Discount factor for future rewards
            learning_rate: Learning rate for Q-value updates
            enable_logging: Whether to log learning events
        """
        self.db_path = db_path
        self.epsilon = epsilon
        self.discount_gamma = discount_gamma
        self.learning_rate = learning_rate
        self.enable_logging = enable_logging

        # Logging
        if enable_logging:
            self.logger = logging.getLogger("RLAgent")
            if not self.logger.handlers:
                handler = logging.FileHandler("logs/rl_agent.log")
                formatter = logging.Formatter(
                    "[%(asctime)s] %(levelname)s: %(message)s"
                )
                handler.setFormatter(formatter)
                self.logger.addHandler(handler)
                self.logger.setLevel(logging.INFO)
        else:
            self.logger = None

        # Stats tracking
        self.decision_count = 0
        self.exploration_count = 0
        self.exploitation_count = 0

        self.conn = sqlite3.connect(db_path)
        self.create_table()

    def _context_to_str(self, context: Tuple) -> str:
        """Serialize a state tuple without assuming a fixed width."""
        if isinstance(context, (list, tuple)):
            return "|".join(str(part) for part in context)
        return str(context)

    def create_table(self):
        """Create Q-table in SQLite"""
        self.conn.execute(
            """CREATE TABLE IF NOT EXISTS rewards (
            context TEXT,
            action INTEGER,
            count INTEGER DEFAULT 0,
            total_reward REAL DEFAULT 0,
            PRIMARY KEY (context, action)
        )"""
        )
        self.conn.commit()

    def build_state(
        self, method: str, path: str, attack_tags: List[str], request_count: int
    ) -> Tuple:
        """
        Build state for RL decision
        
        Args:
            method: HTTP method (GET, POST, etc)
            path: Request path
            attack_tags: Detected attack types
            request_count: Number of requests in this session
            
        Returns:
            State tuple (path, method, primary_attack_tag)
        """
        primary_attack = attack_tags[0] if attack_tags else "normal"
        return (path, method, primary_attack)

    def select_response(
        self, context: Tuple, candidates: List[int]
    ) -> int:
        """
        Select response action using epsilon-greedy strategy
        
        Args:
            context: State tuple (path, method)
            candidates: Available action IDs
            
        Returns:
            Selected action ID
        """
        if not candidates:
            return 0  # fallback

        self.decision_count += 1
        context_str = self._context_to_str(context)

        if random.random() < self.epsilon:
            # Exploration: random action
            action = random.choice(candidates)
            self.exploration_count += 1
            if self.logger:
                self.logger.info(
                    f"EXPLORATION: state={context_str} action={action} (eps={self.epsilon})"
                )
        else:
            # Exploitation: best known action
            action = self._select_best_action(context_str, candidates)
            self.exploitation_count += 1
            if self.logger:
                q_val = self.get_q_value(context, action)
                self.logger.info(
                    f"EXPLOITATION: state={context_str} action={action} q_value={q_val:.4f}"
                )

        return action

    def select_action(self, state: Tuple, candidates: List[int]) -> int:
        """
        Alias for select_response - for honeypot.py compatibility
        """
        return self.select_response(state, candidates)

    def _select_best_action(self, context_str: str, candidates: List[int]) -> int:
        """Select action with highest Q-value"""
        max_q = -float("inf")
        best_action = candidates[0]

        for action in candidates:
            q_val = self._get_q_value_from_db(context_str, action)
            if q_val > max_q:
                max_q = q_val
                best_action = action

        return best_action

    def update_reward(self, context: Tuple, action: int, reward: float):
        """
        Update Q-value based on received reward (Q-learning update)
        
        Args:
            context: State tuple (path, method, attack_type)
            action: Action taken
            reward: Reward received (0 for normal, 1 for attack detected)
        """
        context_str = self._context_to_str(context)

        # Fetch current Q-value
        row = self.conn.execute(
            "SELECT count, total_reward FROM rewards WHERE context=? AND action=?",
            (context_str, action),
        ).fetchone()

        if row:
            count, total = row
            # Incremental average update
            new_count = count + 1
            new_total = total + reward
        else:
            new_count = 1
            new_total = reward

        # Store update
        self.conn.execute(
            "INSERT OR REPLACE INTO rewards (context, action, count, total_reward) VALUES (?, ?, ?, ?)",
            (context_str, action, new_count, new_total),
        )
        self.conn.commit()

        if self.logger:
            avg_reward = new_total / new_count if new_count > 0 else 0
            self.logger.debug(
                f"REWARD_UPDATE: state={context_str} action={action} "
                f"reward={reward} avg_q={avg_reward:.4f} count={new_count}"
            )

    def get_q_value(self, state: Tuple, action: int) -> float:
        """Get Q-value for state-action pair"""
        context_str = self._context_to_str(state)
        return self._get_q_value_from_db(context_str, action)

    def _get_q_value_from_db(self, context_str: str, action: int) -> float:
        """Fetch Q-value from database"""
        row = self.conn.execute(
            "SELECT count, total_reward FROM rewards WHERE context=? AND action=?",
            (context_str, action),
        ).fetchone()

        if row:
            count, total = row
            return total / count if count > 0 else 0
        return 0

    def get_learning_stats(self) -> Dict:
        """Get RL learning statistics"""
        exploration_rate = (
            self.exploration_count / self.decision_count
            if self.decision_count > 0
            else 0
        )

        # Get Q-table summary
        all_rows = self.conn.execute(
            "SELECT action, AVG(total_reward / count) as avg_q FROM rewards WHERE count > 0 GROUP BY action"
        ).fetchall()

        action_q_values = {action: avg_q for action, avg_q in all_rows}

        return {
            "total_decisions": self.decision_count,
            "exploration_count": self.exploration_count,
            "exploitation_count": self.exploitation_count,
            "exploration_rate": exploration_rate,
            "avg_q_values_by_action": action_q_values,
        }

    def verify_rl_learning(self) -> Dict:
        """
        Verify that RL learning is occurring.
        
        Returns:
            Learning status report with:
                - is_learning: bool - whether agent is learning
                - total_states: number of unique states learned
                - sample_q_values: example Q-values
                - action_distribution: distribution of taken actions
                - recommendation: interpretation
        """
        # Count unique states
        state_count = self.conn.execute(
            "SELECT COUNT(DISTINCT context) FROM rewards"
        ).fetchone()[0]

        # Get all Q-values
        all_q_rows = self.conn.execute(
            "SELECT context, action, total_reward, count FROM rewards WHERE count > 0 ORDER BY count DESC LIMIT 10"
        ).fetchall()

        # Get action distribution from rewards table
        action_dist = self.conn.execute(
            "SELECT action, SUM(count) as total_count FROM rewards GROUP BY action"
        ).fetchall()

        is_learning = state_count > 0 and len(all_q_rows) > 0

        sample_q_table = []
        for context, action, total_reward, count in all_q_rows:
            q_val = total_reward / count if count > 0 else 0
            sample_q_table.append(
                {
                    "state": context,
                    "action": action,
                    "q_value": q_val,
                    "visits": count,
                    "total_reward": total_reward,
                }
            )

        action_distribution = {action: count for action, count in action_dist}

        # Interpret learning
        if is_learning:
            max_q = max((q["q_value"] for q in sample_q_table), default=0)
            recommendation = (
                "✓ RL Agent is LEARNING. "
                f"Found {state_count} unique states. "
                f"Max Q-value: {max_q:.4f}"
            )
        else:
            recommendation = "✗ RL Agent has NOT LEARNED yet. No Q-values recorded."

        return {
            "is_learning": is_learning,
            "total_unique_states": state_count,
            "total_q_entries": len(all_q_rows),
            "sample_q_table": sample_q_table,
            "action_distribution": action_distribution,
            "total_decisions_recorded": self.decision_count,
            "exploration_rate": (
                self.exploration_count / self.decision_count
                if self.decision_count > 0
                else 0
            ),
            "recommendation": recommendation,
        }

    def close(self):
        """Close database connection"""
        self.conn.close()
