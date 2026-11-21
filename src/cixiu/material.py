"""纯词库物料的写入侧契约：UTF-8、一行一个词条、按类目分文件。

文件名即类目；顶层组（如 `下里巴人/`）保留在物料路径里。

`read_material` 是生产者侧自检读取器；消费者侧（CiHe）有独立实现，
两侧只通过公开物料文件契约对齐，不互相导入。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath


class MaterialError(ValueError):
    """物料目录不符合公开契约。"""


@dataclass(frozen=True)
class MaterialCategory:
    path: str
    words: tuple[str, ...]


def category_file(root: Path, category: str) -> Path:
    parts = PurePosixPath(category).parts
    if not parts or any(part in {"", ".", ".."} or "\\" in part for part in parts):
        raise ValueError(f"非法类目路径：{category}")
    return root.joinpath(*parts).with_suffix(".txt")


def write_material(root: Path, categories: list[MaterialCategory]) -> None:
    for category in sorted(categories, key=lambda item: item.path):
        target = category_file(root, category.path)
        target.parent.mkdir(parents=True, exist_ok=True)
        words = sorted(category.words)
        for word in words:
            if not word or "\t" in word or "\n" in word or "\r" in word:
                raise ValueError(f"词条不符合物料契约：{word!r}")
        text = "\n".join(words)
        if words:
            text += "\n"
        target.write_text(text, encoding="utf-8", newline="\n")


def _file_order_key(name: str) -> tuple[bool, str]:
    return (name == "其它", name)


def _read_lines(path: Path, relative: str) -> list[str]:
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raise MaterialError(f"物料带 BOM：{relative}")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise MaterialError(f"物料不是 UTF-8：{relative}") from error
    if "\r" in text:
        raise MaterialError(f"物料含 CR：{relative}")
    if "\t" in text:
        raise MaterialError(f"物料含制表符：{relative}")
    lines = text.splitlines()
    for line in lines:
        if not line or line.strip() != line:
            raise MaterialError(f"物料行不符合契约：{relative}: {line!r}")
    return lines


def read_material(root: Path) -> dict[str, dict[str, list[str]]]:
    if not root.is_dir():
        raise MaterialError(f"物料目录不存在：{root}")

    files_by_category: dict[str, dict[str, list[str]]] = {}
    for path in sorted(root.rglob("*.txt")):
        relative = path.relative_to(root)
        if len(relative.parts) != 3:
            raise MaterialError(
                f"物料文件必须位于 组/一级类目/类目.txt：{relative.as_posix()}"
            )
        category = f"{relative.parts[0]}/{relative.parts[1]}"
        files_by_category.setdefault(category, {})[path.stem] = _read_lines(
            path, relative.as_posix()
        )

    if not files_by_category:
        raise MaterialError(f"物料目录为空：{root}")

    return {
        category: {
            name: files[name]
            for name in sorted(files, key=_file_order_key)
        }
        for category, files in sorted(files_by_category.items())
    }
