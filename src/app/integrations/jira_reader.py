from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import structlog

logger = structlog.get_logger("jira_reader")

try:
    import requests as _requests
except ImportError:
    _requests = None


def _require_requests() -> None:
    if _requests is None:
        raise RuntimeError(
            "The 'requests' package is required for Jira API access. "
            "Install it with: pip install requests"
        )


@dataclass
class JiraReaderConfig:
    base_url: str = ""
    email: str = ""
    api_token: str = ""
    project: str = ""


@dataclass
class JiraComment:
    id: str = ""
    author: str = ""
    body: str = ""
    created: str = ""


@dataclass
class JiraIssueData:
    key: str = ""
    summary: str = ""
    description: str = ""
    status: str = ""
    priority: str = ""
    reporter: str = ""
    assignee: str = ""
    labels: list[str] = field(default_factory=list)
    components: list[str] = field(default_factory=list)
    acceptance_criteria: list[str] = field(default_factory=list)
    impacted_areas: list[str] = field(default_factory=list)
    target_environment: str = ""
    dependencies: str = ""
    comments: list[JiraComment] = field(default_factory=list)
    issue_type: str = ""
    created: str = ""
    updated: str = ""
    raw_fields: dict = field(default_factory=dict)


_AC_KEYWORDS = [
    "acceptance criteria", "kabul kriterleri", "kabul kriteri",
    "definition of done", "beklenen davranış", "beklenen davranis",
    "done kriterleri", "tamamlanma kriterleri",
]

_IMPACT_KEYWORDS = [
    "scope", "kapsam", "impacted", "etkilenen", "affected",
    "impact", "etki alanı", "etki alani",
]

_ENV_KEYWORDS = [
    "environment", "ortam", "target environment", "hedef ortam",
    "deployment", "deploy",
]

_DEP_KEYWORDS = [
    "dependencies", "bağımlılıklar", "bagimliliklar", "blocker",
    "prerequisite", "ön koşul", "on kosul", "notes", "notlar",
]


@dataclass
class _ADFSection:
    heading: str = ""
    text: str = ""


def adf_to_text(adf: dict) -> str:
    if not isinstance(adf, dict):
        return str(adf or "")
    parts: list[str] = []
    _walk_adf(adf, parts, 0)
    return "\n".join(parts)


def _walk_adf(node: dict, parts: list[str], depth: int) -> None:
    node_type = node.get("type", "")

    if node_type == "text":
        text = node.get("text", "")
        if text:
            parts.append(text)
        return

    content = node.get("content", [])
    if not content:
        return

    if node_type == "doc":
        for child in content:
            _walk_adf(child, parts, depth)
        return

    if node_type == "paragraph":
        line_parts: list[str] = []
        for child in content:
            _collect_text(child, line_parts)
        if line_parts:
            parts.append("".join(line_parts))
        return

    if node_type == "heading":
        level = node.get("attrs", {}).get("level", 2)
        line_parts: list[str] = []
        for child in content:
            _collect_text(child, line_parts)
        if line_parts:
            parts.append(f"{'#' * level} {"".join(line_parts)}")
        return

    if node_type == "bulletList":
        for child in content:
            _walk_adf(child, parts, depth)
        return

    if node_type == "orderedList":
        for i, child in enumerate(content, 1):
            _collect_list_item(child, parts, depth, f"{i}. ")
        return

    if node_type == "listItem":
        _collect_list_item(node, parts, depth, "- ")
        return

    if node_type == "blockquote":
        for child in content:
            sub_parts: list[str] = []
            _walk_adf(child, sub_parts, depth + 1)
            for line in sub_parts:
                parts.append(f"> {line}")
        return

    if node_type == "codeBlock":
        lang = node.get("attrs", {}).get("language", "")
        parts.append(f"```{lang}")
        for child in content:
            _collect_text(child, parts)
        parts.append("```")
        return

    if node_type in ("panel", "expand"):
        for child in content:
            _walk_adf(child, parts, depth)
        return

    if node_type == "table":
        for row in content:
            if row.get("type") == "tableRow":
                row_cells: list[str] = []
                for cell in row.get("content", []):
                    cell_parts: list[str] = []
                    for cell_child in cell.get("content", []):
                        _collect_text(cell_child, cell_parts)
                    row_cells.append(" ".join(cell_parts))
                parts.append(" | ".join(row_cells))
        return

    if node_type == "mediaGroup":
        for child in content:
            if child.get("type") == "media":
                alt = child.get("attrs", {}).get("alt", "media")
                parts.append(f"[{alt}]")
        return

    for child in content:
        _walk_adf(child, parts, depth)


def _collect_text(node: dict, parts: list[str]) -> None:
    if node.get("type") == "text":
        parts.append(node.get("text", ""))
        return
    for child in node.get("content", []):
        _collect_text(child, parts)


def _collect_list_item(node: dict, parts: list[str], depth: int, prefix: str) -> None:
    indent = "  " * depth
    content = node.get("content", [])
    for child in content:
        if child.get("type") == "paragraph":
            line_parts: list[str] = []
            for inline in child.get("content", []):
                _collect_text(inline, line_parts)
            if line_parts:
                parts.append(f"{indent}{prefix}{"".join(line_parts)}")
        elif child.get("type") in ("bulletList", "orderedList"):
            _walk_adf(child, parts, depth + 1)
        else:
            _walk_adf(child, parts, depth + 1)


