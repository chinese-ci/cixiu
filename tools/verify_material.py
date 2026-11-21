"""校验纯词库物料是否符合契约；JSON 报告供验收读取。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from cixiu.verify import MaterialError, audit_material


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--material", type=Path, required=True)
    parser.add_argument(
        "--report",
        type=Path,
        default=None,
        help="JSON 报告输出路径；省略时只打印摘要",
    )
    arguments = parser.parse_args()

    try:
        report = audit_material(arguments.material)
    except MaterialError as error:
        report = {"ok": False, "error": str(error), "checks": []}
        if arguments.report is not None:
            arguments.report.parent.mkdir(parents=True, exist_ok=True)
            arguments.report.write_text(
                json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
                newline="\n",
            )
        print(f"物料校验失败：{error}", file=sys.stderr)
        return 1

    if arguments.report is not None:
        arguments.report.parent.mkdir(parents=True, exist_ok=True)
        arguments.report.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    failed = [check for check in report["checks"] if not check["ok"]]
    for check in report["checks"]:
        print(
            f"{'通过' if check['ok'] else '失败'}：{check['name']}"
            + (f"（{check['detail']}）" if check["detail"] else "")
        )
    payload = report["payload"]
    print(
        f"物料：{payload['files']} 文件、{payload['words']} 条、"
        f"sha256={payload['sha256']}"
    )
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
