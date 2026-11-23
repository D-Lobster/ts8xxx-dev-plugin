# TS800X Unified Development Workflow

本文件是 Codex、Claude、Pi、PowerShell 的统一流程规范。规则细节见
`RULES/CODING_STANDARD.md`（R01-R29）；宿主适配见 `HOSTS.md`。

## 1. 边界

| 规则 | 要求 |
|------|------|
| SDK | `ts800x_sdk/` 只读，应用改动在 `APP/` |
| 驱动 | 写驱动前先查 `prebuilt_modules/` 和 SDK examples |
| 构建 | 0 Error / 0 Warning + 新鲜非空 HEX/BIN |
| 验证 | 没有新鲜证据不声称完成；没有真机证据不声称硬件成功 |
| 停止 | 用户说暂停时立即停止并汇报当前清单 |

ISR、阻塞、动态内存、Flash、LOG ASCII 等硬性红线见 `RULES/CODING_STANDARD.md` R12-R29。

## 2. 任务入口

### 新项目 / 多模块

```
requirements-analyst → architect → module-dev（逐模块）
→ engineering-ops → rigorous-test → final-reviewer
```

用户确认需求、硬件映射、模块边界、验收标准前不进入实现。

### 已有项目维护

先 `code-reader` 生成 `context/code_map.yaml`，再做基线构建，再由 `maintenance`
拆分任务。移植遵循 R25 逐行 diff。

### 快速通道

单行修复、临时调试、编译错误和纯配置默认走轻量闭环：
`修改 → build 0/0 → 按需烧录并 verify → 日志/行为验证`。
不要求每次修改都执行依赖分析、代码质量或终审；只有模块正式完成、准备提交/交付，
或用户明确要求时才补齐完整检查。
开发测试烧录不要求额外 Gate；写入工具自身仍必须执行地址、范围和 verify 校验。

## 3. 每模块验证循环

一次只推进一个模块：

1. 确认输入/输出/时序/错误处理/验收标准
2. 查 `prebuilt_modules/`、examples、SDK API
3. 实现 `.c/.h`，接入调度和 `.uvprojx`
4. build 0/0 + 新鲜产物
5. 按需写入并快速读日志/行为（JLink / UART / BLE OTA 三选一），不强制 Gate
6. `ts800x-code-quality`（白名单项记录理由）
7. 强制 Rebuild，再次取得 0/0 与新鲜产物
8. `dependency_report.json`（推断项带 `file:line`，人工覆盖函数指针/宏分发）
9. 按需再次写入，完成 RTT/UART/BLE + 用户物理/视觉回归
10. 写 `[已验证]` 证据；无硬件写结构化 `[待硬件验证]`（测试步骤与验收标准）

待硬件 JSON 最小格式：`{"tests":[{"name":"...","procedure":"...","acceptance":"..."}]}`。

步骤 6-10 属于模块完成检查，不阻止步骤 4-5 的日常开发闭环。临时版本烧录成功后可继续迭代，
但在未完成模块检查前只报告“本轮测试通过”，不得声明模块已正式完成。

状态机命令经 `workflow.ps1`：`init → verify-module → mark-code-quality →
verify-module`。字段用 `code_quality` / `build_after_code_quality`。开发测试烧录可在任一次
成功构建后进行；`gate` 仅保留为兼容的可选交付审计命令。

## 4. 烧录策略

日常测试烧录不要求完整流程检查。写入前只执行工具级必要检查：

```text
【测试烧录检查】
- [x] 固件文件存在且非空
- [x] 地址与长度落在目标 Flash 范围
- [x] 目标设备/通道明确
- [x] 写入后执行 verify 或协议完整性校验
- [ ] 日志/物理行为验证（写入后）
```

`pre_flash_gate.ps1` 和 `workflow.ps1 gate` 仅作为兼容的可选交付审计，可检查源码路径、
工程集成、依赖 JSON 和产物时间戳；审计失败不阻止开发测试烧录。模块完成和最终交付仍由
两次 0/0 构建、代码质量、依赖分析、测试证据和终审决定。

## 5. 写入通道

| 通道 | 何时用 | 实现 |
|------|--------|------|
| **JLink**（默认有线） | 有线烧录 / RTT / 调试 | `ts800x-flash`（策略 + `run_cli.ps1` CLI 实现一体，无 MCP server） |
| **UART** | 串口烧录 / 无人值守 | `ts800x-uart-download`（RTS 自动复位推荐 + 人工 RESET 两模式合一） |
| **BLE OTA** | 无线升级 | `ts800x-ble-ota`；生产需 64 字节签名 |

PPK2 不是普通 JLink 烧录的依赖。只有 PPK2 已为功耗测量接入，且用户明确确认
DUT 当前仅由 PPK2 供电时，才允许执行下列可选联动：

- 测量后紧接着烧录：测量使用 `--keep-power`，或在 JLink connect 前重新执行
  `power --state on`。
- JLink connect 因深度睡眠失败：当场通过 PPK2 `scan` + `info` 后执行一次
  `power --state cycle`，再重试一次 JLink connect。

未满足上述条件时不得扫描或操作 PPK2。`power cycle` 是冷启动复位，不是保留
RAM/运行状态的睡眠唤醒；PPK2 供电命令成功也只证明命令已发送，后续 JLink connect
成功才构成 DUT 已可调试的端到端证据。

## 6. 日志与硬件证据

先读 `APP_CFG_LOG_TYPE`：`LOG_RTT` 用 `ts800x-flash` 的 `run_cli.ps1 rtt`；`LOG_UART` 用 `uart_capture.py`。
`log_analyze.py` 把 ERROR/FAIL/WARN/空日志判为失败。日志通过只证明文本可观测；
LED/按键/马达等仍需人工观察。

## 7. Git 与交付

- 默认功能分支；直接在 `main`/`master` 需用户授权。
- Commit：`feat|fix|refactor|docs|chore|test: <summary>`。`git add` 限定路径。
- 提交前需新鲜构建 + 模块验证；push 由用户请求。
- 终审：`workflow.ps1 final-check` 强制 Rebuild，再执行 `ts800x-final-reviewer`，输入含 diff、build、
  依赖报告、R01-R29 合规、硬件 PASS/PENDING。
- 阻断项为零且证据完整才交付；有待硬件项时结论只能是 `PASS_WITH_PENDING_HARDWARE`，不得写"功能正常"。

## 8. 项目状态

状态文件维护在**目标项目**根目录（非本仓库）：

```
PROGRESS.md   TODO.md   MEMORY.md   context/   reports/   logs/
```

文件实际存在且可解析后才能报告已交接或已完成。
