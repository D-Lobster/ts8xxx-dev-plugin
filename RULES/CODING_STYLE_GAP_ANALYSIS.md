# TS800X 代码风格与规范差距分析报告

> **状态**：分析报告（只读）。本文档**只产出建议，不修改** `CODING_STANDARD.md`、`SKILL.md`、`REVIEW_CHECKLIST.md`、`WORKFLOW.md`，也**不修改**任何客户项目代码。
> **日期**：2026-08-08
> **证据来源**：4 个真实客户项目的应用层源码 + TS800X SDK 本身 + 国际 C 编程规范。
> **目的**：服务三个目标——① 优化当前工作流；② 提炼通用编程规范；③ 让 AI 更自动化地写代码。

---

## 第 0 章 — 适用边界与最高红线

### 0.1 最高红线：SDK 只读，所有代码写在应用侧

```
ts800x_sdk/   ← 绝对只读，禁止任何改动
APP/          ← 所有应用代码只写在这里
```

这是本报告一切讨论的**不可动摇的前提**。后续所有"规则修订"建议，均指**应用层（`APP/`）的规则**，不涉及 SDK。本文档把这条已存在的约束明确升格为"最高红线"——任何规范讨论如果需要触碰 SDK，立即终止，不进入建议清单。

### 0.2 观察记录：部分工程对 SoC 时序文件设了 per-file `-O0`（未采纳为规则）

> **状态说明**：本节记录调查时观察到的现象，**不是强制约定**。R29 只要求 Target
> 统一 -O1、不保留按文件的优化等级覆盖；是否对个别 SDK 文件保留 `-O0` 以项目实际
> 验证为准，不作为交付要求。

即使 SDK 本身只读，调查发现部分工程配置（`.uvprojx`）里对以下 5 个 SoC 时序文件设有
per-file 的 `-O0`（不优化）覆盖：

| 文件 | 原因（调查时推断） |
|------|------|
| `soc/ts800x/system.c` | 启动/时钟配置时序敏感 |
| `soc/ts800x/ts800x_it.c` | 中断向量与 ISR 入口 |
| `soc/ts800x/ts800x_rtc.c` | RTC 时序 |
| `soc/ts800x/ts800x_sleep.c` | 睡眠/唤醒时序 |
| `soc/ts800x/ts800x_vtimer.c` | 虚拟定时时序 |

当时 4 个项目都设置了该覆盖。**该做法未被采纳为规则**（用户明确不要求保留 `-O0`）。

---

## 第 1 章 — 分析方法与证据来源

### 1.1 分析对象

| 项目 | 应用层路径 | 定位 |
|------|-----------|------|
| body-scale（人体秤） | `electronic-scale/body-scale/APP/` | ✅ 风格标杆（命名/架构/volatile 最规范） |
| kettlebell-count（壶铃计数） | `Kettlebell_count/kettlebell-count/APP/` | 🟡 部分规范 |
| humiture_ble（温湿度计） | `humiture_ble/humiture_ble_prj/APP/` | 🔴 风格最混乱 + tick 业务大杂烩 |
| heart-band（心率带） | `Heart_Rate/heart-band-main/heart-band-main/app/` | 🟡 tick 干净但"脏下放" |

外加 **TS800X SDK 本身**（`ts800x_sdk/`）作为"厂商原生风格"参照。

### 1.2 国际规范参照

| 规范 | 用途 |
|------|------|
| **MISRA C:2012** | 嵌入式安全最高权威。Rule 15.6 要求 if/else/while 必须有大括号，但**不规定大括号位置** |
| **Linux Kernel Coding Style** | 函数定义 `{` 另起一行，控制语句 `{` 同行（K&R 变体） |
| **GNU Coding Standards** | 全部 Allman（函数 + 控制都另起一行） |
| **Google C++ Style Guide** | 同行（K&R），要求 if/else 一致 |
| **CERT C EXP19-C** | 只要求"总是用大括号" |

### 1.3 证据分级声明

本报告每条结论均附 `file:line` 证据。证据强度分三级：

- **【高】**：多个项目一致 + 有明确机制 + 国际规范背书
- **【中】**：单项目或少量样本，但有清晰代码证据
- **【低】**：观察性结论，样本有限

