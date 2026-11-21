"""读取来源语料（`sources.json` + `text/`）。

契约正本：CiMo `contracts/source-corpus.md`。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cixiu.source import CategoryCandidate, SourceLibrary
from cixiu.taxonomy import FILE_SET

_SOURCE_ID = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


@dataclass(frozen=True)
class CorpusSkip:
    source_id: str
    reason: str


@dataclass(frozen=True)
class CorpusLoad:
    libraries: tuple[SourceLibrary, ...]
    skipped: tuple[CorpusSkip, ...]


def _valid_source_id(source_id: str) -> bool:
    return bool(source_id) and _SOURCE_ID.fullmatch(source_id) is not None


def _read_text(path: Path) -> str:
    data = path.read_bytes()
    text = data.decode("utf-8")
    if text.startswith("﻿"):
        raise ValueError("text 文件带 BOM")
    return text


def _split_lines(text: str) -> tuple[str, ...]:
    if text.endswith("\n"):
        text = text[:-1]
    if not text:
        return ()
    return tuple(text.split("\n"))


def _sort_key(source: dict[str, Any]) -> tuple[int, str]:
    raw_order = source.get("order")
    order = raw_order if isinstance(raw_order, int) else 1 << 30
    return order, str(source.get("source_id", ""))


def _candidates(value: object) -> tuple[CategoryCandidate, ...] | None:
    if not isinstance(value, list):
        return None
    candidates: list[CategoryCandidate] = []
    for item in value:
        if not isinstance(item, dict):
            return None
        path = item.get("path")
        priority = item.get("priority")
        if not isinstance(path, str) or path not in FILE_SET:
            return None
        if not isinstance(priority, list) or not all(
            isinstance(part, int) for part in priority
        ):
            return None
        candidates.append(
            CategoryCandidate(
                material_path=path, priority=tuple(priority)
            )
        )
    return tuple(candidates)


def load_corpus(corpus_dir: Path) -> CorpusLoad:
    sources_path = corpus_dir / "sources.json"
    if not sources_path.is_file():
        raise FileNotFoundError(f"sources.json 不存在：{sources_path}")
    payload = json.loads(sources_path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1:
        raise ValueError(
            f"不支持的来源语料版本：{payload.get('schema_version')!r}"
        )
    raw_sources = payload.get("sources")
    if not isinstance(raw_sources, list):
        raise ValueError("sources.json 缺少 sources 数组")

    text_root = (corpus_dir / "text").resolve()
    libraries: list[SourceLibrary] = []
    skipped: list[CorpusSkip] = []
    seen: set[str] = set()
    for item in sorted(
        (source for source in raw_sources if isinstance(source, dict)),
        key=_sort_key,
    ):
        source_id = str(item.get("source_id", ""))
        if not _valid_source_id(source_id):
            skipped.append(CorpusSkip(source_id, "unsafe_source_id"))
            continue
        if source_id in seen:
            skipped.append(CorpusSkip(source_id, "duplicate_source_id"))
            continue
        seen.add(source_id)
        text_path = (text_root / f"{source_id}.txt").resolve()
        if text_root not in text_path.parents:
            skipped.append(
                CorpusSkip(source_id, "text_path_outside_corpus")
            )
            continue
        if not text_path.is_file():
            skipped.append(CorpusSkip(source_id, "missing_text"))
            continue
        try:
            words = _split_lines(_read_text(text_path))
        except (UnicodeDecodeError, ValueError):
            skipped.append(CorpusSkip(source_id, "invalid_text"))
            continue
        candidates = _candidates(item.get("categories"))
        if candidates is None:
            skipped.append(CorpusSkip(source_id, "invalid_categories"))
            continue
        raw_order = item.get("order")
        libraries.append(
            SourceLibrary(
                source_id=source_id,
                order=raw_order if isinstance(raw_order, int) else 0,
                categories=candidates,
                words=words,
            )
        )
    return CorpusLoad(libraries=tuple(libraries), skipped=tuple(skipped))
