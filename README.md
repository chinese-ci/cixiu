# 词修 CiXiu

[词铸 CiZhu](https://github.com/chinese-ci/cizhu) 的清洗工具。输入是来源语料（UTF-8 文本 + 来源标识与类目候选），输出是结构稳定的纯词库物料；不解析来源平台的私有格式，也不读取采集器的内部 manifest。

契约正本：[词模 CiMo](https://github.com/chinese-ci/cimo) source-corpus 契约、[material](https://github.com/chinese-ci/cimo/blob/main/contracts/material.md)。

## 运行

```bash
uv sync
uv run python tools/run_cixiu.py \
  --corpus ../CiCai/var/corpus \
  --material-dir var/material \
  --report var/cixiu-report.json
```

- `--samples ""` 关闭每类抽检样本；`--events ""` 关闭逐条字形事件。
- `--limit N` 只处理前 N 个来源，便于冒烟。
- 物料目录非空时拒绝覆盖，需加 `--force`。

校验物料契约：

```bash
uv run python tools/verify_material.py \
  --material var/material \
  --report var/material-verify.json
```

## 来源语料

```text
corpus/
├── sources.json
└── text/<source_id>.txt
```

`sources.json` 的 `schema_version` 为 1，每个来源只包含 `source_id`、`order` 与 `categories`；`categories` 是 `{path, priority}` 候选数组，词修 CiXiu 只按 `priority` 元组与路径裁决，不解释来源语义。来源可以手工整理，也可以由任意采集器按契约导出。

## 流水线

条级清洗 → 字形归一 → 去重与类目归属 → 物料与私有报告。

词库级筛选、来源类目到物料类目的映射由来源层完成；词修 CiXiu 只看到不透明 `source_id`，不接触标题、描述或平台信息。

- `data/`：字形表、规范字表与补充表。
- `contracts/vendor/taxonomy-v1/`：vendored 物料类目契约。
- 确定性：来源 `order` → `source_id` → 文本行序；同一输入重复运行逐字节一致。

## 开发

```bash
uv run pytest
uv run pyright
```

## 许可

[MIT](https://opensource.org/license/mit)，见 [LICENSE](LICENSE)。
