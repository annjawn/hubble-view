import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
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
                COUNT(DISTINCT CASE WHEN project_path IS NOT NULL THEN project_path END) active_projects,
                COUNT(DISTINCT CASE WHEN model IS NOT NULL THEN model END) active_models,
                COUNT(DISTINCT provider) active_harnesses,
                COALESCE(SUM(input_tokens),0) input_tokens, COALESCE(SUM(output_tokens),0) output_tokens,
                COALESCE(SUM(cache_read_tokens),0) cache_read_tokens,
                COALESCE(SUM(cache_write_tokens),0) cache_write_tokens,
                COALESCE(SUM(cost_usd),0) cost_usd, COALESCE(SUM(tool_calls),0) tool_calls,
                COALESCE(SUM(duration_ms),0) duration_ms
                FROM usage_events WHERE occurred_at >= ?""", (since,)
            ).fetchone()
            providers = connection.execute(
                """SELECT provider, COUNT(DISTINCT session_id) sessions,
                COALESCE(SUM(input_tokens + output_tokens + cache_read_tokens + cache_write_tokens),0) tokens,
                COALESCE(SUM(cost_usd),0) cost_usd, MAX(occurred_at) last_active,
                (SELECT model FROM usage_events child WHERE child.provider = usage_events.provider
                 AND model IS NOT NULL ORDER BY occurred_at DESC LIMIT 1) model
                FROM usage_events WHERE occurred_at >= ? GROUP BY provider""", (since,)
            ).fetchall()
            models = connection.execute(
                """SELECT provider, COALESCE(model, 'Unknown model') model,
                COUNT(DISTINCT session_id) sessions,
                COALESCE(SUM(input_tokens),0) input_tokens,
                COALESCE(SUM(output_tokens),0) output_tokens,
                COALESCE(SUM(cache_read_tokens),0) cache_read_tokens,
                COALESCE(SUM(cache_write_tokens),0) cache_write_tokens,
                COALESCE(SUM(input_tokens + output_tokens + cache_read_tokens + cache_write_tokens),0) tokens,
                MAX(occurred_at) last_active,
                MAX(CASE WHEN json_extract(metadata, '$.estimated') = 1 THEN 1 ELSE 0 END) estimated
                FROM usage_events WHERE occurred_at >= ?
                GROUP BY provider, model
                HAVING tokens > 0
                ORDER BY tokens DESC""", (since,)
            ).fetchall()
            timeline = connection.execute(
                """SELECT substr(occurred_at,1,10) day, provider,
                SUM(input_tokens + output_tokens + cache_read_tokens + cache_write_tokens) tokens, COUNT(DISTINCT session_id) sessions
                FROM usage_events WHERE occurred_at >= ? GROUP BY day, provider ORDER BY day""", (since,)
            ).fetchall()
            project_rows = connection.execute(
                """SELECT COALESCE(project_path, 'Unknown project') project_path,
                COUNT(DISTINCT session_id) sessions, SUM(input_tokens + output_tokens + cache_read_tokens + cache_write_tokens) tokens,
                SUM(cost_usd) cost_usd, MAX(occurred_at) last_active
                FROM usage_events WHERE occurred_at >= ? GROUP BY project_path""", (since,)
            ).fetchall()
            project_activity = connection.execute(
                """SELECT COALESCE(project_path, 'Unknown project') project_path,
                substr(occurred_at,1,10) day, SUM(input_tokens + output_tokens + cache_read_tokens + cache_write_tokens) tokens
                FROM usage_events WHERE occurred_at >= ?
                GROUP BY project_path, day ORDER BY day""", (since,)
            ).fetchall()
        total_tokens = (
            totals["input_tokens"] + totals["output_tokens"]
            + totals["cache_read_tokens"] + totals["cache_write_tokens"]
        )
        absolute_paths = {
            row["project_path"] for row in project_rows
            if isinstance(row["project_path"], str) and row["project_path"].startswith("/")
        }
        aliases = {path.replace("/", "-"): path for path in absolute_paths}

        def canonical_project(path: str) -> str:
            return aliases.get(path, path)

        projects_by_path: dict[str, dict[str, Any]] = {}
        for row in project_rows:
            project_path = canonical_project(row["project_path"])
            project = projects_by_path.setdefault(project_path, {
                "project_path": project_path, "sessions": 0, "tokens": 0,
                "cost_usd": 0.0, "last_active": row["last_active"], "activity": [],
            })
            project["sessions"] += row["sessions"]
            project["tokens"] += row["tokens"]
            project["cost_usd"] += row["cost_usd"]
            project["last_active"] = max(project["last_active"], row["last_active"])

        activity_by_project: dict[str, dict[str, int]] = {}
        for row in project_activity:
            project_path = canonical_project(row["project_path"])
            days = activity_by_project.setdefault(project_path, {})
            days[row["day"]] = days.get(row["day"], 0) + row["tokens"]
        projects = sorted(projects_by_path.values(), key=lambda project: project["tokens"], reverse=True)
        for project in projects:
            project["activity"] = [
                {"day": day, "tokens": tokens}
                for day, tokens in sorted(activity_by_project.get(project["project_path"], {}).items())
            ]
        return {
            "range_days": days,
            "totals": {**dict(totals), "total_tokens": total_tokens},
            "providers": [dict(row) for row in providers],
            "models": [dict(row) for row in models],
            "timeline": [dict(row) for row in timeline],
            "projects": projects,
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
                    """SELECT COALESCE(SUM(input_tokens + output_tokens + cache_read_tokens + cache_write_tokens),0) tokens,
                    COUNT(DISTINCT session_id) sessions FROM usage_events WHERE occurred_at >= ?""",
                    (start.isoformat(),),
                ).fetchone()
                result.append({
                    "label": label, "tokens": row["tokens"], "sessions": row["sessions"],
                    "resets_at": reset.isoformat(), "duration_seconds": int((reset - start).total_seconds()),
                    "source": "local",
                })
        return result

    def provider_sessions(self, provider: str) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """SELECT session_id, MAX(project_path) project_path, MAX(model) model,
                MIN(occurred_at) started_at, MAX(occurred_at) last_active,
                SUM(input_tokens) input_tokens, SUM(output_tokens) output_tokens,
                SUM(cache_read_tokens) cache_read_tokens, SUM(cache_write_tokens) cache_write_tokens,
                SUM(CASE WHEN kind = 'tool_call' THEN 1 ELSE 0 END) tool_calls,
                COUNT(*) event_count
                FROM trace_events WHERE provider = ? GROUP BY session_id
                ORDER BY last_active DESC LIMIT 100""", (provider,)
            ).fetchall()
            if rows:
                usage_rows = connection.execute(
                    """SELECT session_id, SUM(input_tokens) input_tokens, SUM(output_tokens) output_tokens,
                    SUM(cache_read_tokens) cache_read_tokens, SUM(cache_write_tokens) cache_write_tokens,
                    SUM(tool_calls) tool_calls FROM usage_events
                    WHERE provider = ? AND session_id IS NOT NULL GROUP BY session_id""", (provider,)
                ).fetchall()
                usage = {row["session_id"]: row for row in usage_rows}
            else:
                usage = {}
            if not rows:
                rows = connection.execute(
                    """SELECT session_id, MAX(project_path) project_path, MAX(model) model,
                    MIN(occurred_at) started_at, MAX(occurred_at) last_active,
                    SUM(input_tokens) input_tokens, SUM(output_tokens) output_tokens,
                    SUM(cache_read_tokens) cache_read_tokens, SUM(cache_write_tokens) cache_write_tokens,
                    SUM(tool_calls) tool_calls, COUNT(*) event_count
                    FROM usage_events WHERE provider = ? AND session_id IS NOT NULL
                    GROUP BY session_id ORDER BY last_active DESC LIMIT 100""", (provider,)
                ).fetchall()
        now = datetime.now(timezone.utc)
        result = []
        for row in rows:
            item = dict(row)
            totals = usage.get(item["session_id"])
            if totals:
                for key in ("input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens", "tool_calls"):
                    item[key] = totals[key] or 0
            item["project_path"] = self._project_root(item.get("project_path"))
            last = datetime.fromisoformat(item["last_active"].replace("Z", "+00:00"))
            item["status"] = "live" if (now - last).total_seconds() <= 120 else "ended"
            item["total_tokens"] = sum(item[key] for key in ("input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens"))
            result.append(item)
        return result

    @staticmethod
    def _project_root(value: str | None) -> str | None:
        if not value or not value.startswith("/"):
            return value
        path = Path(value)
        for candidate in (path, *path.parents):
            if (candidate / ".git").exists():
                return str(candidate)
        return value

    def session_events(self, provider: str, session_id: str, limit: int = 500) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """SELECT id, occurred_at, kind, role, name, content, model,
                input_tokens, output_tokens, cache_read_tokens, cache_write_tokens, metadata
                FROM trace_events WHERE provider = ? AND session_id = ?
                ORDER BY occurred_at, id LIMIT ?""", (provider, session_id, limit)
            ).fetchall()
            if not rows:
                rows = connection.execute(
                    """SELECT id, occurred_at, 'usage' kind, NULL role, 'Usage event' name,
                    'Provider usage record' content, model, input_tokens, output_tokens,
                    cache_read_tokens, cache_write_tokens, metadata
                    FROM usage_events WHERE provider = ? AND session_id = ?
                    ORDER BY occurred_at, id LIMIT ?""", (provider, session_id, limit)
                ).fetchall()
        return [{**dict(row), "metadata": json.loads(row["metadata"])} for row in rows]
