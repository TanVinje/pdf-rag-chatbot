import json
import logging
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)

LOG_FILE = Path("unanswered_questions.jsonl")


class QuestionLogger:
    """Logger for tracking questions the bot couldn't answer."""

    @staticmethod
    def log_unanswered(question: str, reason: str, similarity_score: float = None):
        """Log an unanswered question with context.

        Args:
            question: The user's question.
            reason: Why the bot couldn't answer (e.g., "low_similarity", "no_documents").
            similarity_score: The best similarity score found, if applicable.
        """
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "question": question,
            "reason": reason,
            "similarity_score": similarity_score,
        }

        try:
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry) + "\n")
            logger.info(f"Logged unanswered question: {reason} - '{question[:50]}...'")
        except Exception as e:
            logger.error(f"Failed to log unanswered question: {e}")

    @staticmethod
    def get_recent_logs(limit: int = 50) -> list[dict]:
        """Retrieve recent unanswered questions.

        Args:
            limit: Maximum number of entries to return.

        Returns:
            List of log entries, most recent first.
        """
        if not LOG_FILE.exists():
            return []

        try:
            with open(LOG_FILE, "r", encoding="utf-8") as f:
                lines = f.readlines()
            
            # Parse last N lines
            entries = []
            for line in lines[-limit:]:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
            
            return list(reversed(entries))  # Most recent first
        except Exception as e:
            logger.error(f"Failed to read question log: {e}")
            return []
