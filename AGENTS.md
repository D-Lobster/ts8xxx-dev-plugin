# TS800X workflow instructions for DSH

This standalone DSH bundle is authoritative; do not copy obsolete workflow files into it.

> First-time agents should read `README.md` (installation and entry).

## Canonical sources

- Skill inventory and hook mapping: `workflow.manifest.json`
- Full process: `WORKFLOW.md`
- Coding rules: `RULES/CODING_STANDARD.md` (R01-R29)
- Final review: `RULES/REVIEW_CHECKLIST.md`
- DSH preset: `cordis.patch.yml`

When instructions conflict, the files above win in that order. Host-specific files only adapt discovery and invocation.

## Entry and execution

- Start coordinated work with ts800x-workflow, then requirements and architect skills.
- Execute shipped skill scripts directly; use WORKFLOW.md for L1/L2/L3 routing.
- Compile with `_hook_skills/ts800x-build/build.ps1` and require 0 errors, 0 warnings, plus fresh non-empty artifacts.
- Flash and RTT use `_hook_skills/ts800x-flash`: the skill defines the shared write/verify policy and ships the single JLink CLI implementation (`run_cli.ps1`); there is no MCP server and no second flashing implementation.
- UART flashing and BLE OTA remain separate skills. `ts800x-uart-download` covers both
  unattended RTS-reset flashing (`rts_uart_download.py`) and manual RESET flows
  (`uart_download.py --wait-reset`).

## Always-on rules

1. Existing projects require a Code Map before maintenance analysis.
2. Before writing a driver, inspect `ts800x_sdk/prebuilt_modules/` and SDK examples.
3. Application code stays under `APP/`; `ts800x_sdk/` is read-only.
4. No blocking delay, dynamic allocation, ISR logging, ISR Flash writes, or non-ASCII firmware LOG text.
5. Development flashing is allowed after a successful build and never requires a pre-flash Gate. Module completion still requires `ts800x-code-quality`, a second 0/0 build, dependency analysis, and flash/log/hardware verification, or `[待硬件验证]` when hardware is unavailable.
6. L1 permits fast iteration; L2 requires app audit, quality, rebuild, dependency and regression evidence; L3 requires independent final review and R01-R29 evidence before customer delivery.
7. Never claim hardware success without hardware evidence.
8. Persist state in the target project's `PROGRESS.md` and `context/`; use `context/handoffs/` for all agents.
9. Use a branch by default. Direct work on `master` requires explicit user authorization for that project.
10. If the user says stop, pause immediately and report the current checklist.
11. Every BLE-enabled application must include the BBTIME liveness check from R27 (main-loop poll after `tsBle_Init()`, never in an ISR, macros for threshold/reset, bounded pre-reset wait). A BLE module without it is not complete.
12. After every build, check RAM usage (`RW-data + ZI-data` from the Keil `Program Size` line). When it exceeds 16K (`0x4000`, past `0x20004000`), `#define TS_RAM_SAVE_24K` must be enabled in `APP/include/cfg_def_app.h`; the system keeps only the first 16K across sleep by default, so the overflow loses data and the device misbehaves after wake. Record the RAM figure as build evidence.
13. Every project (SDK 1.5 / 1.5.1 / 1.6) builds at **-O1**: Target `<Optim>` = `1` with no per-file optimization overrides, and every ISR/main-loop shared flag is `volatile`. After changing an optimization setting, rebuild fully and verify the `-O` flags in the regenerated `.dep` files. A wrong level or a config/actual drift silently stalls periodic tasks.

DSH discovers bundled skills through cordis.patch.yml. Do not edit installed global skill copies as authoritative sources.