---

## 第 2 章 — 【核心一】框架/架构约束

> R01-R29 规定了"代码怎么写"（命名/格式/注释），但没规定"**代码往哪放**"。本章用 body-scale 的真实代码给 AI 一个明确范本。

### 范本：body-scale 的 tick 函数（`working_process.c:687-721`）

```c
void main_processing_task(void)
{
    /* Keep the MCU ADC idle throughout sleep preparation and deep sleep. */
    if ((g_app.system_state != SYS_STATE_SLEEP_PREP) &&
        (g_app.system_state != SYS_STATE_SLEEP))
    {
        convert_adc_to_battery_voltage();
    }

    /* ---- 10ms 门控: 未到节拍则跳过以下所有任务 ---- */
    if (!take_10ms_task_flag())
    {
        return;
    }

    /* ---- 休眠准备状态机 (优先级最高, 阻塞正常任务) ---- */
    if (g_app.system_state == SYS_STATE_SLEEP_PREP)
    {
        process_sleep_prep_10ms();
        return;
    }

    /* ---- 已休眠: 仅维持电池采样, 其他跳过 ---- */
    if (g_app.system_state == SYS_STATE_SLEEP)
        return;

    mxa1211_adc_process();             /* Step 1: 称重 ADC */
    cht8320_process_10ms();            /* Step 1: 温湿度 */
    battery_update_state();            /* Step 1: 电池 */
    process_business_logic_10ms();     /* Step 2: 称重状态机 + 按键 */
    process_timekeeping_10ms();        /* Step 3: 软时钟计时 */
    process_display_10ms();            /* Step 4: LCD 渲染刷新 */
    process_ble_10ms();                /* Step 5: BLE 广播与数据推送 */
    shutdown_state_machine();          /* Step 6: 空闲/锁定超时休眠 */
}
```

**这就是写法标准。** 对照此范本，AI 写 tick 调度函数时遵守两条规则：

### 2.1 规则：tick 调度函数只做分发（候选 R27）

`main_processing_task()`（及同类 tick 函数）**只允许两种内容**：
1. 节拍门控 / 早退（`if (!take_10ms_task_flag()) return;`、状态机门控）
2. 一串 `xxx_process();` 调用，每个带步骤注释

**禁止在 tick 内**：内联业务计算、数据搬运/快照、状态机分支、init 序列、LOG、静态局部分频计数器（如 `++s_sec_tick`）。这些一律封装成独立 `xxx_process()` 函数。

- 初始化 → 放 `xxx_init()`，不放 tick
- 秒级分频 → 封装成 `process_1s_tick()`
- 数据快照 → 在被调函数内部读 `g_app`，不在 tick 里搬
- LOG → 放在调用点或诊断函数，不放业务流程函数

### 2.2 规则：被 tick 调用的子函数单一职责（候选 R28）

每个 `handle_xxx_workflow` / `xxx_handler` / `process_xxx_10ms` **只做一件事**（如"处理按键"、"更新充电状态"、"刷新显示"）。判定标准：函数名能准确描述其唯一职责。不得把脏活从 tick 挪进子函数凑成大杂烩——那只是换位置，不是分层。

**判定**：新增规则建议。证据强度【高】。优先级 **P0**。

---

## 第 3 章 — 【核心二】编译优化 `-O1` 约束与 volatile 规则链

> **这不是孤立的编译选项。** 调查发现 `-O1` 牵出一条完整的隐藏危险链：配置漂移 + 缺 volatile 的致命 bug + SoC 文件例外 + 全量重编流程。这条链和"框架要合理"是同一性质——本报告提出之前，R01-R28 完全没覆盖它，但它对代码能否正确运行至关重要（现已固化为 **R29**）。

### 3.1 现状：配置漂移（`.uvprojx` 设置 ≠ 实际编译）

通过解析 `.dep` 文件（Keil 记录的真实编译命令行 `-O?` 标志），发现 4 个项目的 XML 配置与实际编译**不一致**：

