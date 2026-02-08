import json
import uuid
import logging
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)

LOG_FILE = Path("unanswered_questions.jsonl")

# Valid statuses
STATUS_NEW = "new"
STATUS_REVIEWING = "reviewing"
STATUS_HANDLED = "handled"
VALID_STATUSES = {STATUS_NEW, STATUS_REVIEWING, STATUS_HANDLED}


class QuestionLogger:
    """Logger for tracking questions the bot couldn't answer, with status management."""

    @staticmethod
    def log_unanswered(question: str, reason: str, similarity_score: float = None):
        """Log an unanswered question with a unique ID and 'new' status."""
        log_entry = {
            "id": uuid.uuid4().hex[:12],
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "question": question,
            "reason": reason,
            "similarity_score": similarity_score,
            "status": STATUS_NEW,
        }

        try:
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry) + "\n")
            logger.info(f"Logged unanswered question: {reason} - '{question[:50]}...'")
        except Exception as e:
            logger.error(f"Failed to log unanswered question: {e}")

    @staticmethod
    def _read_all() -> list[dict]:
        """Read all log entries from disk, migrating old entries if needed."""
        if not LOG_FILE.exists():
            return []
        try:
            needs_write = False
            with open(LOG_FILE, "r", encoding="utf-8") as f:
                entries = []
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                        # Back-compat: add id/status if missing (old entries)
                        if "id" not in entry:
                            entry["id"] = uuid.uuid4().hex[:12]
                            needs_write = True
                        if "status" not in entry:
                            entry["status"] = STATUS_NEW
                            needs_write = True
                        entries.append(entry)
                    except json.JSONDecodeError:
                        continue

            # Persist migrated IDs so they're stable across reads
            if needs_write:
                QuestionLogger._write_all(entries)

            return entries
        except Exception as e:
            logger.error(f"Failed to read question log: {e}")
            return []

    @staticmethod
    def _write_all(entries: list[dict]):
        """Write all entries back to disk."""
        try:
            with open(LOG_FILE, "w", encoding="utf-8") as f:
                for entry in entries:
                    f.write(json.dumps(entry) + "\n")
        except Exception as e:
            logger.error(f"Failed to write question log: {e}")

    @staticmethod
    def get_recent_logs(limit: int = 200) -> list[dict]:
        """Retrieve recent unanswered questions (excludes 'handled')."""
        entries = QuestionLogger._read_all()
        # Filter out handled questions
        active = [e for e in entries if e.get("status") != STATUS_HANDLED]
        # Most recent first, limited
        return list(reversed(active[-limit:]))

    @staticmethod
    def get_all_logs(limit: int = 500) -> list[dict]:
        """Retrieve ALL log entries including handled (for stats)."""
        entries = QuestionLogger._read_all()
        return list(reversed(entries[-limit:]))

    @staticmethod
    def update_status(log_id: str, new_status: str) -> bool:
        """Update the status of a log entry. Returns True if found and updated."""
        if new_status not in VALID_STATUSES:
            return False

        entries = QuestionLogger._read_all()
        found = False

        for entry in entries:
            if entry.get("id") == log_id:
                entry["status"] = new_status
                found = True
                break

        if found:
            # If status is 'handled', remove it from the file entirely
            if new_status == STATUS_HANDLED:
                entries = [e for e in entries if e.get("id") != log_id]
            QuestionLogger._write_all(entries)
            logger.info(f"Updated question {log_id} to status: {new_status}")

        return found

    @staticmethod
    def delete_log(log_id: str) -> bool:
        """Delete a specific log entry. Returns True if found and deleted."""
        entries = QuestionLogger._read_all()
        new_entries = [e for e in entries if e.get("id") != log_id]

        if len(new_entries) == len(entries):
            return False  # Not found

        QuestionLogger._write_all(new_entries)
        logger.info(f"Deleted question log: {log_id}")
        return True
