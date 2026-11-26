---
name: ts800x-memory-handoff
description: TS800X 项目内交接与状态持久化规范。用于 requirements、architecture、worker、test、review 等阶段共享产物，保证 Codex、Claude 和 Pi 可恢复同一状态。
---

# TS800X 项目内 Handoff

所有交接物放在目标项目，不放在宿主 home 目录：

```
<project>/
├── PROGRESS.md
├── TODO.md
├── MEMORY.md
└── context/
    ├── module_status.json
    ├── code_map.yaml
    └── handoffs/
        ├── requirements.md
        ├── architecture.md
        ├── module_specs/<module>.md
        ├── <module>/worker_output.json
        ├── <module>/test_report.json
        ├── <module>/review_result.json
        └── ops/ops_report.json
```

## 最小 JSON 字段

每个 JSON 交接物至少包含：

```json
{
  "schema_version": 1,
  "handoff_type": "WORKER_OUTPUT",
  "project": "<project>",
  "module": "<module-or-empty>",
  "timestamp": "RFC3339",
  "status": "PASS|FAIL|PENDING_HARDWARE",
  "inputs": [],
  "outputs": [],
  "evidence": [],
  "open_issues": [],
  "next_action": "<explicit action>"
}
```

阶段可以增加字段，但不得删除这些公共字段。路径使用项目相对路径；外部工具路径可另行注明，
不要把宿主用户名或机器绝对路径写成接口契约。

## 写入规则

1. 先验证输入产物存在且可解析。
2. 写入本阶段产物后重新读取，验证 JSON/Markdown 非空。
3. 同步更新 `PROGRESS.md`；重要决策写 `MEMORY.md`，未完成项写 `TODO.md`。
4. 状态为 PASS 时必须附实际命令、退出码或硬件证据；推测不能作为 evidence。
5. 无硬件时使用 `PENDING_HARDWARE`，不能伪装成 PASS。
6. 下一宿主从项目文件恢复，不依赖聊天历史或 Claude/Codex/Pi 私有缓存。

由当前执行 Skill 按真实证据更新 context/module_status.json；保留已有字段和 code_quality / build_after_code_quality，写后重新解析；不创造平行状态文件。
