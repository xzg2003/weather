# 气象数据库字段说明

本文档根据当前代码实现整理分钟级和小时级气象数据库中的字段含义，主要对应以下脚本：

- `merge_minute_data.py`：将秒级原始数据聚合为分钟级数据
- `write_minute_data.py`：将分钟级数据写入 `weather_1m`
- `write_hour_data.py`：从分钟级数据提取小时统计结果，并设计写入 `weather_1h`

## 总体说明

### 1. 分钟级数据库

- Bucket：`weather_1m`
- Measurement：`weather`
- Tag：
  - `location=station_1`
- 时间戳：
  - 写库时会转换为 UTC
  - 业务含义上表示该分钟统计结果对应的时刻，例如 `2026-04-03 00:59:00`

### 2. 小时级数据库

- Bucket：`weather_1h`
- Measurement：`weather_hour`
- Tag：
  - `location=station_1`
- 时间戳：
  - 写库时使用整点时刻
  - 例如 `2026040301` 表示 `2026-04-03 00:00:00` 到 `2026-04-03 01:00:00` 这一小时区间，记录时间戳记为 `2026-04-03 01:00:00`

### 3. 缺测值约定

- 数值型缺测值：`-100.0`
- 风向缺测值：`"未知"`
- `max_wind_time` 缺测时当前代码会写成字符串 `"-100"`

### 4. 单位说明

- 代码里没有统一写死所有字段单位。
- 风速相关字段在 `ultils.py` 中按 `m/s` 计算风级。
- 温度、湿度、气压、雨量字段没有在代码里做单位换算，通常应与原始采集数据保持一致。
- 如果现场设备配置与常规气象单位不同，应以原始传感器配置为准。

## 分钟级数据库字段

分钟级数据由 `merge_minute_data(time_str)` 生成，再由 `write_minute_data(minute_data)` 写入 `weather_1m`。

| 字段名 | 类型 | 含义 | 计算方式 |
| --- | --- | --- | --- |
| `time` | 时间戳 | 该分钟记录对应时刻 | 写库时间戳，不作为 field 存储 |
| `temperature` | float | 当前分钟气温 | 查询 `thp_1m` 最近 1 分钟内最新的 `temperature` |
| `humidity` | float | 当前分钟相对湿度 | 查询 `thp_1m` 最近 1 分钟内最新的 `humidity` |
| `pressure` | float | 当前分钟气压 | 查询 `thp_1m` 最近 1 分钟内最新的 `pressure` |
| `instantaneous_rainfall` | float | 当前分钟雨量 | 查询 `rain_1m` 最近 1 分钟内最新的 `instantaneous_rainfall` |
| `current_hour_rainfall` | float | 当前小时累计雨量 | 从本小时起点到当前时刻，对 `rain_1m.instantaneous_rainfall` 求和 |
| `instant_speed` | float | 当前瞬时风速 | 当前时刻前 5 秒内 `wind_speed_1s.wind_speed` 的平均值 |
| `instant_level` | float/int | 当前瞬时风级 | 根据 `instant_speed` 通过 `wind_speed_to_scale()` 计算 |
| `max_speed` | float | 最近 1 分钟最大风速 | 遍历最近 1 分钟内各秒级风速点，取其各自前 5 秒平均风速的最大值 |
| `max_level` | float/int | 最近 1 分钟最大风力 | 根据 `max_speed` 通过 `wind_speed_to_scale()` 计算 |
| `max_wind_time` | string | 最近 1 分钟最大风速出现时间 | `max_speed` 对应的分钟库时间字符串 |
| `avg_speed_2m` | float | 最近 2 分钟平均风速 | 最近 2 分钟 `wind_speed_1s.wind_speed` 平均值；有效点少于 30 个时记为缺测 |
| `avg_level_2m` | float/int | 最近 2 分钟平均风级 | 根据 `avg_speed_2m` 通过 `wind_speed_to_scale()` 计算 |
| `avg_speed_10m` | float | 最近 10 分钟平均风速 | 最近 10 分钟 `wind_speed_1s.wind_speed` 平均值；有效点少于 150 个时记为缺测 |
| `avg_level_10m` | float/int | 最近 10 分钟平均风级 | 根据 `avg_speed_10m` 通过 `wind_speed_to_scale()` 计算 |
| `instant_angle` | float | 当前瞬时风向角 | 当前时刻前 5 秒内 `wind_sock_1s.wind_angle` 的平均值 |
| `instant_direction` | string | 当前瞬时风向 | `instant_angle` 通过 `wind_direction_angle_to_direction()` 转换后的中文风向 |
| `max_angle` | float | 最大风速对应风向角 | 在 `max_wind_time` 对应时刻，取其前 5 秒 `wind_sock_1s.wind_angle` 平均值 |
| `max_direction` | string | 最大风速对应风向 | `max_angle` 对应的中文风向 |
| `avg_angle_2m` | float | 最近 2 分钟平均风向角 | 最近 2 分钟 `wind_sock_1s.wind_angle` 平均值；有效点少于 30 个时记为缺测 |
| `avg_direction_2m` | string | 最近 2 分钟平均风向 | `avg_angle_2m` 对应的中文风向 |
| `avg_angle_10m` | float | 最近 10 分钟平均风向角 | 最近 10 分钟 `wind_sock_1s.wind_angle` 平均值；有效点少于 150 个时记为缺测 |
| `avg_direction_10m` | string | 最近 10 分钟平均风向 | `avg_angle_10m` 对应的中文风向 |

