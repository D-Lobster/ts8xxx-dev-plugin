---
name: ts800x-ble-ota
description: TS800X BLE OTA 固件无线升级。用于蓝牙升级、无线烧录、OTA 协议校验；与 JLink 和 UART 下载分开，并要求签名、地址边界和完整性证据。
---

# TS800X BLE OTA

通过 BLE OTA 服务升级已经运行且支持 OTA profile 的设备。它不是无条件的“远程烧录”：
目标必须在附近、可连接、暴露正确 GATT 属性，并通过扇区 ACK 和最终完整性校验。

## 开发测试策略

开发测试 OTA 不强制 pre-flash Gate，可在成功构建后直接进入目标确认和协议校验：

```
build → 确认目标设备/布局 → OTA → 完整性响应 → 版本/行为验证
```

固件为空、设备身份不明确或地址布局未确认时禁止执行 `flash`。code-quality、第二次 0/0
构建和依赖分析是模块完成/最终交付条件，不阻止中间 OTA 测试。

## 安全规则

- 生产/交付 OTA 必须提供 64 字节 `--sign` 文件。
- 只有开发调试且用户明确授权时，才允许 `--allow-unsigned`。
- 设备名必须精确匹配；发现多个同名设备会拒绝连接，改用 `scan` 返回的 BLE 地址。
- 控制特征必须支持 `indicate` 和 write-with-response；数据特征必须可写且可读 ACK。
- Intel HEX 不在本工具范围；BLE OTA 输入是成功构建生成的 `.bin`。
- 任一扇区 ACK、完整性响应或 GATT 操作失败，整体失败；不得把断连推断为成功。

## 使用

```powershell
# 扫描并记录目标地址
python "<skill-dir>\ble_ota.py" scan --filter <name>

# 只读查看服务与特征
python "<skill-dir>\ble_ota.py" info <BLE-address>

# 生产升级：签名必需
python "<skill-dir>\ble_ota.py" flash <BLE-address> `
  --bin <firmware.bin> --sign <signature.bin> --reboot

# 开发环境无签名测试（必须显式授权）
python "<skill-dir>\ble_ota.py" flash <BLE-address> `
  --bin <firmware.bin> --allow-unsigned
```

默认布局：

| 参数 | 默认值 | 校验 |
|------|--------|------|
| `--ota-addr` | `0x10002000` | 4 KiB 对齐 |
| `--backup-addr` | `0x10020000` | 4 KiB 对齐且不得与 OTA 区重叠 |
| `--boot-addr` | `0x10000000` | 4 字节对齐 |
| `--flash-size` | `0x40000` | 所有地址与完整固件范围必须落入其中 |

固件大小还受 FINISH 协议 24 位长度字段限制。

## 协议成功条件

1. 启用控制特征 Indication。
2. 发送签名（生产）和 SHA-256 digest。
3. START_RSP 明确成功。
4. 每个 4 KiB 扇区的全部 segment 位都在 ACK bitmap 中置位。
5. INTEGRITY_CHECK_RSP 明确成功。
6. FINISH 写入完成；若要求重启，后续仍需重新发现设备或读取日志验证版本。

只有第 6 步后的真机版本/行为验证通过，才可标记 `[已验证]`。

## OTA 测试检查

```text
【BLE OTA 测试检查】
- [x] BIN 非空且地址布局合法
- [x] 目标 BLE 地址唯一，OTA GATT 属性完整
- [x] 生产签名存在（或开发无签名已明确授权）
- [x] 扇区 ACK 与最终完整性响应必须成功
- [ ] 升级后版本/功能验证
→ 可以开始 OTA
```
