import csv
import io
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from harness_metrics.database import Database
from harness_metrics.pricing import PRICING_SOURCES, PRICING_VERSION, estimate_cost

# Providers whose plans meter usage in five-hour windows.
WINDOWED_PROVIDERS = {"claude": "Claude Code", "codex": "Codex"}
FIVE_HOURS = timedelta(hours=5)


def _parse_time(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


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
                """SELECT date(occurred_at, 'localtime') day, provider,
                SUM(input_tokens + output_tokens + cache_read_tokens + cache_write_tokens) tokens, COUNT(DISTINCT session_id) sessions
                FROM usage_events WHERE occurred_at >= ? GROUP BY day, provider
                HAVING day IS NOT NULL ORDER BY day""", (since,)
            ).fetchall()
            project_rows = connection.execute(
                """SELECT COALESCE(project_path, 'Unknown project') project_path,
                COUNT(DISTINCT session_id) sessions, SUM(input_tokens + output_tokens + cache_read_tokens + cache_write_tokens) tokens,
                SUM(cost_usd) cost_usd, MAX(occurred_at) last_active
                FROM usage_events WHERE occurred_at >= ? GROUP BY project_path""", (since,)
            ).fetchall()
            project_models = connection.execute(
                """SELECT COALESCE(project_path, 'Unknown project') project_path, model,
                SUM(input_tokens) input_tokens, SUM(cache_write_tokens) cache_write_tokens,
                SUM(cache_read_tokens) cache_read_tokens, SUM(output_tokens) output_tokens
                FROM usage_events WHERE occurred_at >= ? GROUP BY project_path, model""", (since,)
            ).fetchall()
            project_activity = connection.execute(
                """SELECT COALESCE(project_path, 'Unknown project') project_path,
                date(occurred_at, 'localtime') day, SUM(input_tokens + output_tokens + cache_read_tokens + cache_write_tokens) tokens
                FROM usage_events WHERE occurred_at >= ?
                GROUP BY project_path, day HAVING day IS NOT NULL ORDER BY day""", (since,)
            ).fetchall()
        total_tokens = (
            totals["input_tokens"] + totals["output_tokens"]
            + totals["cache_read_tokens"] + totals["cache_write_tokens"]
        )
        absolute_paths = {
            row["project_path"] for row in project_rows
            if isinstance(row["project_path"], str) and row["project_path"].startswith("/")
        }
        # Claude Code names ~/.claude/projects/<project> by replacing every
        # non-alphanumeric character of the working directory with "-"
        # (https://code.claude.com/docs/en/sessions "Where transcripts are stored").
        aliases = {re.sub(r"[^A-Za-z0-9]", "-", path): path for path in absolute_paths}

        def canonical_project(path: str) -> str:
            return aliases.get(path, path)

        def row_estimate(row: Any) -> float | None:
            return estimate_cost(
                row["model"], row["input_tokens"] or 0, row["cache_write_tokens"] or 0,
                row["cache_read_tokens"] or 0, row["output_tokens"] or 0,
            )

        # Estimates are computed at read time from the price table and kept
        # apart from `cost_usd`, which holds only what a provider reported.
        model_items = [{**dict(row), "estimated_cost_usd": row_estimate(row)} for row in models]
        unpriced = sorted({
            item["model"] for item in model_items
            if item["estimated_cost_usd"] is None and item["model"] != "Unknown model"
        })
        provider_estimates: dict[str, float] = {}
        for item in model_items:
            provider_estimates[item["provider"]] = (
                provider_estimates.get(item["provider"], 0.0) + (item["estimated_cost_usd"] or 0.0)
            )
        project_estimates: dict[str, float] = {}
        for row in project_models:
            key = canonical_project(row["project_path"])
            project_estimates[key] = project_estimates.get(key, 0.0) + (row_estimate(row) or 0.0)

        projects_by_path: dict[str, dict[str, Any]] = {}
        for row in project_rows:
            project_path = canonical_project(row["project_path"])
            project = projects_by_path.setdefault(project_path, {
                "project_path": project_path, "sessions": 0, "tokens": 0,
                "cost_usd": 0.0, "estimated_cost_usd": project_estimates.get(project_path, 0.0),
                "last_active": row["last_active"], "activity": [],
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
            "totals": {
                **dict(totals), "total_tokens": total_tokens,
                "estimated_cost_usd": sum(provider_estimates.values()),
            },
            "providers": [
                {**dict(row), "estimated_cost_usd": provider_estimates.get(row["provider"], 0.0)}
                for row in providers
            ],
            "models": model_items,
            "pricing": {"version": PRICING_VERSION, "sources": PRICING_SOURCES, "unpriced_models": unpriced},
            "timeline": [dict(row) for row in timeline],
            "projects": projects,
            "windows": self.usage_windows(),
        }

    def usage_windows(self) -> list[dict[str, Any]]:
        now = datetime.now(timezone.utc)
        # Weeks follow the user's local calendar (Monday 00:00 local time).
        # Provider weekly limits reset at an account-specific time that local
        # logs do not reveal, so this is a calendar week, not a quota week.
        local_now = now.astimezone()
        week_start = (local_now - timedelta(days=local_now.weekday())).replace(
            hour=0, minute=0, second=0, microsecond=0
        ).astimezone(timezone.utc)
        result = []
        with self.database.connect() as connection:
            for provider, name in WINDOWED_PROVIDERS.items():
                result.append(self._rolling_window(connection, provider, name, now))
            row = connection.execute(
                """SELECT COALESCE(SUM(input_tokens + output_tokens + cache_read_tokens + cache_write_tokens),0) tokens,
                COUNT(DISTINCT session_id) sessions FROM usage_events WHERE occurred_at >= ?""",
                (week_start.isoformat(),),
            ).fetchone()
            reset = week_start + timedelta(days=7)
            result.append({
                "label": "This week", "provider": None, "active": True,
                "tokens": row["tokens"], "sessions": row["sessions"],
                "started_at": week_start.isoformat(), "resets_at": reset.isoformat(),
                "duration_seconds": int((reset - week_start).total_seconds()), "source": "local",
            })
        return result

    @staticmethod
    def _rolling_window(connection: Any, provider: str, name: str, now: datetime) -> dict[str, Any]:
        """Estimate the provider's current five-hour window from local activity.

        Claude: "The period starts when you send your first message, and your
        limit resets in full five hours later"
        (https://support.claude.com/en/articles/11647753-how-do-usage-and-length-limits-work).
        Codex documents a five-hour period without stating when it starts; the
        same rule is assumed. Activity on other devices or in the provider's
        other apps is invisible here, so this is an estimate, not the quota.
        """
        rows = connection.execute(
            "SELECT DISTINCT occurred_at FROM usage_events WHERE provider = ? AND occurred_at >= ? ORDER BY occurred_at",
            (provider, (now - timedelta(days=3)).isoformat()),
        ).fetchall()
        start: datetime | None = None
        for row in rows:
            moment = _parse_time(row["occurred_at"])
            if moment is None or moment > now:
                continue
            if start is None or moment >= start + FIVE_HOURS:
                start = moment
        window = {
            "label": f"{name} 5-hour window", "provider": provider, "active": False,
            "tokens": 0, "sessions": 0, "started_at": None, "resets_at": None,
            "duration_seconds": int(FIVE_HOURS.total_seconds()), "source": "local-estimate",
        }
        if start is None or now >= start + FIVE_HOURS:
            return window
        totals = connection.execute(
            """SELECT COALESCE(SUM(input_tokens + output_tokens + cache_read_tokens + cache_write_tokens),0) tokens,
            COUNT(DISTINCT session_id) sessions FROM usage_events
            WHERE provider = ? AND occurred_at >= ? AND datetime(occurred_at) >= datetime(?)""",
            (provider, (now - timedelta(days=3)).isoformat(), start.isoformat()),
        ).fetchone()
        window.update({
            "active": True, "tokens": totals["tokens"], "sessions": totals["sessions"],
            "started_at": start.isoformat(), "resets_at": (start + FIVE_HOURS).isoformat(),
        })
        return window

    def provider_sessions(self, provider: str) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """SELECT session_id, COALESCE(MAX(CASE WHEN project_path LIKE '/%' THEN project_path END), MAX(project_path)) project_path, MAX(model) model,
                MIN(occurred_at) started_at, MAX(occurred_at) last_active,
                SUM(input_tokens) input_tokens, SUM(output_tokens) output_tokens,
                SUM(cache_read_tokens) cache_read_tokens, SUM(cache_write_tokens) cache_write_tokens,
                SUM(CASE WHEN kind = 'tool_call' THEN 1 ELSE 0 END) tool_calls,
                COUNT(*) event_count
                FROM trace_events WHERE provider = ? GROUP BY session_id
                ORDER BY last_active DESC LIMIT 100""", (provider,)
            ).fetchall()
            # Sessions known only from usage records (no transcript captured,
            # or transcript text pruned by the retention setting) still appear.
            usage_rows = connection.execute(
                """SELECT session_id, COALESCE(MAX(CASE WHEN project_path LIKE '/%' THEN project_path END), MAX(project_path)) project_path, MAX(model) model,
                MIN(occurred_at) started_at, MAX(occurred_at) last_active,
                SUM(input_tokens) input_tokens, SUM(output_tokens) output_tokens,
                SUM(cache_read_tokens) cache_read_tokens, SUM(cache_write_tokens) cache_write_tokens,
                SUM(tool_calls) tool_calls, COUNT(*) event_count
                FROM usage_events WHERE provider = ? AND session_id IS NOT NULL
                GROUP BY session_id ORDER BY last_active DESC""", (provider,)
            ).fetchall()
            # A session can switch models, so cost is estimated per model and
            # the session shows whichever model processed the most tokens.
            model_rows = connection.execute(
                """SELECT session_id, model, SUM(input_tokens) input_tokens,
                SUM(cache_write_tokens) cache_write_tokens, SUM(cache_read_tokens) cache_read_tokens,
                SUM(output_tokens) output_tokens FROM usage_events
                WHERE provider = ? AND session_id IS NOT NULL GROUP BY session_id, model""", (provider,)
            ).fetchall()
        session_models: dict[str, list[Any]] = {}
        for row in model_rows:
            session_models.setdefault(row["session_id"], []).append(row)
        usage = {row["session_id"]: row for row in usage_rows}
        traced = {row["session_id"] for row in rows}
        combined = [dict(row) for row in rows] + [
            dict(row) for row in usage_rows[:100] if row["session_id"] not in traced
        ]
        combined.sort(key=lambda item: item["last_active"] or "", reverse=True)
        now = datetime.now(timezone.utc)
        result = []
        for item in combined[:100]:
            totals = usage.get(item["session_id"])
            if totals:
                for key in ("input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens", "tool_calls"):
                    item[key] = totals[key] or 0
            by_model = session_models.get(item["session_id"], [])
            estimates = [
                estimate_cost(
                    row["model"], row["input_tokens"] or 0, row["cache_write_tokens"] or 0,
                    row["cache_read_tokens"] or 0, row["output_tokens"] or 0,
                )
                for row in by_model
            ]
            priced = [value for value in estimates if value is not None]
            item["estimated_cost_usd"] = sum(priced) if priced else None
            named = [row for row in by_model if row["model"]]
            if named:
                item["model"] = max(named, key=lambda row: sum(
                    row[key] or 0 for key in ("input_tokens", "cache_write_tokens", "cache_read_tokens", "output_tokens")
                ))["model"]
            item["project_path"] = self._project_root(item.get("project_path"))
            item["status"] = "live" if self._is_recent(item.get("last_active"), now) else "ended"
            item["total_tokens"] = sum(item[key] for key in ("input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens"))
            result.append(item)
        return result

    @staticmethod
    def _is_recent(value: object, now: datetime, seconds: int = 120) -> bool:
        if not isinstance(value, str):
            return False
        try:
            last = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return False
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        return (now - last).total_seconds() <= seconds

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
                # Return the newest `limit` events in chronological order, so a
                # long or live session shows its latest activity, not its start.
                """SELECT * FROM (SELECT id, occurred_at, kind, role, name, content, model,
                input_tokens, output_tokens, cache_read_tokens, cache_write_tokens, metadata
                FROM trace_events WHERE provider = ? AND session_id = ?
                ORDER BY occurred_at DESC, id DESC LIMIT ?) ORDER BY occurred_at, id""",
                (provider, session_id, limit)
            ).fetchall()
            if not rows:
                rows = connection.execute(
                    """SELECT id, occurred_at, 'usage' kind, NULL role, 'Usage event' name,
                    'Provider usage record' content, model, input_tokens, output_tokens,
                    cache_read_tokens, cache_write_tokens, metadata
                    FROM usage_events WHERE provider = ? AND session_id = ?
                    ORDER BY occurred_at DESC, id DESC LIMIT ?""", (provider, session_id, limit)
                ).fetchall()
            rows = sorted(rows, key=lambda row: (row["occurred_at"], row["id"]))
        return [{**dict(row), "metadata": json.loads(row["metadata"])} for row in rows]

    def search(self, query: str, provider: str | None = None, limit: int = 50) -> dict[str, Any]:
        """Find transcript events containing every word of ``query``."""
        terms = [term for term in re.findall(r"[\w][\w.-]*", query, re.UNICODE) if term][:8]
        if not terms:
            return {"query": query, "mode": "none", "results": []}
        filters: str = ""
        params: list[Any] = []
        if provider:
            filters, params = " AND t.provider = ?", [provider]
        columns = """t.id, t.provider, t.session_id, t.project_path, t.model, t.occurred_at,
                t.kind, t.role, t.name, t.content"""
        with self.database.connect() as connection:
            rows, mode = None, "fts"
            if self.database.search_enabled:
                # Each word becomes a quoted prefix term, so user text can never
                # be read as FTS5 query syntax.
                match = " ".join('"' + term.replace('"', '""') + '"*' for term in terms)
                try:
                    rows = connection.execute(
                        f"""SELECT {columns} FROM trace_search JOIN trace_events t ON t.rowid = trace_search.rowid
                        WHERE trace_search MATCH ?{filters} ORDER BY t.occurred_at DESC LIMIT ?""",
                        (match, *params, limit),
                    ).fetchall()
                except Exception:  # noqa: BLE001 - fall back to a substring scan
                    rows = None
            if rows is None:
                mode = "scan"
                like = " AND ".join("t.content LIKE ? ESCAPE '\\'" for _ in terms)
                patterns = [
                    "%" + term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
                    for term in terms
                ]
                rows = connection.execute(
                    f"SELECT {columns} FROM trace_events t WHERE {like}{filters} ORDER BY t.occurred_at DESC LIMIT ?",
                    (*patterns, *params, limit),
                ).fetchall()
        results = []
        for row in rows:
            item = dict(row)
            item["snippet"] = self._snippet(item.pop("content") or "", terms)
            item["project_path"] = self._project_root(item.get("project_path"))
            results.append(item)
        return {"query": query, "mode": mode, "results": results}

    @staticmethod
    def _snippet(content: str, terms: list[str], radius: int = 120) -> str:
        lowered = content.lower()
        positions = [index for index in (lowered.find(term.lower()) for term in terms) if index >= 0]
        start = max(0, (min(positions) if positions else 0) - radius)
        end = min(len(content), start + radius * 2 + 80)
        text = " ".join(content[start:end].split())
        return ("… " if start else "") + text + (" …" if end < len(content) else "")

    def export_session(self, provider: str, session_id: str, fmt: str = "markdown") -> tuple[str, str] | None:
        """Return ``(body, media_type)`` for a whole session, or ``None`` if unknown."""
        with self.database.connect() as connection:
            rows = connection.execute(
                """SELECT occurred_at, kind, role, name, content, model, project_path,
                input_tokens, output_tokens, cache_read_tokens, cache_write_tokens, metadata
                FROM trace_events WHERE provider = ? AND session_id = ? ORDER BY occurred_at, id""",
                (provider, session_id),
            ).fetchall()
        if not rows:
            return None
        events = [{**dict(row), "metadata": json.loads(row["metadata"])} for row in rows]
        if fmt == "json":
            body = json.dumps(
                {"provider": provider, "session_id": session_id, "events": events}, indent=2, ensure_ascii=False
            )
            return body, "application/json"
        project = next((event["project_path"] for event in events if event["project_path"]), None)
        model = next((event["model"] for event in reversed(events) if event["model"]), None)
        lines = [
            f"# {provider} session {session_id}", "",
            f"- Project: {project or 'unknown'}", f"- Model: {model or 'unknown'}",
            f"- Started: {events[0]['occurred_at']}", f"- Last event: {events[-1]['occurred_at']}",
            f"- Events: {len(events)}", "",
        ]
        headings = {"thinking": "Thinking", "tool_call": "Tool call", "tool_result": "Tool result", "usage": "Usage"}
        for event in events:
            title = headings.get(event["kind"]) or (event["role"] or "message").capitalize()
            if event["kind"] in {"tool_call", "tool_result"} and event["name"]:
                title = f"{title}: {event['name']}"
            lines += [f"## {title}", f"_{event['occurred_at']}_", ""]
            content = event["content"] or ""
            if event["kind"] in {"tool_call", "tool_result"}:
                # A fence longer than any backtick run inside keeps the block intact.
                fence = "`" * max(3, max((len(run) for run in re.findall(r"`+", content)), default=0) + 1)
                lines += [fence, content, fence, ""]
            else:
                lines += [content, ""]
        return "\n".join(lines), "text/markdown"

    def export_usage_csv(self, days: int = 30) -> str:
        """Daily usage per provider, model and project as CSV text."""
        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        with self.database.connect() as connection:
            rows = connection.execute(
                """SELECT date(occurred_at, 'localtime') day, provider, COALESCE(model, '') model,
                COALESCE(project_path, '') project_path, COUNT(DISTINCT session_id) sessions,
                SUM(input_tokens) input_tokens, SUM(cache_write_tokens) cache_write_tokens,
                SUM(cache_read_tokens) cache_read_tokens, SUM(output_tokens) output_tokens,
                SUM(tool_calls) tool_calls, SUM(cost_usd) reported_cost_usd
                FROM usage_events WHERE occurred_at >= ?
                GROUP BY day, provider, model, project_path HAVING day IS NOT NULL
                ORDER BY day, provider, model, project_path""", (since,)
            ).fetchall()
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow([
            "day", "provider", "model", "project_path", "sessions", "input_tokens", "cache_write_tokens",
            "cache_read_tokens", "output_tokens", "tool_calls", "reported_cost_usd", "estimated_cost_usd",
        ])
        for row in rows:
            estimate = estimate_cost(
                row["model"] or None, row["input_tokens"] or 0, row["cache_write_tokens"] or 0,
                row["cache_read_tokens"] or 0, row["output_tokens"] or 0,
            )
            writer.writerow([
                row["day"], row["provider"], row["model"], row["project_path"], row["sessions"],
                row["input_tokens"], row["cache_write_tokens"], row["cache_read_tokens"], row["output_tokens"],
                row["tool_calls"], round(row["reported_cost_usd"] or 0, 6),
                "" if estimate is None else round(estimate, 6),
            ])
        return buffer.getvalue()
