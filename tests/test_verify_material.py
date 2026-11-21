from __future__ import annotations

from pathlib import Path

from cixiu.taxonomy import write_material_skeleton
from cixiu.verify import audit_material


def test_material_skeleton_is_valid(tmp_path: Path) -> None:
    root = tmp_path / "material"
    write_material_skeleton(root)

    report = audit_material(root)

    assert report["ok"] is True
    assert report["payload"]["files"] == 73
    assert report["payload"]["words"] == 0


def test_material_with_word_is_valid(tmp_path: Path) -> None:
    root = tmp_path / "material"
    write_material_skeleton(root)
    target = root / "下里巴人" / "日常口语" / "其它.txt"
    target.write_text("你好\n", encoding="utf-8", newline="\n")

    report = audit_material(root)

    assert report["ok"] is True
    assert report["payload"]["words"] == 1
    assert report["payload"]["categories"]["下里巴人/日常口语"] == 1


def test_material_with_bad_line_fails(tmp_path: Path) -> None:
    root = tmp_path / "material"
    write_material_skeleton(root)
    target = root / "下里巴人" / "日常口语" / "其它.txt"
    target.write_text(" 你好\n", encoding="utf-8", newline="\n")

    report = audit_material(root)

    assert report["ok"] is False
    failed = [check["name"] for check in report["checks"] if not check["ok"]]
    assert "物料逐行符合条级契约" in failed