| 项目 | `.uvprojx` `<Optim>` | `.dep` 实际编译 | 真实"已验证可工作"等级 |
|------|---------------------|----------------|----------------------|
| kettlebell | 1（-O1） | **全部 -O0**（41 个 .c） | -O0 |
| humiture | 1（-O1） | **全部 -O0**（37 个 .c） | -O0 |
| body-scale | 2（-O2） | **全部 -O1**（48 个 .c） | -O1 |
| heart-band | 2（-O2） | **全部 -O1**（51 个 .c） | -O1 |

**含义**：kettlebell/humiture 的 XML 改成了 -O1，但**从没真正用 -O1 编译验证过**——上次实际编译是 -O0。一旦真用 -O1 全量重编，会立刻暴露下一节的致命 bug。

**SDK 对照**：SDK 示例工程 `.uvprojx` 统一是 `<Optim>2</Optim>`（-O2），但 SDK 交付过的真实编译记录（`ble_lp_wakeup` 的 `.dep`）是 `-O1`。SDK 头文件/源码**无任何** `#pragma optimize`、`#error` 优化断言、或文档约束。

### 3.2 致命风险：ISR 共享标志缺 `volatile`

所有 4 个项目的主循环都靠同一模式工作：

```
SysTick_Handler (ISR) → TickFlag_Handler() → 置 f_task_10ms_flag
                                              ↓
main_processing_task (主循环) → 读 f_task_10ms_flag → 跑 10ms 任务
```

**`-O1` 下，如果 `f_task_10ms_flag` 没有 `volatile`，编译器会把主循环里的标志读取优化成寄存器缓存或常量折叠，导致主循环永远看不到标志置位——10ms 任务停摆。**

#### 4 项目 `f_task_10ms_flag` 声明对照（证据强度【高】）

| 项目 | 声明 | volatile? | `-O1` 后果 |
|------|------|-----------|-----------|
| **body-scale** ✅ | `working_process.c:75` `volatile bool f_task_10ms_flag` + `working_process.h:47` `extern volatile bool ...` | **是（正确）** | 正常 |
| kettlebell 🔴 | `working_process.c:48` `static bool f_task_10ms_flag` | **否** | 10ms 任务停摆 |
| humiture 🔴 | `working_process.c:23` `static bool f_task_10ms_flag` | **否** | 10ms 任务停摆 |
| heart-band 🔴 | `working_process.c:20` `static bool f_task_10ms_flag` | **否** | 10ms 任务停摆 |

**附加缺 volatile 的共享标志**：kettlebell `adc_Sampling.c:77` `bool f_adc_perSampling_flag`（由 ISR 路径置位，主循环消费）同样缺 volatile。

**body-scale 是唯一正确处理的项目**——它的 5 处 volatile（`f_task_10ms_flag`、`f_adc_drdy_flag`、`s_adc_periodic_sampling_flag` 等）+ 临界区（`system_Enter_Critical`）+ 寄存器宏 volatile 全部到位。这也是它能从 -O1 真正编过的根本原因。

#### 建议规则（候选 R29：跨上下文共享变量必须 volatile）

> **所有在 ISR 与主循环之间共享的变量必须加 `volatile`。** 这不是风格偏好，而是 `-O1` 下代码能否正确运行的硬性正确性要求。参照样板：body-scale。

**修复点（若进入修订阶段）**：
- kettlebell `working_process.c:48`
- kettlebell `adc_Sampling.c:77`
- humiture `working_process.c:23`
- heart-band `working_process.c:20`

**判定**：新增规则建议。证据强度【高】（4 项目对照 + 明确机制）。优先级 **P0**。

### 3.3 `-O1` 工程约束建议

| 编号 | 建议 | 动作 | 证据强度 | 优先级 |
|------|------|------|---------|--------|
| **G1** | ISR/主循环共享变量必须 volatile | 见 3.2 修复点 | 【高】 | P0 |
| **G2** | 统一 Target `<Optim>` 为 `1`（-O1） | body-scale、heart-band 从 `<Optim>2</Optim>` 改为 `1`；kettlebell、humiture 已是 1 但需验证 | 【高】 | P0 |
| **G3** | 5 个 SoC 文件保留 per-file `<Optim>0</Optim>` | 不随 Target 改，保持现状 | 【高】 | P0 |
| **G4** | 改 XML 后必须 Rebuild 全量重编 | 核对新生成 `.dep` 的 `-O` 标志与目标一致，杜绝"XML 写 -O1 实编 -O0"的漂移（当前 kettlebell/humiture 正处此状态） | 【高】 | P0 |
| **G5** | 规范显式写明 -O1 是项目自定义约束 | SDK 无优化等级约束可引用，必须自行声明 | 【中】 | P1 |

