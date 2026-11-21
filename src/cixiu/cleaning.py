"""条级接受与清洗（工单 04）。

顺序与 CiZhu `spec/cizhu-v1.md` 一致：去 BOM、首尾空白、控制/零宽/私用区/
内部空白拒收、全半角与点号映射、行内注音剥离、允许字符、纯拉丁/数字、2–10 字。
字形归一不在这里，见 `cixiu.glyph`。
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from typing import Iterable

_BOM = chr(0xFEFF)

_HAN_RANGES = (
    ("㐀", "䶿"),
    ("一", "鿿"),
    ("\uF900", "\uFAFF"),
    ("\U00020000", "\U0002a6df"),
    ("\U0002a700", "\U0002b73f"),
    ("\U0002b740", "\U0002b81f"),
    ("\U0002b820", "\U0002ceaf"),
    ("\U0002ceb0", "\U0002ebef"),
    ("\U00030000", "\U000323af"),
)

_ZERO_WIDTH = frozenset(
    chr(code)
    for code in (
        *(0x00AD, 0x061C, 0x180E),
        *range(0x200B, 0x2010),
        *range(0x202A, 0x202F),
        *range(0x2060, 0x2065),
        *range(0x2066, 0x206A),
        0xFEFF,
    )
)

_DOT_VARIANTS = frozenset("•・")


@dataclass(frozen=True)
class CleanWord:
    raw: str
    word: str
    reason: str | None

    @property
    def accepted(self) -> bool:
        return self.reason is None


@dataclass(frozen=True)
class CleanResult:
    accepted: list[str]
    rejected: dict[str, int]
    entries: tuple[CleanWord, ...] = ()


def _is_han(character: str) -> bool:
    return any(start <= character <= end for start, end in _HAN_RANGES)


def _allowed(character: str) -> bool:
    if _is_han(character):
        return True
    if character.isascii() and character.isalnum():
        return True
    return character in "·-"


def _normalize_widths(text: str) -> str:
    characters: list[str] = []
    for character in text:
        code = ord(character)
        if code == 0x3000:
            characters.append(" ")
        elif 0xFF01 <= code <= 0xFF5E:
            characters.append(chr(code - 0xFEE0))
        elif character in _DOT_VARIANTS:
            characters.append("·")
        else:
            characters.append(character)
    return "".join(characters)


def _strip_inline_pinyin(text: str) -> str:
    """剥掉紧跟单个汉字之后的小写 ASCII 字母段。

    `长chang相守` → `长相守`；`第1个`、`a股`、`AA制` 不受影响。
    """
    characters: list[str] = []
    position = 0
    while position < len(text):
        character = text[position]
        characters.append(character)
        if not _is_han(character):
            position += 1
            continue
        end = position + 1
        while end < len(text) and "a" <= text[end] <= "z":
            end += 1
        position = end if end > position + 1 else position + 1
    return "".join(characters)


def _character_reason(character: str) -> str | None:
    if character.isspace():
        return "whitespace"
    category = unicodedata.category(character)
    if category in ("Cc", "Cs"):
        return "control"
    if category == "Cf" or character in _ZERO_WIDTH:
        return "zero_width"
    if category == "Co":
        return "private_use"
    if 0xFE00 <= ord(character) <= 0xFE0F:
        return "zero_width"
    if 0xE0100 <= ord(character) <= 0xE01EF:
        return "zero_width"
    return None


def _reject_reason(word: str) -> str | None:
    if not word:
        return "empty"
    for character in word:
        reason = _character_reason(character)
        if reason is not None:
            return reason
    if not all(_allowed(character) for character in word):
        return "disallowed_char"
    if not any(_is_han(character) for character in word):
        return "latin_only"
    if len(word) < 2:
        return "too_short"
    if len(word) > 10:
        return "too_long"
    return None


def clean_word(raw: str) -> CleanWord:
    word = _strip_inline_pinyin(
        _normalize_widths(raw.lstrip(_BOM).strip())
    )
    reason = _reject_reason(word)
    if reason is not None:
        return CleanWord(raw=raw, word="", reason=reason)
    return CleanWord(raw=raw, word=word, reason=None)


def clean_words(words: Iterable[str]) -> CleanResult:
    accepted: list[str] = []
    rejected: dict[str, int] = {}
    entries: list[CleanWord] = []
    seen: set[str] = set()
    for raw in words:
        entry = clean_word(raw)
        reason = entry.reason
        if reason is None and entry.word in seen:
            reason = "duplicate"
            entry = CleanWord(raw=raw, word=entry.word, reason=reason)
        if reason is not None:
            rejected[reason] = rejected.get(reason, 0) + 1
            entries.append(entry)
            continue
        seen.add(entry.word)
        accepted.append(entry.word)
        entries.append(entry)
    return CleanResult(
        accepted=accepted, rejected=rejected, entries=tuple(entries)
    )
