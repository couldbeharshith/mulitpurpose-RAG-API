"""Passage references for workspace answers."""

import re
from typing import Literal

from pydantic import BaseModel, Field

from backend.models import RelevantChunk


class Passage(BaseModel):
    id: int
    text: str
    kind: Literal["page", "slide", "sheet", "passage"] = "passage"
    location: int | None = None


class Review(BaseModel):
    answer: str
    citations: list[Passage] = Field(default_factory=list)


MARKER = re.compile(r"[\[【［]\s*source\s*[:：]\s*(\d{1,5})\s*[\]】］]", re.IGNORECASE)


def numbered_passages(chunks: list[RelevantChunk], namespace: str) -> list[Passage]:
    passages = []
    for number, match in enumerate(chunks, 1):
        metadata = match.chunk.metadata
        kind = {"pptx": "slide", "xlsx": "sheet"}.get(metadata.document_type, "passage")
        if metadata.document_type == "pdf" and namespace.endswith(("_markdown_pages_v1", "_text_pages_v1")):
            kind = "page"
        location = metadata.page_number if kind != "passage" and metadata.page_number > 0 else None
        passages.append(Passage(id=number, text=match.chunk.content, kind=kind, location=location))
    return passages


def cited_answer(answer: str, passages: list[Passage]) -> Review:
    valid = {str(passage.id): passage for passage in passages}
    used = {}

    def keep(match: re.Match) -> str:
        identifier = str(int(match[1]))
        if identifier not in valid:
            return ""
        used[identifier] = valid[identifier]
        return f"[source:{identifier}]"

    return Review(answer=MARKER.sub(keep, answer), citations=list(used.values()))


def render_passages(passages: list[Passage]) -> str:
    return "\n\n".join(f"Source {item.id}:\n{item.text}" for item in passages)
