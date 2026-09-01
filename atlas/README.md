# 乙鸣星图 · Yiming Atlas（已冻结原型）

Atlas 是前一阶段做出的 GitHub 创作轨迹浏览器和数据适配器。它现在只保留为
**本地事实源的可视化实验**，不再作为最终产品继续堆叠自定义 UI。

当前产品方向已经转为 [`lab/`](../lab/README.md)：以 OpenWiki、DeepTutor 和
`sunccchengze/-SKILL-` 的书籍/人物 skill 组合出 Yiming Council。Atlas 的
inventory/corpus 结构仍可作为输入适配器，但不是 Council 的核心运行时。

## 数据边界

- 页面数据由本地 `build_data.py` 从 `account_inventory.json` 生成。
- 默认只包含仓库元数据、分支、近期提交摘要和统计，不上传任何内容。
- 采集 private 仓库时，生成的 JSON 只留在本机；`atlas/data/` 下的生成文件已被忽略。
- 采集器会在更早一步跳过密钥、`.env`、凭据和大文件；`.github/` 中的文本、YAML
  和规则文件会保留，因为它们常常是项目治理事实。

## 生成数据

```bash
python -m atlas.build_data \
  --inventory minillm/artifacts/account_inventory.json \
  --corpus minillm/artifacts/github_corpus.jsonl \
  --out atlas/data/generated.json
```

## 本地预览

```bash
python -m http.server 8000 --directory atlas
```

然后打开 <http://localhost:8000>。

## 当前边界

已完成的星图、项目档案、创作轨道、灵感舱和本地收藏功能保持可用；尚未验证的
private 仓库采集和真实浏览器回归仍记录在 [`PROGRESS.md`](PROGRESS.md)。后续只有
在它能直接帮助 Council 做事实源适配时，才继续修改 Atlas。
