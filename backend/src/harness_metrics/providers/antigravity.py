import hashlib
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from urllib.parse import unquote, urlparse

from .base import ProviderAdapter, UsageEvent
from .jsonl import _project_root


WireValue = int | bytes


def _varint(data: bytes, position: int) -> tuple[int, int]:
    value = 0
    shift = 0
    while position < len(data) and shift < 70:
        byte = data[position]
        position += 1
        value |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return value, position
        shift += 7
    raise ValueError("invalid protobuf varint")


def _fields(data: bytes) -> list[tuple[int, int, WireValue]]:
    result: list[tuple[int, int, WireValue]] = []
    position = 0
    try:
        while position < len(data):
            tag, position = _varint(data, position)
            number, wire = tag >> 3, tag & 7
            if not number:
                return []
            if wire == 0:
                value, position = _varint(data, position)
            elif wire == 1:
                value = int.from_bytes(data[position:position + 8], "little")
                position += 8
            elif wire == 2:
                size, position = _varint(data, position)
                value = data[position:position + size]
                position += size
            elif wire == 5:
                value = int.from_bytes(data[position:position + 4], "little")
                position += 4
            else:
                return []
            result.append((number, wire, value))
    except (ValueError, IndexError):
        return []
    return result


def _message(data: bytes, number: int) -> bytes | None:
    return next((value for field, wire, value in _fields(data) if field == number and wire == 2 and isinstance(value, bytes)), None)


def _integer(data: bytes, number: int) -> int:
    value = next((value for field, wire, value in _fields(data) if field == number and wire == 0 and isinstance(value, int)), 0)
    return min(value, 2**63 - 1)


def _string(data: bytes, number: int) -> str | None:
    value = _message(data, number)
    if value is None:
        return None
    try:
        text = value.decode("utf-8")
    except UnicodeDecodeError:
        return None
    return text or None


def _timestamp(data: bytes | None) -> datetime | None:
    if not data:
        return None
    seconds = _integer(data, 1)
    nanos = _integer(data, 2)
    if seconds <= 0 or nanos > 999_999_999:
        return None
    try:
        return datetime.fromtimestamp(seconds + nanos / 1_000_000_000, timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None


def _workspace(blob: bytes | None) -> str | None:
    if not blob:
        return None
    uri = _string(_message(blob, 1) or b"", 1)
    if not uri:
        return None
    parsed = urlparse(uri)
    path = unquote(parsed.path) if parsed.scheme == "file" else uri
    return _project_root(path)


class AntigravityAdapter(ProviderAdapter):
    id = "antigravity"
    name = "Antigravity"

    @staticmethod
    def _roots() -> list[Path]:
        gemini = Path.home() / ".gemini"
        return [gemini / "antigravity" / "conversations", gemini / "antigravity-ide" / "conversations"]

    def log_roots(self) -> list[Path]:
        return self._roots()

    def discover(self) -> Iterable[Path]:
        seen: set[Path] = set()
        for root in self._roots():
            if root.exists():
                for database in root.glob("*.db"):
                    resolved = database.resolve()
                    if resolved not in seen:
                        seen.add(resolved)
                        yield database

    def parse(self, path: Path) -> Iterable[UsageEvent]:
        try:
            connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5)
            rows = connection.execute("SELECT idx, data FROM gen_metadata ORDER BY idx").fetchall()
            step_rows = connection.execute(
                "SELECT metadata FROM steps WHERE step_type = 15 ORDER BY idx"
            ).fetchall()
            trajectory = connection.execute(
                "SELECT data FROM trajectory_metadata_blob ORDER BY id LIMIT 1"
            ).fetchone()
            tool_calls = connection.execute(
                "SELECT COUNT(*) FROM steps WHERE step_type = 132"
            ).fetchone()[0]
            connection.close()
        except sqlite3.Error:
            return

        trajectory_blob = trajectory[0] if trajectory else None
        created_at = _timestamp(_message(trajectory_blob, 2) if trajectory_blob else None)
        fallback = created_at or datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
        project_path = _workspace(trajectory_blob)
        session_id = path.stem
        seen_responses: set[str] = set()

        for ordinal, (index, blob) in enumerate(rows):
            chat_model = _message(blob, 1)
            usage = _message(chat_model or b"", 4)
            if not chat_model or not usage:
                continue
            input_tokens = _integer(usage, 1) + _integer(usage, 2)
            cache_read = _integer(usage, 5)
            visible_output = _integer(usage, 9)
            reasoning = _integer(usage, 10)
            if not any((input_tokens, cache_read, visible_output, reasoning)):
                continue
            response_id = _string(usage, 11)
            if response_id and response_id in seen_responses:
                continue
            if response_id:
                seen_responses.add(response_id)
            model = _string(chat_model, 19) or _string(chat_model, 21) or "Unknown model"
            occurred = fallback
            duration_ms = 0
            if ordinal < len(step_rows):
                step_metadata = step_rows[ordinal][0]
                start = _timestamp(_message(step_metadata, 1))
                end = _timestamp(_message(step_metadata, 8))
                occurred = start or end or fallback
                if start and end:
                    duration_ms = max(0, int((end - start).total_seconds() * 1000))
            raw_id = f"antigravity:{session_id}:{response_id or index}"
            yield UsageEvent(
                id=hashlib.sha256(raw_id.encode()).hexdigest(),
                provider=self.id,
                occurred_at=occurred.isoformat(),
                session_id=session_id,
                project_path=project_path,
                model=model,
                input_tokens=input_tokens,
                output_tokens=visible_output + reasoning,
                cache_read_tokens=cache_read,
                duration_ms=duration_ms,
                tool_calls=int(tool_calls) if ordinal == len(rows) - 1 else 0,
                metadata={
                    "type": "generation",
                    "reasoning_tokens": reasoning,
                    "visible_output_tokens": visible_output,
                    "usage_source": "antigravity-db",
                },
            )
