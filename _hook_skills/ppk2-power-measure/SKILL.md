---
name: ppk2-power-measure
description: PPK2 (PCA63100 Power Profiler Kit II) 功耗自动测量、电源控制与可选 JLink 烧录恢复。用于自动采集电流/功耗数据、测睡眠电流、广播/连接功耗、电量估算、平均/峰值/分位统计，以及当 PPK2 已为测量接入并给 DUT 供电时保持供电、开关电源或通过 power cycle 冷启动深睡眠芯片后重试 JLink；PPK2 不是普通烧录依赖，协议基于 Nordic pc-nrfconnect-ppk 上位机源码，与硬件包分开。
---

# PPK2 功耗自动测量

PPK2 通过 USB 虚拟串口（115200 8N1）与电脑通信。协议细节见同目录
`protocol.md`；所有测量用 `ppk2.py` 执行，禁止手工拼命令字节。

## 角色边界

- 默认只在功耗测量时接入和使用 PPK2；普通 JLink 烧录不得要求、扫描或操作 PPK2。
- 仅当用户明确确认“PPK2 当前已接入 DUT 供电回路且 DUT 仅由 PPK2 供电”时，
  才允许把 PPK2 用于测量后的持续供电或 JLink 连接失败后的电源恢复。
- 扫描到 PPK2 USB 串口不等于它已接入 DUT 供电回路，不得据此自动开关电源。
- 禁止 PPK2 与 DUT USB、外部电源或 JLink 供电脚并联给 VDD；JLink VTref/GND
  只作为目标电平参考和共地使用。

## 技能使能 Gate（防幻觉硬前提）

**只有 PPK2 当场验证可用时本技能才使能**，禁止凭记忆/假设认为 PPK2 在供电：

```powershell
python "<skill-dir>\ppk2.py" scan   # 必须发现 PPK2 串口
python "<skill-dir>\ppk2.py" info --port COMx  # 必须成功解析元数据(END)
```

- 两步都成功 → 技能使能，可执行 measure / power / analyze。
- 任一步失败/无结果 → 技能**未使能**：禁止执行任何 power 命令
  （尤其 cycle），不得在报告中声称“PPK2 供电中”；涉及 PPK2 的结论
  标记 `[PPK2 未使能]`。
- 每个会话/每次重新规划任务时都要重新验证，不得复用旧验证结果。

## 前置条件（先确认再动手）

1. PPK2 已插 USB，`python "<skill-dir>\ppk2.py" scan` 能识别出串口
   （Nordic VID 0x1915 或描述含 JLink CDC/nRF/PPK）。没有识别结果就停止，
   绝不猜测串口号。
2. DUT 接线已就绪：PPK2 的 VDD/GND 与开关电流测量路径接好被测设备。
   接线是物理动作，AI 不能代劳，需用户确认或标记 `[待硬件连接]`。
3. 关闭其他占用该串口的程序（nRF Connect for Desktop 等）。

## 标准流程

```powershell
# 1. 发现并确认 PPK2 串口
python "<skill-dir>\ppk2.py" scan

# 2. 连接验证: 必须成功解析元数据(END 结尾), 失败=连接不可用
python "<skill-dir>\ppk2.py" info --port COMx

# 3. 采集 (smu=PPK2供电并测量; am=外部供电只测电流)
python "<skill-dir>\ppk2.py" measure --port COMx `
  --vdd 3000 --mode smu --duration 10 --output reports/ppk2_adv

# 4. 分析 (同目录 .json 摘要自动带入校准系数; 输出平均功耗 mW)
python "<skill-dir>\ppk2.py" analyze --input reports/ppk2_adv.bin `
  --phase-threshold 100
```

## PPK 供电 + 平均功耗（TS800X 典型用法）

PPK2 在 SMU 模式下可**直接给 DUT 供 3.3V 并同时测电流**，用于测 TS800X
上电后的平均功耗：

```powershell
# 打开 3.3V 电源给 DUT, 采集 30s, 得到平均功耗
# (上电后默认等 2 秒 --settle 再采集, 避开启动瞬态)
python "<skill-dir>\ppk2.py" measure --port COMx `
  --vdd 3300 --mode smu --duration 30 --output reports/ts800x_avg_power