### 3.4 不存在的风险（已排除）

- 绝对地址/`__at`/`#pragma location`：4 项目 APP 代码均 0 处，-O1 不影响
- 多字节共享变量竞态：未发现裸露问题；body-scale/humiture 已用 `system_Enter_Critical` 保护

---

## 第 4 章 — 命名与格式（轻量，承认现状）

> 按用户指示："匈牙利命名法基本就够了，不需要特别严格的规范。" 本章只**承认现状**，不造新前缀规则。

### 4.1 匈牙利命名法：承认为主基调

4 个项目一致采用匈牙利命名法，已行之有效。现状如下（不作强制细化，仅记录）：

| 类别 | 前缀 | 示例 |
|------|------|------|
| 全局变量 | `g_` | `g_app`、`g_usKeyLong_chat` |
| 静态变量 | `s_` | `s_ucKeychk_buf`、`s_sec_tick` |
| 标志位 | `f_` | `f_task_10ms_flag`、`f_keyin` |
| 类型前缀（局部） | `uc`(u8)/`us`(u16)/`ul`(u32) | `ucKey`、`usAdc_TimeOut` |
| 指针 | `p` / `ucp` | `ucpData` |
| const | `c_` | `c_ucaDefult_passWordSet` |
| 宏-定义类 | `D_` | `D_KEY_DEBUNCE` |
| 宏-引脚类 | `P_` | `P_KEY1_IN` |

**建议**：规范显式承认匈牙利命名法为项目主基调，与现有 R03（`g_`）/R04（`s_`）协调。**不新增** `f_/uc/us/D_/P_` 的强制条款——这些已在实际中稳定使用，写成现状描述即可。

### 4.2 大括号 R08：建议 K&R 改 Allman

这是规范与现实**最系统性的冲突**。

**证据一：TS800X SDK 本身就是 Allman。** 抽样 8 个 SDK `.c` 文件统计：

| SDK 文件 | K&R（同行） | Allman（单独行） |
|----------|------------|----------------|
| `main.c` | 0 | **5** |
| `system_init.c` | 1 | **9** |
| `ts800x_sleep_2g4.c` | 1 | **12** |
| `ts800x_it_2g4.c` | 0 | **1** |
| （唯一例外）`ts800x_otp_cfg_2g4.c` | 24 | 2 |

**证据二：4 个项目 100% 用 Allman。**

**证据三：国际规范不禁止 Allman。**

| 规范 | 立场 |
|------|------|
| **MISRA C:2012 Rule 15.6** | 只要求"if/else/while 必须有大括号"，**不规定位置** |
| **GNU Coding Standards** | 提倡 Allman |
| **Linux Kernel** | 函数定义 `{` 另起一行（与 Allman 函数部分一致） |
| **CERT C EXP19-C** | 只要求"总是用大括号" |

**结论**：没有任何国际规范禁止 Allman。MISRA——嵌入式最高权威——对位置完全不表态。STM32 HAL、GD32 固件库这些 MCU 厂商 SDK 普遍用 Allman。**R08 应当从 K&R 改为 Allman**，理由：①与只读 SDK 一致 ②与全部现有项目一致 ③MISRA 不禁止 ④嵌入式领域主流。

**建议**：R08 修订为 "使用 Allman 大括号（`{` 单独成行）"。但补充一条 MISRA 15.6 对齐要求：**所有 if/else/while/for 必须有大括号，即使单语句**（这点现有项目已基本做到）。

**判定**：规范误定修订。证据强度【高】。优先级 **P1**。

### 4.3 R05/R07 执行不彻底（强化执行，不重写规则）

