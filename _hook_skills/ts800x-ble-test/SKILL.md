---
name: ts800x-ble-test
description: TS800X BLE 扫描、连接、GATT 属性检查和交互式透传测试；用于验证广播、服务和数据收发，不用于 OTA。
---

# TS800X BLE 测试

```powershell
python "<skill-dir>\ble_test.py" scan --timeout 5 --name <filter>
python "<skill-dir>\ble_test.py" connect <exact-name-or-address>
python "<skill-dir>\ble_test.py" passthrough <exact-name-or-address> `
  --write <uuid> --notify <uuid>
```

设备名按不区分大小写的精确值解析。若有多个同名设备，工具会失败并要求使用扫描结果中的
BLE 地址，避免连接到错误目标。扫描无结果、连接失败、指定 UUID 不存在或属性不匹配均返回非 0。

透传命令：

| 输入 | 行为 |
|------|------|
| `01 02 FF` | 原始字节写入 |
| `frame 03 01` | 构建 `[A5][Len][Cmd][Payload][Sum]` 后写入 |
| `read [uuid]` | 读取指定或当前写特征 |
| `quit` | 退出并清理 notify/连接 |

`--protocol` 会让所有普通十六进制输入都按协议帧处理。未指定 UUID 时可自动选择第一个属性
匹配的特征；正式验证建议显式提供 UUID，并把扫描、连接、收发结果连同设备地址写入报告。

BLE “能扫描”不等于 GATT 或业务协议通过；只有预期服务、写入、通知/指示和响应都验证后，
才能记录对应测试项成功。BLE OTA 使用独立的 `ts800x-ble-ota` Skill。
