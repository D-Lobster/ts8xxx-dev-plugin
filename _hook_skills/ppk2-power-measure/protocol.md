# PPK2 上位机通信协议速查

来源：Nordic `pc-nrfconnect-ppk`（src/device/serialDevice.ts、src/constants.ts、
worker/serialDevice.js）+ PPK2 固件 1.2.4（pca63100_ppk2_1.2.4_db16a94.hex 提取）。

## 物理层

- USB CDC 虚拟串口，115200 baud，8N1
- 上位机通过子进程 serialport 读写；数据流式，无帧头

## 命令（单字节命令码 + 定长参数）

| 命令码 | 名称 | 参数 |
|---|---|---|
| 0x06 | AverageStart | 无（开始连续采样） |
| 0x07 | AverageStop | 无 |
| 0x0C | DeviceRunningSet | 1 字节：**1=打开 DUT 电源(VDD 输出)**，0=关闭。RegulatorSet 只设电压值，必须再发 0x0C=1 才有输出 |
| 0x0D | RegulatorSet | VDD 大端 2 字节，单位 mV |
| 0x11 | SetPowerMode | 1 字节：2=SMU（供电+测量），1=AM（外供只测电流） |
| 0x19 | GetMetadata | 无（回文本元数据直到 `END`） |
| 0x20 | Reset | 无 |
| 0x25 | SetUserGains | range(1B) + float32 小端(4B) |
| 0x01/0x03/0x05 | 触发相关 | 本应用未使用（触发在上位机软件实现） |
| 0x0E/0x0F/0x12/0x15/0x16 | 开关点/用户电阻/滤波 | 备用 |

## 采样数据（连续流，每样本 4 字节小端 32bit）

```
bit 0-13   ADC 原始值（实际 = 值 × 4）
bit 14-16  量程 range（0-4，固件自动切换）
bit 18-23  采样计数器（0-63 循环，用于丢包检测；bit17 保留）
bit 24-31  8 路数字通道逻辑电平
```

- 采样周期 10 µs → 100 kHz
- 丢包 = 计数器跳变 `(cur - prev) & 0x3F`

## 电流换算（µA）

```
r = R[range]   (量程电阻: 默认 1031.64/101.65/10.15/0.94/0.043 Ω)
o = O[range]
x = (adc*4 - o) * (1.8/163840) / r
I(uA) = UG[range] * ( x*(GS[range]*x + GI[range]) + S[range]*(VDD/1000) + I[range] ) * 1e6
```

GS/GI/UG 默认 1，O/S/I 默认 0；真实值来自 GetMetadata 回读。

## 元数据（0x19 回读文本）

`R0..R4`、`GS0..GS4`、`GI0..GI4`、`O0..O4`、`S0..S4`、`I0..I4`、
`UG0..UG4`、`VDD`（mV）、`mode`（2=SMU 供电+测量 / 1=AM 外供只测电流）、
`Calibrated`（0=未用户校准）、`HW`、`IA`，以 `END` 结尾。
缺省时用上位机默认值（R 见上表，其余 1/0，VDD 5000，mode 2）。

协议已与 Nordic 官方上位机 `pc-nrfconnect-ppk` 及第三方实现
（IRNAS/ppk2-api-python、hdoordt/ppk2-rs）双向交叉验证一致；
真机（PPK2 序列号 C9165C5333FC）元数据回读：R0=996.6180、O0=87.594、
GS1=77.40、S0=1.385e-7、I0=-3.018e-7、VDD=3300、mode=2、Calibrated=0。

## 电量与功耗

```
mAh = 平均电流(µA) × 时长(s) / 3600 / 1000
mW  = 电流(µA) × VDD(mV) / 1e6      # 逐样本, 平均功耗 = mean(mW)
mWh = 平均功耗(mW) × 时长(s) / 3600
```
