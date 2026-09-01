# 乙鸣星图 · Yiming Atlas

把 `sunccchengze` 的 GitHub 创作轨迹变成一个可浏览的个人数字宇宙。

## 数据边界

- 页面数据由本地 `build_data.py` 从 `account_inventory.json` 生成。
- 默认只包含仓库元数据、分支、近期提交摘要和统计，不上传任何内容。
- 采集 private 仓库时，生成的 JSON 只留在本机；`atlas/data/` 下的生成文件已被忽略。
- 采集器会在更早一步跳过密钥、`.env`、凭据和大文件。

## 生成数据

```bash
python -m atlas.build_data \
  --inventory minillm/artifacts/account_inventory.json \
  --out atlas/data/generated.json
```

## 本地预览

```bash
python -m http.server 8000 --directory atlas
```

然后打开 <http://localhost:8000>。

## 设计语言

这不是 GitHub 管理后台，而是一个个人创作档案：

- 星系：学习系统、工程现场、AI 与工作流、重要的人、未归档星体
- 轨道：近期提交活动和项目演化
- 档案：仓库、branch、最近 commit
- 灵感舱：根据两个已有方向组合下一个可做实验
- 未来信：明确区分 GitHub 事实和系统的诗意解释
