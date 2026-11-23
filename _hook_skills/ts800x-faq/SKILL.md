---
name: ts800x-faq
description: TS800X SDK V1.5.1+ 常见问题速查。用于报错、异常现象、配置疑问、编译/烧录失败、BLE 行为异常、2.4G、低功耗休眠、ADC/PWM/串口外设、Flash/OTA、HardFault 与日志、EMC 认证、硬件工具与例程对应等问题，先查 FAQ 定位再排查；含三条必看规则（外设初始化必须在 tsBle_Init 之后、连接参数变更时禁止进入休眠、BLE 存活检测 BBTIME 为所有 BLE 应用强制功能）。完整答案见 references/TS800X-FAQ.md。
---

# TS800X SDK FAQ 速查

适用 SDK **V1.5.1+**。本技能是官方 FAQ 的检索入口：先用下面的索引定位问题，
再到 `references/TS800X-FAQ.md` 查完整答案（含代码示例与参数说明）。

**使用原则**：FAQ 给出的是"已知原因 + 官方推荐做法"，不是猜测。若 FAQ 与该版本
SDK 的实际头文件/例程冲突，以本地 SDK 为准并报告差异，不要凭 FAQ 记忆改代码。

---

## 必看规则（违反会导致不可预期异常）

### FAQ-R1 外设初始化必须在 tsBle_Init 之后

**规则**：所有外设（UART、ADC、PWM、I2C、SPI、GPIO 等）的初始化必须在
`tsBle_Init()` 完成之后执行。

**原因**：`tsBle_Init()` 内部初始化 BLE 协议栈、射频时钟和系统电源管理；
外设若先于蓝牙初始化配置，寄存器状态可能被协议栈初始化覆盖，导致外设异常或 HardFault。

```c
SystemClock_Init();    // ① 系统时钟（必须最先）
tsBle_Init();          // ② BLE 协议栈（在外设之前）
TS_LOG_INIT();         // ③ 外设（必须在 tsBle_Init 之后）
ts800x_HAL_UART_Init(...);
```

**常见错误**：把日志 UART 初始化放在 `tsBle_Init()` 之前 → 日志无输出或死机。

### FAQ-R2 连接参数变更时禁止进入休眠

**规则**：调用 `tsBleSlave_Set_ConnInterval()` 修改连接参数时，芯片必须处于唤醒状态。

**原因**：休眠期间调用会触发协议栈内部状态冲突，导致系统复位。

```c
case DEVEVT_CONNECTED:                    // 唤醒状态下修改
    tsBleSlave_Set_ConnInterval(40, 48, 0, 500);
    TS800X_SLEEP_FLAG_SET();
    break;

if (g_request_conn_update && !ts800x_Is_Sleeping()) {   // 或主循环异步处理
    tsBleSlave_Set_ConnInterval(40, 48, 0, 500);
    g_request_conn_update = 0;
}
```

### FAQ-R3 BLE 存活检测（BBTIME）是所有 BLE 应用的强制功能

**规则**：所有启用 BLE 的应用固件（从机/主机/多角色，含与 2.4G 共存）**必须**内置
BLE 基带定时器（BBTIME）存活检测——见编码规范 **R27**。BLE 相关模块缺失该功能视为未完成。

**原因**：强电磁场、电源纹波、ESD 等环境干扰可能导致 BBTIME 停振、协议栈卡死，
且不再产生广播/连接事件；此时主循环仍在运行，通用看门狗覆盖不到。

**要求**（完整规则与参考实现见 `ts800x-coding-standard` 的 R27）：

1. 主循环调用（`tsBle_Loop()` 之后），**禁止放 ISR**。
2. 周期读取 `GET_CUR_TICK_US()` 与上次值比对；连续 N 次（默认 30）无变化 → LOG + 系统复位。
3. 必须在 `tsBle_Init()` 之后调用，否则定时器未运行会误判。
4. 阈值、复位寄存器地址/写入值集中宏定义，禁止魔法数字。
5. 复位前日志等待必须有界并注明依据（R15 例外）。

**写 BLE 代码时**：新建或修改任何 BLE 模块（广播、连接、GATT、透传、OTA、低功耗
休眠、2.4G 共存）都要检查该检测是否存在；缺失则补齐，并在模块报告中记录
该检测的位置与触发验证结果（真机无法触发时写 `[待硬件验证]` + 测试步骤）。

---

## 分类索引

