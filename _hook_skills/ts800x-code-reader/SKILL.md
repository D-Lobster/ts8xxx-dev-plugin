---
name: ts800x-code-reader
description: Read, explain, and map an existing TS800X codebase, and look up SDK APIs/types/constants from the local SDK. Use for 代码阅读、理解代码、调用链、执行流程、状态机分析、SDK API 查询、函数签名、GPIO/UART/I2C/SPI/ADC/Timer、code map、学习代码库、维护前建立 context/code_map; never invent an API when the SDK is unavailable.
---

# TS800X 代码阅读与 SDK 查询

只读分析 Skill。不编辑代码，除非用户另行要求修改或持久化。SDK 版本可能不同，任何签名、
枚举、时序和限制都必须从目标项目的实际 SDK 取证。

## 阅读与查询顺序

1. 确认目标项目根目录、构建目标、SDK 版本和 `.uvprojx`；多个工程时不要擅自选取。
2. 从工程文件列出实际编译源、include path 和关键宏，而不是仅按目录猜测。
3. 先查目标项目的 `prebuilt_modules/`、已集成模块和官方例程，评估能否复用。
4. 用 `rg` 查声明、实现和调用示例：
   - `rg -n "symbol|type" <sdk-root> -g "*.h" -g "*.c"`
   - `rg -n "#include.*header" <project-root> -g "*.c" -g "*.h"`
5. 核对：完整函数签名与返回值；必需头文件、结构体初始化和枚举；阻塞/中断/DMA 语义；
   ISR、临界区、时钟、引脚复用和调用上下文限制；SDK 例程是否与当前芯片、构建宏和版本一致。
6. 围绕用户问题追踪定义、调用点、回调注册、函数指针和条件编译。
7. 识别状态枚举、转换条件、超时、错误恢复和不可达/无出口路径。
8. 映射跨模块共享状态，区分 ISR、回调和主循环上下文；对共享变量记录 `volatile`、临界区和竞态风险。
9. 每个关键结论附 `file:line`、证据类型和置信度。

## 规则

- 找不到声明时，明确回答"当前 SDK 未找到"，不要凭记忆生成近似 API。
- 不把旧项目封装函数误写成 SDK 公共接口；不复制整套例程，只提取当前任务必需且已核验的部分。
- 不修改 `ts800x_sdk/`。需要适配时在 `APP/` 建薄层，并说明原因。
- 文本搜索不是完整 C 解析器；宏、函数指针和链接裁剪造成的不确定性必须明确写出。
- 涉及 Flash、BLE 协议、RF 或时序异常时，查 `ts800x-sdk-bug-reference`，但候选缺陷仍需当前版本证据。

## 持久化建图

用户只要求解释/审查时，在回复中给地图，不写文件。进入维护工作流并允许持久化时，写入项目根的
`context/code_map.yaml` 和可选的 `context/code_map_brief.md`。不扫描工作流仓库中的示例项目
代替用户目标。

最小结构：

```yaml
schema_version: 1
project:
  root: "<absolute path>"
  uvprojx: "<absolute path>"
  build_target: "<target or unknown>"
  sdk_fingerprint: "<version/commit/hash or unknown>"
modules: []
entry_and_scheduling: []
symbols: []
call_paths: []
shared_state: []
isr_boundaries: []
conventions_observed: []
risks: []
analysis_limits: []
generated_at_utc: "<ISO-8601>"
```

每个列表项至少包含 `location` 和 `evidence`；推断项增加 `confidence: low|medium|high`。
不要填造示例模块、API、SDK 版本或风险。从相邻代码归纳命名、错误处理、日志和模块接口时，
把"观察到的约定"与"R01-R29 要求"分开。

## 输出

- 构建与入口：工程、目标、入口和调度模式；
- 执行链：按事件或时间顺序列出 `file:line`；
- 状态机：状态、入口、动作、出口、超时与错误路径；
- 依赖：直接调用、include、共享变量和回调；
- 风险：ISR 工作量、竞态、边界、阻塞和 SDK 只读边界；
- 未确认项：缺失配置、条件编译分支或需要运行证据的结论。

不要输出虚构的标准架构图、固定设备配置或"BLE 初始化三部曲"。
