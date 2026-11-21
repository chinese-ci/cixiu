"""词修的输入模型：一个已映射到物料类目的来源。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CategoryCandidate:
    material_path: str
    priority: tuple[int, ...]


@dataclass(frozen=True)
class SourceLibrary:
    source_id: str
    order: int
    categories: tuple[CategoryCandidate, ...]
    words: tuple[str, ...]