| 章节 | 主题 | 典型问题（完整列表见 references） |
|------|------|-----------------------------------|
| 2.1 | 开发环境 | 需要的软件、J-Link "No Algorithm found"、头文件找不到、undefined symbol、flash loader 加载失败、GCC/其他 IDE 支持 |
| 2.2 | BLE 基础 | 角色配置、广播名修改不生效、广播/连接间隔、自定义 GATT Service、Notify 发送、最大连接数、MTU 与吞吐、自动断开、串口透传、31 字节广播扩展 |
| 2.3 | BLE 配对 | 启用配对/加密、Passkey 失败排查、断连后重复配对 |
| 2.4 | BLE 进阶 | iPhone 来电提醒、ANCS 收不到通知、HID 键盘、BLE 与 2.4G 共存、多角色限制 |
| 2.5 | 2.4G 协议 | 初始化配置、通信距离优化、数据格式（MSB/LSB/Whitening）、例程对应、2.4G 与 BLE 休眠差异 |
| 2.6 | 低功耗休眠 | 深度休眠启用、休眠宏无效、GPIO 唤醒、RTC 唤醒、唤醒后死机/HardFault、唤醒后 UART 无输出、休眠电流优化、休眠中断连、广播/连接间隔与休眠关系、连接事件内改间隔 |
| 2.7 | ADC 采样 | BLE 共存限制、采样不准/漂移、最小代码模板、启动时初始化问题 |
| 2.8 | PWM 输出 | 无波形排查、频率/占空比计算、改占空比影响频率、互补输出、GPIO0/GPIO1 异常、GPIO2 配 PWM 导致系统复位、分频器取值、定时器 48MHz 限制 |
| 2.9 | 串行外设 | 日志 RTT/UART 切换、UART 波特率、I2C 失败、SPI 中断 vs 轮询 |
| 2.10 | Flash & OTA | Flash 读写、OTA 流程、升级后无法启动、Flash 布局、Bootloader 烧录确认 |
| 2.11 | 调试日志 | RTT vs UART、HardFault 定位、看门狗、Assert 框架、协议栈内部日志、BLE 干扰卡死检测 |
| 2.12 | EMC 认证 | 已通过认证、FCC 注意项、TX Power 范围、谐波处理 |
| 2.13 | 硬件工具 | 晶振选型、32K 校准、OTP 配置、bin2c/srec_cat、J-Link RTT、GPIO0/1 调试占用、项目模板、BLE 例程功能 |

---

## 高频坑位（先查这几条）

| 现象 | 优先查 |
|------|--------|
| 日志无输出 / 启动死机 | 必看 R1；2.1 头文件与符号；2.11 日志配置 |
| 编译报头文件找不到 / 大量 undefined symbol | 2.1 Q3、Q4 |
| J-Link 烧录报算法或 flash loader 错误 | 2.1 Q2、Q5 |
| 手机搜不到设备 / 广播名仍旧 | 2.2 Q2；2.6 Q9 广播间隔 |
| 上电后几秒内搜不到广播 | 2.2 Q11：上电到首个广播固定 400~500 ms，属正常（与程序无关） |
| 连接后自动断开 | 2.2 Q8；2.6 Q8 休眠中断连 |
| 修改连接间隔后复位 | 必看 R2；2.6 Q11、Q12 |
| 配了休眠宏却进不去休眠 | 2.6 Q2；2.6 Q10 连接间隔 <50ms |
| 休眠电流偏大 | 2.6 Q7 |
| 唤醒后 HardFault / UART 无输出 | 2.6 Q5、Q6 |
| ADC 采样不准或启动异常 | 2.7 Q2、Q4 |
| PWM 无输出 / 频率不对 | 2.8 Q1、Q3；GPIO2 上配置会复位，见 2.8 Q8 |
| 不明原因系统复位 | 检查是否把 GPIO2 配成了 PWM（2.8 Q8）；改连接间隔后复位见必看 R2 |
| OTA 升级后不启动 | 2.10 Q3；2.10 Q4 Flash 布局 |
| 进入 HardFault 无定位手段 | 2.11 Q2；2.11 Q5 协议栈日志 |
| GPIO0/GPIO1 功能异常或无法调试 | 2.8 Q5；2.13 Q6 |

---

## 与其他技能的分工

| 场景 | 用哪个 |
|------|--------|
| 查"这个问题已知原因是什么" | **本技能**（FAQ） |
| 读懂现有工程结构与调用链 | `ts800x-code-reader` |
| 查 SDK 函数签名/类型/常量 | `ts800x-code-reader`（本地 SDK 为准） |
| 编译失败需要跑构建并验证 0/0 | `ts800x-build` |
| 烧录/JLink 连接失败 | `ts800x-flash` |
| 日志捕获与严格分析（RTT/UART） | `ts800x-log-system` |
| 怀疑 SDK 已知缺陷 | `ts800x-sdk-bug-reference` |
| 写应用代码需遵守编码规则 | `ts800x-coding-standard` |

---

## 详细答案位置

- 完整 FAQ（含 83 个问答、代码示例、参数表）：
  `references/TS800X-FAQ.md`
- 按章节查：先在上表定位章节号（如 2.6），再到 references 文件搜索
  `## 2.6` 或问题关键词。
- 引用 FAQ 结论时必须区分「官方 FAQ 说法」与「本机 SDK 实测结果」；
  未在真机复现的结论不得写成 `[已验证]`。