| 规则 | 现状 | 建议 |
|------|------|------|
| R05 函数名 snake_case | 混用：`Battery_GetState`（PascalCase）/ `working_processInit`（混）/ `kettlebell_counter_get_count`（snake） | 强化执行，新代码统一 `module_snake_case` |
| R07 布尔函数 `is_/has_` | 仅 body-scale 贯彻（`is_ble_connected` 等），其余多用动词 | 强化执行，以 body-scale 为样板 |

**判定**：执行问题。证据强度【中】。优先级 **P2**。

### 4.4 固化拼写错误清单（建议修，不强求）

这些拼写错误已固化在符号名/宏里，建议在接触相关模块时顺手修正，不做大规模重命名：

| 错误 | 正确 | 位置 |
|------|------|------|
| `D_KEY_DEBUNCE` | `D_KEY_DEBOUNCE` | kettlebell `scanKey.c:22` |
| `D_KEYLING_CHAT` | `D_KEY_CHATTER` | kettlebell |
| `c_ucaDefult_passWordSet` | `c_ucaDefault_password_set` | kettlebell `working_process.c:32` |
| `wrok_Mode` | `work_Mode` | kettlebell |
| `let_state_t` | `led_state_t` | heart-band `led.h` |

**判定**：执行问题。证据强度【中】。优先级 **P2**。

### 4.5 规范缺项的好实践（建议提升为规范）

现实里存在但 R01-R29 没覆盖的好实践：

| 实践 | 示例 | 建议 |
|------|------|------|
| **日志模块标签** | `LOG_I("[Bat] charging...")`、`"[PM]"`、`"[Led]"` | 建议提升为规范：LOG 字符串以 `[Module]` 标签开头 |
| **typedef 统一** | 现状 `AppContext`(PascalCase)/`KettlebellAction_t`(`_t`)/`BatteryState`(无后缀) 三种并存 | 建议二选一统一（推荐 PascalCase 无后缀，与 body-scale 一致） |

**判定**：规范缺项补充。证据强度【中】。优先级 **P2**。

---

## 第 5 章 — 红线条款（不可让步基线）

确认以下 R12-R16/R23 红线在 4 项目基本守住，作为"硬性红线不可让步"的基线。本报告**不弱化**任何一条：

| 规则 | 要求 | 4 项目现状 |
|------|------|-----------|
| R12 | ISR 禁 LOG | ✅ 守住（ISR 只置标志） |
| R13 | ISR 只做最少工作 | ✅ 守住 |
| R14 | ISR 禁 Flash 擦写 | ✅ 守住 |
| R15 | 业务禁阻塞延时 | 🟡 边界（heart-band `hynitron.c:107` `delay_ms(1000)` 在 `#if 0` 内；body-scale LCD 初始化 `Delay_Ms`） |
| R16 | 禁动态内存 | ✅ 守住（全静态） |
| R23 | Flash 操作遵守 SDK 约束 | ✅ 守住 |

**新增红线候选**（来自本报告）：
- **R29 候选**：ISR/主循环共享变量必须 `volatile`（3.2 节）——这是正确性红线，不是风格
- **SDK 只读**：最高红线（0.1 节）

---

## 第 6 章 — 面向 AI 自动化的强化建议

> 用户目标之一："让 AI 更自动化写代码。" 当前规范对 AI 存在系统性盲点。

### 6.1 AI 的三大盲点

| 盲点 | 后果 | 根因 |
|------|------|------|
| **把 SDK 空壳注释当真** | AI 看到残留的 `Function:/PreCondition:/Input:` 全空模板，可能照着学，生成空注释 | R02 只说"写 brief"，没说"禁止残留空模板" |
| **在 tick 里堆代码** | AI 生成新模块时，习惯把业务逻辑直接写进 `main_processing_task`（LLM 训练数据里 tick 常是业务大杂烩） | R01-R29 完全没提"代码往哪放" |
| **漏 volatile** | AI 写 ISR 共享变量时容易忘记 volatile（这是 C 的著名陷阱） | R 规则没覆盖，且 -O0 下不暴露 |

### 6.2 给 AI 的正例 + 反例

建议在 `ts800x-coding-standard` SKILL 增加两节，配正例反例：

**正例模板（tick 调度函数）**——以 body-scale 为范本：
```
✅ tick 函数只含：节拍门控 + 一串 xxx_process() 调用
❌ tick 函数禁止：业务计算、数据搬运、状态机、init、LOG、分频计数器
```

