"""《通用规范汉字表》附件 1 字形归一。

归一表是私有数据，由 `tools/extract_glyph_table.py` 从官方附件 1 提取。
运行时只回答一个问题：给定词条与它的输出类目，每个字应该保留、归一还是丢弃。

规则来自表注：

- 无注：直接归一到规范字。
- `scope`：仅在表注写明的使用范围内保留原字或使用注明的类推简化字；范围外归一。
- `drop`：义项/读音无法唯一判定，整条丢弃并报告。
- 6 个直接调整为规范字的异体字不在映射表中，按规范字原样保留。
- 附件 1 未收的常见繁体字形由私有补充表补足（如 `別`→`别`）。
- Unicode 兼容汉字是同一字的旧编码形式，无法确认规范字形，按表外丢弃；
  8,105 之外的普通增广字仍交给词合按方案字符集处理。
"""

from __future__ import annotations

import json
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Mapping

from cixiu.taxonomy import MATERIAL_CATEGORIES

DATA_DIR = Path(__file__).resolve().parent / "data"
TABLE_PATH = DATA_DIR / "glyph-table.tsv"
NOTES_PATH = DATA_DIR / "glyph-notes.tsv"
SUPPLEMENT_PATH = DATA_DIR / "glyph-supplement.tsv"
STANDARD_CHARS_PATH = DATA_DIR / "standard-chars.tsv"
META_PATH = DATA_DIR / "glyph-meta.json"

Action = Literal["convert", "scope", "drop"]

# 表注使用范围 → 物料一级类目。
_SCOPE_CATEGORIES: dict[str, frozenset[str]] = {
    "person": frozenset({"下里巴人/影视娱乐"}),
    "place": frozenset({"阳春白雪/地名"}),
    "science": frozenset(
        {
            "阳春白雪/科学技术",
            "阳春白雪/医药、卫生",
            "阳春白雪/电子信息产业",
            "阳春白雪/矿业、工业",
            "阳春白雪/农业、农村",
            "阳春白雪/能源、水务、水利",
            "阳春白雪/环境、气象",
        }
    ),
    "classical": frozenset(
        {"阳春白雪/文学、艺术", "下里巴人/成语熟语"}
    ),
}


class GlyphTableError(ValueError):
    """字形归一表不符合预期。"""


@dataclass(frozen=True)
class GlyphRule:
    kind: str
    char: str
    standard: str
    number: str
    note: int | None
    action: Action
    in_scope: str
    out_scope: str
    scopes: tuple[str, ...]


@dataclass(frozen=True)
class GlyphChange:
    char: str
    action: str
    output: str
    reason: str


@dataclass(frozen=True)
class Normalization:
    word: str
    action: str
    reason: str | None
    changes: tuple[GlyphChange, ...]
    reason_code: str | None = None


@dataclass(frozen=True)
class GlyphTable:
    rules: Mapping[str, GlyphRule]
    supplement: Mapping[str, tuple[str, str]]
    notes: Mapping[int, str]
    direct_promoted: frozenset[str]
    standard_chars: frozenset[str]


