# TS800X SDK 常见问题解答

适用于 SDK V1.5.1+。

---

## 快速索引

| # | 问题 | 章节 |
|---|------|------|
|   | **软件开发重点建议（必看）** | 必看 |
|   | [外设初始化必须在 tsBle_Init 之后](#必看1-外设初始化必须在-tsble_init-之后) | 必看 |
|   | [连接参数变更时禁止进入休眠](#必看2-连接参数变更时禁止进入休眠) | 必看 |
| 1 | [开发 TS800X 需要哪些软件？](#q1-开发-ts800x-需要哪些软件) | 2.1 |
| 2 | [首次烧录时 J-Link 报 "No Algorithm found"？](#q2-首次烧录时-j-link-报-no-algorithm-found-或下载失败) | 2.1 |
| 3 | [编译时提示头文件找不到？](#q3-编译时提示-no-such-file-or-directory-或头文件找不到) | 2.1 |
| 4 | [编译时提示大量 undefined symbol？](#q4-编译时提示大量-undefined-symbol--unresolved-external) | 2.1 |
| 5 | [烧录提示 "The flash loader cannot be loaded"？](#q5-编译后烧录提示-the-flash-loader-cannot-be-loaded) | 2.1 |
| 6 | [SDK 是否支持 GCC / 其他 IDE？](#q6-sdk-是否支持-gcc--其他-ide) | 2.1 |
| 7 | [如何配置 BLE 角色？](#q1-如何配置-ble-角色从机主机多角色) | 2.2 |
| 8 | [修改广播名后手机搜不到？](#q2-修改了广播名称但手机上搜不到或仍显示旧名称) | 2.2 |
| 9 | [BLE 从机如何设置广播和连接间隔？](#q3-ble-从机如何设置广播间隔和连接间隔) | 2.2 |
| 10 | [如何注册自定义 GATT Service？](#q4-如何注册自定义-gatt-service) | 2.2 |
| 11 | [BLE 从机如何发送 Notify？](#q5-ble-从机如何向主机发送数据notify) | 2.2 |
| 12 | [BLE 可以同时连接多少个设备？](#q6-ble-可以同时连接多少个设备) | 2.2 |
| 13 | [BLE 最大 MTU 和吞吐量？](#q7-ble-最大-mtu-和吞吐量是多少) | 2.2 |
| 14 | [BLE 从机连接后自动断开？](#q8-ble-从机连接后自动断开) | 2.2 |
| 15 | [如何实现 BLE 串口透传？](#q9-如何实现-ble-串口透传) | 2.2 |
| 16 | [BLE 广播数据只有 31 字节如何扩展？](#q10-ble-广播数据只有-31-字节如何扩展) | 2.2 |
| 17 | [上电到第一个广播要多久？](#q11-ts8001-从机上电到发出第一个广播需要多长时间) | 2.2 |
| 18 | [如何启用 BLE 配对/加密？](#q1-如何启用-ble-配对加密) | 2.3 |
| 19 | [配对失败（Passkey）怎么排查？](#q2-配对失败passkey-模式怎么排查) | 2.3 |
| 20 | [配对成功后断连需要重新配对？](#q3-配对成功但断连后需要重新配对) | 2.3 |
| 21 | [TS800X 能实现 iPhone 来电提醒吗？](#q1-ts800x-能实现-iphone-来电提醒吗) | 2.4 |
| 22 | [ANCS 来电提醒收不到通知？](#q2-ancs-来电提醒总是收不到通知) | 2.4 |
| 23 | [如何实现 HID 键盘？](#q3-如何实现-hid-键盘) | 2.4 |
| 24 | [BLE 和 2.4G 能同时使用吗？](#q4-ble-和-24g-私有协议能同时使用吗) | 2.4 |
| 25 | [BLE 多角色模式的限制？](#q5-ble-多角色模式的限制是什么) | 2.4 |
| 26 | [2M / S2 / S8 速率如何申请？](#q6-如何申请-2m-或-s2s8-长距离速率) | 2.4 |
| 27 | [2.4G 如何初始化和配置？](#q1-24g-如何初始化和配置) | 2.5 |
| 28 | [2.4G 通信距离短怎么优化？](#q2-24g-通信距离短怎么优化) | 2.5 |
| 29 | [2.4G 数据格式如何配置？](#q3-24g-数据格式如何配置msblsbwhitening) | 2.5 |
| 30 | [2.4G 各例程的用途？](#q4-24g-例程之间如何对应) | 2.5 |
| 31 | [2.4G 休眠与 BLE 休眠有何不同？](#q5-24g-协议休眠与-ble-休眠有何不同) | 2.5 |
| 32 | [如何启用深度休眠？](#q1-如何启用深度休眠) | 2.6 |
| 33 | [配置了休眠宏但无法进入休眠？](#q2-已经配置了休眠宏但无法进入休眠) | 2.6 |
| 34 | [GPIO 唤醒如何配置？支持哪些引脚？](#q3-gpio-唤醒如何配置支持哪些引脚) | 2.6 |
| 35 | [TS800X 支持 RTC 唤醒吗？](#q4-ts800x-支持-rtc-唤醒吗) | 2.6 |
| 36 | [唤醒后程序死机 / HardFault？](#q5-唤醒后程序死机hardfault) | 2.6 |
| 37 | [唤醒后 UART 无输出 / HAL 延时异常？](#q6-唤醒后-uart-无输出--hal-延时异常) | 2.6 |
| 38 | [休眠电流太大怎么优化？](#q7-休眠电流太大怎么优化) | 2.6 |
| 39 | [BLE 连接在休眠中被断开？](#q8-ble-连接在休眠中被断开) | 2.6 |
| 40 | [广播间隔超过 2 秒？](#q9-广播间隔超过-2-秒如何配置) | 2.6 |
| 41 | [连接间隔低于 50ms 无法进入休眠？](#q10-连接间隔低于-50ms-无法进入休眠) | 2.6 |
| 42 | [休眠时改变连接间隔会导致系统复位？](#q11-休眠时改变连接间隔会导致系统复位) | 2.6 |
| 43 | [连接后不能在连接事件里面改变连接间隔？](#q12-连接后不能在连接事件里面改变连接间隔) | 2.6 |
| 44 | [BLE 共存时 ADC 有什么限制？](#q1-ble-共存时-adc-有什么特殊限制) | 2.7 |
| 45 | [ADC 采样值不准 / 漂移？](#q2-adc-采样值不准漂移) | 2.7 |
| 46 | [ADC 采样的最小代码模板？](#q3-adc-采样的最小代码模板) | 2.7 |
| 47 | [为什么 ADC 在启动时初始化会出问题？](#q4-为什么-adc-在系统启动时初始化会出问题) | 2.7 |
| 48 | [PWM 无波形输出怎么排查？](#q1-pwm-无波形输出怎么排查) | 2.8 |
| 49 | [PWM 频率 / 占空比如何计算？](#q2-pwm-频率占空比如何计算) | 2.8 |
| 50 | [修改占空比后频率也变了？](#q3-修改占空比后频率也变了) | 2.8 |
| 51 | [互补输出通道没有信号？](#q4-互补输出通道没有信号) | 2.8 |
| 52 | [GPIO0/GPIO1 功能异常？](#q5-gpio0gpio1-功能异常) | 2.8 |
| 53 | [PWM 分频器支持哪些值？](#q6-分频器支持哪些值) | 2.8 |
| 54 | [PWM 定时器能配 48MHz 吗？](#q7-pwm-定时器能配-48mhz-吗为什么只能用-24m) | 2.8 |
| 55 | [日志输出如何切换 RTT / UART？](#q1-uart-日志输出如何切换-rtt--uart) | 2.9 |
| 56 | [UART 波特率如何修改？](#q2-uart-波特率如何修改) | 2.9 |
| 57 | [I2C 通信失败怎么排查？](#q3-i2c-通信失败) | 2.9 |
| 58 | [SPI 应该用中断还是轮询？](#q4-spi-应该用中断还是轮询) | 2.9 |
| 59 | [TS800X Flash 如何读写？](#q1-ts800x-flash-如何读写) | 2.10 |
| 60 | [OTA 升级的流程是怎样的？](#q2-ota-升级的流程是怎样的) | 2.10 |
| 61 | [OTA 升级后无法启动应用？](#q3-ota-升级后无法启动应用) | 2.10 |
| 62 | [Flash 布局是怎样的？](#q4-flash-布局是怎样的) | 2.10 |
| 63 | [如何确认 Bootloader 已正确烧录？](#q5-如何确认-bootloader-已正确烧录) | 2.10 |
| 64 | [OTA 校验失败 / 流程中断？](#q6-ota-完整性校验失败--流程中断finish_ind-空指针) | 2.10 |
| 65 | [推荐用 RTT 还是 UART 输出日志？](#q1-推荐用-rtt-还是-uart-输出日志) | 2.11 |
| 66 | [HardFault 如何定位？](#q2-hardfault-如何定位) | 2.11 |
| 67 | [如何启用看门狗（WDT）？](#q3-如何启用看门狗wdt) | 2.11 |
| 68 | [Assert 框架如何使用？](#q4-assert-框架如何使用) | 2.11 |
| 69 | [如何查看 BLE 协议栈内部日志？](#q5-如何查看-ble-协议栈内部日志) | 2.11 |
| 70 | [TS800X 通过了哪些认证？](#q1-ts800x-通过了哪些认证) | 2.12 |
| 71 | [FCC 认证需要注意什么？](#q2-fcc-认证需要注意什么) | 2.12 |
| 72 | [TX Power 可调范围？](#q3-tx-power-可调范围是多少) | 2.12 |
| 73 | [谐波问题如何处理？](#q4-谐波问题如何处理) | 2.12 |
| 74 | [推荐使用什么晶振？](#q1-推荐使用什么晶振) | 2.13 |
| 75 | [32K 时钟校准的作用？](#q2-32k-时钟校准有什么作用) | 2.13 |
| 76 | [OTP 配置需要修改吗？](#q3-otp-配置是什么需要修改吗) | 2.13 |
| 77 | [bin2c 和 srec_cat 工具用途？](#q4-bin2c-和-srec_cat-工具用途) | 2.13 |
| 78 | [J-Link RTT 如何查看日志？](#q5-j-link-rtt-如何查看日志) | 2.13 |
| 79 | [GPIO0/GPIO1 无法调试？](#q6-使用-gpio0gpio1-后无法调试怎么办) | 2.13 |
| 80 | [有哪些项目模板可用？](#q7-有哪些项目模板可用) | 2.13 |
| 81 | [各 BLE 例程分别实现什么功能？](#q8-各-ble-例程分别实现什么功能) | 2.13 |
| 82 | [如何检测 BLE 是否因环境干扰而卡死？](#q6-如何检测-ble-是否因环境干扰而卡死) | 2.11 |
| 83 | [GPIO2 能用作 PWM 输出吗？](#q8-gpio2-能用作-pwm-输出吗) | 2.8 |

---

## 1 软件开发重点建议（必看）

> **本章为 SDK 开发中必须遵守的核心规则。违反将导致不可预期的异常，请务必在开发前阅读。**

| # | 问题 |
|---|------|
| Q1 | [外设初始化必须在 tsBle_Init 之后](#q1-外设初始化必须在-tsble_init-之后) |
| Q2 | [连接参数变更时禁止进入休眠](#q2-连接参数变更时禁止进入休眠) |

### Q1: 外设初始化必须在 tsBle_Init 之后

**规则**：所有外设（UART、ADC、PWM、I2C、SPI、GPIO 等）的初始化必须在 `tsBle_Init()` 调用完成之后执行。

**原因**：`tsBle_Init()` 内部会初始化 BLE 协议栈、射频时钟和系统电源管理模块。若外设在蓝牙初始化之前配置，其寄存器状态可能被协议栈初始化覆盖，导致外设工作异常或系统 HardFault。

**正确做法**：

```c
// main() 或系统初始化流程

// ① 系统时钟初始化（必须最先）
SystemClock_Init();

// ② BLE 协议栈初始化（在外设之前）
tsBle_Init();

// ③ 外设初始化（必须在 tsBle_Init 之后）
TS_LOG_INIT();             // 日志 UART
ts800x_HAL_UART_Init(...);  // 业务 UART
ts800x_LL_Adc_Init(&cfg);   // ADC
// 其他外设...
```

**常见错误**：将 UART 日志初始化放在 `tsBle_Init()` 之前，导致日志无输出或死机。

### Q2: 连接参数变更时禁止进入休眠

**规则**：调用 `tsBleSlave_Set_ConnInterval()` 修改连接参数时，芯片必须处于唤醒状态，禁止在休眠期间执行。

**原因**：休眠期间调用 `tsBleSlave_Set_ConnInterval()` 会触发协议栈内部状态冲突，导致系统复位。

**正确做法**：

```c
// 在 DEVEVT_CONNECTED 事件中修改（此时芯片处于唤醒状态）
case DEVEVT_CONNECTED:
    tsBleSlave_Set_ConnInterval(40, 48, 0, 500);
    TS800X_SLEEP_FLAG_SET();
    break;

// 或在主循环中通过标志位异步处理（确保修改时未休眠）
if (g_request_conn_update && !ts800x_Is_Sleeping()) {
    tsBleSlave_Set_ConnInterval(40, 48, 0, 500);
    g_request_conn_update = 0;
}
```

**常见错误**：休眠中检测到连接参数不匹配后直接调用 `tsBleSlave_Set_ConnInterval()`，导致复位。

> 详见 [2.6 Q11: 休眠时改变连接间隔会导致系统复位？](#q11-休眠时改变连接间隔会导致系统复位)

---

## 2 常见问题解答

### 2.1 开发环境

| # | 问题 |
|---|------|
| Q1 | [J-Link 报 "No Algorithm found"？](#q2-首次烧录时-j-link-报-no-algorithm-found-或下载失败) |
| Q2 | [编译时头文件找不到？](#q3-编译时提示-no-such-file-or-directory-或头文件找不到) |
| Q3 | [undefined symbol？](#q4-编译时提示大量-undefined-symbol--unresolved-external) |
| Q4 | [flash loader cannot be loaded？](#q5-编译后烧录提示-the-flash-loader-cannot-be-loaded) |
| Q5 | [支持 GCC / 其他 IDE？](#q6-sdk-是否支持-gcc--其他-ide) |

#### Q1: 首次烧录时 J-Link 报 "No Algorithm found" 或下载失败？

**推荐方式**：在终端运行优化脚本，自动配置 J-Link：

```powershell
powershell -File tools\keil_jlink_optimize.ps1
```

**手动方式**：Keil → Options for Target → Debug → J-Link Settings → Misc → Script File 填入 `TS800x.jlinkscript` 完整路径；Flash Download 页添加 `TS800x_256K_flash_prog.FLM`。

#### Q2: 编译时提示 "No such file or directory" 或头文件找不到？

检查 Keil 的 Include Paths（Options for Target → C/C++），确保包含：
- `soc/m0` / `soc/ts800x`
- `modules/drv` / `modules/ble` / `modules/ble/v0_2_0`
- `modules/debug`
- 工程自身的 `include/`

#### Q3: 编译时提示大量 undefined symbol / unresolved external？

缺少库文件，需加入工程：

| 工程类型 | 需要的库文件 |
|---------|-------------|
| BLE 工程 | `soc/ts800x/lib/ts800x_lib.lib` |
| 2.4G 工程 | `soc/ts800x/lib/ts800x_2G4_lib.lib` |
| BLE 协议栈（标准） | `modules/ble/v0_2_0/lib/ts_ble_stack.a` |
| BLE 协议栈（Slave Latency） | `modules/ble/v0_2_0/lib/ts_ble_stack_latency.a` |

#### Q4: 编译后烧录，提示 "The flash loader cannot be loaded"？

- J-Link 驱动版本过低 → 升级至 V6.80+
- FLM 文件路径含中文/空格 → 移至纯英文路径
- 目标芯片未选为 TS8001

#### Q5: SDK 是否支持 GCC / 其他 IDE？

当前仅支持 Keil MDK。GCC 用户需自行编写链接脚本并移植启动文件。

---

### 2.2 BLE 基础

| # | 问题 |
|---|------|
| Q1 | [配置 BLE 角色？](#q1-如何配置-ble-角色从机主机多角色) |
| Q2 | [广播名搜不到？](#q2-修改了广播名称但手机上搜不到或仍显示旧名称) |
| Q3 | [广播和连接间隔？](#q3-ble-从机如何设置广播间隔和连接间隔) |
| Q4 | [自定义 GATT Service？](#q4-如何注册自定义-gatt-service) |
| Q5 | [发送 Notify？](#q5-ble-从机如何向主机发送数据notify) |
| Q6 | [同时连接数？](#q6-ble-可以同时连接多少个设备) |
| Q7 | [MTU 和吞吐量？](#q7-ble-最大-mtu-和吞吐量是多少) |
| Q8 | [连接后自动断开？](#q8-ble-从机连接后自动断开) |
| Q9 | [串口透传？](#q9-如何实现-ble-串口透传) |
| Q10 | [广播数据只有 31 字节？](#q10-ble-广播数据只有-31-字节如何扩展) |
| Q11 | [上电到第一个广播要多久？](#q11-ts8001-从机上电到发出第一个广播需要多长时间) |

#### Q1: 如何配置 BLE 角色（从机/主机/多角色）？

在 `cfg_def_ble.h` 中设置：

```c
#define BLE_CFG_ROLE_TYPE (TS_BLE_ROLE_SLAVE)                       // 仅从机
#define BLE_CFG_ROLE_TYPE (TS_BLE_ROLE_MASTER)                      // 仅主机
#define BLE_CFG_ROLE_TYPE (TS_BLE_ROLE_SLAVE | TS_BLE_ROLE_MASTER)  // 多角色
```

#### Q2: 修改了广播名称但手机上搜不到或仍显示旧名称？

1. `cfg_def_ble.h` → `BLE_DEVICE_NAME`（建议 ASCII，注意广播包长度限制）
2. 手机蓝牙设置中"忽略此设备"后重新搜索（清除缓存）
3. 确认 `tsBleSlave_Set_AdvEnable(true)` 已调用

#### Q3: BLE 从机如何设置广播间隔和连接间隔？

```c
// 广播间隔（0.625ms/单位，范围 0x20~0x4000）
#define DFT_ADV_INT_MIN  0xA0   // 100ms

// 连接间隔（1.25ms/单位，范围 0x06~0x0C80）
#define DFT_CONN_INT_MIN  0x06   // 7.5ms
#define DFT_CONN_INT_MAX  0x0C   // 15ms
#define DFT_CONN_TIMEOUT  0x3E8  // 10s

// 运行时动态修改连接间隔
tsBleSlave_Set_ConnInterval(12, 16, 0, 500); // 15~20ms
```

#### Q4: 如何注册自定义 GATT Service？

```c
static BLE_SVC_ts myService;
static BLE_CHAR_ts myChar;

myService.uuid = 0xFF00;
myService.charCnt = 1;
tsBleSlave_Service_Register(&myService);

myChar.charUuid = 0xFF01;
myChar.charProp = CHAR_PROP_READ | CHAR_PROP_NOTIFY;
myChar.read_cb = my_read_callback;
tsBleSlave_Char_Register(&myService, &myChar);
```

#### Q5: BLE 从机如何向主机发送数据（Notify）？

前提：主机已订阅 CCCD。

```c
uint8_t data[] = {0x01, 0x02, 0x03};
userSimpleProfile_Notify(0xFF02, data, sizeof(data));
```

#### Q6: BLE 可以同时连接多少个设备？

| 模式 | 连接能力 |
|------|---------|
| 从机 | 1 个主机 |
| 主机 | 多个从机（由 `BLE_SLAVE_NUM_MAX` 决定） |
| 多角色 | `ble_mult_role_m1s1`（1主1从）/ `ble_mult_role_m2s3`（2主3从），时分复用 |

#### Q7: BLE 最大 MTU 和吞吐量是多少？

- 默认 MTU = 23 字节（BLE 4.x）
- 可通过 `tsBle_ExchangeMtuReq()` 协商更大 MTU
- 实际吞吐量取决于连接间隔 × MTU × 物理层速率

#### Q8: BLE 从机连接后自动断开？

| 原因 | 解决 |
|------|------|
| 连接超时 | 检查 `DFT_CONN_TIMEOUT`，确保 `tsBle_Loop()` 有规律调用 |
| 休眠期间 BLE 事件处理不及时 | 确保连接间隔远小于超时时间 |
| 晶振频偏 | 换用推荐型号晶振 |
| TX Power 不当 | 调整 `tsBle_Set_TxPower(-25~12)` |

#### Q9: 如何实现 BLE 串口透传？

参考 `ble_uart_transmit` 例程：
1. UART 接收 → 存入发送缓冲
2. BLE Notify 发送至主机
3. 主机下发 → GATT Write 回调 → UART 发出
4. 注意 UART 与 BLE 的速率匹配

#### Q10: BLE 广播数据只有 31 字节，如何扩展？

BLE 广播包有效载荷固定 31 字节，这是 BLE 规范限制，无法绕过。扩展方式：

| 方式 | 说明 |
|------|------|
| Scan Response | 额外 31 字节，主机主动扫描时返回（被动扫描不返回） |
| 缩减广播名 | 缩短 `BLE_DEVICE_NAME` 腾出空间 |
| 裁剪 AD 结构 | TX Power、Connection Interval Range 等可按需移除 |
| GATT 承载 | 连接建立后通过 Characteristic Read/Notify 传输完整信息 |

#### Q11: TS8001 从机上电到发出第一个广播需要多长时间？

**400 ms ~ 500 ms**。这是协议栈 / ROM 启动的**固定开销，与应用程序无关**——不受应用
初始化顺序、任务调度或业务逻辑影响，也**无法通过改写应用代码缩短**。

| 项 | 说明 |
|----|------|
| 实测区间 | 上电（复位释放）→ 第一个广播包发出：**400~500 ms** |
| 构成 | 晶振起振 + 协议栈初始化 + ROM 启动等固定流程 |
| 与程序的关系 | **无关**。不要试图用代码优化它，也不要因此改动初始化时序或休眠策略 |
| 测试注意 | 上电广播验收的等待窗口应 **≥ 500 ms**（建议留 600~1000 ms 余量），否则会把正常启动误判为"广播失败" |

> 若明显超出该区间（例如 >1 s 仍无广播），属于异常，应按 2.11 的日志手段排查供电、
> 晶振与复位原因，而不是当作"启动慢"接受。

---

### 2.3 BLE 配对

| # | 问题 |
|---|------|
| Q1 | [启用配对/加密？](#q1-如何启用-ble-配对加密) |
| Q2 | [Passkey 配对失败？](#q2-配对失败passkey-模式怎么排查) |
| Q3 | [断连需要重新配对？](#q3-配对成功但断连后需要重新配对) |

#### Q1: 如何启用 BLE 配对/加密？

```c
#define CONFIG_BT_SMP  1   // 启用 SMP 安全管理
```

`BLE_CFG_HID_METHOD` 设置配对方式：
- `0` → Just Works（自动配对，无需密码）
- `2` → Passkey（串口打印 6 位密钥，手机端输入）

#### Q2: 配对失败（Passkey 模式）怎么排查？

1. 确认 `CONFIG_BT_SMP = 1` 且 `BLE_CFG_HID_METHOD = 2`
2. 串口应打印 6 位 Passkey
3. 手机端输入该密钥
4. 若无配对弹窗 → 系统蓝牙设置中"忽略此设备"后重连

#### Q3: 配对成功但断连后需要重新配对？

确认 `bt_storage_kv.c` 管理的绑定数据未被覆盖或擦除。若 Flash 存储区被意外擦除，绑定信息会丢失。

---

### 2.4 BLE 进阶

| # | 问题 |
|---|------|
| Q1 | [iPhone 来电提醒？](#q1-ts800x-能实现-iphone-来电提醒吗) |
| Q2 | [ANCS 收不到通知？](#q2-ancs-来电提醒总是收不到通知) |
| Q3 | [HID 键盘？](#q3-如何实现-hid-键盘) |
| Q4 | [BLE+2.4G 共存？](#q4-ble-和-24g-私有协议能同时使用吗) |
| Q5 | [多角色限制？](#q5-ble-多角色模式的限制是什么) |
| Q6 | [2M / S2 / S8 速率？](#q6-如何申请-2m-或-s2s8-长距离速率) |

#### Q1: TS800X 能实现 iPhone 来电提醒吗？

**仅限 iPhone**（依赖苹果 ANCS 服务，Android 无对等功能）。参考 `examples/ble/ble_hid_callalert`。

流程：BLE Peripheral 连接 iPhone → HID Keyboard GATT → 配对加密 → 发现并订阅 ANCS Notification Source → 来电（Category ID=1）时驱动 GPIO 闪灯。

详见 `examples/ble/ble_hid_callalert/readme.md`。

#### Q2: ANCS 来电提醒总是收不到通知？

按顺序排查：
1. 必须是 iPhone（Android 不支持 ANCS）
2. 配对与加密已完成
3. iPhone 设置 → 蓝牙 → 已连接设备 → 开启"通知"
4. `CONFIG_BT_SMP = 1` 已启用
5. 用另一部手机拨打测试（本机拨号行为可能不一致）

#### Q3: 如何实现 HID 键盘？

参考 `examples/ble/ble_hid_slave`。`cfg_def_ble.h` 中注册 HID Service（UUID 0x1812），配置 Report Map，通过 HID Report Characteristic 发送按键事件。

#### Q4: BLE 和 2.4G 私有协议能同时使用吗？

可以，参考 `examples/ble/ble_loopback_24G`。

- 使用 `modules/2g4/ts_2g4.h`（共存 API），非 `ts800x_single_2g4.h`
- BLE 优先级更高，2.4G 在 BLE 空闲时隙工作
- 2.4G 延迟可能增加

#### Q5: BLE 多角色模式的限制是什么？

单射频链路时分复用。连接数越多，每连接可用时间越少。实时性要求高时减少活跃连接数。Slave Latency 可减轻调度压力。

#### Q6: 如何申请 2M 或 S2/S8 长距离速率？

BLE 5.0 支持三种 PHY：**1M**（默认）、**2M**（高速率）、**Coded**（长距离，分
**S2** 与 **S8** 两种编码方案；S8 距离最远、速率最低，S2 居中）。速率切换在
**连接建立之后**通过 `bt_conn_le_phy_update()` 申请，接口声明在
`modules/ble/v0_2_0/host/conn.h`。

**参数结构**（`struct bt_conn_le_phy_param`）：

| 字段 | 取值 |
|------|------|
| `pref_tx_phy` / `pref_rx_phy` | `BT_GAP_LE_PHY_1M` / `BT_GAP_LE_PHY_2M` / `BT_GAP_LE_PHY_CODED` |
| `options` | `BT_CONN_LE_PHY_OPT_NONE`（1M/2M）；`BT_CONN_LE_PHY_OPT_CODED_S2` 或 `BT_CONN_LE_PHY_OPT_CODED_S8`（Coded） |

**申请示例**（参考 `examples/ble/ble_single_master/source/user_master.c` 的
`userMaster_PHY_UpdateReq()`）：

```c
struct bt_conn_le_phy_param phy_param = {0};

/* S8：长距离（最远、最低速率） */
phy_param.options     = BT_CONN_LE_PHY_OPT_CODED_S8;
phy_param.pref_tx_phy = BT_GAP_LE_PHY_CODED;
phy_param.pref_rx_phy = BT_GAP_LE_PHY_CODED;

/* S2：长距离（折中） */
/* phy_param.options = BT_CONN_LE_PHY_OPT_CODED_S2;
   phy_param.pref_tx_phy = BT_GAP_LE_PHY_CODED;
   phy_param.pref_rx_phy = BT_GAP_LE_PHY_CODED; */

/* 2M：高速率（大吞吐，如 OTA/透传） */
/* phy_param.options = BT_CONN_LE_PHY_OPT_NONE;
   phy_param.pref_tx_phy = BT_GAP_LE_PHY_2M;
   phy_param.pref_rx_phy = BT_GAP_LE_PHY_2M; */

bool ret = bt_conn_le_phy_update((BLE_CONN_ts *)conn_handle, &phy_param);
LOG_I("phy change res: %d", ret);
```

**要点**：

- 只能在**连接后**申请（未连接/广播阶段无效）；需链路两端都支持目标 PHY，最终以
  双方协商结果为准，申请可能被对端拒绝。
- 结果以 GAP 事件 `BLE_GAP_PHY_UPDATED_ts`（`phy_updated.txPhy` / `rxPhy`）确认，
  不要只看接口返回值。
- 便捷宏：`BT_CONN_LE_PHY_PARAM_1M` / `_2M` / `_CODED` / `_ALL`（`_ALL` 表示
  "1M/2M/Coded 均可"）。
- 取舍：**2M** 适合大吞吐（OTA、透传）；**S8** 适合远距/穿墙但速率最低；
  **S2** 居中。切换 PHY 会短暂影响连接稳定性，避免高频切换。
- 返回值类型与错误码以本地 SDK `conn.h` 声明为准（不同版本可能是 `int` 或 `bool`）。

---

### 2.5 2.4G 协议

| # | 问题 |
|---|------|
| Q1 | [初始化和配置？](#q1-24g-如何初始化和配置) |
| Q2 | [通信距离优化？](#q2-24g-通信距离短怎么优化) |
| Q3 | [数据格式配置？](#q3-24g-数据格式如何配置msblsbwhitening) |
| Q4 | [各例程用途？](#q4-24g-例程之间如何对应) |
| Q5 | [与 BLE 休眠区别？](#q5-24g-协议休眠与-ble-休眠有何不同) |

#### Q1: 2.4G 如何初始化和配置？

```c
ts2G4_Coe_Init();                        // 初始化
ts2G4_Coe_TxData(tx_buf, len, 0, 0);    // 发送
ts2G4_Coe_RxData(rx_buf, len);          // 接收
```

参考 `examples/2G4/` 下各例程。

#### Q2: 2.4G 通信距离短怎么优化？

| 方法 | 说明 |
|------|------|
| 降低数据速率 | 使用 62.5kbps 模式（`2g4_tx_rx_slp_62k`） |
| 增加 TX Power | 调整发送功率 |
| 天线匹配 | 检查阻抗匹配和布局 |
| 避开干扰 | 避开 WiFi 密集信道 |

#### Q3: 2.4G 数据格式如何配置（MSB/LSB、Whitening）？

在 `ts_2g4_def.h` 或初始化参数中配置：位序（MSB/LSB first）、Whitening 白化、Preamble 长度、Sync Word、CRC 校验。

#### Q4: 2.4G 例程之间如何对应？

| 例程 | 功能 |
|------|------|
| `2g4_tx_rx_slp` | 标准速率收发 + 低功耗 |
| `2g4_tx_rx_slp_62k` | 62.5kbps 长距离收发 |
| `2g4_adv_slp` | 广播 + ADC + 低功耗 |
| `2g4_remote` | 遥控器（按键扫描 + 收发） |
| `2g4_xfer_long_range` | 长距离数据传输 |

#### Q5: 2.4G 协议休眠与 BLE 休眠有何不同？

- 直接调用 `_TS800X_InternalSleep()`，无 BLE 协议栈协商
- 需手动管理 Flash VDDIO 掉电/上电（休眠漏电）
- 唤醒后需手动恢复 QSPI GPIO 功能（`qspi_regs_restore()`）
- 仅依赖 GPIO 电平或 VTimer 唤醒，无 BLE 事件唤醒

---

### 2.6 低功耗休眠

| # | 问题 |
|---|------|
| Q1 | [启用深度休眠？](#q1-如何启用深度休眠) |
| Q2 | [无法进入休眠？](#q2-已经配置了休眠宏但无法进入休眠) |
| Q3 | [GPIO 唤醒配置？](#q3-gpio-唤醒如何配置支持哪些引脚) |
| Q4 | [支持 RTC 唤醒？](#q4-ts800x-支持-rtc-唤醒吗) |
| Q5 | [唤醒后 HardFault？](#q5-唤醒后程序死机hardfault) |
| Q6 | [唤醒后 UART 无输出？](#q6-唤醒后-uart-无输出--hal-延时异常) |
| Q7 | [休眠电流优化？](#q7-休眠电流太大怎么优化) |
| Q8 | [休眠中 BLE 断连？](#q8-ble-连接在休眠中被断开) |
| Q9 | [广播间隔超过 2 秒？](#q9-广播间隔超过-2-秒如何配置) |
| Q10 | [连接间隔 <50ms 无法休眠？](#q10-连接间隔低于-50ms-无法进入休眠) |
| Q11 | [休眠改连接间隔复位？](#q11-休眠时改变连接间隔会导致系统复位) |
| Q12 | [连接事件内改连接间隔？](#q12-连接后不能在连接事件里面改变连接间隔) |

#### Q1: 如何启用深度休眠？

在 `cfg_def_app.h` 中：

```c
#define TS_EN_DEEP_SLEEP     // 必须
#define TS_SAVE_UART0_REGS   // 推荐：休眠时保存 UART 寄存器
#define TS_EN_CLK_CAL        // 推荐：RC32K 时钟校准，提高定时精度
```

主循环中调用 `TS800X_SLEEP_CHECK()` 和 `apps_SleepWakeup()`。

#### Q2: 已经配置了休眠宏但无法进入休眠？

- `TS800X_SLEEP_FLAG_SET()` 未调用（需在 `DEVEVT_READY` 中调用）
- BLE 连接间隔 < 50ms
- GPIO 误触发唤醒（检查唤醒电平是否稳定）

#### Q3: GPIO 唤醒如何配置？支持哪些引脚？

**仅支持电平唤醒，不支持边沿唤醒**。

```c
#define TS_GPIO_WAKEUP_MASK    0      // 高电平唤醒 GPIO 掩码
#define TS_GPIO_nWAKEUP_MASK   0x4    // 低电平唤醒（0x4 = GPIO2）
```

- 同一 GPIO 不能同时设为高、低电平唤醒
- 唤醒 GPIO 须为输入模式 + 上下拉
- 按键低电平 → 输入上拉 + `TS_GPIO_nWAKEUP_MASK`
- 按键高电平 → 输入下拉 + `TS_GPIO_WAKEUP_MASK`

#### Q4: TS800X 支持 RTC 唤醒吗？

**不支持 RTC 中断唤醒**。定时唤醒替代方案：

| 方式 | 宏 | 场景 |
|------|---|------|
| BLE 事件唤醒 | `TS_EN_SLEEP_TMR_CHK` + `USER_DEF_SLEEP_ELPS` | BLE 保持运行时 |
| VTimer 唤醒 | `USER_SLEEP_BLE_OFF` + `USER_DEF_SLEEP_ELPS` | BLE 完全关闭时 |

#### Q5: 唤醒后程序死机/HardFault？

最常见原因：**休眠相关代码未放入 RAM**。

以下函数须标记 `__RAM_CODE_SECTION`：
- `ts800x_Sleep_Check()` 及子函数
- `Bt_SleepMode_Check()` / `Timer_SleepMode_Check()`
- `VTIMER_ClkCali_Trigger()` / `VTIMER_ClkCali_Wait()`
- 用户自定义的 `user_Sleep_SubProcess()`、`app_calc_sec_tick()`

#### Q6: 唤醒后 UART 无输出 / HAL 延时异常？

深度休眠后外设寄存器丢失，唤醒后**必须重新初始化**：

```c
static inline void apps_SleepWakeup(void) {
    if (ts800x_Sleep_WakeupSource()) {
        ts800x_HAL_SysTick_Init(1);        // ① SysTick（HAL 延时依赖）
        TS_LOG_INIT();                      // ② 日志输出
        // user_peripheral_reinit();        // ③ 业务外设（I2C/SPI/ADC 等）
        TS800X_SLEEP_FLAG_CLR();
    }
}
```

建议同时开启 `TS_SAVE_UART0_REGS`。

#### Q7: 休眠电流太大怎么优化？

```c
#define TS_EN_UNUSED_GPIO
#define TS_WHEN_SLEEP_GPIO_MASK  (0x356000)   // 休眠时高阻
#define TS_UNUSED_GPIO_MASK      (0x8A9FFC)   // 永久高阻
```

- 不广播/不连接时 BLE 射频不工作，功耗进一步降低
- 2.4G 应用需手动控制 Flash VDDIO 掉电

#### Q8: BLE 连接在休眠中被断开？

协议栈会在连接事件前自动唤醒，通常不会因休眠断连。若出现：
1. 检查 `DFT_CONN_TIMEOUT`
2. 确保 `tsBle_Loop()` 在休眠期间及时执行
3. 检查晶振是否为推荐型号（频偏导致定时偏差）

#### Q9: 广播间隔超过 2 秒如何配置？

当从机广播间隔 ≥ 2 秒（`DFT_SLP_ADV_MIN_INTVL >= 3200`，单位 0.625ms）时，需在 BLE Ready 事件中增加预唤醒配置，确保芯片在广播事件前有足够时间恢复：

```c
case DEVEVT_READY:
    tsBleSlave_Set_AdvEnable(true);
    TS800X_SLEEP_FLAG_SET();
    if (DEF_SLP_ADV_MIN_INTVL >= 3200) {
        ts800x_Sleep_Set_Pre_Wakeup_Time(60);   // 预唤醒时间 60ms
        ts800x_Sleep_Update_Pre_Wakeup_Val(30);  // 更新预唤醒值 30ms
    }
    break;
```

否则可能因唤醒时序不够导致广播异常或无法被主机发现。

#### Q10: 连接间隔低于 50ms 无法进入休眠？

BLE 连接间隔 < 50ms 时，两次连接事件间隔太短，芯片唤醒后没有足够窗口完成休眠流程（时钟切换、Flash 掉电等）。将连接间隔设为 ≥ 50ms（即 ≥ 40，单位 1.25ms）即可进入休眠：

```c
#define DFT_CONN_INT_MIN  40   // 50ms
#define DFT_CONN_INT_MAX  48   // 60ms
```

#### Q11: 休眠时改变连接间隔会导致系统复位？

休眠期间调用 `tsBleSlave_Set_ConnInterval()` 修改连接参数会触发协议栈异常复位。连接间隔的修改必须在唤醒状态下完成，建议在 `DEVEVT_CONNECTED` 事件或主循环中确保芯片未休眠时执行。

#### Q12: 连接后不能在连接事件里面改变连接间隔？

BLE 协议要求连接参数更新请求在连接事件之外发起。在 GAP 事件回调中直接调用 `tsBleSlave_Set_ConnInterval()` 可能与当前连接事件冲突，导致参数更新被拒绝或异常。通过标志位异步处理：

```c
// GAP 回调中设置标志，不在回调内直接修改
g_request_conn_update = 1;

// 主循环中处理
if (g_request_conn_update) {
    tsBleSlave_Set_ConnInterval(40, 48, 0, 500);
    g_request_conn_update = 0;
}
```

---

### 2.7 ADC 采样

| # | 问题 |
|---|------|
| Q1 | [BLE 共存时限制？](#q1-ble-共存时-adc-有什么特殊限制) |
| Q2 | [采样值不准？](#q2-adc-采样值不准漂移) |
| Q3 | [最小代码模板？](#q3-adc-采样的最小代码模板) |
| Q4 | [启动初始化问题？](#q4-为什么-adc-在系统启动时初始化会出问题) |

#### Q1: BLE 共存时 ADC 有什么特殊限制？

**两条必须遵守的规则：**

1. 时钟分频必须为 `ADC_CLOCK_DIV8`（否则谐波干扰 2.4GHz BLE 射频）
2. 禁止调用 `ts800x_LL_Adc_LDOInit()`（仅 ADC 独立工作场景使用）

```c
ADC_init.Clk_Div = ADC_CLOCK_DIV8;   // BLE 共存时必须
```

#### Q2: ADC 采样值不准/漂移？

| 原因 | 解决 |
|------|------|
| 电池电压下降 | 每 32 次采样调用 `ts800x_LL_Adc_BatUpdate()` |
| 采样噪声 | 增加 `Avg_Value`（7 = 128 次平均） |
| 微弱信号 | 启用 PGA（`PGA_EN=ENABLE`, `GPA_Gain` 0~15） |
| BLE 中断干扰 | 采样放在临界区内执行 |

#### Q3: ADC 采样的最小代码模板？

```c
// 初始化（仅一次）
ADC_StartCalibration();
TS_LL_ADC_CTRL_INIT_ts cfg = { .Vin_Sel=ADC_CH_GPIO2, .Avg_Value=7,
    .Sample_Mode=ADC_MODE_SINGLE, .Trig_Mode=ADC_TRIG_SOFT,
    .Clk_Div=ADC_CLOCK_DIV8 };
ts800x_LL_Adc_Init(&cfg);
ts800x_LL_Adc_Cmd(ENABLE);

// 采样（放入临界区）
uint32_t sta = system_Enter_Critical();
if (ts800x_LL_Adc_Set_Busy(1)) {
    uint32_t mv = ts800x_LL_Adc_Get_Voltage_Poll();
    ts800x_LL_Adc_Set_Busy(0);
}
system_Exit_Critical(sta);
```

#### Q4: 为什么 ADC 在系统启动时初始化会出问题？

ADC 采用延迟初始化——首次需要采样时才初始化，避免与 BLE 协议栈初始化时序冲突。参考 `ble_loopback_adc`。

---

### 2.8 PWM 输出

| # | 问题 |
|---|------|
| Q1 | [无波形输出？](#q1-pwm-无波形输出怎么排查) |
| Q2 | [频率/占空比计算？](#q2-pwm-频率占空比如何计算) |
| Q3 | [改占空比频率变了？](#q3-修改占空比后频率也变了) |
| Q4 | [互补通道无信号？](#q4-互补输出通道没有信号) |
| Q5 | [GPIO0/1 异常？](#q5-gpio0gpio1-功能异常) |
| Q6 | [分频器可选值？](#q6-分频器支持哪些值) |
| Q7 | [定时器能配 48M？](#q7-pwm-定时器能配-48mhz-吗为什么只能用-24m) |
| Q8 | [GPIO2 能用作 PWM？](#q8-gpio2-能用作-pwm-输出吗) |

#### Q1: PWM 无波形输出怎么排查？

1. GPIO 复用功能设为 AF=7：`ts800x_LL_Gpio_Set_Func(PIN, 7)`
2. Timer 使能：`ts800x_LL_Timer_State_Set(TIMER, ENABLE)`
3. 检查 GPIO 是否冲突或不支持 PWM（GPIO0/1 为 SWD 引脚；**GPIO2 不支持 PWM，配置会导致系统复位**，见 Q8）
4. 互补输出需额外使能：`timer_pwm0n100_en = ENABLE`

#### Q2: PWM 频率/占空比如何计算？

```
TimerClock = 24MHz / Divider
PWM_PERIOD = TimerClock / TargetFreq
CCR = PWM_PERIOD × Duty / 100
LOAD_COUNT = PWM_PERIOD - CCR
```

约束：`LOAD_COUNT + CCR = PWM_PERIOD`，更新时必须同步改两个寄存器。

#### Q3: 修改占空比后频率也变了？

只改了 CCR，未同步修改 LOAD_COUNT。

```c
// 正确做法
uint16_t ccr = PWM_PERIOD * duty / 100;
ts800x_LL_Timer_Set_CCR(TIMER, ccr);
ts800x_LL_Timer_Set_LoadCount(TIMER, PWM_PERIOD - ccr);  // 必须同步
```

#### Q4: 互补输出通道没有信号？

| 通道 | 主输出 | 互补输出 |
|------|--------|---------|
| TIMER0 | GPIO0 (PWM0) | GPIO8 (PWM0_N) |
| TIMER6 | GPIO20 (PWM6) | GPIO21 (PWM6_N) |

- 两路 GPIO AF 都设为 7
- `timer_pwm0n100_en = ENABLE`
- GPIO0~GPIO7 **不支持**互补输出

#### Q5: GPIO0/GPIO1 功能异常？

GPIO0(SWCLK) 和 GPIO1(SWDIO) 默认为 SWD 调试引脚。切换为 GPIO 后将无法 SWD 调试。

#### Q6: 分频器支持哪些值？

2, 4, 8, 16, 32, 64, 128, 256, 512, 1024, 2048, 4096（时钟源 24MHz）。

#### Q7: PWM 定时器能配 48MHz 吗？为什么只能用 24M？

TS800X 定时器时钟源为 **24MHz**（系统主频），不支持 48MHz 输入。分频器 `ts800x_LL_Timer_Set_Divider()` 作用于 24MHz：

```
TimerClock = 24MHz / Divider
```

若需更高精度 PWM，可调小分频系数（最小 2），此时定时器时钟 = 12MHz。

#### Q8: GPIO2 能用作 PWM 输出吗？

**不能，且会导致系统复位。** GPIO2 没有复用到任何定时器 PWM 通道，把 GPIO2 配置为
PWM（如 `ts800x_LL_Gpio_Set_Func(GPIO2, 7)` 并启动对应定时器）会引起系统复位，
而不是简单的"无波形"。

- 需要 PWM 时请改用支持 PWM 的引脚（参考 Q4 互补输出表与目标 SDK 的 pinmux 表）。
- GPIO2 可正常用作其他功能，如 ADC 采样通道（`ADC_CH_GPIO2`）和低功耗唤醒
  （`TS_GPIO_nWAKEUP_MASK = 0x4`）。
- 出现**不明原因系统复位**且代码中有 GPIO2 的 PWM 配置时，优先怀疑本条目。
- 排查"PWM 无波形"时若使用的是 GPIO2，直接换引脚，不要再查定时器配置。

---

### 2.9 串行外设

| # | 问题 |
|---|------|
| Q1 | [RTT / UART 切换？](#q1-uart-日志输出如何切换-rtt--uart) |
| Q2 | [波特率修改？](#q2-uart-波特率如何修改) |
| Q3 | [I2C 通信失败？](#q3-i2c-通信失败) |
| Q4 | [SPI 中断/轮询？](#q4-spi-应该用中断还是轮询) |

#### Q1: UART 日志输出如何切换 RTT / UART？

```c
#define APP_CFG_DBG_LOG
#define LOG_RTT            // RTT：J-Link 输出，无引脚占用，推荐调试用
// #define LOG_UART        // UART：物理串口，不需 J-Link，适合现场调试
```

#### Q2: UART 波特率如何修改？

```c
ts800x_HAL_UART_Init(UART0, 921600);  // 默认 921600
```

常用值：9600 ~ 921600。

#### Q3: I2C 通信失败？

1. 确认主从机地址匹配
2. 外接上拉电阻（必须）
3. 检查 GPIO AF 值
4. 降低通信速率

#### Q4: SPI 应该用中断还是轮询？

| 模式 | 适用场景 |
|------|---------|
| 轮询 | 数据量小、CPU 占用不敏感 |
| 中断 | 数据量大、需后台传输 |

SDK 提供 4 个例程：`spi_master_polling`、`spi_master_it`、`spi_slave_polling`、`spi_slave_it`。

---

### 2.10 Flash & OTA

| # | 问题 |
|---|------|
| Q1 | [Flash 读写？](#q1-ts800x-flash-如何读写) |
| Q2 | [OTA 流程？](#q2-ota-升级的流程是怎样的) |
| Q3 | [OTA 后无法启动？](#q3-ota-升级后无法启动应用) |
| Q4 | [Flash 布局？](#q4-flash-布局是怎样的) |
| Q5 | [Bootloader 确认？](#q5-如何确认-bootloader-已正确烧录) |
| Q6 | [OTA 校验失败 / 流程中断（finish_ind 空指针）？](#q6-ota-完整性校验失败--流程中断finish_ind-空指针) |

#### Q1: TS800X Flash 如何读写？

```c
ts800x_Flash_Read(addr, buf, len);             // 读
ts800x_Flash_Sector_Erase(addr);               // 扇区擦除（4KB，必须先擦后写）
ts800x_Flash_Write(addr, buf, len);            // 写
```

> 擦除耗时长，不可在中断/临界区内执行。总容量 256KB。

#### Q2: OTA 升级的流程是怎样的？

```
编译 Bootloader（boot_ts800x）→ 烧录至 0x10000000
编译应用固件（ble_ota_data_xfer）→ 烧录至 0x10002000
上电 → Bootloader 检查 OTA 标志
  ├─ 有新固件 → 擦除应用区 → 拷贝 → SHA256 校验 → 跳转
  └─ 无新固件 → 直接跳转应用
应用运行时通过 BLE 接收新固件 → 写入 Flash 尾部暂存区
```

#### Q3: OTA 升级后无法启动应用？

- SHA256 校验失败 → 重新执行 OTA
- 应用区地址与 Bootloader 跳转地址不一致
- Bootloader 未正确烧录至 Flash 起始地址

#### Q4: Flash 布局是怎样的？

| 区域 | 起始地址 | 大小 |
|------|---------|------|
| Bootloader | 0x10000000 | ~8KB |
| Application | 0x10002000 | ~240KB |
| OTA 暂存区 | Flash 尾部 | ~8KB |

#### Q5: 如何确认 Bootloader 已正确烧录？

上电后串口应有 Bootloader 版本和启动日志。如无输出，检查烧录地址和工具链配置。

#### Q6: OTA 完整性校验失败 / 流程中断（finish_ind 空指针）？

**现象**：OTA 走到完整性校验（`TS_FOTA_INTEGRITY_CHECK_REQ`）后，digest 校验结果错误、
返回失败（0x80），OTA 流程中断；部分芯片表现为写低地址异常或 HardFault。

**根因**：`examples/ble/ble_ota_data_xfer/source/fota_profile.c` 中 `struct ts_fota_param`
的 `finish_ind` 是**指针成员**，但全工程从未赋值；`fota_params` 为静态变量（零初始化）→
`finish_ind == NULL`。校验分支执行
`fota_params.finish_ind->integrity_checking_result = ...` 即向 NULL 解引用写数据 →
未定义行为，校验结果取到错误值。

**判断方法**：在目标工程搜索 `finish_ind`——若只有声明与解引用、**没有任何赋值**
（`= &...` 或 `= ...`），即命中本缺陷。

**修复**（二选一，应用层优先）：

```c
/* 方案一：改用局部变量（推荐，改动最小） */
bool integrity_ok = ts_fota_svc_digest_check();
uint8_t digest_check_status = integrity_ok ? 0 : 0x80;
```

```c
/* 方案二：成员改为内嵌值结构 */
struct ts_fota_finish_ind finish_ind;   /* 原：struct ts_fota_finish_ind *finish_ind; */
fota_params.finish_ind.integrity_checking_result = ts_fota_svc_digest_check();  /* -> 改 . */
```

> 影响范围：该示例在 SDK 1.4.0～1.6.x 及大量客户工程中被沿用。详细证据与排查顺序见
> `ts800x-sdk-bug-reference` 技能的「已确认缺陷」章节。

---

### 2.11 调试日志

| # | 问题 |
|---|------|
| Q1 | [RTT vs UART？](#q1-推荐用-rtt-还是-uart-输出日志) |
| Q2 | [HardFault 定位？](#q2-hardfault-如何定位) |
| Q3 | [看门狗启用？](#q3-如何启用看门狗wdt) |
| Q4 | [Assert 使用？](#q4-assert-框架如何使用) |
| Q5 | [BLE 内部日志？](#q5-如何查看-ble-协议栈内部日志) |
| Q6 | [BLE 环境干扰卡死检测？](#q6-如何检测-ble-是否因环境干扰而卡死) |

#### Q1: 推荐用 RTT 还是 UART 输出日志？

| 方式 | 优点 | 适用阶段 |
|------|------|---------|
| RTT | 速率高、不占引脚、J-Link 直连 | 开发调试 |
| UART | 无需 J-Link、普通串口工具即可 | 量产/现场 |

通过 `cfg_def_app.h` 中 `LOG_RTT` / `LOG_UART` 宏切换。

#### Q2: HardFault 如何定位？

1. 栈溢出（Cortex-M0+ 默认 1~2KB）→ 减少局部大数组或增大栈
2. 空指针/野指针 → 检查外设初始化顺序
3. 休眠代码在 Flash → 确保标记 `__RAM_CODE_SECTION`
4. J-Link 设断点在 `HardFault_Handler`，查 LR 和栈回溯

#### Q3: 如何启用看门狗（WDT）？

```c
#define TS_EN_WDG   // 启用
FEED_WTD(TS_FEED_WDG_TIME);   // 主循环喂狗，放 TS800X_SLEEP_CHECK 之前
```

#### Q4: Assert 框架如何使用？

```c
#include "assert.h"
ASSERT(ptr != NULL);
ASSERT(len <= MAX_BUF_SIZE);
```

仅调试阶段使用，量产固件建议关闭。

#### Q5: 如何查看 BLE 协议栈内部日志？

`cfg_def_app.h` 启用 `APP_CFG_DBG_LOG`，通过 `bt_log.h` 接口查看。日志级别参考 `modules/ble/bt_log.h`。

#### Q6: 如何检测 BLE 是否因环境干扰而卡死？

环境干扰（强电磁场、电源纹波、ESD 等）可能导致 BLE 基带定时器停振，BLE 协议栈卡死。可在主循环中加入 BLE 存活检测函数，发现异常后自动复位恢复：

```c
void task_check_ble_is_working(void)
{
    static uint32_t bb_timer_back = 0;
    static uint32_t ble_no_work   = 0;
    uint32_t        bb_timer      = GET_CUR_TICK_US();

    if (bb_timer == bb_timer_back) {
        ble_no_work++;
        if (ble_no_work > 30) {
            ble_no_work = 0;
            uart_printf("task_check_ble_is_working\r\n");
            user_delay_ms(100);
            REG_WRT(0x40000008, 1);   // 系统复位
            while (1);
        }
    } else {
        bb_timer_back = bb_timer;
        ble_no_work   = 0;
    }
}
```

**原理**：`GET_CUR_TICK_US()` 读取 BLE 基带定时器。若连续 30 次检测到该定时器值未变化，说明 BLE 已停振，触发系统复位。

**调用位置**：主循环中 `tsBle_Loop()` 之后：

```c
while (true) {
    tsBle_Loop();
    // ... 其他业务处理 ...
    task_check_ble_is_working();
}
```

> 注意：`GET_CUR_TICK_US()` 依赖 BLE 协议栈已初始化（`tsBle_Init()` 之后），不要在 BLE 初始化之前调用。检测阈值（30 次）可根据主循环速率调整。

**项目集成要点（JX122118，2026-09-14，[待硬件验证]）**：

本地 SDK 已确认具备条件，可直接落地：

| 项 | 结论 | 出处 |
|----|------|------|
| `GET_CUR_TICK_US()` 存在 | `REG_RD(0x42000104)`，读 BLE 基带定时器 | `soc/ts800x/system.h:207` |
| 复位方式与工程一致 | `REG_WRT(0x40000008, 1)`（同 `System_reset_Process`） | `working_process.c` |
| 集成位置 | `main.c` → `apps_Process()` 主循环，`tsBle_Loop()` 之后、`TS800X_SLEEP_CHECK()` 之前 | `main.c:90-107` |
| 日志输出 | 工程日志走 RTT，用 `LOG_I` 替代示例的 `uart_printf` | `cfg_def_app.h` |

```c
/* main.c: apps_Process() 内 */
while (true) {
    tsBle_Loop();
    main_processing_task();
    task_check_ble_is_working();   /* ← 新增：BLE 停振检测 */
    #ifdef TS_EN_DEEP_SLEEP
    TS800X_SLEEP_CHECK();
    apps_SleepWakeup();
    #endif
}
```

**两个本项目特有的注意点（集成时必须处理，否则会误复位）**：

1. **深睡/浅睡期间基带定时器会停走**——`bb_timer` 不变会被误判为卡死。计数前先确认唤醒状态（参考 `apps_SleepWakeup()` 的唤醒判定），或在 `tRopeSkp.power_on == true` 且非睡眠挂起时才累计。
2. **2.4G 与 BLE 共存场景**（`TS_BLE_2G4_COEXIST`）：2.4G 收发占射频时 BLE 基带定时器是否停走未实测；若跳绳中（2.4G 持续收发）出现误复位，将阈值放大或仅在非 2.4G 活跃期计数。

典型适用场景：**广播莫名消失、扫描/连接突然全部失败、OTA 中途 ACK 全 NAK**——先加本检测确认是"BLE 停振"还是"射频环境丢包"，二者处理方向完全不同（前者复位恢复，后者查干扰源/距离）。

---

### 2.12 EMC 认证

| # | 问题 |
|---|------|
| Q1 | [通过了哪些认证？](#q1-ts800x-通过了哪些认证) |
| Q2 | [FCC 注意事项？](#q2-fcc-认证需要注意什么) |
| Q3 | [TX Power 范围？](#q3-tx-power-可调范围是多少) |
| Q4 | [谐波处理？](#q4-谐波问题如何处理) |

#### Q1: TS800X 通过了哪些认证？

SRRC（中国）、BQB（蓝牙）、FCC（美国）、RFPHY（蓝牙射频）、KC（韩国）。

#### Q2: FCC 认证需要注意什么？

| 措施 | 效果 |
|------|------|
| TX Power ≤ -6dBm | 降低谐波能量集中（PRBS9 不支持，仅 1010 pattern） |
| 天线位置优化 | 减少谐波发射 |
| 底层覆铜 | 改善接地 |
| LC 匹配滤波 | 天线端阻抗匹配 |

#### Q3: TX Power 可调范围是多少？

```c
tsBle_Set_TxPower(txPower);  // -25 ~ 12 dBm
```

认证测试时降低功率，实际应用按通信距离需求调节。

#### Q4: 谐波问题如何处理？

1. 降低 TX Power（最直接）
2. 优化天线匹配电路
3. 改善 PCB 接地
4. 增加谐波滤波器

---

### 2.13 硬件工具

| Q1 | [推荐晶振？](#q1-推荐使用什么晶振) |
| Q2 | [32K 时钟校准？](#q2-32k-时钟校准有什么作用) |
| Q3 | [OTP 配置？](#q3-otp-配置是什么需要修改吗) |
| Q4 | [bin2c / srec_cat？](#q4-bin2c-和-srec_cat-工具用途) |
| Q5 | [J-Link RTT 使用？](#q5-j-link-rtt-如何查看日志) |
| Q6 | [GPIO0/1 无法调试？](#q6-使用-gpio0gpio1-后无法调试怎么办) |
| Q7 | [项目模板？](#q7-有哪些项目模板可用) |
| Q8 | [BLE 例程一览？](#q8-各-ble-例程分别实现什么功能) |

#### Q1: 推荐使用什么晶振？

24MHz 晶振**必须使用推荐型号**，否则导致 BLE 断连（频偏）、BT Timer 异常（0x14）、射频性能下降。

#### Q2: 32K 时钟校准有什么作用？

```c
#define TS_EN_CLK_CAL   // 校准 RC32K，提高 BLE 事件和 VTimer 定时精度
```

系统初始化时自动执行，低功耗应用建议始终启用。

#### Q3: OTP 配置是什么？需要修改吗？

OTP 存储芯片启动参数，默认配置一般不需要修改。仅产品固化/量产阶段可能需要调整。相关文件：`soc/ts800x/bin/TS8001_otp_*.bin`。

#### Q4: bin2c 和 srec_cat 工具用途？

| 工具 | 功能 |
|------|------|
| `bin2c.exe` | .bin → .c 数组（固件镜像嵌入代码） |
| `srec_cat.exe` | 固件格式转换（hex ↔ bin） |

主要用于 OTA 固件打包。

#### Q5: J-Link RTT 如何查看日志？

打开 J-Link RTT Viewer → 选择 J-Link 和目标芯片 → 连接即实时查看。

> RTT 通过 SWD 接口传输数据，不占用 UART 引脚。

#### Q6: 使用 GPIO0/GPIO1 后无法调试怎么办？

GPIO0(SWCLK) 和 GPIO1(SWDIO) 切换为 GPIO 后将丢失 SWD。解决方案：

1. 程序启动时加 2~3 秒延迟，留出连接 J-Link 的时间窗口
2. 按住复位 → 点击烧录 → 立即松开复位
3. 条件编译：调试版本不切换这两个引脚

#### Q7: 有哪些项目模板可用？

| 模板 | 路径 | 说明 |
|------|------|------|
| BLE 空模板 | `solutions/empty_ble_sln` | BLE 初始化、事件回调、主循环框架 |
| MCU 空模板 | `solutions/empty_mcu_sln` | 无 BLE 的纯 MCU 应用框架 |

#### Q8: 各 BLE 例程分别实现什么功能？

| 例程 | 功能 |
|------|------|
| `ble_loopback` | 从机数据回环 |
| `ble_loopback_auth` | 从机回环 + SMP 配对认证 |
| `ble_loopback_adc` | 从机 + ADC 采样 + Notify |
| `ble_loopback_24G` | BLE + 2.4G 共存 |
| `ble_hid_slave` | HID 键盘从机 |
| `ble_hid_callalert` | HID 键盘 + iPhone ANCS 来电提醒 |
| `ble_hid_2g4_rssi` | HID + 2.4G + RSSI |
| `ble_single_master` | 单主机扫描连接 |
| `ble_mult_maste_subscribe` | 多主机 GATT 订阅 |
| `ble_mult_role_m1s1` | 多角色：1主1从 |
| `ble_mult_role_m2s3` | 多角色：2主3从 |
| `ble_uart_cmd` | 串口命令控制 BLE |
| `ble_uart_transmit` | 串口透传 |
| `ble_lowpower` | 低功耗从机 |
| `ble_lp_wakeup` | 低功耗 GPIO 唤醒 |
| `ble_lp_wakeup_RTC` | 低功耗 + BLE 事件定时 + 日历 |
| `ble_lp_latency` | Slave Latency 低功耗优化 |
| `ble_ota_data_xfer` | OTA 固件传输 |
| `ble_phone_test` | 手机连接测试 |
| `ble_disc_ancs` | ANCS 服务反向发现 |

---

| 关联文档 | 路径 |
|---------|------|
| SDK 应用教程 | `SDK应用教程.md` |
| 版本发布说明 | `release_note.txt` |

*本文档基于 TS800X SDK V1.5.1 整理。如有新增问题请更新本文档。*
