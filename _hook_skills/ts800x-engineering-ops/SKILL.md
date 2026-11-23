---
name: ts800x-engineering-ops
description: TS800X 工程配置与交付工程化。处理 .uvprojx、include path、linker、可复现构建、CI 检查和带 checksum 的交付包；不负责业务代码清理。
---

# TS800X Engineering Ops

## 检查范围

- `.uvprojx` 源文件、include path、输出目录和目标配置；
- linker/scatter 文件与 Flash/RAM 布局；
- SDK 路径只读且来源可追溯；
- `build.ps1` 在干净/增量场景都输出可信 0/0 和新鲜 HEX/BIN；
- CI/检查脚本的非交互退出码；
- 交付文件、版本、SHA-256 和重建说明。

不得用正则盲改 XML 工程；解析 XML、规范化路径、检查每个新增源文件。构建脚本不得把旧产物、
空日志或缺失 Keil 汇总当作成功。

## 交付流程

1. 新鲜 rebuild 0/0。
2. `auto_check.ps1` 和依赖分析通过。
3. 终审与硬件状态已明确。
4. 复制明确列出的 HEX/BIN、map、配置、版本说明和报告到版本目录。
5. 为每个交付文件计算 SHA-256，并重新验证。
6. 从交付说明复现一次关键构建步骤。

不自动清理分支、丢弃工作区、合并、推送或发布；这些动作必须单独获得用户授权。

## 输出

写入 `context/handoffs/ops/ops_report.json`，至少包含：项目/工具链版本、工程文件、构建命令与
退出码、错误/警告数、产物大小/hash、依赖版本、CI 结果、缺失测试、交付目录和 next_action。
写入后重新解析并核对列出的每个文件实际存在。
