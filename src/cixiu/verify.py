"""校验纯词库物料是否符合契约，供 CI 与验收调用。"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from cixiu.cleaning import clean_word
from cixiu.taxonomy import MATERIAL_CATEGORIES, material_file_paths


class MaterialError(ValueError):
    """物料不符合契约。"""


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str = ""


def _tree_sha256(root: Path, pattern: str = "*") -> tuple[str, int, int]:
    files = sorted(
        path for path in root.rglob(pattern) if path.is_file()
    )
    digest = hashlib.sha256()
    total = 0
    for path in files:
        relative = path.relative_to(root).as_posix().encode("utf-8")
        data = path.read_bytes()
        digest.update(relative)
        digest.update(b"\0")
        digest.update(data)
        digest.update(b"\0")
        total += len(data)
    return digest.hexdigest(), len(files), total


def _read_utf8(path: Path, *, what: str) -> str:
    if not path.is_file():
        raise MaterialError(f"{what}不存在：{path}")
    data = path.read_bytes()
    if data.startswith(b"\xef\xbb\xbf"):
        raise MaterialError(f"{what}带 BOM：{path}")
    if b"\r" in data:
        raise MaterialError(f"{what}含 CR（应为 LF）：{path}")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise MaterialError(f"{what}不是 UTF-8：{path}") from error


def audit_material(root: Path) -> dict[str, Any]:
    if not root.is_dir():
        raise MaterialError(f"物料目录不存在：{root}")
    expected_files = [f"{path}.txt" for path in material_file_paths()]
    actual_paths = sorted(
        path.relative_to(root).as_posix()
        for path in root.rglob("*.txt")
        if path.is_file()
    )
    missing = sorted(set(expected_files) - set(actual_paths))
    extra = sorted(set(actual_paths) - set(expected_files))
    checks = [
        Check("物料类目文件齐全", not missing, "、".join(missing[:8])),
        Check("物料没有契约外文件", not extra, "、".join(extra[:8])),
    ]

    planned = {
        f"{category.path}/{file.name}.txt"
        for category in MATERIAL_CATEGORIES
        for file in category.files
        if file.planned
    }
    seen_keys: dict[str, str] = {}
    duplicates: list[str] = []
    material: dict[str, dict[str, list[str]]] = {}
    line_errors: list[str] = []
    total_words = 0
    file_counts: dict[str, int] = {}
    for relative_file in expected_files:
        path = root / relative_file
        if not path.is_file():
            material.setdefault(relative_file.rsplit("/", 1)[0], {})
            continue
        text = _read_utf8(path, what="物料")
        lines = text.splitlines()
        if "\t" in text:
            line_errors.append(f"{relative_file}（制表符）")
            continue
        if relative_file in planned and lines:
            line_errors.append(f"{relative_file}（planned 文件应为空）")
            continue
        words: list[str] = []
        for line in lines:
            if not line or line.strip() != line:
                line_errors.append(f"{relative_file}（空行或首尾空白）")
                continue
            cleaned = clean_word(line)
            if cleaned.reason is not None or cleaned.word != line:
                reason = cleaned.reason or "未归一"
                line_errors.append(f"{relative_file}（{line!r}：{reason}）")
                continue
            key = "".join(
                character.lower() if character.isascii() else character
                for character in line
            )
            if key in seen_keys:
                duplicates.append(line)
            else:
                seen_keys[key] = relative_file
            words.append(line)
        category = relative_file.rsplit("/", 1)[0]
        material.setdefault(category, {})[path.stem] = words
        file_counts[relative_file] = len(words)
        total_words += len(words)

    checks.append(
        Check("物料逐行符合条级契约", not line_errors, "；".join(line_errors[:5]))
    )
    checks.append(Check("物料全局去重", not duplicates, "、".join(duplicates[:5])))

    category_counts = {
        category: sum(len(words) for words in files.values())
        for category, files in material.items()
    }
    empty_categories = [
        category for category, count in category_counts.items() if count == 0
    ]
    digest, files, size = _tree_sha256(root, "*.txt")
    payload = {
        "root": str(root),
        "files": files,
        "bytes": size,
        "words": total_words,
        "unique_words": len(seen_keys),
        "duplicates": len(duplicates),
        "categories": category_counts,
        "categories_with_words": len(category_counts) - len(empty_categories),
        "files_empty": sorted(
            path for path, count in file_counts.items() if count == 0
        ),
        "planned_files": sorted(planned),
        "expected_files": expected_files,
        "sha256": digest,
        "file_counts": dict(sorted(file_counts.items())),
    }
    return {
        "ok": all(check.ok for check in checks),
        "checks": [asdict(check) for check in checks],
        "payload": payload,
    }
