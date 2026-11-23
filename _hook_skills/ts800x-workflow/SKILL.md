---
name: ts800x-workflow
description: TS800X 工作流统一参考（会话启动加载 + 新项目/多模块开发入口）。统一 Codex、Claude、Pi 和 PowerShell 的阶段、证据、烧录策略、工具入口与项目内状态。
---

# TS800X Workflow

规范优先级：

1. `workflow.manifest.json`（Skill/Hook/宿主映射）
2. `WORKFLOW.md`（完整阶段与烧录/交付策略）
3. `RULES/CODING_STANDARD.md`（R01-R29）
4. `RULES/REVIEW_CHECKLIST.md`（终审）

宿主适配文件不得覆盖上述规则。所有宿主执行同一模块循环：

```
prebuilt/examples → implement/integrate → build 0/0
→ 按需 JLink/UART/OTA 快速验证 → ts800x-code-quality
→ build 0/0 → dependency report → log/hardware verify
→ final-reviewer
```

该循环用于模块正式完成，不是每次修改的强制 Gate。日常迭代直接使用 `ts800x-build`，
构建成功后按需烧录 verify、读取日志并继续修改；准备提交/交付时再补齐后半段检查。

## 工具入口

表中相对路径均以 `TS800X_WORKFLOW_ROOT` 为基准；各工具 Skill 中的 `<skill-dir>` 表示当前
`SKILL.md` 所在目录，不能把占位符原样传给 shell，也不能假设当前工作目录是工作流仓库。

| 目的 | 入口 |
|------|------|
| 状态机 | `workflow.ps1` |
| 编译 | `_hook_skills/ts800x-build/build.ps1` |
| 依赖 | `_hook_skills/ts800x-dependency-analyzer/analyze_dependencies.ps1` |
| 可选交付审计 | `_hook_skills/ts800x-flash/pre_flash_gate.ps1` |
| JLink（烧录/RTT/调试） | `_hook_skills/ts800x-flash/`（策略 + `run_cli.ps1` CLI 实现） |
| UART（RTS 自动 + 人工 RESET） | `_hook_skills/ts800x-uart-download/`（rts_uart_download.py / uart_download.py） |
| OTA | `_hook_skills/ts800x-ble-ota/ble_ota.py` |
| UART 日志 | `_hook_skills/ts800x-log-system/uart_capture.py` |
| 日志分析 | `_hook_skills/ts800x-log-system/log_analyze.py` |
| 功耗测量 | `_hook_skills/ppk2-power-measure/ppk2.py` |

## 新项目/多模块开发

实现前必须形成并让用户确认：产品行为和可验收场景；芯片/板卡、GPIO、电平、外设、时钟、
UART/BLE 参数；电源、休眠、唤醒和安全要求；有无硬件、JLink、串口、BLE 测试条件；
模块边界、公共状态所有权和错误处理。

单行修复可快速通道；BLE 协议、ISR、Flash、电源状态机、多模块接口不属于快速通道。

### 建立项目

1. `create_project.ps1` 创建目标项目，不在规范仓库内直接开发业务固件。
2. 检查生成文件，初始化项目 `PROGRESS.md/TODO.md/MEMORY.md/context/`。
3. 创建功能分支；直接使用 `main/master` 需要用户明确授权。
4. 不加业务代码先运行基线 build，要求 0/0 和新鲜 HEX/BIN。
5. 有硬件时先用最小测试确认供电、下载、日志及关键外设；无硬件时记录限制。

### 设计产物

依次使用 `requirements-analyst → architect`，输出到 `context/handoffs/requirements.md`、
`architecture.md` 和 `module_specs/<module>.md`。每个模块 Spec 至少包含 API、输入输出、
调用周期、状态、错误码、资源、依赖和验收测试。

### 实现顺序

按依赖拓扑逐模块执行 `ts800x-module-dev`。交叉依赖时可先建立最小可编译骨架，但禁止一次
填完所有实现后再统一验证。硬件验证失败时留在当前模块，修复并重跑完整循环。

### 集成与交付

全部模块结束后：

1. `engineering-ops` 校验工程配置和可复现构建。
2. `rigorous-test` 覆盖启动、正常、边界、故障、低功耗、BLE 和恢复路径。
3. `workflow.ps1 final-check` 生成最终构建/依赖状态。
4. `final-reviewer` 独立终审。
5. 更新项目状态和交付说明；未做的硬件项必须显式列为待验证。

不得自动烧录、提交、推送或发布；烧录不强制 Gate，但仍需用户意图和工具级范围/verify 校验。

## 状态与边界

状态只写目标项目的 `PROGRESS.md`、`TODO.md`、`MEMORY.md`、`context/`、`reports/`、
`logs/`。没有硬件时使用 `PENDING_HARDWARE/[待硬件验证]`；绝不把静态检查当作真机成功。

用户说暂停时立即停止。测试烧录可直接进行；仅模块正式完成、准备提交/交付或用户明确要求时，
才执行完整构建、依赖、测试和终审证据。
