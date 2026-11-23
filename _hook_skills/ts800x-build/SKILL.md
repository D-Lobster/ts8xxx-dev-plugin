---
name: ts800x-build
description: 使用 Keil MDK UV4 编译 TS800X .uvprojx，并严格验证进程退出码、0 Error/0 Warning 汇总和本次新生成的非空 HEX/BIN；用于编译、链接和产物问题。
---

# TS800X MDK Build

```powershell
powershell -NoProfile -File "<skill-dir>\build.ps1" `
  -Uvprojx <project.uvprojx> [-Rebuild] [-Uv4Path <UV4.exe>]
```

脚本依次从 `-Uv4Path`、`KEIL_UV4`、常见安装目录和注册表定位 UV4。输出目录和
`OutputName` 从 `.uvprojx` 读取，不假定固定 `obj/ble_project`。

## 成功条件

UV4 进程退出码为 0、且日志存在明确的 Keil `0 Error(s), 0 Warning(s)` 汇总，是两种构建模式的共同前提。产物校验按模式区分：

- **增量构建（`-b`，默认）**：若 Keil 无需重新链接（源码无改动），允许复用已存在的非空 HEX/BIN 并判定通过；仅当编译成功但产物缺失/为空时（例如 Keil 重装后 obj 缓存损坏）才自动重跑一次 rebuild 兑底。
- **Rebuild（`-r`，即 `-Rebuild`/`-Clean`）**：HEX/BIN 必须非空且修改时间属于本次构建，否则判定失败。

只有项目明确不生成 BIN 时才可使用 `-AllowMissingBin` 并记录理由。缺少汇总、空产物、警告和编译错误都返回非 0。
`-Clean` 使用 rebuild 语义，以确保清理后立刻产生可验证产物。

## 编译后 RAM 检查（R28）

每次编译成功后，除 0/0 汇总与产物校验外，**必须**检查本次 RAM 占用：

1. 从构建日志读取 `Program Size: Code=… RO-data=… RW-data=… ZI-data=…`，
   RAM 占用取 `RW-data + ZI-data`（或读 map 文件中 RAM 段的最高地址）。
2. **超过 16K（`0x4000`，即越过 `0x20004000`）** 时，目标工程必须已在
   `APP/include/cfg_def_app.h` 中启用 `#define TS_RAM_SAVE_24K`；未启用即为阻断项。
3. 未超过 16K 时保持默认（不开启）。
4. 构建报告与项目 `PROGRESS.md` 中记录本次 RAM 数值——它是编译证据的一部分。

**原因**：片上 RAM 共 24K，系统默认休眠只保留前 16K（`system.c` 写
`AON_CTRL->AON_CTRL0 = 0x7A`）；只有定义 `TS_RAM_SAVE_24K` 才写 `0xFA`（24K 全保留）。
RAM 占用越过 16K 而未开启，休眠后高地址数据丢失，唤醒后异常（变量被破坏、状态机错乱、
HardFault）。完整规则见 `RULES/CODING_STANDARD.md` R28。

## 编译配置校验（R29）

所有项目（SDK 1.5 / 1.5.1 / 1.6）的优化等级固定 **-O1**，构建前/后须核对：

1. `.uvprojx` 中 Target 的 `<Optim>` = `1`（-O1）；不得为 -O0 / -O2 / -O3，也不得保留按文件的优化等级覆盖。
2. **改动优化配置后必须全量 Rebuild**，并核对新生成 `.dep` 文件中的 `-O` 标志与目标一致，
   杜绝"XML 写 -O1、实际编 -O0"的配置漂移。
3. 应用层 ISR 与主循环共享的标志必须 `volatile` —— 缺它在 -O1 下会导致周期任务停摆。

完整规则见 `RULES/CODING_STANDARD.md` R29。

## 静态检查

```powershell
powershell -NoProfile -File "<skill-dir>\auto_check.ps1" `
  -Check banned_functions -SourceDir <APP-source>
powershell -NoProfile -File "<skill-dir>\auto_check.ps1" `
  -Check isr_logging -SourceDir <APP-source>
```

其他检查包括 `compile_output`、`flash_layout` 和 `stack_size`。静态正则检查只是补充，不能替代
编译或人工审查。

初次 build 通过后可以直接进入开发测试烧录和日志/行为闭环，不强制 Gate。模块正式完成、
准备提交/交付或用户明确要求时，再执行 code-quality、回归 Rebuild、依赖分析和终审。
构建成功本身不代表功能或硬件验证成功。
