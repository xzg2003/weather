# 气象数据采集系统使用说明

## 功能特点
- 每分钟自动读取RS485气象传感器数据（温度、湿度、气压）
- 自动上传数据到InfluxDB时序数据库
- 完整的日志记录和错误处理
- 支持长时间稳定运行

## 快速开始

### 方法一：使用一键启动脚本（推荐）

1. 双击运行 `启动气象采集.bat`
2. 首次使用需要先初始化 InfluxDB（见下方说明）

### 方法二：手动启动

详见 `快速启动指南.md` 文件。

## 安装步骤

### 1. 安装Python依赖
```bash
conda create -n weather_station python=3.10 -y
conda activate weather_station
pip install -r requirements.txt
```

### 2. 启动并配置 InfluxDB

#### 启动 InfluxDB：
进入 `influxdb` 目录，双击运行 `start_influxdb.bat`

#### 初始化配置（首次使用）：
1. 访问 http://localhost:8086 进行初始化配置
2. 设置用户名和密码
3. 创建组织(Organization): `weather_station`
4. 创建存储桶(Bucket): `weather`
5. **重要：复制并保存生成的 API Token**

### 3. 配置参数

编辑 `config.env` 文件，填入从 InfluxDB 获得的 Token：

```env
INFLUXDB_URL=http://localhost:8086
INFLUXDB_TOKEN=你的Token（从Web界面复制）
INFLUXDB_ORG=weather_station
INFLUXDB_BUCKET=weather
SERIAL_PORT=COM3  # 根据实际情况修改
```

### 4. 测试连接

运行测试脚本验证配置：
```bash
python test_influxdb.py
```

如果看到 "✓ 所有测试通过！" 说明配置正确。

## 运行程序

```bash
python weather_collector.py
```

或者双击运行 `启动气象采集.bat`

## 目录结构

```
get_data/
├── influxdb/              # InfluxDB 数据库
│   ├── influxd.exe       # InfluxDB 主程序
│   ├── start_influxdb.bat # 启动脚本
│   ├── data/             # 数据存储目录
│   └── 使用说明.md
├── weather_collector.py   # 主数据采集程序
├── test_influxdb.py      # 连接测试脚本
├── config.env            # 配置文件
├── requirements.txt      # Python依赖
├── 启动气象采集.bat      # 一键启动脚本
└── 快速启动指南.md       # 详细使用说明
```

## 日志文件

程序运行日志保存在 `weather_data.log` 文件中。

## 数据查询示例

在InfluxDB中查询数据（Flux语言）：

```flux
from(bucket: "weather")
  |> range(start: -1h)
  |> filter(fn: (r) => r["_measurement"] == "weather")
  |> filter(fn: (r) => r["_field"] == "temperature" or r["_field"] == "humidity" or r["_field"] == "pressure")
```

## 停止程序

按 `Ctrl+C` 安全停止程序。

## 故障排查

### 串口连接失败
- 检查COM端口号是否正确
- 确认设备已连接并供电
- 检查是否有其他程序占用串口

### InfluxDB连接失败
- 确认InfluxDB服务正在运行
- 检查URL、Token、组织名和Bucket名是否正确
- 运行 `python test_influxdb.py` 进行诊断
- 查看InfluxDB日志

### 数据读取失败
- 检查Modbus设备地址是否正确（默认0x01）
- 确认波特率设置（默认4800）
- 查看日志文件中的详细错误信息
