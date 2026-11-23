---
name: ts800x-dependency-analyzer
description: 在 TS800X 改动前后分析变更文件、直接函数/全局引用、头文件 include 传播和工程配置风险，输出 JSON 波及面报告；必须结合人工调用链审查。
---

# TS800X Dependency Analyzer

```powershell
# 包含 tracked diff 和未跟踪文件
powershell -NoProfile -File "<skill-dir>\analyze_dependencies.ps1" `
  -GitDiff -ProjectRoot <project> -JsonOutput `
  -OutputFile reports/dependency_report.json

# 限定文件
powershell -NoProfile -File "<skill-dir>\analyze_dependencies.ps1" `
  -Files "APP/modules/a.c,APP/include/a.h" -ProjectRoot <project>
```

报告 schema 3 包含全部 changed files、非 C/H 配置改动、提取到的函数/`g_` 全局、直接调用者、
头文件 include dependent、`file:line` 推导证据、人工复核标记和总风险。SDK、`.uvprojx`、
linker/scatter 改动自动提高风险。

## 局限

实现是保守的正则静态分析，不解析 C AST，也不可靠识别：

- 函数指针/回调和运行时 dispatch；
- 宏生成函数或 include；
- 条件编译、链接弱符号和汇编引用；
- 间接调用深度和数据语义。

因此报告不是“安全证明”。HIGH 风险、公共头文件、ISR、协议、Flash、低功耗和工程配置必须
结合 `git diff`、Code Map、符号搜索和人工调用链复核。报告 JSON 必须实际可解析，才能作为
模块完成和最终交付证据。
