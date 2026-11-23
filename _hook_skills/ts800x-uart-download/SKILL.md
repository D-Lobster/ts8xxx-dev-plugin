---
name: ts800x-uart-download
description: TS800X ROM bootloader UART 固件下载。两种模式：RTS 硬件复位自动烧录（无人值守，AI 推荐）和人工按 RESET 手动模式。用于串口烧录、UART 下载、等待硬件 RESET、A0/A1 开发诊断；与 JLink 有线烧录和 BLE OTA 分开。
---

# TS800X UART 下载

通过 TS800X ROM bootloader 从 UART 写入 `.bin` 或 Intel HEX。`--firmware` 参数自动
检测 `.hex` 格式并解析地址，无需手动转换或指定基地址。

默认有线方式仍是 `ts800x-flash`（JLink）；只有用户明确要求串口时才使用本 Skill。

## 两种模式选择

| 模式 | 进入 bootloader 手段 | 是否需要人工 | 脚本 | 适用场景 |
|------|----------------------|--------------|------|---------|
| **RTS 自动（AI 推荐）** | RTS 管脚拉低 100ms 触发硬件复位 | 不需要 | `rts_uart_download.py` | CI/无人值守/AI 反复烧录验证 |
| 人工 RESET | 用户手动按 RESET | 需要 | `uart_download.py --wait-reset` | 无 RTS 接线的板子 |
| A0/A1 软件复位 | 软件复位 | 不能保证进 ROM | `uart_download.py --reset` | 仅开发诊断 |

---

## 模式一：RTS 自动烧录（推荐）

通过 CH340（或其他 USB 转串口）的 **RTS 管脚控制芯片硬件 RESET**，实现**完全无人值守**
烧录：RTS 拉低 100ms 复位芯片 → 芯片上电进入 ROM bootloader → 工具立即连续发送
SYNC 同步 → 下载固件 → BOOT 运行。

### ⚠ RTS 电平纪律（必须遵守）

**RTS 只在烧录的复位脉冲期间才允许拉低；其余任何时刻必须保持释放（高电平）。**

RTS 接的是芯片硬件 RESET（低有效）。任何工具在打开串口时若默认把 RTS 置低，
芯片就被一直按在复位状态：无启动日志、无广播、看似"死机"。实测 pyserial 默认
打开串口不会自动拉低，但不少串口助手（SSCOM/XCOM 等勾选 RTS/流控）会拉低。

因此：

- **烧录脚本**：仅在复位脉冲期间 `setRTS(True)`（拉低）拉 100ms，随后立即
  `setRTS(False)`（释放）；下载、BOOT、退出全程保持高。
- **日志抓取/串口助手**：打开串口时必须 `rts=False`（DTR 同样 `dtr=False`）；
  不得启用 RTS/CTS 硬件流控。
- **被按住复位的恢复**：调高/释放 RTS 后必须按一次 RESET（或用 RTS 再发一次
  低脉冲）让芯片重新上电，否则芯片仍停在复位状态。
- 一次会话内烧录+抓日志的推荐顺序：烧录（脚本自动管理 RTS）→ 断开 →
  以 rts=False 重新打开抓日志。

### 硬件前提（已验证）

- CH340 RTS 管脚连接到 TS800X 硬件 RESET（或复位使能电路）。
- 极性（pyserial / CH340 通用）：`setRTS(True)` → RTS 物理管脚**低电平**；
  `setRTS(False)` → RTS 物理管脚**高电平**。
- 已验证流程：**RTS 拉低 100ms → 释放 → 连续 SYNC 同步成功**。
- 若目标板极性相反（RTS 高有效复位），使用 `--rts-active-high`；默认低有效。

### 使用

```powershell
# 查看可用串口
python "<skill-dir>\rts_uart_download.py" --list

# AI 自动烧录 HEX（RTS 复位 → SYNC → 下载 → BOOT）
python "<skill-dir>\rts_uart_download.py" `
  --firmware firmware.hex --port COM15 --erase

# 只探测：RTS 复位后确认 ROM bootloader 响应，不写 Flash
python "<skill-dir>\rts_uart_download.py" `
  --port COM15 --sync-only -V
```

退出码 `0` = 成功；非 `0` = 失败。

### RTS 模式关键参数

| 参数 | 说明 |
|------|------|
| `--rts-hold-ms` | RTS 拉低保持时间，默认 `100`（已验证值） |
| `--rts-active-high` | 目标板 RTS 高有效复位时使用（默认低有效） |
| `--port` | 串口号；**不指定时自动选择 CH340**（多个 CH340 时需明确指定） |

### 自动复位时序

1. 打开串口（115200 8N1，`rtscts=False` 以便软件控制 RTS）。
2. 归一化：`setRTS(False)`、`setDTR(False)`（RTS/DTR 高电平）。
3. **复位脉冲**：`setRTS(True)` 保持 `--rts-hold-ms`（默认 100ms）。
4. `setRTS(False)` 释放 → 芯片上电 → 进入 ROM bootloader。
5. 立即以 30ms 间隔连续发送 SYNC，直到收到响应（`--sync-timeout` 内）。
6. `[--baud] → [--erase] → DOWNLOAD → BOOT`。

---

## 模式二：人工 RESET（--wait-reset）

TS800X 只有 POR 或硬件 RESET 才会进入 ROM bootloader。`NVIC_SystemReset()` 等软件复位
会重新进入 APP，不能替代人工按 RESET。

