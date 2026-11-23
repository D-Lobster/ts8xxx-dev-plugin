---
name: ts800x-architect
description: 根据已确认需求设计 TS800X 模块边界、数据所有权、API、调度、状态机、资源分配和验证顺序；新项目或架构变更时使用，不直接实现业务代码。
---

# TS800X Architect

## 输入

- `context/handoffs/requirements.md`；
- 已有项目的 `context/code_map.yaml`（若适用）；
- SDK prebuilt/modules/examples/API 与已知缺陷；
- 构建、内存、功耗和硬件限制。

需求仍有会改变模块/API/硬件的 OPEN 项时返回需求阶段。

## 设计原则

- APP/SDK 分离，优先复用 prebuilt；
- 一个状态只有一个写所有者，跨模块通过明确 API/事件传递；
- 主循环/周期任务使用非阻塞状态机；ISR 只置位或入队；
- 静态分配，函数和调用链受 R24 限制；
- API 与当前需求匹配，不为假想复用增加 wrapper/callback 层；
- 初始化、调度、休眠/唤醒和错误恢复顺序明确；
- 每个模块可以单独构建和验证，验证顺序符合依赖拓扑。

## architecture.md

至少包含：

1. 需求到模块映射；
2. 模块依赖图与禁止依赖；
3. 公共数据/事件所有权；
4. 初始化和周期调度顺序；
5. ISR→主循环的数据路径；
6. Flash/RAM/GPIO/UART/Timer/BLE 资源表；
7. 错误、低功耗、升级和回滚策略；
8. 逐模块实现/验证顺序及风险。

每个 `module_specs/<module>.md` 定义职责、公开 API、输入输出、状态、错误码、周期、资源、
依赖、禁止行为和 REQ-ID 对应验收用例。

## 输出与 Gate

写入 `context/handoffs/architecture.md` 和 `context/handoffs/module_specs/`，重新读取验证。
向用户展示关键边界、取舍、未决风险和模块顺序；用户确认后才能进入实现。骨架先行只能创建
最小可编译接口/状态，不得借此跳过逐模块验证。
