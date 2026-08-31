from datetime import datetime, timedelta, timezone
from typing import Any

from harness_metrics.database import Database


class AnalyticsService:
    def __init__(self, database: Database):
        self.database = database

    def overview(self, days: int = 7) -> dict[str, Any]:
        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        with self.database.connect() as connection:
            totals = connection.execute(
                """SELECT COUNT(DISTINCT session_id) sessions,
                COALESCE(SUM(input_tokens),0) input_tokens, COALESCE(SUM(output_tokens),0) output_tokens,
                COALESCE(SUM(cache_read_tokens),0) cache_read_tokens,
                COALESCE(SUM(cache_write_tokens),0) cache_write_tokens,
                COALESCE(SUM(cost_usd),0) cost_usd, COALESCE(SUM(tool_calls),0) tool_calls,
                COALESCE(SUM(duration_ms),0) duration_ms
                FROM usage_events WHERE occurred_at >= ?""", (since,)
            ).fetchone()
            providers = connection.execute(
                """SELECT provider, COUNT(DISTINCT session_id) sessions,
                COALESCE(SUM(input_tokens + output_tokens),0) tokens,
                COALESCE(SUM(cost_usd),0) cost_usd, MAX(occurred_at) last_active,
                (SELECT model FROM usage_events child WHERE child.provider = usage_events.provider
                 AND model IS NOT NULL ORDER BY occurred_at DESC LIMIT 1) model
                FROM usage_events WHERE occurred_at >= ? GROUP BY provider""", (since,)
            ).fetchall()
            timeline = connection.execute(
                """SELECT substr(occurred_at,1,10) day, provider,
                SUM(input_tokens + output_tokens) tokens, COUNT(DISTINCT session_id) sessions
                FROM usage_events WHERE occurred_at >= ? GROUP BY day, provider ORDER BY day""", (since,)
            ).fetchall()
            projects = connection.execute(
                """SELECT COALESCE(project_path, 'Unknown project') project_path,
                COUNT(DISTINCT session_id) sessions, SUM(input_tokens + output_tokens) tokens,
                SUM(cost_usd) cost_usd, MAX(occurred_at) last_active
                FROM usage_events WHERE occurred_at >= ? GROUP BY project_path ORDER BY tokens DESC LIMIT 8""", (since,)
            ).fetchall()
        total_tokens = totals["input_tokens"] + totals["output_tokens"]
        return {
            "range_days": days,
            "totals": {**dict(totals), "total_tokens": total_tokens},
            "providers": [dict(row) for row in providers],
            "timeline": [dict(row) for row in timeline],
            "projects": [dict(row) for row in projects],
            "windows": self.usage_windows(),
        }

    def usage_windows(self) -> list[dict[str, Any]]:
        now = datetime.now(timezone.utc)
        epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
        five_hours = timedelta(hours=5)
        session_start = epoch + ((now - epoch) // five_hours) * five_hours
        week_start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        windows = [
            ("Current 5-hour window", session_start, session_start + five_hours),
            ("Current week", week_start, week_start + timedelta(days=7)),
        ]
        result = []
        with self.database.connect() as connection:
            for label, start, reset in windows:
                row = connection.execute(
                    """SELECT COALESCE(SUM(input_tokens + output_tokens),0) tokens,
                    COUNT(DISTINCT session_id) sessions FROM usage_events WHERE occurred_at >= ?""",
                    (start.isoformat(),),
                ).fetchone()
                result.append({
                    "label": label, "tokens": row["tokens"], "sessions": row["sessions"],
                    "resets_at": reset.isoformat(), "duration_seconds": int((reset - start).total_seconds()),
                    "source": "local",
                })
        return result