def _read_tsv(path: Path) -> list[list[str]]:
    if not path.is_file():
        raise GlyphTableError(f"字形数据文件不存在：{path}")
    rows: list[list[str]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        rows.append(line.split("\t"))
    return rows


def _single_han(value: str, where: str) -> str:
    if len(value) != 1 or not _is_han(value):
        raise GlyphTableError(f"{where} 不是单个汉字：{value!r}")
    return value


def _is_han(character: str) -> bool:
    code = ord(character)
    return (
        0x3400 <= code <= 0x4DBF
        or 0x4E00 <= code <= 0x9FFF
        or 0xF900 <= code <= 0xFAFF
        or 0x20000 <= code <= 0x3FFFF
    )


def load_glyph_table(
    table_path: Path = TABLE_PATH,
    notes_path: Path = NOTES_PATH,
    supplement_path: Path = SUPPLEMENT_PATH,
    standard_chars_path: Path = STANDARD_CHARS_PATH,
    meta_path: Path = META_PATH,
) -> GlyphTable:
    rules: dict[str, GlyphRule] = {}
    for row in _read_tsv(table_path):
        if len(row) < 9:
            row += [""] * (9 - len(row))
        if len(row) != 9:
            raise GlyphTableError(f"字形表列数不符：{row!r}")
        kind, char, standard, number, note_text, action, in_scope, out_scope, scopes_text = row
        if action not in ("convert", "scope", "drop"):
            raise GlyphTableError(f"未知字形动作：{action!r}")
        _single_han(char, "字形表 char")
        _single_han(standard, "字形表 standard")
        if char in rules:
            raise GlyphTableError(f"字形表重复字：{char}")
        note = int(note_text) if note_text else None
        scopes = tuple(
            item for item in scopes_text.split(",") if item
        )
        if action == "scope":
            if not scopes:
                raise GlyphTableError(f"scope 规则缺少使用范围：{char}")
            _single_han(in_scope, f"字形表 in_scope（{char}）")
            _single_han(out_scope, f"字形表 out_scope（{char}）")
            unknown = set(scopes) - set(_SCOPE_CATEGORIES)
            if unknown:
                raise GlyphTableError(
                    f"未知使用范围 {sorted(unknown)}：{char}"
                )
        rules[char] = GlyphRule(
            kind=kind,
            char=char,
            standard=standard,
            number=number,
            note=note,
            action=action,  # type: ignore[arg-type]
            in_scope=in_scope,
            out_scope=out_scope or standard,
            scopes=scopes,
        )

    supplement: dict[str, tuple[str, str]] = {}
    for row in _read_tsv(supplement_path):
        if len(row) != 3:
            raise GlyphTableError(f"补充表列数不符：{row!r}")
        char, standard, source = row
        _single_han(char, "补充表 char")
        _single_han(standard, "补充表 standard")
        if char in rules:
            raise GlyphTableError(f"补充字与附件 1 重复：{char}")
        supplement[char] = (standard, source)

    notes: dict[int, str] = {}
    for row in _read_tsv(notes_path):
        if len(row) != 4:
            raise GlyphTableError(f"表注列数不符：{row!r}")
        notes[int(row[0])] = row[3]
    standard_chars = frozenset(
        line.strip()
        for line in standard_chars_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    )
    for character in standard_chars:
        _single_han(character, "8,105 字表")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    if len(standard_chars) != int(meta["standard_chars"]):
        raise GlyphTableError(
            f"8,105 字表数量不符：{len(standard_chars)}"
        )
    missing = {
        rule.out_scope
        for rule in rules.values()
        if _is_han(rule.out_scope)
    } - standard_chars
    if missing:
        raise GlyphTableError(
            f"归一目标不在 8,105 内：{sorted(missing)}"
        )
    supplement_missing = {
        standard for standard, _source in supplement.values()
    } - standard_chars
    if supplement_missing:
        raise GlyphTableError(
            f"补充表目标不在 8,105 内：{sorted(supplement_missing)}"
        )
    direct_promoted = frozenset(str(item) for item in meta["direct_promoted"])
    overlap = direct_promoted & (set(rules) | set(supplement))
    if overlap:
        raise GlyphTableError(
            f"直接调整字不应出现在映射中：{sorted(overlap)}"
        )

    return GlyphTable(
        rules=rules,
        supplement=supplement,
        notes=notes,
        direct_promoted=direct_promoted,
        standard_chars=standard_chars,
    )


_KNOWN_CATEGORIES = frozenset(
    category.path for category in MATERIAL_CATEGORIES
)


def material_category(material_path: str) -> str:
    parts = material_path.split("/")
    if len(parts) < 2:
        raise ValueError(f"物料路径缺少组/一级类目：{material_path}")
    return "/".join(parts[:2])


def scope_matches(scopes: tuple[str, ...], material_path: str) -> bool | None:
    """返回 True/False 表示范围匹配；None 表示类目不在已知体系内。"""
    try:
        category = material_category(material_path)
    except ValueError:
        return None
    if category not in _KNOWN_CATEGORIES:
        return None
    return any(
        category in _SCOPE_CATEGORIES[scope] for scope in scopes
    )


def _is_compatibility_ideograph(character: str) -> bool:
    return unicodedata.name(character, "").startswith(
        "CJK COMPATIBILITY IDEOGRAPH"
    )


def normalize_word(
    word: str,
    material_path: str,
    table: GlyphTable | None = None,
) -> Normalization:
    table = table or load_glyph_table()
    changes: list[GlyphChange] = []
    output: list[str] = []
    for character in word:
        if (
            _is_compatibility_ideograph(character)
            and character not in table.standard_chars
        ):
            return Normalization(
                word=word,
                action="dropped",
                reason=(
                    f"表外字形：{character}（Unicode 兼容汉字，不在 8,105 内）"
                ),
                changes=tuple(changes),
                reason_code="outside_table",
            )
        if character in table.direct_promoted:
            output.append(character)
            continue
        supplement = table.supplement.get(character)
        if supplement is not None:
            standard, source = supplement
            output.append(standard)
            changes.append(
                GlyphChange(
                    char=character,
                    action="supplement_converted",
                    output=standard,
                    reason=source,
                )
            )
            continue
        rule = table.rules.get(character)
        if rule is None:
            output.append(character)
            continue
        if rule.action == "convert":
            output.append(rule.out_scope)
            changes.append(
                GlyphChange(
                    char=character,
                    action="converted",
                    output=rule.out_scope,
                    reason=f"附件 1 序号 {rule.number}：繁体/异体归一到规范字",
                )
            )
            continue
        if rule.action == "drop":
            note = table.notes.get(rule.note or 0, "")
            return Normalization(
                word=word,
                action="dropped",
                reason=(
                    f"字形无法唯一判定：{character}"
                    + (f"（表注 {rule.note}：{note}）" if note else "")
                ),
                changes=tuple(changes),
                reason_code="ambiguous",
            )
        matched = scope_matches(rule.scopes, material_path)
        if matched is None:
            return Normalization(
                word=word,
                action="dropped",
                reason=(
                    f"字形使用范围无法判定：{character}"
                    f"（表注 {rule.note}，类目 {material_path}）"
                ),
                changes=tuple(changes),
                reason_code="scope_unknown",
            )
        if matched:
            output.append(rule.in_scope)
            changes.append(
                GlyphChange(
                    char=character,
                    action=(
                        "kept_variant"
                        if rule.in_scope == character
                        else "converted"
                    ),
                    output=rule.in_scope,
                    reason=(
                        f"表注 {rule.note} 的使用范围与类目匹配"
                        + (
                            ""
                            if rule.in_scope == character
                            else f"，按表注使用 {rule.in_scope}"
                        )
                    ),
                )
            )
        else:
            output.append(rule.out_scope)
            changes.append(
                GlyphChange(
                    char=character,
                    action="converted",
                    output=rule.out_scope,
                    reason=f"表注 {rule.note} 的使用范围与类目不匹配",
                )
            )

    normalized = "".join(output)
    if any(change.action in ("converted", "supplement_converted") for change in changes):
        action = "converted"
    elif any(change.action == "kept_variant" for change in changes):
        action = "kept_variant"
    else:
        action = "unchanged"
    return Normalization(
        word=normalized,
        action=action,
        reason=None,
        changes=tuple(changes),
    )
