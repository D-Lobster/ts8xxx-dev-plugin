# TS800X 编码规范（R01-R29）

> 本文件是仓库内唯一权威规则。`_hook_skills/ts800x-coding-standard/SKILL.md` 是供 Codex、Claude 和 Pi 同步使用的可携带镜像；一致性由 `check_workflow.ps1` 检查。

## R01-R29

| 编号 | 主题 | 核心要求 |
|---|---|---|
| R01 | 文件头 | 新文件记录真实的 file/author/brief/date，作者 Daniel。 |
| R02 | 函数说明 | 公共与非显然函数记录 brief，并按需记录 param/retval/note；注释与实现一致。 |
| R03 | 全局变量 | 应用全局变量使用 `g_`。 |
| R04 | 静态变量 | 文件静态变量使用 `s_`。 |
| R05 | 局部/函数 | `lower_snake_case`，SDK/协议 ABI 例外。 |
| R06 | 宏/常量 | `UPPER_SNAKE_CASE`。 |
| R07 | 条件函数 | 优先 `is_/has_/can_`。 |
| R08 | 大括号 | K&R。 |
| R09 | 缩进 | 4 空格，无 Tab。 |
| R10 | 行宽 | ≤100 字符；不可分割内容需说明。 |
| R11 | 空格 | 运算符两侧、逗号后留空格。 |
| R12 | ISR 日志 | ISR 禁止 LOG/printf。 |
| R13 | ISR 工作量 | 只做清中断、必要寄存器、固定上限入队/置位；禁止等待和复杂计算。 |
| R14 | ISR Flash | ISR 禁止 Flash 擦写。 |
| R15 | 阻塞 | 业务流程禁止阻塞延时；有数据手册依据的短硬件时序需有界并说明。 |
| R16 | 内存 | 禁止动态分配，使用静态或编译期有界存储。 |
| R17 | 错误处理 | 校验指针/长度/范围/返回值；错误路径有状态、清理和超时。 |
| R18 | 模块接口 | 暴露最小且符合实际调度的 init/周期/事件接口，不造空接口。 |
| R19 | include | 自身→应用→SDK/系统，组内稳定排序，不依赖传递 include。 |
| R20 | GPIO | 板级映射集中定义，业务逻辑不散落裸引脚；引脚功能必须符合芯片能力——GPIO2 没有 PWM 复用通道，禁止配置为 PWM 输出（会导致系统复位，FAQ 2.8 Q8）。 |
| R21 | 错误码 | 多原因使用类型化错误码，纯成功/失败可用 bool。 |
| R22 | 多速率 | 从统一时基派生，避免模块各自漂移计时。 |
| R23 | Flash | 遵守当前 SDK 的地址/对齐/临界区/上下文要求，API 必须本地核验。 |
| R24 | 复杂度 | 函数通常 ≤50 行、应用调用深度通常 ≤3；分发可 ≤80 且分支 ≤10；删除无语义包装。 |
| R25 | 移植 | 保留来源并逐行 diff；时序/协议/索引/引脚差异逐项解释。 |
| R26 | LOG | 设备 LOG 字符串使用可打印 ASCII。 |
| R27 | BLE 存活检测 | 所有启用 BLE 的应用必须内置 BBTIME 存活检测：主循环周期比对基带定时器，连续 N 次无变化判定协议栈卡死，LOG 后复位恢复。禁止放 ISR；必须在 `tsBle_Init()` 之后；阈值与复位地址集中宏定义；复位前等待有界并说明依据。 |
| R28 | RAM 24K 配置 | 编译后 RAM 占用超过 16K（`0x4000`，越过 `0x20004000`）时，必须启用 `TS_RAM_SAVE_24K`；系统默认休眠只保留 16K，超出部分休眠后丢失会导致异常。每次编译后须记录 RAM 占用数值。 |
| R29 | 编译优化 | 所有项目（SDK 1.5 / 1.5.1 / 1.6）Target 优化等级固定 **-O1**（`<Optim>1</Optim>`），不得保留按文件的优化等级覆盖；ISR 与主循环共享变量必须 `volatile`；改配置后须全量 Rebuild 并核对 `.dep` 实际 `-O` 标志。 |

## R27 BLE 存活检测（强制）

**适用范围**：所有启用 BLE 的应用固件——从机、主机、多角色，以及 BLE 与 2.4G 共存
的场景，不分产品形态，均**必须**内置本检测。BLE 相关模块缺失该功能视为未完成。

