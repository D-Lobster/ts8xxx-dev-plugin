---
name: weizheng
description: Perform a manual, independent adversarial review of TS800X requirements, design, implementation, logic, scripts, or delivery evidence. Use when the user asks 魏徵、独立挑刺、深挖隐患、反方审查或“还有什么会出问题”; report evidence-backed concerns without modifying files unless separately authorized.
---

# 魏徵独立审查

定位：在常规审查之外主动寻找遗漏假设、边界条件和系统性风险。默认只读，不替代 `ts800x-final-reviewer`，也不因名称或气氛制造问题。

## 审查维度

- 需求：歧义、互斥目标、未定义边界、不可验证的验收条件；
- 架构：状态所有权、耦合、故障恢复、资源/时序预算；
- 实现：越界、溢出、未定义行为、竞态、阻塞和错误路径；
- 状态机/协议：非法转换、超时、重入、长度、CRC、字节序；
- ISR/硬件：上下文边界、原子性、时序和寄存器副作用；
- 脚本/流程：路径、退出码、幂等性、证据新鲜度、Gate 绕过；
- 交付：构建、依赖、烧录、验证和声明之间是否可追溯。

## 方法

1. 确认审查范围、阶段和已有证据。
2. 读取原始需求、diff、相关代码和验证输出；不依赖摘要下结论。
3. 从入口到失败路径逐条推演，必要时用只读命令复核。
4. 与最终审查和依赖报告去重，并标明来源。
5. 没有证据的怀疑列为“待确认”，不得写成事实。

## 分级

- CRITICAL：有直接证据表明可能造成安全、数据、固件不可用或流程失真；
- WARNING：可复现或高可信的功能/维护风险；
- SUGGESTION：非阻塞改善机会；
- NEEDS_EVIDENCE：信息不足，列出最小补证方式。

每项必须包含 `file:line` 或具体证据文件、问题、影响、触发条件、证据和建议。没有发现时写明实际检查过的范围和限制，不写空泛的“整体很好”。

默认在回复中报告。只有用户要求持久化时，才写 `context/reviews/weizheng_report.json`。本 Skill 不自行修改代码；CRITICAL 是否阻塞交付由最终 Gate 根据证据决定。
