from __future__ import annotations

from pathlib import Path

import pytest

from cixiu.material import MaterialCategory, write_material
from cixiu.taxonomy import (
    MATERIAL_CATEGORIES,
    XIA_LI_BA_REN,
    YANG_CHUN_BAI_XUE,
    material_skeleton,
    write_material_skeleton,
)

XIA_LI_BA_REN_NAMES = [
    "日常口语",
    "生活服务",
    "成语熟语",
    "新词",
    "方言",
    "游戏电竞",
    "动漫二次元",
    "影视娱乐",
]

YANG_CHUN_BAI_XUE_NAMES = [
    "政治",
    "法律、司法",
    "对外关系、国际关系",
    "军事",
    "社会、劳动",
    "灾难、事故",
    "经济",
    "财政、金融",
    "基本建设、建筑业、房地产",
    "农业、农村",
    "矿业、工业",
    "能源、水务、水利",
    "电子信息产业",
    "交通运输、邮政、物流",
    "商业、外贸、海关",
    "服务业、旅游业",
    "环境、气象",
    "教育",
    "科学技术",
    "文化、休闲娱乐",
    "文学、艺术",
    "传媒",
    "医药、卫生",
    "体育",
]


def _written_material_paths(root: Path) -> list[str]:
    return sorted(
        path.relative_to(root).as_posix()
        for path in root.rglob("*.txt")
    )


def test_material_skeleton_has_complete_taxonomy() -> None:
    assert [category.name for category in XIA_LI_BA_REN] == XIA_LI_BA_REN_NAMES
    assert [category.name for category in YANG_CHUN_BAI_XUE] == YANG_CHUN_BAI_XUE_NAMES
    assert len(YANG_CHUN_BAI_XUE) == 24
    assert YANG_CHUN_BAI_XUE_NAMES[21] == "传媒"

    paths = [category.path for category in MATERIAL_CATEGORIES]
    assert len(paths) == len(set(paths)) == 33
    assert sum(len(category.files) for category in MATERIAL_CATEGORIES) == 73

    for category in MATERIAL_CATEGORIES:
        assert category.files[-1].name == "其它"
        assert len({file.name for file in category.files}) == len(category.files)

    skeleton_paths = [category.path for category in material_skeleton()]
    assert len(skeleton_paths) == len(set(skeleton_paths)) == 73

    planned = [
        (category.path, file.name)
        for category in MATERIAL_CATEGORIES
        for file in category.files
        if file.planned
    ]
    assert planned == [("下里巴人/成语熟语", "诗词名句")]


def test_material_skeleton_matches_golden_tree(
    golden_root: Path, tmp_path: Path
) -> None:
    expected = (
        golden_root / "taxonomy" / "material-tree.txt"
    ).read_text(encoding="utf-8").splitlines()
    declared = [
        f"{category.path}/{file.name}.txt"
        for category in MATERIAL_CATEGORIES
        for file in category.files
    ]
    assert declared == expected

    write_material_skeleton(tmp_path)
    assert _written_material_paths(tmp_path) == sorted(expected)


def test_planned_material_files_match_golden(golden_root: Path) -> None:
    declared = [
        f"{category.path}/{file.name}.txt"
        for category in MATERIAL_CATEGORIES
        for file in category.files
        if file.planned
    ]
    expected = (
        golden_root / "taxonomy" / "planned-files.txt"
    ).read_text(encoding="utf-8").splitlines()
    assert declared == expected


def test_place_name_files_carry_their_standards() -> None:
    places = next(
        category
        for category in MATERIAL_CATEGORIES
        if category.path == "阳春白雪/地名"
    )
    assert {file.name: file.standard for file in places.files} == {
        "行政区划": "GB/T 2260",
        "道路": None,
        "机构": None,
        "风景名胜": None,
        "国外地名": "GB/T 2659",
        "其它": None,
    }


def test_write_material_skeleton_writes_only_empty_category_files(
    tmp_path: Path,
) -> None:
    write_material_skeleton(tmp_path)

    expected = sorted(
        category.path + ".txt" for category in material_skeleton()
    )
    written = _written_material_paths(tmp_path)
    assert written == expected

    for relative in written:
        raw = (tmp_path / relative).read_bytes()
        assert raw == b"", relative


def test_write_material_skeleton_refuses_to_overwrite_non_empty_material(
    tmp_path: Path,
) -> None:
    write_material(
        tmp_path,
        [MaterialCategory("下里巴人/日常口语/口头语", ("你好",))],
    )

    with pytest.raises(ValueError):
        write_material_skeleton(tmp_path)

    assert (
        tmp_path / "下里巴人" / "日常口语" / "口头语.txt"
    ).read_text(encoding="utf-8") == "你好\n"


def test_write_material_skeleton_refuses_any_non_empty_material(
    tmp_path: Path,
) -> None:
    write_material(
        tmp_path,
        [MaterialCategory("下里巴人/旧布局", ("你好",))],
    )

    with pytest.raises(ValueError):
        write_material_skeleton(tmp_path)


def test_material_directories_use_chinese_names() -> None:
    han = "一"
    han_end = "鿿"
    for category in MATERIAL_CATEGORIES:
        assert category.group in {"阳春白雪", "下里巴人"}
        assert all(
            han <= character <= han_end or character == "、"
            for character in category.name
        ), category.name