def _parse_adf_sections(adf: dict) -> tuple[str, list[_ADFSection]]:
    if not isinstance(adf, dict):
        return str(adf or ""), []

    plain_text = adf_to_text(adf)
    sections: list[_ADFSection] = []

    content_list = adf.get("content", [])
    current_heading = ""
    current_lines: list[str] = []

    def _flush():
        if current_heading and current_lines:
            sections.append(
                _ADFSection(
                    heading=current_heading,
                    text="\n".join(current_lines),
                )
            )

    for block in content_list:
        block_type = block.get("type", "")

        if block_type == "heading":
            _flush()
            heading_parts: list[str] = []
            for inline in block.get("content", []):
                _collect_text(inline, heading_parts)
            current_heading = "".join(heading_parts)
            current_lines = []
            continue

        block_text_parts: list[str] = []
        _walk_adf(block, block_text_parts, 0)
        block_text = "\n".join(block_text_parts)

        if block_text.strip():
            if block_type in (
                "bulletList", "orderedList", "blockquote", "panel",
            ):
                current_lines.append(block_text)
            else:
                for line in block_text.split("\n"):
                    current_lines.append(line)

    _flush()
    return plain_text, sections


class JiraReader:
    def __init__(self, config: JiraReaderConfig) -> None:
        _require_requests()
        self.config = config
        self.base_url = f"{config.base_url}/rest/api/3"
        self.auth = (config.email, config.api_token)
        self.headers = {"Accept": "application/json"}

    def fetch_issue(self, issue_key: str) -> Optional[JiraIssueData]:
        url = f"{self.base_url}/issue/{issue_key}"
        try:
            resp = _requests.get(url, auth=self.auth, headers=self.headers)
            resp.raise_for_status()
            issue = resp.json()
        except _requests.exceptions.RequestException as e:
            logger.error("jira_fetch_failed", key=issue_key, error=str(e))
            return None

        return self._parse_issue(issue)

    def fetch_comments(self, issue_key: str) -> list[JiraComment]:
        url = f"{self.base_url}/issue/{issue_key}/comment"
        try:
            resp = _requests.get(url, auth=self.auth, headers=self.headers)
            resp.raise_for_status()
            data = resp.json()
        except _requests.exceptions.RequestException:
            return []

        comments = []
        for c in data.get("comments", []):
            author_obj = c.get("author", {})
            author = author_obj.get("displayName") or author_obj.get("emailAddress", "")
            body_adf = c.get("body", {})
            body_text = adf_to_text(body_adf) if isinstance(body_adf, dict) else str(body_adf)
            comments.append(JiraComment(
                id=c.get("id", ""),
                author=author,
                body=body_text,
                created=c.get("created", ""),
            ))
        return comments

    def _parse_issue(self, issue: dict) -> JiraIssueData:
        fields = issue.get("fields", {})

        reporter_obj = fields.get("reporter") or {}
        assignee_obj = fields.get("assignee") or {}
        reporter = reporter_obj.get("displayName") or reporter_obj.get("emailAddress", "")
        assignee = assignee_obj.get("displayName") or assignee_obj.get("emailAddress", "")

        description_raw = fields.get("description", "")
        description_text, sections = (
            _parse_adf_sections(description_raw)
            if isinstance(description_raw, dict)
            else (str(description_raw or ""), [])
        )

        acceptance_criteria = self._extract_section(sections, _AC_KEYWORDS)
        impacted_areas = self._extract_section(sections, _IMPACT_KEYWORDS)
        target_environment = self._extract_first_line(sections, _ENV_KEYWORDS)
        dependencies = self._extract_first_line(sections, _DEP_KEYWORDS)

        if not impacted_areas:
            labels = fields.get("labels") or []
            components = [c.get("name", "") for c in (fields.get("components") or [])]
            impacted_areas = labels + [c for c in components if c]

        if not dependencies:
            issue_links = fields.get("issuelinks") or []
            dep_parts: list[str] = []
            for link in issue_links:
                link_type = link.get("type", {}).get("name", "")
                outward = link.get("outwardIssue", {})
                inward = link.get("inwardIssue", {})
                if outward:
                    dep_parts.append(f"{link_type}: {outward.get('key', '')}")
                if inward:
                    dep_parts.append(f"{link_type}: {inward.get('key', '')}")
            if dep_parts:
                dependencies = "; ".join(dep_parts)

        status_obj = fields.get("status") or {}
        priority_obj = fields.get("priority") or {}

        return JiraIssueData(
            key=issue.get("key", ""),
            summary=fields.get("summary", ""),
            description=description_text,
            status=status_obj.get("name", ""),
            priority=priority_obj.get("name", ""),
            reporter=reporter,
            assignee=assignee,
            labels=fields.get("labels") or [],
            components=[c.get("name", "") for c in (fields.get("components") or [])],
            acceptance_criteria=acceptance_criteria,
            impacted_areas=impacted_areas,
            target_environment=target_environment,
            dependencies=dependencies or "none",
            issue_type=(fields.get("issuetype") or {}).get("name", ""),
            created=fields.get("created", ""),
            updated=fields.get("updated", ""),
            raw_fields=fields,
        )

    @staticmethod
    def _extract_section(sections: list[_ADFSection], keywords: list[str]) -> list[str]:
        for section in sections:
            if any(kw in section.heading.lower() for kw in keywords):
                return [line.strip() for line in section.text.split("\n") if line.strip()]
        return []

    @staticmethod
    def _extract_first_line(sections: list[_ADFSection], keywords: list[str]) -> str:
        for section in sections:
            if any(kw in section.heading.lower() for kw in keywords):
                return section.text.strip()
        return ""


def build_jira_config_from_env() -> Optional[JiraReaderConfig]:
    import os

    email = os.environ.get("DQG_JIRA_EMAIL", "")
    token = os.environ.get("DQG_JIRA_API_TOKEN", "")
    if not email or not token:
        return None
    return JiraReaderConfig(
        base_url=os.environ.get("DQG_JIRA_BASE_URL", ""),
        email=email,
        api_token=token,
        project=os.environ.get("DQG_JIRA_PROJECT", ""),
    )
