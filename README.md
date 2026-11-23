# TS8XXX 系列开发插件 · DeepSeek Harness

把 **TS8XXX 系列芯片（当前支持 TS800X / SDK V1.5–V1.6）的 BLE 固件开发工作流**
装进 DeepSeek Harness（DSH）：一个预设「TS8XXX 系列开发」，
加 24 个可自动路由的技能（编码规范 R01-R29、Keil 构建、JLink/UART/OTA 烧录、
日志分析、代码质量、依赖分析、终审等）。后续新增芯片/SDK 版本时在同一插件内扩展技能。

- 版本：见 [`VERSION`](VERSION)（跟随工作流版本）
- 许可：[MIT](LICENSE)
- 依赖：Windows + PowerShell 5.1+、已安装 DeepSeek Harness（无需 pnpm、无需 npm）

安装后，新建会话时在预设选择器里选择「**TS8XXX 系列开发**」，agent 即按 TS8XXX 工作流
执行：模块闭环（build 0/0 → 烧录 verify → 日志/硬件验证 → code-quality → 终审），
硬性红线（SDK 只读、ISR 禁 LOG/Flash、R27 BBTIME 存活检测、R28 RAM 24K、R29 -O1 编译等）。

## 安装

### 方式一：下载 ZIP（推荐，无需 pnpm）

1. 在本仓库页面点 **Code → Download ZIP**，解压到任意目录；
2. 打开 PowerShell，执行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\ts8xxx-dev-plugin\install.ps1
```

3. 重启 DeepSeek Harness（Web 端刷新页面），新建会话选择预设「TS8XXX 系列开发」。

### 方式二：DSH 插件管理器（github 源）

需要本机有 pnpm，且 DSH 具备插件安装权限：

```powershell
dsh plugin --profile desktop add github:D-Lobster/ts8xxx-dev-plugin
```

安装后按提示重启宿主；后续用 `dsh plugin --profile desktop list` 查看。

### 方式三：插件市场

本仓库已打上 GitHub topic `dsh-plugin`，会被 DSH 插件市场/索引按 topic 自动聚合；
市场安装即等价于上面的 github 源安装。若你的客户端支持「发现 → 索引源」，
也可直接把本仓库地址加为插件源。


### 方式四：本地目录 / Git clone

```powershell
git clone https://github.com/D-Lobster/ts8xxx-dev-plugin.git
# 直接运行仓库根目录的 install.ps1（本仓库根目录即插件包）
powershell -NoProfile -ExecutionPolicy Bypass -File .\ts8xxx-dev-plugin\install.ps1 -NoCopy
```

## 安装脚本做了什么

`install.ps1` 会把本插件安装到 `%USERPROFILE%\.dsh\plugins\ts800x-workflow`，然后：

1. 把 `cordis.patch.yml` 的预设声明合并进 `%USERPROFILE%\.dsh\profiles\<profile>\cordis.patch.yml`
   的托管块（带标记，可校验、可卸载）；
2. 把 `_hook_skills` 下的技能以 **Junction** 链接到 `%USERPROFILE%\.agents\skills`
   （DSH 的 `dsh-skill-filesystem` 默认扫描该目录，不复制技能正文）；
3. 设置用户环境变量 `TS800X_WORKFLOW_ROOT` 指向安装目录；
4. 用已安装 DSH 的解析器校验预设声明（`check_preset_patch.mjs`），失败即不写入。

常用参数：

```powershell
# 校验安装完整性
.\install.ps1 -Check
# 预览计划，不写文件
.\install.ps1 -DryRun
# 指定 DSH profile（默认读包内配置）
.\install.ps1 -Profile web
# 升级/替换已存在的同名技能链接
.\install.ps1 -Force
# 不复制到安装目录，直接使用当前文件夹
.\install.ps1 -NoCopy
# 卸载（移除托管块、技能链接、安装目录）
.\install.ps1 -Uninstall
```

## 包内结构

| 路径 | 说明 |
|---|---|
| `install.ps1` | 自包含安装/校验/卸载脚本 |
| `cordis.patch.yml` | DSH 预设声明（`@deepseek-ai/dsh-agent-preset`） |
| `package.json` | DSH bundle 清单（`dsh.bundle.patch` 指向预设声明） |
| `check_preset_patch.mjs` | 预设声明校验器（调用已安装 DSH 的解析器） |
| `workflow.manifest.json` | 技能清单与宿主映射（规范优先级第一层） |
| `WORKFLOW.md` / `AGENTS.md` | 完整流程与工作流规则入口 |
| `RULES/` | `CODING_STANDARD.md`（R01-R29）、`REVIEW_CHECKLIST.md` |
| `TEMPLATES/` | `PROGRESS.md` / `TODO.md` / `MEMORY.md` 模板 |
| `_hook_skills/` | 24 个技能及其脚本（构建、烧录、日志、OTA、功耗、审查等） |
| `VERSION` / `CHANGELOG.md` / `LICENSE` | 版本、更新日志、许可 |

> 任一技能目录的上两级（`<skill-dir>/../..`）即工作流根，内含上面的规范文件，
> 所以 `TS800X_WORKFLOW_ROOT` 指向安装目录即可被所有技能正确定位。

## 验证安装

```powershell
# 安装完整性
powershell -NoProfile -ExecutionPolicy Bypass -File .\ts8xxx-dev-plugin\install.ps1 -Check

# 预设声明是否出现在组合配置中（profile 名按实际改）
dsh --profile desktop --dump-config | Select-String preset-ts800x-dev
```

DSH 中新建会话 → 预设选「TS8XXX 系列开发」→ 输入「编译固件」或「烧录固件」，
agent 应自动加载 `ts800x-build` / `ts800x-flash` 技能。

## 常见问题

| 现象 | 处理 |
|---|---|
| 提示 profile 不存在 | 先启动一次该 profile（`dsh --profile desktop`），或用 `-Profile <name>` |
| 预设选择器里没有「TS8XXX 系列开发」 | 重启 DSH / 刷新 Web 页面；再跑 `install.ps1 -Check` |
| agent 说找不到技能 | 检查 `%USERPROFILE%\.agents\skills` 下是否有 ts800x-* 目录 |
| 提示 patch 校验失败 | 多为 DSH 大版本升级后插件包改名；把报错反馈，更新插件后重装 |
| 想恢复原状 | `install.ps1 -Uninstall`，重启 DSH |

## 与工作流仓库的关系

本仓库由 TS800X 工作流仓库的 `build_dsh_plugin.ps1` 生成，**请勿直接手改包内文件**；
规则/技能/预设的修改都在工作流仓库进行，然后重新生成、打 tag 发版
（见 `build_dsh_plugin.ps1` 与 `CHANGELOG.md`）。
