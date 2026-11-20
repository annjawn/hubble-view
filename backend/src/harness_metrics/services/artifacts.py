import json
import re
from pathlib import Path
from typing import Any

from harness_metrics.database import Database

MAX_ARTIFACT_BYTES = 512_000
SECRET_KEY = re.compile(
    r"(?i)(api[_-]?key|private[_-]?key|token|password|passwd|secret|credential|authorization|bearer)"
)
# Keys such as `max_tokens` or `tokenizer` describe limits, not credentials.
NON_SECRET_KEY = re.compile(r"(?i)(tokens|tokenizer|token[_-]?(count|limit|budget))")
# Well-known credential shapes that can appear in values (for example in an
# MCP server's `args` list) regardless of the key they are stored under.
SECRET_VALUE = re.compile(
    r"(sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}"
    r"|xox[abprs]-[A-Za-z0-9-]{10,}|AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z_-]{30,}"
    r"|(?i:bearer)\s+[A-Za-z0-9._~+/=-]{16,})"
)
MASK = "••••••••"


def _is_secret_key(key: object) -> bool:
    text = str(key)
    return bool(SECRET_KEY.search(text)) and not NON_SECRET_KEY.search(text)


# Provider-native configuration locations, normalized into shared UI categories.
# A path may intentionally appear twice when it contains both settings and hooks.
GLOBAL_PATTERNS: dict[str, list[tuple[str, str]]] = {
    "claude": [
        ("memory", ".claude/CLAUDE.md"),
        ("settings", ".claude/settings.json"),
        ("hooks", ".claude/settings.json"), ("rules", ".claude/rules/**/*.md"),
        ("skills", ".claude/skills/**/SKILL.md"),
    ],
    "codex": [
        ("instructions", ".codex/AGENTS.md"), ("settings", ".codex/config.toml"),
        ("hooks", ".codex/config.toml"), ("rules", ".codex/rules/**/*.rules"),
        ("skills", ".codex/skills/**/SKILL.md"), ("skills", ".agents/skills/**/SKILL.md"),
    ],
    "cursor": [
        ("settings", ".cursor/mcp.json"), ("hooks", ".cursor/hooks.json"),
        ("skills", ".cursor/skills/**/SKILL.md"), ("skills", ".cursor/skills-cursor/**/SKILL.md"),
        ("skills", ".agents/skills/**/SKILL.md"),
    ],
    "kiro": [
        ("settings", ".kiro/settings/*.json"), ("rules", ".kiro/steering/**/*.md"),
        ("hooks", ".kiro/hooks/**/*"), ("skills", ".kiro/skills/**/SKILL.md"),
        ("skills", ".kiro/powers/*/plugin.json"), ("settings", ".kiro/powers/installed.json"),
    ],
    "opencode": [
        ("instructions", ".config/opencode/AGENTS.md"), ("settings", ".config/opencode/opencode.json*"),
        ("skills", ".config/opencode/skills/**/SKILL.md"), ("skills", ".agents/skills/**/SKILL.md"),
        ("rules", ".config/opencode/agents/*.md"), ("hooks", ".config/opencode/plugins/**/*"),
    ],
    "antigravity": [
        ("instructions", ".gemini/GEMINI.md"), ("settings", ".gemini/settings.json"),
        ("settings", ".gemini/config/config.json"), ("settings", ".gemini/config/mcp_config.json"),
        ("rules", ".gemini/antigravity/rules/**/*.md"),
        ("hooks", ".gemini/config/global_workflows/**/*.md"),
        ("skills", ".gemini/antigravity/skills/**/SKILL.md"),
    ],
}

PROJECT_PATTERNS: dict[str, list[tuple[str, str]]] = {
    "claude": [
        ("memory", "CLAUDE.md"), ("memory", "CLAUDE.local.md"),
        ("memory", ".claude/CLAUDE.md"), ("settings", ".claude/settings.json"),
        ("settings", ".claude/settings.local.json"), ("hooks", ".claude/settings.json"),
        ("hooks", ".claude/settings.local.json"), ("rules", ".claude/rules/**/*.md"),
        ("skills", ".claude/skills/**/SKILL.md"),
    ],
    "codex": [
        ("instructions", "AGENTS.md"), ("instructions", ".codex/AGENTS.md"),
        ("settings", ".codex/config.toml"), ("hooks", ".codex/config.toml"),
        ("rules", ".codex/rules/**/*.rules"), ("skills", ".agents/skills/**/SKILL.md"),
        ("skills", ".codex/skills/**/SKILL.md"),
    ],
    "cursor": [
        ("instructions", "AGENTS.md"), ("instructions", "CLAUDE.md"),
        ("rules", ".cursorrules"), ("rules", ".cursor/rules/**/*.mdc"),
        ("hooks", ".cursor/hooks.json"), ("settings", ".cursor/mcp.json"),
        ("skills", ".cursor/skills/**/SKILL.md"), ("skills", ".agents/skills/**/SKILL.md"),
    ],
    "kiro": [
        ("instructions", "AGENTS.md"), ("rules", ".kiro/steering/**/*.md"),
        ("hooks", ".kiro/hooks/**/*"), ("settings", ".kiro/settings/*.json"),
        ("skills", ".kiro/skills/**/SKILL.md"), ("skills", ".kiro/powers/*/plugin.json"),
        ("settings", ".kiro/specs/**/*.md"),
    ],
    "opencode": [
        ("instructions", "AGENTS.md"), ("settings", "opencode.json*"),
        ("rules", ".opencode/agents/*.md"), ("hooks", ".opencode/plugins/**/*"),
        ("skills", ".opencode/skills/**/SKILL.md"), ("skills", ".agents/skills/**/SKILL.md"),
        ("skills", ".claude/skills/**/SKILL.md"),
    ],
    "antigravity": [
        ("instructions", "GEMINI.md"), ("rules", ".agents/rules/**/*.md"),
        ("rules", ".agent/rules/**/*.md"), ("hooks", ".agents/workflows/**/*.md"),
        ("hooks", ".agent/workflows/**/*.md"), ("skills", ".agents/skills/**/SKILL.md"),
        ("settings", ".gemini/settings.json"),
    ],
}