`--wait-reset` 工作方式：
1. **立即打开串口**：在弹窗前就打开 COM 口并开始后台发送 SYNC。
2. **非阻塞 tkinter 弹窗**：弹窗同时后台线程持续发送 SYNC（每 30ms 一次）。
3. 用户按 RESET → 芯片进入 ROM bootloader → 回复 SYNC 响应 → 后台线程捕获。
4. **弹窗自动关闭**：检测到 SYNC 后自动销毁弹窗，无需用户手动点击确定。
5. 超时仍未检测到 SYNC 则自动关闭弹窗并报告失败。

```powershell
# 推荐：烧录 HEX（自动解析地址，弹窗等待 RESET）
python "<skill-dir>\uart_download.py" `
  --firmware firmware.hex --port COM3 --wait-reset

# 烧录 .bin（需指定 --address）
python "<skill-dir>\uart_download.py" `
  --firmware firmware.bin --address 0x10000000 --port COM3 --wait-reset

# 远程桌面等弹窗不便时用纯控制台提示
python "<skill-dir>\uart_download.py" `
  --port COM3 --wait-reset --sync-only --no-popup -V
```

---

## 测试烧录流程（两种模式通用）

1. 使用成功构建生成的非空 `.hex`/`.bin`；开发中间版本不要求完整 Gate。
2. 确认串口、TX/RX/GND、供电和目标板；关闭其他串口程序。
3. 工具解析固件并校验地址、长度和 Flash 范围。
4. 执行下载；退出码非 0 均视为失败。
5. 读取日志并进行人工/功能验证，再记录硬件验证证据。
6. 模块完成或最终交付前补齐 code-quality、第二次 0/0 构建、依赖分析和终审。

---

## 通用关键参数

| 参数 | 规则 |
|------|------|
| `--firmware` | `.bin` 或 `.hex`（HEX 自动解析地址，忽略 `--address`） |
| `--address` | BIN 基地址，默认 `0x10000000`；HEX 自动从文件解析 |
| `--flash-size` | Flash 容量，用于地址范围校验（默认 `0x40000`） |
| `--erase` | 显式请求擦除；默认不擦除 |
| `--erase-blocks` | 每块 4 KiB，必须落在 Flash 容量内 |
| `--baud` | 下载波特率，默认 `115200`（RTS 模式，必须先支持才可切换） |
| `--sync-only` | 只验证 ROM SYNC，不读取固件、不擦除、不下载 |
| `--no-popup` | 与 `--wait-reset` 同用；只用控制台显示等待状态 |
| `--retries` | 只重试打开串口，不重发固件包 |
| `--allow-boot-no-response` | 旧 bootloader 兼容开关；使用后 BOOT 结果为未确认 |

## 串口选择（不固定）

串口号不固定，拔插 USB 后 COM 号会变化。两个脚本都自动处理：
- `--port COM15`：显式指定（校验存在，不存在即报错）。
- 不指定 `--port`：**RTS 模式自动检测并选择 CH340**（避免误选蓝牙串口）；
  人工模式需明确指定。
- 检测到**多个 CH340** 时明确报错，要求用 `--port` 指定。
- 无 CH340 时退回第一个可用串口并给出警告（仅 RTS 模式）。

## Intel HEX 烧录

`--firmware` 自动检测 `.hex` 文件（扩展名 `.hex` 且首字符为 `:`），调用 `parse_hex()`
解析为连续二进制数据。

支持记录类型：`0x00` 数据（按地址填充）、`0x01` EOF、`0x02` 扩展段地址、`0x04` 扩展线性地址；
`0x03`/`0x05` 起始地址忽略。

解析规则：每行校验（长度、ASCII HEX、checksum）、重叠检测、未填充区域用 `0xFF` 占位、
地址跨度限制（默认 256KB，`--flash-size` 可调整）、最终地址必须 4 字节对齐。

## ROM 响应协议

ROM 响应允许两种长度：
- **无 payload**：12 字节 header，`len=0`，无 checksum 尾部
- **带 payload**：12 字节 header + 4B payload checksum + payload，`len ≥ 4`

两种形式都必须通过 header checksum。BOOT 无响应默认失败，除非显式使用
`--allow-boot-no-response`。

## A0/A1 开发解析器

`soft_reset.c/.h` 是可选的传输层无关开发解析器，不自动注入项目，也不定义 UART ISR、
初始化 UART、阻塞发送或直接复位。集成前必须先检查项目 UART 架构，由项目代码完成：
UART ISR 收字节调 `soft_reset_rx_byte_isr()`、主循环调 `soft_reset_process()`、
RESET 由主循环执行项目认可的 SoC 复位流程。

这是开发后门。量产/交付前必须删除解析器及调用点，并由终审确认。

## 失败判定

- 无串口、SYNC 超时、ERASE/DOWNLOAD/BOOT 错误：失败。
- 复位问题先运行 `--wait-reset --sync-only -V` 或 RTS 模式 `--sync-only`；
  `SYNC RX` 可区分无数据与无效响应。
- RTS 模式 SYNC 超时：检查 RTS 接线、极性、`--rts-active-high`、目标板供电。
- **串口有打开但目标无任何输出**：先怀疑 RTS 被拉低按住复位（见上文 RTS 电平纪律），
  释放 RTS 并 RESET 后重试，再查波特率/接线。
- 仅在显式使用 `--allow-boot-no-response` 时才可接受 BOOT 无响应，并标记"未确认"。
- 未做硬件验证时只能标记 `[待硬件验证]`，不能标记 `[已验证]`。