python "<skill-dir>\ppk2.py" analyze --input reports/ts800x_avg_power.bin
```

`measure` 默认在采集结束后关闭 DUT 电源。若功耗测量后要立即 JLink 烧录、读取 RTT
或继续硬件验证，给 `measure` 增加 `--keep-power`；若采集已经按默认行为结束，则必须
重新通过使能 Gate，并在 JLink connect 前执行 `power --state on`。

`analyze` 输出中的功耗字段直接可用：`mean_mw`（平均功耗）、`p50_mw`/
`p90_mw`（分位）、`energy_mwh`（总能量）、`mean_ua`（平均电流）。
功耗按逐样本 `mW = 电流µA × VDD(mV) / 1e6` 计算，VDD 取实际设置值。

**电源开关序列（与官方上位机一致）**：`SetPowerMode(0x11)` →
`RegulatorSet(0x0D 设电压)` → **`DeviceRunningSet(0x0C, 1) 打开 DUT 电源`** →
`AverageStart`；结束后 `AverageStop` + `DeviceRunningSet(0x0C, 0) 关电源`。
只设电压不发 0x0C=1 时 VDD 无输出，会测到漏电而非真实功耗——
如果测得电流接近 0 且 DUT 应该运行，先检查此序列是否完整。

**供电接线前提（必须确认，否则测量无效）**：DUT 必须由 PPK2 单独供电——
断开 DUT 自身的 USB/外部电源，只接 PPK2 的 VDD/GND/开关测量路径。
若 DUT 另有电源并联供电，PPK2 测到的是旁路电流，结论作废。

## 场景联动（测 DUT 各工作状态功耗）

测“某状态下功耗”时，先启动采集，再用对应的业务工具触发状态，最后停止：

- **BLE 广播/连接/透传功耗**：先 `measure`（后台采集），再用
  `ts800x-ble-test` 触发广播/连接/收发，采集结束后停止测量。
- **睡眠/唤醒功耗**：采集期间让 DUT 进入睡眠、再唤醒；用
  `--phase-threshold` 或分位统计区分低功耗态与活跃态。
- 测量命令与业务命令的先后顺序、时间点必须写进报告，作为证据链。

## 电源控制与 JLink 可选联动

**前提：技能必须已通过使能 Gate（scan + info 当场验证）**，
未验证时禁止执行 power 命令——PPK2 未接在供电回路时 cycle 无效且会误导结论。

PPK2 在 SMU 模式下可直接控制 DUT 电源。只在本 Skill 的角色边界成立时执行：

```powershell
# 上电 (SMU, VDD 3300mV)
python "<skill-dir>\ppk2.py" power --port COMx --state on --vdd 3300
# 断电 (VDD 输出关闭)
python "<skill-dir>\ppk2.py" power --port COMx --state off
# 重新上电: 断电保持 2s 再恢复 (默认 --hold 1.5s)
python "<skill-dir>\ppk2.py" power --port COMx --state cycle --vdd 3300 --hold 2
```

按场景选择动作：

1. **测量后立即烧录**：优先让 `measure` 使用 `--keep-power`；如果测量已经结束并
   关闭电源，则重新 `scan` + `info`，执行 `power --state on`，再开始 JLink connect。
2. **深度睡眠恢复**：先尝试一次 JLink connect。仅当 connect 失败、PPK2 已使能且
   用户确认它正在给 DUT 供电时，执行一次 `power --state cycle`，然后只重试一次
   JLink connect。不得因为 PPK2 可见而跳过首次 JLink connect。
3. **烧录后验证**：默认保持 PPK2 供电，完成 reset、RTT/UART 日志和硬件观察；
   只有用户明确要求结束供电时才执行 `power --state off`。

`power on/cycle` 返回成功只证明 PPK2 已接受并发送控制序列，不证明 VDD 在物理接线
端已经有效。后续 JLink connect 成功才是 DUT 已可调试的端到端证据。若 cycle 后仍
无法连接，立即按烧录失败处理；不得继续 unlock/erase/program。

`power cycle` 会使芯片完全掉电并冷启动，不是保留 RAM 或运行状态的睡眠唤醒。
若固件冷启动后很快再次睡眠，记录失败并改用目标/JLink 明确支持的
connect-under-reset 方案，不得无限重复 cycle。

## 真机实测验证记录

设备：PPK2（VID 1915:C00A，数据口 COM7，序列号 C9165C5333FC）；
DUT：TS800X @ 3.3V SMU 供电，`--settle 2` 开电源后等 2 秒再采集。

| 测试 | 平均电流 | 平均功耗 | 空闲/睡眠电流 | 模块状态 |
|---|---|---|---|---|
| 10s×2 | 371/369 µA | 1.22 mW | 85 µA (92%) | 周期广播 |
| 10s | 150 µA | 0.49 mW | 85 µA (99%) | 安静待机 |
| 10s | 3206 µA | 10.58 mW | ~9 µA (1%) | 持续活跃 |
| 10s | 38 µA | 0.126 mW | **2 µA (99.6%)** | 深度睡眠 |

结论：TS800X 状态功耗谱 2 µA(睡眠) → 85 µA(空闲) → 3.2 mA(持续活跃)；
空闲功耗 0.28 mW 稳定复现（三次差异 <1%）。全部 0 丢包，原始数据落盘
`<测试输出目录>/ts800x_10s_{c,d,e,f,g}.bin`(+.json) 可追溯。

**实测教训**：
1. 只发 RegulatorSet 不开 0x0C=1 时 VDD 无输出，会误测成漏电
   （曾测得 0.175 µA，补开电源后正常）——遇“电流接近 0 且 DUT 应运行”
   先查电源序列。
2. 刚上电有启动瞬态，`--settle 2` 等稳定再采。
3. 模块状态会自主变化（睡眠/广播/持续活跃），同一配置多次测量平均值
   会不同，报告必须记录测量时刻模块状态；要测固定状态需用业务工具触发
   （见下节）。
4. 串口被占用（nRF Connect Power Profiler / JCom 等）时
   `PermissionError(13)`，先关闭占用程序再测。

## 严格规则（违反即失败/标注）

- 连接验证未通过（元数据超时/无 END）→ 禁止继续测量。
- 丢包率 > 1% → 报告结论必须标注“数据不完整”，不能当作精确功耗值。
- 采集 0 样本、duration 未达预期、串口打不开 → 非 0 退出，按失败处理。
- 电流出现负值/极大值：多为量程切换伪影（R 高量程段），按 `range_stats`
  核实，不能直接当真实电流引用。
- 只测到“某时刻电流”不算功耗结论；平均值、时间占比、电量(mAh)、分位值
  一起给出。涉及物理接线的项没有用户确认时标记 `[待硬件验证]`。
- 分析结果必须落盘 JSON 并写入报告；不引用未经落盘的中间数字。
