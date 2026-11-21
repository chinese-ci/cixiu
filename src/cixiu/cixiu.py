"""词修流水线：条级接受 → 字形归一 → 去重/类目归属 → 物料与私有报告。

输入是来源层已筛选并映射好物料类目的来源（`SourceLibrary`），输出是完整的纯词库
物料目录、私有清洗报告与每类抽检样本。物料只含归一后的词条字符串，不含来源、
权重、频次或原字形。
"""

from __future__ import annotations

import gc
import json
import random
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from cixiu.cleaning import clean_words
from cixiu.glyph import (
    GlyphTable,
    Normalization,
    load_glyph_table,
    normalize_word,
)
from cixiu.material import MaterialCategory, write_material
from cixiu.source import CategoryCandidate, SourceLibrary
from cixiu.taxonomy import MATERIAL_CATEGORIES, material_file_paths

PLANNED_FILES = frozenset(
    f"{category.path}/{file.name}"
    for category in MATERIAL_CATEGORIES
    for file in category.files
    if file.planned
)

EXAMPLE_LIMIT = 20


@dataclass(frozen=True)
class CurationSettings:
    material_root: Path
    report_path: Path
    samples_root: Path | None = None
    events_path: Path | None = None
    seed: int = 0
    sample_size: int = 100
    example_limit: int = EXAMPLE_LIMIT


@dataclass(frozen=True)
class CurationResult:
    material_root: Path
    report_path: Path
    samples_root: Path | None
    report: dict[str, Any]


@dataclass(frozen=True, slots=True)
class _PendingWord:
    cleaned: str
    library_key: str
    candidates: tuple[CategoryCandidate, ...]
    weight: int


@dataclass(frozen=True, slots=True)
class _Occurrence:
    key: str
    display: str
    library_key: str
    candidates: tuple[CategoryCandidate, ...]
    weight: int


@dataclass(slots=True)
class _LibraryRecord:
    library: SourceLibrary
    candidates: tuple[CategoryCandidate, ...] = ()
    excluded: bool = False
    reason: str | None = None
    raw_entries: int = 0
    cleaned_entries: int = 0
    rejected: dict[str, int] = field(default_factory=dict)
    glyph_dropped: int = 0
    occurrences: int = 0


@dataclass
class _GlyphStats:
    word_actions: Counter[str] = field(default_factory=Counter)
    change_actions: Counter[str] = field(default_factory=Counter)
    dropped_ambiguous: int = 0
    dropped_unknown_scope: int = 0
    dropped_outside_table: int = 0
    examples: dict[str, list[dict[str, str]]] = field(
        default_factory=lambda: defaultdict(list)
    )
    event_count: int = 0

    def record(self, raw: str, result: Normalization, limit: int) -> None:
        self.word_actions[result.action] += 1
        if result.action == "dropped":
            if result.reason_code == "scope_unknown":
                self.dropped_unknown_scope += 1
                bucket = "dropped_unknown_scope"
            elif result.reason_code == "outside_table":
                self.dropped_outside_table += 1
                bucket = "dropped_outside_table"
            else:
                self.dropped_ambiguous += 1
                bucket = "dropped_ambiguous"
        else:
            bucket = result.action
        for change in result.changes:
            self.change_actions[change.action] += 1
        self.event_count += 1
        if len(self.examples[bucket]) < limit:
            self.examples[bucket].append(
                {
                    "raw": raw,
                    "normalized": result.word,
                    "action": result.action,
                    "reason": result.reason or "",
                    "reason_code": result.reason_code or "",
                    "changes": "; ".join(
                        f"{change.char}->{change.output} ({change.action})"
                        for change in result.changes
                    ),
                }
            )


def _best_candidate(
    candidates: Iterable[CategoryCandidate],
) -> CategoryCandidate | None:
    candidates = tuple(candidates)
    if not candidates:
        return None
    return min(
        candidates,
        key=lambda candidate: (
            candidate.priority,
            candidate.material_path,
        ),
    )


