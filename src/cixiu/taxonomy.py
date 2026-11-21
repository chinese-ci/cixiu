"""纯词库物料的类目骨架，从 vendored taxonomy 契约读取。

正本：CiMo `contracts/taxonomy.json`；本仓库副本在
`contracts/vendor/taxonomy-v1/`，测试校验版本与哈希。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from cixiu.material import MaterialCategory, write_material

VENDOR_DIR = (
    Path(__file__).resolve().parents[2] / "contracts" / "vendor" / "taxonomy-v1"
)
TAXONOMY_PATH = VENDOR_DIR / "taxonomy.json"


@dataclass(frozen=True)
class MaterialFileSpec:
    name: str
    planned: bool = False
    standard: str | None = None


@dataclass(frozen=True)
class MaterialCategorySpec:
    group: str
    name: str
    slug: str
    files: tuple[MaterialFileSpec, ...]

    @property
    def path(self) -> str:
        return f"{self.group}/{self.name}"


def _load() -> tuple[dict[str, object], tuple[MaterialCategorySpec, ...]]:
    payload = json.loads(TAXONOMY_PATH.read_text(encoding="utf-8"))
    categories: list[MaterialCategorySpec] = []
    for group in payload.get("groups", []):
        group_name = str(group["name"])
        for category in group.get("categories", []):
            files = tuple(
                MaterialFileSpec(
                    name=str(file["name"]),
                    planned=bool(file.get("planned", False)),
                    standard=(
                        str(file["standard"])
                        if file.get("standard") is not None
                        else None
                    ),
                )
                for file in category.get("files", [])
            )
            categories.append(
                MaterialCategorySpec(
                    group=group_name,
                    name=str(category["name"]),
                    slug=str(category["slug"]),
                    files=files,
                )
            )
    return payload, tuple(categories)


PAYLOAD, MATERIAL_CATEGORIES = _load()
XIA_LI_BA_REN: tuple[MaterialCategorySpec, ...] = tuple(
    category for category in MATERIAL_CATEGORIES if category.group == "下里巴人"
)
YANG_CHUN_BAI_XUE: tuple[MaterialCategorySpec, ...] = tuple(
    category
    for category in MATERIAL_CATEGORIES
    if category.group == "阳春白雪" and category.name != "地名"
)
DI_MING = next(
    category
    for category in MATERIAL_CATEGORIES
    if category.group == "阳春白雪" and category.name == "地名"
)

FILE_PATHS: tuple[str, ...] = tuple(
    f"{category.path}/{file.name}"
    for category in MATERIAL_CATEGORIES
    for file in category.files
)
FILE_SET = frozenset(FILE_PATHS)
PLANNED_PATHS = frozenset(
    f"{category.path}/{file.name}"
    for category in MATERIAL_CATEGORIES
    for file in category.files
    if file.planned
)


def material_file_paths() -> tuple[str, ...]:
    return FILE_PATHS


def material_skeleton() -> list[MaterialCategory]:
    return [
        MaterialCategory(path=path, words=())
        for path in material_file_paths()
    ]


def write_material_skeleton(root: Path) -> None:
    if root.is_dir():
        for path in root.rglob("*.txt"):
            if path.stat().st_size:
                relative = path.relative_to(root).as_posix()
                raise ValueError(f"拒绝覆盖非空物料：{relative}")
    write_material(root, material_skeleton())


def validate() -> None:
    if len(MATERIAL_CATEGORIES) != 33 or len(FILE_PATHS) != 73:
        raise ValueError(
            f"taxonomy 规模不符：{len(MATERIAL_CATEGORIES)} 类、"
            f"{len(FILE_PATHS)} 文件"
        )
    slugs = [category.slug for category in MATERIAL_CATEGORIES]
    if len(slugs) != len(set(slugs)):
        raise ValueError("taxonomy 存在重复 slug")


validate()