## 小时级数据库字段

小时级数据的“设计写库字段”由 `write_hour_data(hour_data)` 决定，也就是当前 `weather_1h` 计划写入的字段。

| 字段名 | 类型 | 含义 | 说明 |
| --- | --- | --- | --- |
| `time` | 时间戳 | 小时记录对应整点时刻 | 例如 01:00 表示前一小时区间的统计结果 |
| `temperature` | float | 整点气温 | 仅当该小时末尾附近存在有效分钟数据时取最后一条，否则为 `-100.0` |
| `temperature_max` | float | 小时最高气温 | 当前 `write_hour_data()` 设计要写入该字段 |
| `temperature_min` | float | 小时最低气温 | 当前 `write_hour_data()` 设计要写入该字段 |
| `humidity` | float | 整点湿度 | 仅当该小时末尾附近存在有效分钟数据时取最后一条，否则为 `-100.0` |
| `pressure` | float | 整点气压 | 仅当该小时末尾附近存在有效分钟数据时取最后一条，否则为 `-100.0` |
| `hourly_rainfall` | float | 小时雨量 | 设计上表示该小时累计降雨量 |
| `max_instantaneous_rainfall` | float | 小时最大分钟雨量 | 该小时内 `instantaneous_rainfall` 的最大值 |
| `max_wind_level` | float/int | 小时最大风力 | 设计上表示该小时内最大风级 |
| `wind_speed_2min` | float | 整点前 2 分钟平均风速 | 设计上对应整点前 2 分钟风速平均 |
| `wind_angle_2min` | float | 整点前 2 分钟平均风向角 | 设计上对应整点前 2 分钟风向角平均 |
| `wind_direction_2min` | string | 整点前 2 分钟平均风向 | 设计上对应整点前 2 分钟中文风向 |
| `wind_speed_10min` | float | 整点前 10 分钟平均风速 | 设计上对应整点前 10 分钟风速平均 |
| `wind_angle_10min` | float | 整点前 10 分钟平均风向角 | 设计上对应整点前 10 分钟风向角平均 |
| `wind_direction_10min` | string | 整点前 10 分钟平均风向 | 设计上对应整点前 10 分钟中文风向 |

## 小时统计计算结果中的扩展字段

除了上面的“设计写库字段”，`write_hour_data.py` 中的 `process()` 和 `process_hour_stats()` 还会计算一批扩展字段。这些字段当前会出现在小时统计结果字典中，但 **并没有全部被 `write_hour_data()` 写入 `weather_1h`**。

