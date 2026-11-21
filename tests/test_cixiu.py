from __future__ import annotations

import json
from pathlib import Path

from cixiu.cixiu import PLANNED_FILES, CurationSettings, run_cixiu
from cixiu.material import read_material
from cixiu.source import CategoryCandidate, SourceLibrary

DAILY = "下里巴人/日常口语"
DAILY_OTHER = "下里巴人/日常口语/其它"


def candidate(path: str, priority: tuple[int, ...] = (0,)) -> CategoryCandidate:
    return CategoryCandidate(material_path=path, priority=priority)


def library(
    source_id: str,
    order: int,
    candidates: list[CategoryCandidate],
    words: list[str],
) -> SourceLibrary:
    return SourceLibrary(
        source_id=source_id,
        order=order,
        categories=tuple(candidates),
        words=tuple(words),
    )


def settings(tmp_path: Path, **overrides: object) -> CurationSettings:
    values: dict[str, object] = {
        "material_root": tmp_path / "material",
        "report_path": tmp_path / "cleaning-report.json",
        "samples_root": tmp_path / "samples",
        "seed": 7,
    }
    values.update(overrides)
    return CurationSettings(**values)  # type: ignore[arg-type]


def report_of(result) -> dict:
    return json.loads(result.report_path.read_text(encoding="utf-8"))


def all_material_words(material: dict[str, dict[str, list[str]]]) -> list[str]:
    return [
        word
        for category in material.values()
        for words in category.values()
        for word in words
    ]


def test_pipeline_writes_clean_material_and_report(tmp_path: Path) -> None:
    result = run_cixiu(
        [
            library(
                "source-a",
                0,
                [candidate(DAILY_OTHER)],
                [
                    "你好",
                    "谢谢",
                    "你好",
                    "好",
                    "hello",
                    "你好！",
                    "  ",
                    "上班",
                    "吃饭",
                    "睡觉",
                    "学校",
                ],
            ),
            library(
                "source-b",
                1,
                [candidate(DAILY_OTHER)],
                ["你好", "上班", "下班"],
            ),
        ],
        settings(tmp_path),
    )

    material = read_material(result.material_root)
    assert material[DAILY]["其它"] == [
        "上班",
        "下班",
        "你好",
        "吃饭",
        "学校",
        "睡觉",
        "谢谢",
    ]
    assert material[DAILY]["口头语"] == []

    report = report_of(result)
    assert report["summary"]["libraries"] == 2
    assert report["summary"]["material_words"] == 7
    assert report["dedup"]["cross_library_groups"] == 2
    assert report["sources"][0]["source_id"] == "source-a"
    assert "title" not in report["sources"][0]

    daily = next(
        item
        for item in report["categories"]
        if item["material_path"] == DAILY
    )
    assert daily["sources"] == ["source-a", "source-b"]


def test_glyph_normalization_runs_before_dedup(tmp_path: Path) -> None:
    result = run_cixiu(
        [
            library(
                "source-a",
                0,
                [candidate(DAILY_OTHER)],
                ["裏面", "別克", "著名", "瞭望", "乾坤", "慰藉", "什麽", "慰藉"],
            ),
            library(
                "source-b",
                1,
                [candidate("阳春白雪/科学技术/其它")],
                ["昇华", "椏枝"],
            ),
            library(
                "source-c",
                2,
                [candidate("下里巴人/影视娱乐/明星")],
                ["毕昇", "丘堃", "鍾意"],
            ),
            library(
                "source-d",
                3,
                [candidate("阳春白雪/地名/其它")],
                ["大阪"],
            ),
        ],
        settings(tmp_path),
    )

    material = read_material(result.material_root)
    assert material[DAILY]["其它"] == ["别克", "著名", "里面"]
    assert material["阳春白雪/科学技术"]["其它"] == ["升华", "桠枝"]
    assert material["下里巴人/影视娱乐"]["明星"] == ["丘堃", "毕昇", "锺意"]
    assert material["阳春白雪/地名"]["其它"] == ["大阪"]

    words = all_material_words(material)
    for original in "裏別瞭乾藉麽":
        assert all(original not in word for word in words), original

    glyph = report_of(result)["glyph"]
    assert glyph["word_actions"]["converted"] == 5
    assert glyph["word_actions"]["kept_variant"] == 3
    assert glyph["word_actions"]["unchanged"] == 1
    assert glyph["word_actions"]["dropped"] == 4