**正例模板（volatile）**——以 body-scale 为范本：
```
✅ ISR 共享标志: volatile bool f_task_10ms_flag
❌ ISR 共享标志: static bool f_task_10ms_flag   // -O1 下会被优化掉
```

### 6.3 SKILL 强化建议

建议 `ts800x-coding-standard` SKILL 增加两节：
1. **"调度函数约束"**：第 2.1/2.2 节的 tick 纯净性 + 反脏下放规则
2. **"volatile 约束"**：第 3.2 节的跨上下文共享变量规则

这两节让 AI 写新模块时自动遵守，无需人工反复纠正。

---

## 第 7 章 — 建议清单与下一步

### 7.1 汇总表

| 编号 | 建议 | 类型 | 证据强度 | 优先级 | 影响范围 |
|------|------|------|---------|--------|---------|
| **R27** | tick 调度函数纯净性（只做分发） | 架构约束新增 | 【高】 | **P0** | 应用层新代码 |
| **R28** | 子流程函数单一职责（反脏下放） | 架构约束新增 | 【高】 | **P0** | 应用层新代码 |
| **R29** | ISR/主循环共享变量必须 volatile | 正确性红线新增 | 【高】 | **P0** | 应用层 + 修复 3 项目 |
| **G2** | 统一 Target -O1 | 工程约束 | 【高】 | **P0** | body-scale/heart-band 的 .uvprojx |
| **G3** | 5 SoC 文件保留 per-file -O0 | SDK 隐性约定 | 【高】 | **P0** | .uvprojx（已是现状） |
| **G4** | 改 XML 后 Rebuild 全量重编 + 核对 .dep | 流程约束 | 【高】 | **P0** | 工作流流程 |
| **R08 修订** | K&R 改 Allman | 规范误定修订 | 【高】 | P1 | 规则文本 + SKILL 镜像 |
| **G5** | 规范显式写明 -O1 自定义 | 工程约束 | 【中】 | P1 | 规则文本 |
| R05/R07 强化 | 函数名 snake_case / 布尔 is_ | 执行强化 | 【中】 | P2 | 应用层新代码 |
| 匈牙利承认 | 承认现状，写入规范 | 现状承认 | 【中】 | P2 | 规则文本 |
| 拼写修正 | DEBUNCE→DEBOUNCE 等 | 执行问题 | 【中】 | P2 | 接触时顺手 |
| typedef 统一 | PascalCase 无后缀 | 缺项补充 | 【中】 | P2 | 应用层新代码 |
| 日志标签 | `[Module]` 前缀 | 缺项补充 | 【中】 | P2 | 应用层新代码 |

### 7.2 优先级说明

- **P0（必须先解决）**：R27/R28（框架）+ R29/G2/G3/G4（-O1 与 volatile）。这些是"代码能否正确运行"和"框架是否合理"的根，且 3 个项目存在真实的 10ms 任务停摆风险。
- **P1（规范误定）**：R08 大括号。规范与 SDK/现实脱节，应修订。
- **P2（渐进改善）**：命名强化、拼写、typedef、日志标签。不影响正确性，接触时顺手改。

### 7.3 下一步

**本报告只产出建议，不执行任何规则修订。** 建议的后续路径：

1. **你逐条审阅**本清单，决定哪些进入"修订规则"阶段。
2. 对批准的条目，再启动独立的修订任务（改 `CODING_STANDARD.md` + 同步 `SKILL.md` 镜像 + 更新 `REVIEW_CHECKLIST.md`）。
3. P0 项涉及的 3 个客户项目 volatile 修复，需在各自项目分支单独进行（遵循 R25 逐行 diff + build 0/0 + 硬件验证），不在本仓库内完成。

### 7.4 本报告未做的事（边界声明）

- ❌ 未修改 `RULES/CODING_STANDARD.md`
- ❌ 未修改 `_hook_skills/ts800x-coding-standard/SKILL.md`
- ❌ 未修改 `REVIEW_CHECKLIST.md`、`WORKFLOW.md`
- ❌ 未修改任何客户项目代码（含 `.uvprojx`）
- ❌ 未做 git 提交

---
