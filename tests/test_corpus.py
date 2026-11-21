from __future__ import annotations

import json
from pathlib import Path

from cixiu.cixiu import CurationSettings, run_cixiu
from cixiu.corpus import load_corpus
from cixiu.material import read_material


def _curate(libraries, root: Path):
    settings = CurationSettings(
        material_root=root / "material",
        report_path=root / "report.json",
        samples_root=None,
        events_path=None,
        seed=7,
    )
    return run_cixiu(libraries, settings)


def test_hand_written_corpus_runs_without_collection(tmp_path: Path) -> None:
    corpus_dir = tmp_path / "manual-corpus"
    text_path = corpus_dir / "text" / "manual-demo.txt"
    text_path.parent.mkdir(parents=True)
    text_path.write_text("你好\n谢谢\n早上好\n", encoding="utf-8", newline="\n")
    (corpus_dir / "sources.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "sources": [
                    {
                        "source_id": "manual-demo",
                        "order": 0,
                        "categories": [
                            {
                                "path": "下里巴人/日常口语/其它",
                                "priority": [0],
                            }
                        ],
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    loaded = load_corpus(corpus_dir)
    assert loaded.skipped == ()
    result = _curate(loaded.libraries, tmp_path / "run")

    material = read_material(result.material_root)
    assert material["下里巴人/日常口语"]["其它"] == [
        "你好",
        "早上好",
        "谢谢",
    ]


def test_corpus_reports_missing_and_unsafe_sources(tmp_path: Path) -> None:
    corpus_dir = tmp_path / "corpus"
    (corpus_dir / "text").mkdir(parents=True)
    (corpus_dir / "sources.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "sources": [
                    {
                        "source_id": "../escape",
                        "order": 0,
                        "categories": [],
                    },
                    {
                        "source_id": "manual-missing",
                        "order": 1,
                        "categories": [],
                    },
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    loaded = load_corpus(corpus_dir)

    assert loaded.libraries == ()
    reasons = {(item.source_id, item.reason) for item in loaded.skipped}
    assert ("../escape", "unsafe_source_id") in reasons
    assert ("manual-missing", "missing_text") in reasons


def test_corpus_order_controls_source_sequence(tmp_path: Path) -> None:
    corpus_dir = tmp_path / "corpus"
    for name in ("b", "a"):
        path = corpus_dir / "text" / f"manual-{name}.txt"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("你好\n", encoding="utf-8", newline="\n")
    sources = [
        {
            "source_id": "manual-b",
            "order": 1,
            "categories": [{"path": "下里巴人/日常口语/其它", "priority": [0]}],
        },
        {
            "source_id": "manual-a",
            "order": 0,
            "categories": [{"path": "下里巴人/日常口语/其它", "priority": [0]}],
        },
    ]
    (corpus_dir / "sources.json").write_text(
        json.dumps({"schema_version": 1, "sources": sources}) + "\n",
        encoding="utf-8",
    )

    loaded = load_corpus(corpus_dir)

    assert [item.source_id for item in loaded.libraries] == [
        "manual-a",
        "manual-b",
    ]
