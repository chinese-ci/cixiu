from __future__ import annotations

import json
from pathlib import Path

import pytest

from cixiu.glyph import (
    DATA_DIR,
    load_glyph_table,
    normalize_word,
    scope_matches,
)

DAILY = "下里巴人/日常口语/其它"
PERSON = "下里巴人/影视娱乐/明星"
PLACE = "阳春白雪/地名/其它"
SCIENCE = "阳春白雪/科学技术/其它"


@pytest.fixture(scope="module")
def table():
    return load_glyph_table()


def test_extracted_table_matches_official_counts() -> None:
    meta = json.loads((DATA_DIR / "glyph-meta.json").read_text(encoding="utf-8"))

    assert meta["standard_chars"] == 8105
    assert meta["table_standards"] == 3120
    assert meta["traditional_occurrences"] == 2574
    assert meta["variant_groups"] == 794
    assert meta["notes"] == 52
    assert meta["scope_rules"] == 39
    assert meta["note_drop_rules"] == 13
    assert meta["unresolved_multi_map_rules"] == 6
    assert meta["direct_promoted"] == ["皙", "瞋", "噘", "蹚", "凓", "勠"]
    # 官方说明 1,023 个异体字；维基文库转录少 2 字，作为已知缺口记录。
    assert meta["variant_occurrences"] == 1021
    assert meta["variant_occurrences_official"] == 1023
    assert meta["known_gaps"]


def test_table_loads_with_scopes_and_notes(table) -> None:
    assert len(table.rules) > 3000
    assert len(table.standard_chars) == 8105
    assert "别" in table.standard_chars
    assert table.rules["裏"].action == "convert"
    assert table.rules["裏"].out_scope == "里"
    assert table.rules["瞭"].action == "drop"
    assert table.rules["瞭"].note == 1
    assert table.rules["甦"].action == "scope"
    assert table.rules["甦"].scopes == ("person",)
    assert table.supplement["別"][0] == "别"
    assert 52 in table.notes


def test_traditional_unambiguous_converts(table) -> None:
    result = normalize_word("裏面", DAILY, table)

    assert result.word == "里面"
    assert result.action == "converted"
    assert [(change.char, change.action, change.output) for change in result.changes] == [
        ("裏", "converted", "里")
    ]


def test_supplement_converts_common_traditional(table) -> None:
    result = normalize_word("別克", DAILY, table)

    assert result.word == "别克"
    assert result.action == "converted"
    assert result.changes[0].action == "supplement_converted"


def test_standard_char_is_not_converted(table) -> None:
    result = normalize_word("著名", DAILY, table)

    assert result.word == "著名"
    assert result.action == "unchanged"
    assert result.changes == ()


@pytest.mark.parametrize(
    ("word", "character"),
    [
        ("瞭望", "瞭"),
        ("乾坤", "乾"),
        ("慰藉", "藉"),
        ("什麽", "麽"),
    ],
)
def test_ambiguous_glyph_drops_word(table, word: str, character: str) -> None:
    result = normalize_word(word, DAILY, table)

    assert result.action == "dropped"
    assert result.reason_code == "ambiguous"
    assert character in (result.reason or "")
    assert "表注" in (result.reason or "")


def test_direct_promoted_chars_are_kept(table) -> None:
    for character in "皙瞋噘蹚凓勠":
        result = normalize_word(f"{character}字", DAILY, table)
        assert result.word == f"{character}字", character
        assert result.action == "unchanged", character


@pytest.mark.parametrize("word", ["妳好", "噁心", "尅服"])
def test_unresolved_multi_mapping_drops_word(table, word: str) -> None:
    result = normalize_word(word, DAILY, table)

    assert result.action == "dropped"
    assert result.reason_code == "ambiguous"
    assert "无法唯一判定" in (result.reason or "")


def test_compatibility_ideograph_is_dropped_as_outside_table(table) -> None:
    result = normalize_word(chr(0xFA19) + "明", DAILY, table)

    assert result.action == "dropped"
    assert result.reason_code == "outside_table"
    assert "表外" in (result.reason or "")


def test_usage_scope_keeps_variant_in_matching_category(table) -> None:
    result = normalize_word("毕昇", PERSON, table)

    assert result.word == "毕昇"
    assert result.action == "kept_variant"
    assert result.changes[0].action == "kept_variant"


def test_usage_scope_normalizes_outside_matching_category(table) -> None:
    result = normalize_word("昇华", SCIENCE, table)

    assert result.word == "升华"
    assert result.action == "converted"
    assert result.changes[0].reason.endswith("使用范围与类目不匹配")


def test_usage_scope_with_mandated_simplified_form(table) -> None:
    in_scope = normalize_word("鍾意", PERSON, table)
    out_scope = normalize_word("鍾意", DAILY, table)

    assert in_scope.word == "锺意"
    assert out_scope.word == "钟意"


def test_usage_scope_place_only(table) -> None:
    kept = normalize_word("大阪", PLACE, table)
    converted = normalize_word("大阪", DAILY, table)

    assert kept.word == "大阪"
    assert kept.action == "kept_variant"
    assert converted.word == "大坂"


def test_usage_scope_science_target(table) -> None:
    result = normalize_word("椏枝", SCIENCE, table)

    assert result.word == "桠枝"
    assert result.action == "converted"


def test_usage_scope_unknown_category_drops(table) -> None:
    result = normalize_word("堃", "未知/类目/其它", table)

    assert result.action == "dropped"
    assert result.reason_code == "scope_unknown"
    assert "无法判定" in (result.reason or "")


def test_scope_match_returns_none_for_unknown_category() -> None:
    assert scope_matches(("person",), PERSON) is True
    assert scope_matches(("place",), PERSON) is False
    assert scope_matches(("person",), "未知/类目/其它") is None