def test_dedup_uses_priority_then_path(tmp_path: Path) -> None:
    result = run_cixiu(
        [
            library(
                "source-a",
                0,
                [candidate("下里巴人/新词/网络新词")],
                ["AA制", "aa制", "火锅", "综艺"],
            ),
            library(
                "source-b",
                1,
                [candidate("阳春白雪/文化、休闲娱乐/其它", (-2, 20, 0))],
                ["AA制", "综艺"],
            ),
            library(
                "source-c",
                2,
                [candidate("下里巴人/影视娱乐/其它", (-2, 30, 0))],
                ["综艺"],
            ),
            library(
                "source-d",
                3,
                [candidate("下里巴人/生活服务/饮食", (-3, 50, 0))],
                ["火锅"],
            ),
            library(
                "source-e",
                4,
                [candidate("下里巴人/生活服务/其它", (-2, 50, 0))],
                ["火锅"],
            ),
        ],
        settings(tmp_path),
    )

    material = read_material(result.material_root)
    words = all_material_words(material)
    assert words.count("AA制") == 1
    assert words.count("aa制") == 0
    assert words.count("火锅") == 1
    assert words.count("综艺") == 1
    assert "AA制" in material["阳春白雪/文化、休闲娱乐"]["其它"]
    assert "火锅" in material["下里巴人/生活服务"]["饮食"]
    assert "综艺" in material["阳春白雪/文化、休闲娱乐"]["其它"]


def test_same_word_in_two_categories_uses_one_final_category(
    tmp_path: Path,
) -> None:
    result = run_cixiu(
        [
            library(
                "source-a",
                0,
                [candidate("下里巴人/影视娱乐/明星", (-2, 30, 0))],
                ["毕昇"],
            ),
            library(
                "source-b",
                1,
                [candidate("下里巴人/成语熟语/成语", (-2, 10, 0))],
                ["毕昇"],
            ),
        ],
        settings(tmp_path),
    )

    material = read_material(result.material_root)
    words = all_material_words(material)
    assert words.count("毕升") == 1
    assert "毕昇" not in words
    assert "毕升" in material["下里巴人/成语熟语"]["成语"]


def test_display_choice_uses_raw_occurrence_frequency(tmp_path: Path) -> None:
    result = run_cixiu(
        [
            library(
                "source-a",
                0,
                [candidate(DAILY_OTHER)],
                ["aa股", "aa股", "aa股", "AA股"],
            )
        ],
        settings(tmp_path),
    )

    material = read_material(result.material_root)
    assert material[DAILY]["其它"] == ["aa股"]


def test_outside_table_glyph_is_reported(tmp_path: Path) -> None:
    result = run_cixiu(
        [
            library(
                "source-a",
                0,
                [candidate(DAILY_OTHER)],
                [chr(0xFA19) + "明", "你好"],
            )
        ],
        settings(tmp_path),
    )

    report = report_of(result)
    assert report["glyph"]["dropped_outside_table"] == 1
    material = read_material(result.material_root)
    assert material[DAILY]["其它"] == ["你好"]


def test_planned_file_stays_empty(tmp_path: Path) -> None:
    result = run_cixiu(
        [
            library(
                "source-a",
                0,
                [candidate("下里巴人/成语熟语/成语")],
                ["一心一意", "画蛇添足"],
            )
        ],
        settings(tmp_path),
    )

    for path in PLANNED_FILES:
        target = result.material_root / f"{path}.txt"
        assert target.read_bytes() == b"", path


def test_report_and_samples_are_deterministic(tmp_path: Path) -> None:
    words = [f"阿{chr(0x4E00 + index)}" for index in range(250)]
    libraries = [
        library("source-a", 0, [candidate(DAILY_OTHER)], words)
    ]

    first = run_cixiu(libraries, settings(tmp_path / "first"))
    second = run_cixiu(libraries, settings(tmp_path / "second"))

    assert first.report_path.read_bytes() == second.report_path.read_bytes()
    assert first.samples_root is not None
    assert second.samples_root is not None
    first_sample = (
        first.samples_root / "下里巴人_日常口语.txt"
    ).read_text(encoding="utf-8")
    second_sample = (
        second.samples_root / "下里巴人_日常口语.txt"
    ).read_text(encoding="utf-8")
    assert first_sample == second_sample
    assert len(first_sample.splitlines()) == 100


def test_report_examples_are_capped_at_twenty(tmp_path: Path) -> None:
    rejection_words = [f"hello{index}" for index in range(25)]
    result = run_cixiu(
        [
            library(
                "source-a",
                0,
                [candidate(DAILY_OTHER)],
                rejection_words + ["你好", "谢谢"],
            )
        ],
        settings(tmp_path / "rejections"),
    )
    assert len(report_of(result)["entry_rejections"]["examples"]) == 20


def test_events_file_records_each_accepted_entry(tmp_path: Path) -> None:
    events_path = tmp_path / "glyph-events.jsonl"
    result = run_cixiu(
        [
            library(
                "source-a",
                0,
                [candidate(DAILY_OTHER)],
                ["裏面", "著名", "瞭望", "你好"],
            )
        ],
        settings(tmp_path, events_path=events_path),
    )

    lines = [
        json.loads(line)
        for line in events_path.read_text(encoding="utf-8").splitlines()
    ]
    assert len(lines) == 4
    assert all(line["source_id"] == "source-a" for line in lines)
    assert "platform" not in lines[0]
    assert report_of(result)["glyph"]["events_path"] == events_path.as_posix()