def _redact(content: str, suffix: str) -> str:
    if suffix.lower() in {".json", ".jsonc"}:
        try:
            value = json.loads(content)

            def clean(item: Any, secret: bool = False) -> Any:
                if isinstance(item, dict):
                    return {key: clean(child, secret or _is_secret_key(key)) for key, child in item.items()}
                if isinstance(item, list):
                    return [clean(child, secret) for child in item]
                if isinstance(item, str):
                    return MASK if secret and item else SECRET_VALUE.sub(MASK, item)
                return item

            return json.dumps(clean(value), indent=2, ensure_ascii=False)
        except (json.JSONDecodeError, TypeError, RecursionError):
            pass

    def mask_line(match: re.Match[str]) -> str:
        key = match.group("key")
        return match.group(0) if NON_SECRET_KEY.search(key) else f'{match.group("prefix")}"{MASK}"'

    content = re.sub(
        r"(?im)^(?P<prefix>\s*[\"']?(?P<key>[\w.-]*(?:key|token|password|passwd|secret|credential|authorization)[\w.-]*)"
        r"[\"']?\s*[=:]\s*)(.+)$",
        mask_line, content,
    )
    return SECRET_VALUE.sub(MASK, content)


class ArtifactService:
    def __init__(self, database: Database, home: Path | None = None):
        self.database = database
        self.home = home or Path.home()

    def _projects(self, provider: str) -> list[Path]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """SELECT DISTINCT project_path FROM (
                    SELECT project_path FROM trace_events WHERE provider = ?
                    UNION SELECT project_path FROM usage_events WHERE provider = ?
                ) WHERE project_path IS NOT NULL""", (provider, provider)
            ).fetchall()
        return [Path(row["project_path"]).expanduser() for row in rows if Path(row["project_path"]).is_absolute()]

    def _collect(self, roots: list[tuple[Path, str, str | None, str, list[tuple[str, str]]]]) -> list[dict[str, Any]]:
        artifacts: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()

        def collect(base: Path, scope: str, project_path: str | None, provider: str, patterns: list[tuple[str, str]]) -> None:
            for category, pattern in patterns:
                try:
                    matches = base.glob(pattern)
                    for path in matches:
                        if not path.is_file() or path.stat().st_size > MAX_ARTIFACT_BYTES:
                            continue
                        identity = (category, str(path))
                        if identity in seen:
                            existing = next(item for item in artifacts if (item["category"], item["path"]) == identity)
                            if provider not in existing["providers"]:
                                existing["providers"].append(provider)
                            continue
                        seen.add(identity)
                        content = path.read_text(encoding="utf-8", errors="replace")
                        artifacts.append({
                            "id": f"{category}:{path}", "category": category, "scope": scope,
                            "name": path.name, "path": str(path), "project_path": project_path,
                            "providers": [provider],
                            "content": _redact(content, path.suffix), "size": path.stat().st_size,
                            "modified_at": path.stat().st_mtime,
                        })
                except OSError:
                    continue

        for base, scope, project_path, provider, patterns in roots:
            collect(base, scope, project_path, provider, patterns)
        artifacts.sort(key=lambda item: (item["category"], item["name"].lower()))
        return artifacts

    def global_list(self, provider: str) -> dict[str, Any]:
        artifacts = self._collect([
            (self.home, "global", None, provider, GLOBAL_PATTERNS.get(provider, []))
        ])
        return {"provider": provider, "projects": [], "artifacts": artifacts}

    def project_list(self, project_path: str) -> dict[str, Any] | None:
        project = Path(project_path).expanduser()
        known_projects = {path for provider in PROJECT_PATTERNS for path in self._projects(provider)}
        if not project.is_absolute() or project not in known_projects or not project.is_dir():
            return None
        roots = [
            (project, "project", str(project), provider, patterns)
            for provider, patterns in PROJECT_PATTERNS.items()
        ]
        artifacts = self._collect(roots)
        # Claude auto-memory is project-scoped despite living below ~/.claude.
        # <project> is the path with non-alphanumeric characters replaced by "-"
        # (https://code.claude.com/docs/en/sessions "Where transcripts are stored").
        encoded = re.sub(r"[^A-Za-z0-9]", "-", str(project))
        memory = self._collect([(
            self.home, "project", str(project), "claude",
            [("memory", f".claude/projects/{encoded}/memory/**/*.md")],
        )])
        existing = {(item["category"], item["path"]) for item in artifacts}
        artifacts.extend(item for item in memory if (item["category"], item["path"]) not in existing)
        artifacts.sort(key=lambda item: (item["category"], item["name"].lower()))
        return {"project_path": str(project), "artifacts": artifacts}
