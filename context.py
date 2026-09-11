"""Everything a view needs, assembled once at startup and passed down."""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Ctx:
    raw_sheets: dict
    sheets: dict
    quality_reports: dict
    tracker: Any
    analyzer: Any
    logger: Any
    speech_gen: Any
    api_key: str | None
