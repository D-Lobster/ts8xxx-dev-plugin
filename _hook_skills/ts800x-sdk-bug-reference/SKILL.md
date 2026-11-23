---
name: ts800x-sdk-bug-reference
description: Check legacy candidate TS800X SDK defects against the target SDK version and reproducible evidence. Use for SDK 已知问题、BLE/低功耗/2.4G/UART/RF 异常、例程缺陷、广播消失、断连或 timing 问题; never treat the legacy list as confirmed without current-version proof.
---

# TS800X SDK 缺陷候选库

此清单来自历史项目笔记，没有随 Skill 提供原始缺陷表、SDK 提交、工单号或复现工程，因此所有条目默认是 **LEGACY_UNVERIFIED**。它只能生成排查假设，不能直接证明 SDK 有缺陷，也不能授权修改 SDK。

## 使用流程

1. 记录芯片型号、板卡、目标 SDK 版本/提交、编译优化、关键宏和最小复现步骤。
2. 在当前 SDK 源码、发布说明、用户提供的缺陷表和例程中查证。
3. 先排除应用配置、硬件、电源、时钟、竞态、缓冲区和测试端问题。
4. 用 A/B 固件或最小复现确认，记录日志、时间条件和复现率。
5. 将结论分类为：
   - `CONFIRMED_CURRENT`：当前版本可复现且证据指向 SDK；
   - `FIXED_OR_INAPPLICABLE`：版本已修复或条件不适用；
   - `APPLICATION_CAUSE`：根因在应用/配置/硬件；
   - `LEGACY_UNVERIFIED`：仍缺证据。
6. 工作区的 `ts800x_sdk/` 保持只读；需要供应商补丁或 SDK 改动时先停下并报告。

## 历史候选项

以下只是检索关键词，不附带已验证 workaround：

| 领域 | 历史候选描述 |
|---|---|
| 低功耗 | 短连接间隔下无法休眠；休眠中调整连接参数复位；BLE 事件误唤醒；`TS_EN_SLEEP_TMR_CHK` 与断连相关 |
| GPIO/低功耗 | `TS_UNUSED_GPIO_MASK` 与 GPIO20/NANO 板漏电；唤醒引脚配置导致持续唤醒 |
| 广播 | 长广播间隔挂起；特定 BPIO4/5 休眠配置影响广播；长期通信后广播消失 |
| BLE 数据 | 大 Notify 长度失败；连接后定时断开；RSSI 波动 |
| UART | LOG UART RX 浮空；非默认 UART 引脚残留配置；`TS_SAVE_UART0_REGS` 相关行为 |
| 编译/时序 | 优化等级变化导致底层 timing 异常 |
| 2.4G | BLE/2.4G 并行冲突；`ts2G4_Coe_Stop_TxRx` 收发切换异常；接入地址配置差异 |
| HID | 电量上报接口行为异常 |
| 例程 | M1S1/M2S3、多角色、低功耗、24G loopback、OTA、HID 和 UART 示例可能缺配置或文档 |

## 已确认缺陷（CONFIRMED_CURRENT）

### OTA 示例 `finish_ind` 空指针解引用

- **位置**：`examples/ble/ble_ota_data_xfer/source/fota_profile.c`
  - `struct ts_fota_param`（约 L116）含 `struct ts_fota_finish_ind *finish_ind;`
  - `static struct ts_fota_param fota_params;`（约 L261）零初始化 → `finish_ind == NULL`
  - `TS_FOTA_INTEGRITY_CHECK_REQ` 分支（约 L490）：`fota_params.finish_ind->integrity_checking_result = ...`
- **证据**：全文件/全工程搜索 `finish_ind` 只有声明与两处解引用，**没有任何赋值**。
- **后果**：空指针解引用（写/读 `NULL + offset`），属未定义行为；本芯片表现为写低地址异常或
  HardFault，digest 校验结果取到错误值，OTA 完整性校验失败、流程中断。
- **修复**（已验证方案，二选一）：
  1. 改用局部变量（应用层最稳妥）：
     ```c
     bool integrity_ok = ts_fota_svc_digest_check();
     uint8_t digest_check_status = integrity_ok ? 0 : 0x80;
     ```
  2. 把成员改为内嵌值结构：`struct ts_fota_finish_ind finish_ind;`，解引用改 `.`。
- **受影响范围**：该示例在 SDK 1.4.0～1.6.x 及大量客户工程中被沿用；实测扫描显示
  绝大多数工程的 `fota_profile.c` 仍是 `ptr=True assign=False`。

> 排查顺序仍是：先查本节 → 确认目标版本源码 → 最小复现 → 再判定是否 SDK 缺陷。

历史笔记曾提到版本 1.4.0/1.5.0 的若干修复，但没有可核验来源，仍须从当前 SDK 发布记录确认。

## 输出

报告必须给出候选项、当前版本证据、反证、复现状态、结论级别和下一步。若只有症状相似，写“命中历史候选，尚未确认”，不得写“SDK 已知缺陷导致”。