### 1. 整点风场字段

| 字段名 | 含义 |
| --- | --- |
| `instant_speed` | 整点附近最近一条分钟记录的瞬时风速 |
| `instant_level` | 整点附近最近一条分钟记录的瞬时风级 |
| `instant_angle` | 整点附近最近一条分钟记录的瞬时风向角 |
| `instant_direction` | 整点附近最近一条分钟记录的瞬时风向 |
| `avg_speed_2m` | 整点前 2 分钟平均风速 |
| `avg_level_2m` | 整点前 2 分钟平均风级 |
| `avg_angle_2m` | 整点前 2 分钟平均风向角 |
| `avg_direction_2m` | 整点前 2 分钟平均风向 |
| `avg_speed_10m` | 整点前 10 分钟平均风速 |
| `avg_level_10m` | 整点前 10 分钟平均风级 |
| `avg_angle_10m` | 整点前 10 分钟平均风向角 |
| `avg_direction_10m` | 整点前 10 分钟平均风向 |

### 2. 小时极值及出现时间字段

| 字段名 | 含义 |
| --- | --- |
| `max_temperature` | 小时最高气温 |
| `max_temperature_time` | 小时最高气温出现时间 |
| `min_temperature` | 小时最低气温 |
| `min_temperature_time` | 小时最低气温出现时间 |
| `max_humidity` | 小时最高湿度 |
| `max_humidity_time` | 小时最高湿度出现时间 |
| `min_humidity` | 小时最低湿度 |
| `min_humidity_time` | 小时最低湿度出现时间 |
| `max_pressure` | 小时最高气压 |
| `max_pressure_time` | 小时最高气压出现时间 |
| `min_pressure` | 小时最低气压 |
| `min_pressure_time` | 小时最低气压出现时间 |
| `max_instantaneous_rainfall` | 小时最大分钟雨量 |
| `max_instantaneous_rainfall_time` | 小时最大分钟雨量出现时间 |
| `max_wind` | 小时最大风速 |
| `max_wind_time` | 小时最大风速出现时间 |
| `max_level` | 小时最大风速对应风级 |
| `max_direction` | 小时最大风速对应风向 |
| `max_angle` | 小时最大风速对应风向角 |

### 3. 当前代码中的命名差异

`write_hour_data.process()` 计算出的部分字段名，与 `write_hour_data.write_hour_data()` 设计写入的字段名并不完全一致。当前代码里主要有这些差异：

| 统计结果字段 | 设计写库字段 | 说明 |
| --- | --- | --- |
| `hourly_total_rainfall` | `hourly_rainfall` | 含义一致，名称不同 |
| `avg_speed_2m` | `wind_speed_2min` | 含义一致，名称不同 |
| `avg_angle_2m` | `wind_angle_2min` | 含义一致，名称不同 |
| `avg_direction_2m` | `wind_direction_2min` | 含义一致，名称不同 |
| `avg_speed_10m` | `wind_speed_10min` | 含义一致，名称不同 |
| `avg_angle_10m` | `wind_angle_10min` | 含义一致，名称不同 |
| `avg_direction_10m` | `wind_direction_10min` | 含义一致，名称不同 |
| `max_temperature` / `min_temperature` | `temperature_max` / `temperature_min` | 含义一致，名称不同 |
| `max_level` | `max_wind_level` | 含义接近，但当前代码没有做统一映射 |

如果后续需要把 `process()` 的结果完整写入 `weather_1h`，建议在写库前先做一次字段名映射。

## 查询结果中的 `time` 列说明

`query_data.py` 查询出的 DataFrame 中，`time` 列格式是：

```text
YYYYMMDD HH:MM:SS
```

例如：

```text
20260403 00:59:00
```

这是查询接口返回给 Python 的本地时间字符串格式，不是 InfluxDB 内部存储时的 UTC 原始格式。
