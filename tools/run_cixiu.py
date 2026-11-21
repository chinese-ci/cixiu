"""运行词修：来源语料 → 纯词库物料、私有清洗报告与抽检样本。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from cixiu.cixiu import CurationSettings, run_cixiu
from cixiu.corpus import load_corpus

ROOT = Path(__file__).resolve().parent.parent


def _material_is_non_empty(path: Path) -> bool:
    if not path.is_dir():
        return False
    return any(
        candidate.is_file() and candidate.stat().st_size
        for candidate in path.rglob("*.txt")
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--corpus",
        type=Path,
        required=True,
        help="来源语料目录（sources.json 与 text/）",
    )
    parser.add_argument(
        "--material-dir",
        type=Path,
        default=ROOT / "var" / "material",
        help="纯词库物料输出目录",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=ROOT / "var" / "cixiu-report.json",
        help="私有清洗报告路径",
    )
    parser.add_argument(
        "--samples",
        type=str,
        default=str(ROOT / "var" / "cixiu-samples"),
        help="每类 100 条抽检样本目录；传空字符串可关闭",
    )
    parser.add_argument(
        "--events",
        type=str,
        default=None,
        help=(
            "逐条字形动作 JSONL（私有，可能很大）；省略时写到报告同目录的 "
            "<报告名>-events.jsonl，传空字符串可关闭"
        ),
    )
    parser.add_argument("--seed", type=int, default=0, help="抽检随机种子")
    parser.add_argument(
        "--sample-size", type=int, default=100, help="每类抽检条数"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="只处理前 N 个来源（冒烟用）",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="允许覆盖已有非空物料目录",
    )
    arguments = parser.parse_args()

    if arguments.material_dir.is_dir() and _material_is_non_empty(
        arguments.material_dir
    ) and not arguments.force:
        print(
            f"物料目录已有非空内容，拒绝覆盖：{arguments.material_dir}（可用 --force）",
            file=sys.stderr,
        )
        return 1

    loaded = load_corpus(arguments.corpus)
    libraries = list(loaded.libraries)
    if arguments.limit is not None:
        libraries = libraries[: arguments.limit]
    if not libraries:
        print("来源语料为空或全部被跳过", file=sys.stderr)
        for item in loaded.skipped:
            print(
                f"  跳过 {item.source_id}：{item.reason}",
                file=sys.stderr,
            )
        return 1

    if arguments.events is None:
        events_path: Path | None = arguments.report.with_name(
            f"{arguments.report.stem}-events.jsonl"
        )
    elif arguments.events == "":
        events_path = None
    else:
        events_path = Path(arguments.events)

    settings = CurationSettings(
        material_root=arguments.material_dir,
        report_path=arguments.report,
        samples_root=(
            Path(arguments.samples) if arguments.samples else None
        ),
        events_path=events_path,
        seed=arguments.seed,
        sample_size=arguments.sample_size,
    )
    result = run_cixiu(libraries, settings)

    print(f"物料：{result.material_root}")
    print(f"清洗报告：{result.report_path}")
    if result.samples_root is not None:
        print(f"抽检样本：{result.samples_root}")
    if settings.events_path is not None:
        print(f"字形事件：{settings.events_path}")
    print(
        json.dumps(
            result.report["summary"], ensure_ascii=False, sort_keys=True
        )
    )
    for item in loaded.skipped:
        print(
            f"跳过 {item.source_id}：{item.reason}",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
