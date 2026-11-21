from __future__ import annotations

import pytest

from cixiu.cleaning import clean_word, clean_words


@pytest.mark.parametrize(
    ("raw", "word"),
    [
        ("  你好  ", "你好"),
        ("　你好　", "你好"),
        ("﻿你好", "你好"),
        ("长chang相守", "长相守"),
        ("Ａ股", "A股"),
        ("你好·世界", "你好·世界"),
        ("T恤", "T恤"),
    ],
)
def test_clean_word_accepts_and_normalizes(raw: str, word: str) -> None:
    result = clean_word(raw)

    assert result.accepted
    assert result.word == word
    assert result.reason is None


@pytest.mark.parametrize(
    ("raw", "reason"),
    [
        ("", "empty"),
        ("   ", "empty"),
        ("　", "empty"),
        ("你 好", "whitespace"),
        ("你 好", "whitespace"),
        ("你​好", "zero_width"),
        ("你\u0000好", "control"),
        ("你好", "private_use"),
        ("你好！", "disallowed_char"),
        ("你好。", "disallowed_char"),
        ("你好~", "disallowed_char"),
        ("hello", "latin_only"),
        ("123", "latin_only"),
        ("·", "latin_only"),
        ("好", "too_short"),
        ("一二三四五六七八九十十", "too_long"),
    ],
)
def test_clean_word_rejects(raw: str, reason: str) -> None:
    result = clean_word(raw)

    assert not result.accepted
    assert result.word == ""
    assert result.reason == reason


@pytest.mark.parametrize(
    ("raw", "word"),
    [
        ("a股", "a股"),
        ("AA制", "AA制"),
        ("T恤", "T恤"),
        ("U盘", "U盘"),
        ("第1个", "第1个"),
        ("巴依卡·凯力迪別克", "巴依卡·凯力迪別克"),
        ("一二三四五六七八九十", "一二三四五六七八九十"),
    ],
)
def test_clean_word_accepts_mixed_and_ten_char_words(
    raw: str, word: str
) -> None:
    result = clean_word(raw)

    assert result.accepted
    assert result.word == word


def test_clean_words_reports_reasons_and_library_duplicates() -> None:
    result = clean_words(
        [
            "你好",
            "你好",
            "好",
            "hello",
            "你好！",
            "上班",
            "  ",
            "上班",
        ]
    )

    assert result.accepted == ["你好", "上班"]
    assert result.rejected == {
        "duplicate": 2,
        "too_short": 1,
        "latin_only": 1,
        "disallowed_char": 1,
        "empty": 1,
    }


def test_clean_words_preserves_first_seen_order() -> None:
    result = clean_words(["乙乙", "甲甲", "乙乙"])

    assert result.accepted == ["乙乙", "甲甲"]
