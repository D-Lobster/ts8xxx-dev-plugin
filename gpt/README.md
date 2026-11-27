# TS8XXX 系列开发 · ChatGPT 适配

`workflow.manifest.json`、`_hook_skills/`、`RULES/` 和 `WORKFLOW.md` 是 DSH 和 GPT 的共同源文件。构建时复制 24 个技能正文与规范快照，并为每个技能注入 GPT 主机执行边界。工具操作通过已连接的 Remote Desktop Commander 调用 Windows 插件目录中的原有脚本。SDK 和客户工程留在 Windows。

## 构建与安装

从仓库根目录运行。默认产物在 `dist/gpt-marketplace`。再次构建使用新的输出目录，例如 `node gpt/build.mjs dist/gpt-next`。

```powershell
node gpt/build.mjs
codex plugin marketplace add ./dist/gpt-marketplace
codex plugin add ts8xxx-development@ts8xxx-local --json
codex plugin list --marketplace ts8xxx-local --json
```

在 ChatGPT 桌面端的插件目录选择 **TS8XXX 个人插件**。上传为 ChatGPT 账号私有插件时，只打包 `dist/gpt-marketplace/plugins/ts8xxx-development/` 目录的内容，包含隐藏的 `.app.json`。私有账号插件通过该清单关联已安装的 Remote Desktop Commander。

新会话验证用语：使用「TS8XXX 系列开发」，通过 Remote Desktop Commander 只读检查 Windows 的 DSH 版本及技能清单，并概述 L1/L2/L3。不指定客户工程，不连接硬件。

共同源版本更新时，同步 `gpt/plugin.json` 的版本后重新生成并安装或上传。不要直接编辑生成包。
