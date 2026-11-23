---
name: ts800x-code-quality
description: Audit and, when authorized, simplify TS800X application code after an initial clean build and before module completion. Use for simplify、代码简化、代码质量、过度设计、R24、自查或交付前审计; preserve timing, ISR, protocol, state-machine, and verified SDK sequences unless evidence supports a change.
---

# TS800X Code Quality

目标是减少不必要复杂度，同时保持行为、时序、ABI 和协议不变。用户只要求审查时仅报告；用户要求修复或处于已授权开发闭环时才编辑。

## 前置证据

- 明确目标文件与需求；
- 模块已完成编译初验并有 0 Error / 0 Warning 证据；
- 读取改动 diff、调用点和 `ts800x-coding-standard`；
- 涉及旧代码移植时保留源/目标逐行 diff。

## 审计项

1. 函数代码行通常不超过 50；调度或分发函数可到 80，但每个分支保持简短。
2. 业务调用深度通常不超过 3；SDK 内部层级不计入应用层硬性重构。
3. 单调用者辅助函数只有在没有独立语义、隔离价值、测试价值或上下文约束时才考虑内联。
4. 删除不可达代码、无用途配置和重复包装；不要删除诊断所需或由构建配置选择的有效分支。
5. 三处以上且语义一致的重复逻辑可提取；不同硬件/协议语义相似不等于可合并。
6. 状态机应对应异步事件或时间推进；不要把阻塞流程包装成伪状态机。
7. 不为未提出的未来需求增加接口、回调、配置或动态扩展点。
8. 检查 R01-R29，尤其 ISR、阻塞延时、动态内存、Flash、边界和 LOG ASCII。
9. 启用 BLE 的工程必须存在 R27 BBTIME 存活检测（主循环、`tsBle_Init()` 之后、
   阈值/复位宏化、复位前等待有界）；缺失时作为阻断项报告，不以"简化"为由删除该检测。
10. 核对 R29 编译配置与可见性：Target 优化等级 -O1（无按文件覆盖）、
    ISR 与主循环共享变量为 `volatile`；等级错误或配置漂移作为阻断项报告。

## 保护清单

除非有明确缺陷证据和专项验证，不以“简化”为由重排或折叠：

- 硬件时序、bit-banging、Charlieplexing 相位；
- ISR 必需的最小寄存器/入队/置位操作；
- BLE/串口协议帧、长度、CRC 与字节序；
- `switch` 状态分发；
- 当前 SDK 要求的 API 调用序列；
- 安全检查、超时、边界和错误恢复；
- BLE 存活检测（R27 BBTIME 轮询与复位恢复路径）；
- ISR/主循环共享变量的 `volatile` 与临界区（R29；-O1 下的正确性前提）。

## 执行与验证

若进行修改：

1. 只改已确认的复杂度问题，逐项记录行为保持理由。
2. 重新编译，要求 0 Error / 0 Warning 和新鲜产物。
3. 比较修改前后 diff，运行依赖分析。
4. 生成审计证据，并用：
   `workflow.ps1 mark-code-quality -Evidence <report-or-evidence>`
5. 未通过再次编译时，不得标记模块完成或进入最终交付。

不要把行数/深度注释写进每个生产函数；在审计报告中记录即可。

## 报告

每项发现包含严重度、`file:line`、证据、风险和建议/实际修改。结论只能是：

- PASS：未发现阻塞问题，且验证证据完整；
- PASS_WITH_NOTES：无阻塞问题，有明确非阻塞债务；
- FAIL：存在行为风险、规范违规或验证缺失。

没有硬件证据时只能声明“代码质量与编译检查通过，待硬件验证”。