def _key(display: str) -> str:
    return "".join(
        character.lower() if character.isascii() else character
        for character in display
    )


def _select_display(occurrences: list[_Occurrence]) -> str:
    libraries: dict[str, set[str]] = defaultdict(set)
    counts: Counter[str] = Counter()
    for occurrence in occurrences:
        libraries[occurrence.display].add(occurrence.library_key)
        counts[occurrence.display] += occurrence.weight
    return min(
        counts,
        key=lambda display: (
            -len(libraries[display]),
            -counts[display],
            display,
        ),
    )


def _select_category(
    occurrences: list[_Occurrence],
) -> CategoryCandidate | None:
    candidates = [
        candidate
        for occurrence in occurrences
        for candidate in occurrence.candidates
    ]
    return _best_candidate(candidates)


def _sample(
    words: list[str], size: int, seed: int, key: str
) -> list[str]:
    ordered = sorted(set(words))
    if len(ordered) <= size:
        return ordered
    generator = random.Random(f"{seed}:{key}")
    return generator.sample(ordered, size)


def _write_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def run_cixiu(
    libraries: Iterable[SourceLibrary],
    settings: CurationSettings,
    *,
    glyph_table: GlyphTable | None = None,
) -> CurationResult:
    table = glyph_table or load_glyph_table()
    records: list[_LibraryRecord] = []
    occurrences: list[_Occurrence] = []
    glyph_stats = _GlyphStats()
    rejection_counts: Counter[str] = Counter()
    rejection_examples: list[dict[str, str]] = []
    pending: list[_PendingWord] = []
    records_by_key: dict[str, _LibraryRecord] = {}

    for library in sorted(
        libraries, key=lambda item: (item.order, item.source_id)
    ):
        record = _LibraryRecord(
            library=library,
            raw_entries=len(library.words),
        )
        records.append(record)
        library_key = library.source_id
        records_by_key[library_key] = record

        candidates = library.categories
        if not candidates:
            record.excluded = True
            record.reason = "unmapped_source"
            continue
        record.candidates = candidates

        cleaned = clean_words(library.words)
        record.cleaned_entries = len(cleaned.accepted)
        record.rejected = dict(cleaned.rejected)
        for reason, count in cleaned.rejected.items():
            rejection_counts[reason] += count
        for entry in cleaned.entries:
            if entry.reason is None:
                continue
            if len(rejection_examples) < settings.example_limit:
                rejection_examples.append(
                    {"raw": entry.raw, "reason": entry.reason}
                )

        raw_counts = Counter(
            entry.word for entry in cleaned.entries if entry.word
        )
        for word in cleaned.accepted:
            pending.append(
                _PendingWord(
                    cleaned=word,
                    library_key=library_key,
                    candidates=candidates,
                    weight=raw_counts.get(word, 1),
                )
            )

    # 先按清洗后的词形确定唯一输出类目，再做字形归一：同一词形在不同来源
    # 出现时，使用范围判定必须看到全部候选，不能各来源各判。
    pre_groups: dict[str, list[_PendingWord]] = defaultdict(list)
    for item in pending:
        pre_groups[_key(item.cleaned)].append(item)
    category_by_key: dict[str, CategoryCandidate] = {}
    for key, group in pre_groups.items():
        category = _best_candidate(
            [
                candidate
                for item in group
                for candidate in item.candidates
            ]
        )
        if category is None:
            raise ValueError(f"词条没有可用的物料类目：{group[0].cleaned}")
        category_by_key[key] = category

    events_file = None
    if settings.events_path is not None:
        settings.events_path.parent.mkdir(parents=True, exist_ok=True)
        events_file = settings.events_path.open(
            "w", encoding="utf-8", newline="\n"
        )
    try:
        for item in pending:
            category = category_by_key[_key(item.cleaned)]
            normalized = normalize_word(
                item.cleaned, category.material_path, table
            )
            glyph_stats.record(
                item.cleaned, normalized, settings.example_limit
            )
            if events_file is not None:
                events_file.write(
                    json.dumps(
                        {
                            "source_id": item.library_key,
                            "raw": item.cleaned,
                            "normalized": normalized.word,
                            "action": normalized.action,
                            "reason": normalized.reason,
                            "reason_code": normalized.reason_code,
                            "changes": [
                                {
                                    "char": change.char,
                                    "action": change.action,
                                    "output": change.output,
                                    "reason": change.reason,
                                }
                                for change in normalized.changes
                            ],
                            "category": category.material_path,
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
            record = records_by_key[item.library_key]
            if normalized.action == "dropped":
                record.glyph_dropped += 1
                continue
            occurrences.append(
                _Occurrence(
                    key=_key(normalized.word),
                    display=normalized.word,
                    library_key=item.library_key,
                    candidates=item.candidates,
                    weight=item.weight,
                )
            )
            record.occurrences += 1
    finally:
        if events_file is not None:
            events_file.close()

    # 全量语料可达数百万词条；分组前释放待处理列表与中间索引，降低峰值内存。
    del pending, pre_groups, category_by_key
    gc.collect()

    grouped: dict[str, list[_Occurrence]] = defaultdict(list)
    for occurrence in occurrences:
        grouped[occurrence.key].append(occurrence)

    material_words: dict[str, list[str]] = {
        path: [] for path in material_file_paths()
    }
    dedup_stats: dict[str, Any] = {
        "occurrences": len(occurrences),
        "unique_keys": len(grouped),
        "duplicates": len(occurrences) - len(grouped),
        "cross_library_groups": 0,
        "cross_library_duplicates": 0,
        "cross_category_groups": 0,
        "multi_display_groups": 0,
        "display_examples": [],
        "category_examples": [],
    }
    category_sources: dict[str, set[str]] = defaultdict(set)
    category_files: dict[str, Counter[str]] = defaultdict(Counter)

    for key in sorted(grouped):
        group = grouped[key]
        display = _select_display(group)
        category = _select_category(group)
        if category is None or category.material_path in PLANNED_FILES:
            raise ValueError(f"词条没有可用的物料类目：{display}")
        material_words[category.material_path].append(display)

        library_keys = {item.library_key for item in group}
        category_paths = {
            candidate.material_path
            for item in group
            for candidate in item.candidates
        }
        parent = "/".join(category.material_path.split("/")[:2])
        file_name = category.material_path.split("/")[-1]
        category_sources[parent].update(library_keys)
        category_files[parent][file_name] += 1

        if len(library_keys) > 1:
            dedup_stats["cross_library_groups"] += 1
            dedup_stats["cross_library_duplicates"] += len(group) - 1
        if len(category_paths) > 1:
            dedup_stats["cross_category_groups"] += 1
        displays = {item.display for item in group}
        if len(displays) > 1:
            dedup_stats["multi_display_groups"] += 1
            if len(dedup_stats["display_examples"]) < settings.example_limit:
                dedup_stats["display_examples"].append(
                    {
                        "key": key,
                        "chosen": display,
                        "variants": sorted(displays),
                    }
                )
        if (
            len(dedup_stats["category_examples"]) < settings.example_limit
            and (len(library_keys) > 1 or len(category_paths) > 1)
        ):
            dedup_stats["category_examples"].append(
                {
                    "word": display,
                    "category": category.material_path,
                    "sources": sorted(library_keys),
                }
            )

    for path in PLANNED_FILES:
        material_words[path] = []

    write_material(
        settings.material_root,
        [
            MaterialCategory(path=path, words=tuple(words))
            for path, words in material_words.items()
        ],
    )


    category_report: list[dict[str, Any]] = []
    samples_root = settings.samples_root
    if samples_root is not None:
        samples_root.mkdir(parents=True, exist_ok=True)

    for spec in MATERIAL_CATEGORIES:
        parent = spec.path
        words: list[str] = []
        for file in spec.files:
            words.extend(material_words[f"{parent}/{file.name}"])
        sample = _sample(
            words,
            settings.sample_size,
            settings.seed,
            parent,
        )
        sample_path: str | None = None
        if samples_root is not None and words:
            sample_name = f"{parent.replace('/', '_')}.txt"
            sample_path = sample_name
            (samples_root / sample_name).write_text(
                "\n".join(sample) + "\n",
                encoding="utf-8",
                newline="\n",
            )
        category_report.append(
            {
                "material_path": parent,
                "words": len(words),
                "files": dict(sorted(category_files[parent].items())),
                "sources": sorted(category_sources[parent]),
                "has_two_sources": len(category_sources[parent]) >= 2,
                "sample_size": len(sample),
                "sample_path": sample_path,
            }
        )

    exclusion_reasons: Counter[str] = Counter(
        record.reason or "unknown"
        for record in records
        if record.excluded
    )

    report: dict[str, Any] = {
        "schema_version": 1,
        "settings": {
            "seed": settings.seed,
            "sample_size": settings.sample_size,
            "example_limit": settings.example_limit,
        },
        "summary": {
            "libraries": len(records),
            "libraries_excluded": sum(
                1 for record in records if record.excluded
            ),
            "libraries_used": sum(
                1 for record in records if not record.excluded
            ),
            "raw_entries": sum(record.raw_entries for record in records),
            "cleaned_entries": sum(
                record.cleaned_entries for record in records
            ),
            "rejected_entries": sum(rejection_counts.values()),
            "glyph_dropped": sum(
                record.glyph_dropped for record in records
            ),
            "word_occurrences": len(occurrences),
            "unique_words": len(grouped),
            "material_words": sum(
                len(words) for words in material_words.values()
            ),
            "categories_with_words": sum(
                1 for item in category_report if item["words"] > 0
            ),
        },
        "sources": [
            {
                "source_id": record.library.source_id,
                "categories": [
                    candidate.material_path
                    for candidate in record.library.categories
                ],
                "excluded": record.excluded,
                "reason": record.reason,
                "raw_entries": record.raw_entries,
                "cleaned_entries": record.cleaned_entries,
                "rejected": dict(sorted(record.rejected.items())),
                "glyph_dropped": record.glyph_dropped,
                "occurrences": record.occurrences,
                "candidates": [
                    candidate.material_path
                    for candidate in record.candidates
                ],
            }
            for record in records
        ],
        "source_exclusions": {
            "counts": dict(sorted(exclusion_reasons.items())),
        },
        "entry_rejections": {
            "counts": dict(sorted(rejection_counts.items())),
            "examples": rejection_examples,
        },
        "glyph": {
            "word_actions": dict(sorted(glyph_stats.word_actions.items())),
            "change_actions": dict(sorted(glyph_stats.change_actions.items())),
            "dropped_ambiguous": glyph_stats.dropped_ambiguous,
            "dropped_unknown_scope": glyph_stats.dropped_unknown_scope,
            "dropped_outside_table": glyph_stats.dropped_outside_table,
            "examples": dict(glyph_stats.examples),
            "events": glyph_stats.event_count,
            "events_path": (
                None
                if settings.events_path is None
                else settings.events_path.as_posix()
            ),
        },
        "dedup": dedup_stats,
        "categories": category_report,
        "sampling": {
            "seed": settings.seed,
            "sample_size": settings.sample_size,
            "resample_threshold": 0.01,
            "rule": (
                "每个输出一级类目随机抽 100 条人工判定；不合格率 >1% 再抽 100 条；"
                "仍 >1% 该类目阻塞发布并回查规则。"
            ),
        },
    }
    _write_report(settings.report_path, report)
    return CurationResult(
        material_root=settings.material_root,
        report_path=settings.report_path,
        samples_root=samples_root,
        report=report,
    )