**背景**：强电磁场、电源纹波、ESD 等环境干扰可能导致 BLE 基带定时器（BBTIME）停振，
协议栈卡死且不再产生广播/连接事件。此时主循环往往仍在运行，通用看门狗无法覆盖，
必须显式检测 BBTIME 是否推进，并在确认卡死后复位恢复。

**要求**：

1. 主循环周期性读取 BLE 基带定时器（`GET_CUR_TICK_US()`），与上次采样值比对。
2. 连续 `N` 次（默认 30，按主循环速率调整）无变化 → 判定卡死：输出 LOG 后触发系统复位。
3. 检测函数在**主循环**调用（`tsBle_Loop()` 之后），禁止放入 ISR（R12/R13）。
4. 必须在 `tsBle_Init()` 完成之后调用；初始化前该定时器未运行，会产生误判。
5. 阈值、复位寄存器地址与写入值必须集中宏定义（R06/R20），不得散落魔法数字。
6. 复位前的日志输出等待必须**有界并注明依据**（R15 例外）；禁止无界等待或轮询。
7. 静态变量使用 `s_` 前缀（R04）；检测路径不得动态分配（R16）。
8. 模块完成验证必须覆盖该检测的触发路径（注入/模拟卡死），无法在真机触发时记录
   `[待硬件验证]` 并写明测试步骤与验收标准。

**参考实现**（符号名称以目标项目与本地 SDK 核验为准，不得凭记忆套用）：

```c
#define BLE_WATCHDOG_FAIL_LIMIT   30u          /* 连续无变化阈值，按主循环速率调整 */
#define BLE_WATCHDOG_FLUSH_MS     100u         /* 复位前日志等待，有界，见 R15 例外 */
#define BLE_WATCHDOG_RESET_REG    0x40000008u  /* 复位寄存器，须本地核验后宏化 */
#define BLE_WATCHDOG_RESET_VAL    1u

static uint32_t s_bb_timer_back = 0u;
static uint32_t s_ble_no_work   = 0u;

/**
 * @brief  BLE 基带定时器存活检测，确认协议栈因环境干扰卡死后复位恢复。
 * @note   必须在 tsBle_Init() 之后、主循环中调用；禁止在 ISR 中调用。
 */
void ts800x_ble_watchdog_poll(void)
{
    uint32_t bb_timer = GET_CUR_TICK_US();

    if (bb_timer == s_bb_timer_back) {
        s_ble_no_work++;
        if (s_ble_no_work > BLE_WATCHDOG_FAIL_LIMIT) {
            s_ble_no_work = 0u;
            TS_LOG_INFO("ble watchdog reset\r\n");              /* ASCII，见 R26 */
            user_delay_ms(BLE_WATCHDOG_FLUSH_MS);               /* R15 有界例外 */
            REG_WRT(BLE_WATCHDOG_RESET_REG, BLE_WATCHDOG_RESET_VAL);
            while (1) {
                /* 等待复位生效 */
            }
        }
    } else {
        s_bb_timer_back = bb_timer;
        s_ble_no_work   = 0u;
    }
}
```

调用位置：

```c
while (true) {
    tsBle_Loop();
    /* ... 其他业务处理 ... */
    ts800x_ble_watchdog_poll();
}
```

> 详细问答与原始示例见 `_hook_skills/ts800x-faq/references/TS800X-FAQ.md` 2.11 Q6。

## R28 RAM 容量配置（16K / 24K，编译后检查）

**适用范围**：所有 TS800X 应用；对启用深睡（`TS_EN_DEEP_SLEEP`）的工程为强制项。

**背景**：

- 片上 RAM 共 24K：`0x20000000`–`0x20006000`，其中 **16K 边界为 `0x20004000`**。
- 系统**默认只保留前 16K**。见 `ts800x_sdk/soc/ts800x/system.c`：

  ```c
  #ifdef TS_EN_DEEP_SLEEP
  #ifndef TS_RAM_SAVE_24K
      AON_CTRL->AON_CTRL0 = 0x7A;   /* 默认：休眠仅保留 16K */
  #else
      AON_CTRL->AON_CTRL0 = 0xFA;   /* 24K 全保留 */
  #endif
  ```

- SDK 示例的 `cfg_def_app.h` 保留说明（默认注释掉）：
  `/*if the user needs to keep the last 8k of ram when sleep,Please open:TS_RAM_SAVE_24K*/`
