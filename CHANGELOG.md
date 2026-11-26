# 更新日志

版本号与 TS8XXX 工作流版本（`workflow.manifest.json` 的 `workflow_version`）保持一致。

## v2.2.2

- 单一编码规范源、自动同步 Skill、逐条终审证据；R08 统一 Allman。
- 新增 APP 基础扫描与 R24 近似直接调用深度、正反例测试。
- 明确 L1/L2/L3，清理不存在的旧工作流入口，新增 GPT 远程开发入口。
- 保留 2.2.1 市场入口与现有硬件工具。

## v2.2.1

插件市场收录准备：

- 新增 `index.js` 导出 `apply(ctx)`（市场收录要求；bundle patch 层本身不产生 Host 行，
  该导出为兼容性空实现）；
- `package.json` 增加 `main`/`exports` 与 `dsh-plugin` 等 keywords；
- GitHub 仓库添加 `dsh-plugin` topic（市场按 topic 自动聚合）。

## v2.2.0

插件家族化重命名（为后续芯片与 SDK 版本预留）：

- 仓库/包名：`ts8xxx-dev-plugin`；预设 id：`ts8xxx-dev`；显示名：「TS8XXX 系列开发」；
- 当前支持 TS800X / SDK V1.5–V1.6；后续新增芯片或 SDK 版本时在同一插件内扩展技能，
  不再改仓库名；
- `package.json` 移除 `private`，为后续发布到 npm 插件市场做准备；
- 自包含安装包与 `install.ps1` 行为不变（预设合并、技能链接、环境变量、`-Check`/`-Uninstall`）。

## v2.1.0

首个公开版本：

- DeepSeek Harness Agent Preset「TS8XXX 系列开发」（`@deepseek-ai/dsh-agent-preset` 声明）；
- 自包含安装包：预设 + 24 个 ts800x 技能 + 规则（R01-R29）+ 工作流规范；
- `install.ps1`：一条命令完成预设合并、技能链接（Junction）、环境变量配置，
  支持 `-Check` / `-DryRun` / `-Uninstall` / `-Force` / `-Profile` / `-Mode Copy`；
- `check_preset_patch.mjs`：用已安装 DSH 的解析器校验预设声明，校验失败不写入；
- 支持两种安装路线：ZIP + `install.ps1`（无需 pnpm），或 DSH 插件管理器
  `dsh plugin add github:D-Lobster/ts8xxx-dev-plugin`。
