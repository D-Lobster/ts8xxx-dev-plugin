---
name: ts800x-flash
description: Use when flashing TS800X firmware with JLink or diagnosing connection/program/verify failures. Development flashing does not require a pre-flash Gate; JLink 操作（烧录/调试/RTT）统一由本 Skill 的 CLI 实现驱动，UART 下载与 BLE OTA 使用各自的技能。
---

# TS800X JLink 烧录技能

本 Skill 统一 Codex、Claude、Pi、DeepSeek 和纯 PowerShell 的烧录契约：**策略与实现在同一处**。
连接、解锁、擦除、烧录、校验、复位和 RTT 都由本目录的 JLink CLI（`run_cli.ps1`，
实现位于 `src/ts800x_jlink/`，核心是同一个 JLinkManager）完成。所有宿主一律通过
PowerShell 调用 CLI，不再使用 MCP server。

## 调用方式

```powershell
powershell -NoProfile -File "<skill-dir>\run_cli.ps1" list
powershell -NoProfile -File "<skill-dir>\run_cli.ps1" flash --firmware D:\absolute\firmware.hex
powershell -NoProfile -File "<skill-dir>\run_cli.ps1" rtt --duration 10
```

- `flash` 是复合命令，固定顺序：`connect → unlock → erase → program(verify=true) → reset → disconnect`。
- `rtt` 是有界捕获：自动 start、按 `--duration` 轮询读取、stop 并断开。
- 探针序列号不写死；多探针环境先 `list` 并明确选择，或设置 `TS800X_JLINK_SERIAL`。
- 可选环境变量：`TS800X_FLASH_SIZE`（默认 `0x40000`）、`TS800X_FIRMWARE_PATH`。

## 禁止分叉

- 不维护第二套 `flash.ps1`、MCP server 或隐藏的 JLink Commander 流程。
- UART Bootloader 下载使用 `ts800x-uart-download`。
- BLE 无线升级使用 `ts800x-ble-ota`。
- 写入前确认固件路径、目标设备和地址范围；写入后必须 verify。

## 开发测试顺序

1. 成功构建并生成非空 HEX/BIN；开发中间版本不要求先完成 code-quality 或依赖分析。
2. 确认固件路径、目标探针/设备和 Flash 布局。
3. 执行 `run_cli.ps1 flash --firmware <absolute-path>`（所有宿主同一入口）。
4. 保存 flash/verify JSON 结果，再读取 RTT/UART 日志并验证目标行为。
5. 模块完成或最终交付前，再补齐 code-quality、第二次 0/0 构建、依赖分析和终审证据。

`workflow.ps1 gate` 仅保留为可选交付审计；不运行或审计失败都不阻止开发测试烧录。

## 状态约束

- 断开连接会清除 unlock/erase 状态；任一步 `success != true` 立即停止。
- 默认禁止 `verify=false`；verify mismatch 是失败。
- BIN 基址由调用方明确提供；Intel HEX 使用文件真实段地址并严格校验。
- 所有地址必须落入配置的 TS800X Flash 范围（基址 `0x10000000`）；默认值只是工具配置，
  不替代目标工程/器件确认。
- RTT 默认 Control Block `0x20005F00`、Up Buffer `0x20002988`；先用目标 map/SDK 确认。

## 可选 PPK2 供电准备

PPK2 不是普通 JLink 烧录的依赖。默认路径不得扫描或操作 PPK2。只有同时满足以下
条件才启用本分支：

1. PPK2 已为本次功耗测量接入；
2. 用户明确确认 DUT 当前仅由 PPK2 供电；
3. 本次测量之后需要继续 JLink 烧录或日志验证。

测量尚未结束时，让 `measure` 使用 `--keep-power`。测量已经按默认行为结束并关闭
DUT 电源时，在首次 JLink connect 前执行：

```powershell
python "<ppk2-skill-dir>\ppk2.py" scan
python "<ppk2-skill-dir>\ppk2.py" info --port COMx
python "<ppk2-skill-dir>\ppk2.py" power --port COMx --state on --vdd 3300
```

任一步非 0 退出都停止 PPK2 分支，不得继续声称 DUT 已上电。`power on` 成功只证明
控制序列已发送；随后的 JLink connect 成功才构成 DUT 已可调试的端到端证据。

烧录后默认保持 PPK2 供电，完成 reset、RTT/UART 日志和硬件验证。只有用户明确要求
结束供电时才执行 `power --state off`。

## 写入失败语义

- connect/unlock/erase/program/verify 任一步 `success != true`：立即停止，禁止继续。
- verify 不匹配必须算失败，不能以“写入调用成功”替代校验成功。
- 固件为空、地址越界、目标不明确或 verify 不匹配：写入失败。
- 两次编译、代码质量、依赖报告和 ASCII LOG 属于模块完成/交付证据，不阻止中间测试烧录。

## 电源恢复（JLink 连不上时的处理）

芯片深度睡眠时 JLink connect 可能失败。先执行一次正常 connect；只有 connect 失败，
且 PPK2 已按上一节明确启用时，才用 PPK2 重新上电并重试：

```powershell
# 0. 使能 PPK2: 必须当场验证, 禁止复用旧结果/凭假设
python "<ppk2-skill-dir>\ppk2.py" scan
python "<ppk2-skill-dir>\ppk2.py" info --port COMx
# 1. 断电保持 2s 再重新上电（冷启动休眠芯片，默认 VDD 3300mV）
python "<ppk2-skill-dir>\ppk2.py" power --port COMx --state cycle --vdd 3300 --hold 2
# 2. 仅重试一次 JLink connect；成功后才 unlock → erase → program(verify) → reset
```

约束：
- **PPK2 未使能（scan/info 失败）→ 禁止执行 power cycle**，本恢复路径
  直接跳过，按原失败处理并记录；不得声称“已用 PPK2 重启”。
- 仅当 DUT 确认由 PPK2 供电时才可执行 power cycle；若 PPK2 未接入
  供电回路，执行后仍连不上，必须按失败处理并记录。
- power 命令必须连接验证通过（info 成功）才允许执行，非 0 退出即失败。
- power cycle 是完全掉电后的冷启动复位，不是保留 RAM/运行状态的睡眠唤醒。
- cycle 后只允许重试一次 connect；仍失败则立即停止。若固件冷启动后快速再次睡眠，
  记录失败并改用目标/JLink 明确支持的 connect-under-reset 方案。
- 记录 power cycle 时间点与结果，写入烧录报告作为证据链。

## 测试烧录最小检查

```text
【测试烧录检查】
- [x] 固件文件存在且非空
- [x] 固件地址与长度在目标 Flash 范围
- [x] 目标 JLink/设备明确
- [x] program 使用 verify=true
- [ ] 日志/物理行为验证（烧录后）
```

无真机日志与行为证据时仍标记 `[待硬件验证]`；CLI 返回 JSON 只证明调用结果。