- **RAM 占用越过 16K 而未开启该宏时，休眠后高地址数据丢失 → 唤醒后异常**
  （变量被破坏、状态机错乱、HardFault）。

**要求**：

1. **每次编译后检查 RAM 占用**：Keil 构建输出的 `Program Size: Code=… RO-data=… RW-data=… ZI-data=…`
   中 `RW-data + ZI-data` 之和（或 map 文件中 RAM 段的最高地址）。
2. 占用 **超过 16K**（`0x4000`，即越过 `0x20004000`）时，必须在 `APP/include/cfg_def_app.h`
   中加入：

   ```c
   #define TS_RAM_SAVE_24K
   ```

3. 未超过 16K 时保持默认（不开启）。
4. 该配置属工程级系统配置：改动须记录在模块报告与 `PROGRESS.md`，并写明触发时的 RAM 实测值。
5. 编译证据必须包含**本次 RAM 占用数值**，与 0/0 汇总、产物时间一并记录。

**检查位置**：`ts800x-build` 的构建后检查；模块完成与终审按本规则复核。

> 依据来自实际项目实践：JX122118 / JX122123 / JX122127（跳绳）、心率手环、体脂秤等项目
> 均已启用 `TS_RAM_SAVE_24K`；FAE 模板工程默认未开启。

## R29 编译优化等级（-O1）与共享变量可见性（强制）

**适用范围**：**所有** TS800X 应用项目——不论建立于 SDK **1.5 / 1.5.1 / 1.6** 哪个版本，
一律使用 **-O1**。优化等级错误（尤其 -O0，或"配置写 -O1、实际编 -O0"的漂移）会导致
时序、任务调度和共享变量可见性异常。

**背景**：SDK 自身未声明任何优化等级约束（无 `#pragma optimize`、无 `#error` 断言、
无文档约定），因此这是**项目自定义的强制工程约束**，必须在每个工程的 `.uvprojx`
中显式落实并验证。

**要求**：

1. **Target 优化等级固定为 -O1**：`.uvprojx` 中 `<Optim>1</Optim>`（Keil Level 1）。
   全部项目统一，不得使用 -O0 / -O2 / -O3，也不得保留或新增按文件的优化等级覆盖。
2. **ISR 与主循环共享的变量必须 `volatile`**（-O1 下的硬性正确性前提）：
   凡由 ISR/中断路径置位、主循环读取的标志（如 `f_task_10ms_flag`）必须声明为
   `volatile`（含 `extern` 声明处）。缺 `volatile` 时，编译器会把主循环的读取
   优化成寄存器缓存或常量折叠，**标志永远看不到、周期任务停摆**。
   正确样板：`body-scale` 项目（共享标志 + 临界区 + 寄存器宏 volatile 全部到位）。
3. **改动优化配置后必须全量 Rebuild 并核对实际编译标志**：检查新生成的 `.dep`
   文件中的 `-O` 标志是否与目标一致，杜绝"XML 写 -O1、实际编 -O0"的配置漂移
   （已有项目处于"XML 已改 -O1 但从未真正用 -O1 编译验证"的状态）。
4. 优化等级属工程级配置：变更须记入模块报告与 `PROGRESS.md`，并保留 Rebuild 后的
   `.dep` 证据。

**检查位置**：`ts800x-build`（构建配置校验 + `.dep` 核对）；`ts800x-code-quality`
与终审按本规则复核。

> 依据：`RULES/CODING_STYLE_GAP_ANALYSIS.md` 第 3 章（4 项目 `.uvprojx` 与 `.dep`
> 实测对照 + 缺 `volatile` 导致 10ms 任务停摆的机制分析）。

## R24 例外

硬件时序、ISR、协议帧、状态分发和核验过的 SDK 调用序列不得为了指标机械改写。例外必须说明原因、边界与验证方式，不能成为隐藏过度设计的借口。

## 架构原则

- 每个模块有单一状态所有者；跨模块共享状态记录所有者、读写方与并发策略。
- ISR 只做清中断、必要寄存器和固定上限入队/置位，业务在主循环处理。
- 写驱动前先查目标项目已集成模块 → `prebuilt_modules/` → SDK 例程，最后才新增。
- 应用代码在 `APP/`；`ts800x_sdk/` 只读。板级 GPIO 集中定义，业务不散落裸引脚。

> 每模块验证循环、测试烧录策略和最终交付声明见 `WORKFLOW.md`；R01-R29 逐条终审见 `REVIEW_CHECKLIST.md`。
