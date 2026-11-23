---
name: ts800x-rigorous-test
description: TS800X 严格测试设计与证据收口。覆盖单元、集成、边界、异常、BLE、Flash、低功耗和恢复路径，并区分已执行与待硬件测试。
---

# TS800X Rigorous Test

## 测试矩阵

每条需求至少映射一个正常用例和必要的边界/失败用例：

- 初始化、周期调度、状态转换和错误恢复；
- 最小/最大/零值、溢出、重复、乱序、超时和校验错误；
- ISR 与主循环竞态、队列满、事件丢失；
- BLE 扫描/连接/断连/重连/GATT 属性/分包；
- Flash 边界、掉电恢复、设置兼容；
- 睡眠/唤醒、时钟切换、低电压；
- 资源上限、长时间运行和回归基线。

## 每个用例字段

`id`、requirement、level、preconditions、hardware、steps、input、expected、observed、
evidence、status、cleanup。status 只能是 PASS、FAIL、BLOCKED 或 PENDING_HARDWARE。

## 执行规则

1. 测试固件需成功构建；开发测试烧录不强制 Gate，最终结论仍需 0/0 构建证据。
2. 自动化脚本必须检查退出码，日志分析默认 WARN/ERROR/缺失期望均失败。
3. 物理行为由用户观察时，记录用户确认内容和时间，不代替用户作视觉结论。
4. 重试不能隐藏首次失败；报告次数、原因和最终结果。
5. 没执行的用例不得计入 passed 或通过率分母伪装成功。

可使用 `full_test.ps1` 串联构建、外部 JLink CLI（`ts800x-flash` 的 `run_cli.ps1`）烧录
结果、UART/RTT 日志和分析；该脚本不会自行烧录。

## 输出

写入 `context/handoffs/<module>/test_report.json`，包含固件 hash、硬件标识、环境、用例总数、
各状态数量、失败项、日志/报告路径、未覆盖项和 next_action。任何 FAIL 都进入终审阻断清单；
PENDING_HARDWARE 必须在交付摘要显式显示。
