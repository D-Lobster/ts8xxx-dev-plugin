---
name: ts800x-module-dev
description: TS800X 单模块开发全闭环。先查 prebuilt/examples 和 SDK API，再实现、集成诊断、两次零警告构建、代码质量、依赖、烧录及日志验证，产出可验证 handoff。
---

# TS800X 单模块开发

边界清晰、可独立验证的模块用本 Skill。涉及多模块边界或已有项目广泛改动时，分别见
`ts800x-workflow`（新项目流程）或 `ts800x-maintenance`（维护）。不负责改需求或跨模块架构决策。

## 输入契约

实现前确认：模块名、职责、API、调用周期、状态/错误、硬件资源、依赖、并发/ISR 边界、
功耗要求和验收测试。缺少会改变设计的信息时暂停确认。输入冲突时返回架构阶段，不自行改变
公共接口。

## 实现步骤

1. 变更前运行依赖分析并检查符号冲突。
2. 搜索目标项目 `ts800x_sdk/prebuilt_modules/`；可复用则优先复用。
3. 搜索 SDK examples 和 `ts800x-code-reader`，核对真实 API 与已知缺陷。
4. 定义最小 `.h` 接口；实现直接逻辑，不增加单调用者 wrapper、回调链或未来抽象。
5. 遵循 R01-R29：静态分配、非阻塞、ISR 最小、函数 ≤50 行、调用深度 ≤3、LOG ASCII。
   **涉及 BLE 的模块（广播、连接、GATT、透传、OTA、低功耗休眠、2.4G 共存）必须实现或
   确认 R27 BBTIME 存活检测存在**：主循环调用、在 `tsBle_Init()` 之后、阈值与复位地址
   宏化、复位前等待有界。缺失则补齐后再进入构建验证；BLE 模块无此检测不算完成。
   同时在构建后核对 **R28 RAM 占用**：`RW-data + ZI-data` 超过 16K 时，
   `APP/include/cfg_def_app.h` 必须启用 `TS_RAM_SAVE_24K`，否则休眠后异常。
   并确认 **R29 编译配置**：Target 优化等级为 -O1（无按文件覆盖）、
   ISR 与主循环共享的标志为 `volatile`；改配置后须全量 Rebuild 并核对 `.dep`。
6. 接入实际调度和 `.uvprojx`；仅生成未调用的文件不算集成（见下方集成诊断）。
7. `workflow.ps1 verify-module` 执行初验构建（含 RAM 占用检查，见 R28）。
8. 按需通过 JLink/UART/OTA 快速验证；开发测试烧录不强制 Gate，写入后必须 verify/完整性确认。
9. 运行 `ts800x-code-quality` 并记录证据，再次执行 `verify-module` 完成强制 Rebuild 和依赖报告。
10. 按需再次烧录并完成日志、测试输入和人工观察；无硬件时记录测试步骤和验收标准。

步骤 9-10 是模块完成检查。日常迭代在步骤 7 构建成功后即可烧录、读日志并继续修改，
不要求每轮都执行 code-quality、依赖分析和终审；未完成这些检查时不得宣称模块正式完成。

## 集成诊断

只依据目标工程的实际 `.uvprojx`、源文件和构建日志操作。不要假设工程名、目录、调度周期、
引脚或工具链中存在 GNU `nm`。

集成检查：
1. 找到用户指定或项目中唯一的 `.uvprojx`，记录绝对路径。
2. 确认新代码位于应用目录；`ts800x_sdk/` 保持只读。
3. 在 `.uvprojx` 中加入需要编译的 `.c`，路径相对工程文件有效且无重复条目。
4. 仅在编译确实需要时增加 include path；不要用宽泛根目录掩盖错误依赖。
5. 核对 `.h` 声明与 `.c` 定义的名称、类型、链接属性和条件编译一致。
6. 从目标项目现有入口确定初始化、周期任务或事件入口；事件驱动模块不强制伪造 `process_10ms`。

错误定位：
- 头文件缺失：报告 include 语句、当前 include 路径和缺失文件的真实位置。
- 未定义符号：确认调用点、声明、定义、源文件是否入工程以及定义是否被 `static`/宏排除。
- 重复符号：定位所有定义，保留唯一所有者，不用弱符号掩盖冲突。
- 签名不一致：以头文件和实际 ABI 为证据修正，不做强制类型转换规避。
- 链接区域溢出：读取 map/build 输出和链接配置；不要先删功能或改 SDK。

## 代码质量白名单

硬件时序、ISR、协议帧、状态机 switch 和 SDK 固定调用序列可以不做结构简化，但仍检查边界、
错误处理和规则合规，并在 code-quality evidence 中记录白名单理由。

## handoff 输出

写入 `<project>/context/handoffs/<module>/worker_output.json`：

```json
{
  "schema_version": 1,
  "handoff_type": "WORKER_OUTPUT",
  "project": "<project>",
  "module": "<module>",
  "timestamp": "RFC3339",
  "status": "PASS|FAIL|PENDING_HARDWARE",
  "inputs": ["context/handoffs/module_specs/<module>.md"],
  "outputs": ["APP/modules/<module>.c", "APP/modules/<module>.h"],
  "evidence": ["build", "code-quality", "dependency", "test/log"],
  "open_issues": [],
  "next_action": "<explicit action>"
}
```

写后重新解析 JSON，并同步项目 `PROGRESS.md`。

## 退出条件

模块只有同时满足以下条件才完成：

- 源文件已在项目和 `.uvprojx`；
- 两次 build 均 0/0 且产物新鲜；
- code-quality 与依赖报告存在；
- 测试烧录、verify/完整性和硬件验证状态明确；
- 硬件 PASS 或明确 PENDING_HARDWARE；
- `PROGRESS.md` 和模块 handoff 已更新。

用户提供"已验证模块"也必须至少核对接口、工程集成和当前项目 build，不能直接信任标签。
