---
name: ts800x-log-system
description: TS800X RTT/UART 日志捕获与严格分析。用于烧录后验证、RTT、串口日志、无输出、乱码和 APP_CFG_LOG_TYPE 排查；日志证据是模块硬件验证的一部分。
---

# TS800X 日志捕获与验证

RTT 与 UART 是互斥构建配置。先读取目标项目 `cfg_def_app.h` 的
`APP_CFG_LOG_TYPE`，不要根据习惯猜测通道、端口、引脚或波特率。

## 选择通道

- `LOG_RTT`：使用 `ts800x-flash` 技能的 JLink CLI（`run_cli.ps1 rtt`）捕获。
- `LOG_UART`：继续读取项目中的 UART 保存/初始化配置（包括
  `TS_SAVE_UART0_REGS`），确认实际 UART、波特率和引脚后再捕获。
- 配置不明确时停止并报告冲突；不得同时启动 RTT 和 UART 验证并把两者混为一份证据。

## RTT

JLink CLI 的默认 RTT Control Block 是 `0x20005F00`；先用目标 map/SDK 确认，必要时覆盖。
通过 `ts800x-flash` 技能的有界捕获命令执行：

```powershell
powershell -NoProfile -File "<ts800x-flash-skill-dir>\run_cli.ps1" rtt --duration 15
```

深睡后 SWD 可能关闭，需要用户配合 RESET。空 RTT、连接失败或没有期望事件都不能算验证通过。

## UART

```powershell
python "<skill-dir>\uart_capture.py" `
  --port COM3 --baudrate 115200 --duration 15 `
  --output logs/module.log --expect "init done"
```

工具只接受系统实际枚举到的串口；无数据、捕获时间不足、正则非法或期望事件缺失均返回非 0。
关闭其他串口工具后再运行。

### ⚠ RTS 接复位脚的板子：抓日志前先看这里

若目标板的 RTS 线接芯片硬件 RESET（低有效，常见于 RTS 自动烧录接线），抓日志时
RTS 必须保持释放（高）：打开串口时 `rts=False`、`dtr=False`，禁用 RTS/CTS 硬件流控。
否则 RTS 拉低 = 芯片被按在复位状态，抓到的永远是 0 字节。

本仓库 `uart_capture.py` 若未显式释放 RTS，请改用带 RTS 管理的抓取工具
（如项目内 `tools/uart_capture_rts.py`），或给 `uart_capture.py` 补上
`ser.rts = False; ser.dtr = False`。被按过复位后需再发一次 RTS 低脉冲或按 RESET
让芯片重新启动。

## 严格分析

```powershell
python "<skill-dir>\log_analyze.py" `
  --log logs/module.log --output reports/module.log.json `
  --expect "init done,expected event"
```

默认失败条件：文件不存在/不可读、空日志、ERROR/FAIL/NG/fault、WARN、非法或缺失的
期望正则。只有已确认某条 WARN 为无害且记录了理由时，才可显式使用 `--allow-warnings`。

日志分析通过只证明日志中的可观测行为；涉及 LED、按键、马达等视觉/物理结果，仍需用户确认。
没有真机证据时标记 `[待硬件验证]`。
