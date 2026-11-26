# GPT Remote Development

ChatGPT 通过用户授权的 Remote Desktop Commander 操作 Windows，不是原生加载 DSH bundle。每个新会话先指定本插件绝对路径与目标工程路径。

1. 读取 VERSION、workflow.manifest.json、AGENTS.md、WORKFLOW.md、RULES/CODING_STANDARD.md。确认版本一致与用户目标，按 L1/L2/L3 路由。
2. 根据任务读取 _hook_skills/<skill>/SKILL.md 的完整正文，并核对其中真实脚本路径及工具参数。相对路径以本插件根为准。
3. 通过远程工具读取目标工程、执行 PowerShell/Node/Python；编译、烧录、OTA、RTT、功耗等仅用对应 Skill 的现有工具，禁止猜测地址、设备、API。烧录须用户意图明确并校验目标和产物。
4. L1 只执行必要闭环；L2 完成 APP 扫描/质量/Rebuild/依赖/回归；L3 独立终审并逐条提供 R01-R29 证据。未执行不得称通过。
5. 保护客户源码和日志：不将其上传到公开插件仓库；仅提交授权的插件改动。项目状态写入目标项目，不依赖聊天记忆。没有设备连接或工具权限时明确 BLOCKED。

新会话示例：使用 Remote Desktop Commander 读取我电脑上的 TS8XXX 插件 GPT_REMOTE.md，按其规范开发目标工程 <绝对路径>。先确认插件版本和目标工程，不自动烧录。
