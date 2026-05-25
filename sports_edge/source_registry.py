from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_REGISTRY_PATH = REPO_ROOT / "docs" / "ai" / "source_registry.json"
ACTIVE_RESEARCH_CATEGORIES = ("sports", "geopolitics", "crypto", "macro", "weather", "culture")
REGISTRY_FIELDS = (
    "id",
    "name",
    "category",
    "source_type",
    "access",
    "freshness",
    "history_depth",
    "reliability_tier",
    "license_notes",
    "query_template",
    "allowed_by_default",
)
HIGH_RELIABILITY_TIERS = {"primary", "high"}


@dataclass(frozen=True)
class SourceRecord:
    id: str
    name: str
    category: str
    source_type: str
    access: str
    freshness: str
    history_depth: str
    reliability_tier: str
    license_notes: str
    query_template: str
    allowed_by_default: bool

    @classmethod
    def from_dict(cls, row: dict[str, Any]) -> "SourceRecord":
        missing = [field for field in REGISTRY_FIELDS if field not in row]
        if missing:
            raise ValueError(f"Source registry row is missing fields: {', '.join(missing)}")
        values = {field: row[field] for field in REGISTRY_FIELDS}
        for key, value in values.items():
            if key == "allowed_by_default":
                if not isinstance(value, bool):
                    raise ValueError(f"{row.get('id', '<unknown>')} has non-boolean allowed_by_default")
            elif not isinstance(value, str) or not value.strip():
                raise ValueError(f"{row.get('id', '<unknown>')} has invalid {key}")
        return cls(**values)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "category": self.category,
            "source_type": self.source_type,
            "access": self.access,
            "freshness": self.freshness,
            "history_depth": self.history_depth,
            "reliability_tier": self.reliability_tier,
            "license_notes": self.license_notes,
            "query_template": self.query_template,
            "allowed_by_default": self.allowed_by_default,
        }

    @property
    def is_high_reliability(self) -> bool:
        return self.reliability_tier in HIGH_RELIABILITY_TIERS


class SourceRegistry:
    def __init__(self, path: Path | str = DEFAULT_SOURCE_REGISTRY_PATH) -> None:
        self.path = Path(path)
        self.sources = self._load()

    def _load(self) -> list[SourceRecord]:
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            raise ValueError("Source registry root must be a JSON list")
        return [SourceRecord.from_dict(row) for row in payload]

    def validate(self) -> list[str]:
        errors: list[str] = []
        seen_ids: set[str] = set()
        for source in self.sources:
            if source.id in seen_ids:
                errors.append(f"duplicate source id: {source.id}")
            seen_ids.add(source.id)
            if source.access in {"paid", "restricted", "manual-licensed", "unofficial", "free-key"} and source.allowed_by_default:
                errors.append(f"{source.id} requires access review but is allowed by default")

        for category in ACTIVE_RESEARCH_CATEGORIES:
            category_sources = [source for source in self.sources if source.category == category]
            if len(category_sources) < 5:
                errors.append(f"{category} has fewer than five sources")
            high_reliability = [source for source in category_sources if source.is_high_reliability]
            if len(high_reliability) < 2:
                errors.append(f"{category} has fewer than two high-reliability sources")
        return errors

    def require_valid(self) -> None:
        errors = self.validate()
        if errors:
            raise ValueError("Invalid source registry:\n" + "\n".join(f"- {error}" for error in errors))

    def categories(self) -> list[str]:
        return sorted({source.category for source in self.sources})

    def for_category(
        self,
        category: str,
        *,
        include_global: bool = False,
        include_polymarket: bool = False,
        allowed_only: bool = False,
    ) -> list[SourceRecord]:
        allowed_categories = {category}
        if include_global:
            allowed_categories.add("global")
        if include_polymarket:
            allowed_categories.add("polymarket")
        sources = [source for source in self.sources if source.category in allowed_categories]
        if allowed_only:
            sources = [source for source in sources if source.allowed_by_default]
        return sorted(sources, key=self._sort_key)

    def search(
        self,
        topic: str,
        *,
        category: str | None = None,
        allowed_only: bool = False,
        limit: int = 12,
    ) -> list[SourceRecord]:
        candidates = self.sources
        if allowed_only:
            candidates = [source for source in candidates if source.allowed_by_default]
        scored = [
            (self._topic_score(source, topic, category), source)
            for source in candidates
            if category is None or source.category in {category, "global", "polymarket"}
        ]
        scored = [(score, source) for score, source in scored if score > 0.0]
        scored.sort(key=lambda pair: (pair[0], self._reliability_weight(pair[1]), pair[1].allowed_by_default), reverse=True)
        return [source for _, source in scored[:limit]]

    def render_query(self, source: SourceRecord, **values: str) -> str:
        safe_values = _SafeFormatDict({key: value or "" for key, value in values.items()})
        return source.query_template.format_map(safe_values)

    @staticmethod
    def _sort_key(source: SourceRecord) -> tuple[int, str, str]:
        return (-SourceRegistry._reliability_weight(source), source.category, source.id)

    @staticmethod
    def _reliability_weight(source: SourceRecord) -> int:
        weights = {"primary": 3, "high": 2, "medium": 1, "low": 0}
        return weights.get(source.reliability_tier, 0)

    @staticmethod
    def _topic_score(source: SourceRecord, topic: str, category: str | None) -> float:
        score = 0.0
        if category and source.category == category:
            score += 5.0
        if source.category == "polymarket":
            score += 2.0
        if source.category == "global":
            score += 1.5
        if source.allowed_by_default:
            score += 0.25
        if source.is_high_reliability:
            score += 0.25

        corpus = " ".join(
            [
                source.id,
                source.name,
                source.category,
                source.source_type,
                source.freshness,
                source.history_depth,
                source.query_template,
            ]
        ).lower()
        for token in topic_tokens(topic):
            if token in corpus:
                score += 1.0
        return score


class _SafeFormatDict(dict[str, str]):
    def __missing__(self, key: str) -> str:
        return ""


def topic_tokens(topic: str) -> list[str]:
    return [token for token in re.findall(r"[a-z0-9]{3,}", topic.lower()) if token not in {"will", "the", "and", "for"}]


def validate_source_registry(path: Path | str = DEFAULT_SOURCE_REGISTRY_PATH) -> list[str]:
    return SourceRegistry(path).validate()
