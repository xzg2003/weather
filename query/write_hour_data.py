"""
查询 InfluxDB 中的气象数据
"""
import logging
import os
from influxdb_client import InfluxDBClient
from datetime import datetime, timezone, timedelta
import pandas as pd
from query_data import *
from ultils import *
# 使用你的配置
INFLUXDB_URL = "http://localhost:8086"
INFLUXDB_TOKEN = "ln7NNOLrHk8y8w0KjE3nzR_qEXQBLANoZJMFPdMxsznISkpR1hOZt_CaZ0juIYU7Fwjft34NrO7061koydqolg=="
INFLUXDB_ORG = "USTC"
INFLUXDB_BUCKET = os.getenv("INFLUXDB_BUCKET", "weather_1h")
MISSING_VALUE = -100.0

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('weather_data.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def write_hour_data(hour_data: dict):
    """
    将一条小时数据写入 weather_1h bucket

    参数:
        hour_data: 包含小时统计字段的字典，必须包含 'time'（datetime 对象，UTC）
    """
    from influxdb_client import Point
    from influxdb_client.client.write_api import SYNCHRONOUS
    import math

    BUCKET_1H = "weather_1h"

    try:
        client = InfluxDBClient(
            url=INFLUXDB_URL,
            token=INFLUXDB_TOKEN,
            org=INFLUXDB_ORG
        )
        write_api = client.write_api(write_options=SYNCHRONOUS)

        point = Point("weather_hour").tag("location", "station_1")

        float_fields = [
            'temperature', 'temperature_max', 'temperature_min',
            'humidity', 'pressure',
            'hourly_rainfall', 'max_instantaneous_rainfall',
            'max_wind_level',
            'wind_speed_2min', 'wind_angle_2min',
            'wind_speed_10min', 'wind_angle_10min',
        ]
        str_fields = ['wind_direction_2min', 'wind_direction_10min']

        for f in float_fields:
            val = hour_data.get(f)
            if val is not None and not (isinstance(val, float) and math.isnan(val)):
                point = point.field(f, float(val))

        for f in str_fields:
            val = hour_data.get(f)
            if val is not None:
                point = point.field(f, str(val))

        point = point.time(hour_data['time'])

        write_api.write(bucket=BUCKET_1H, record=point)
        logger.info(f"小时数据写入成功: {hour_data['time']}")
        client.close()
        return True
    except Exception as e:
        logger.error(f"小时数据写入失败: {e}")
        return False

def _has_59min_data(df: pd.DataFrame, end_dt: str, tolerance_minutes: int = 2) -> bool:
    """检查区间内是否存在接近整点（59分）的数据"""
    end_dt = normalize_time(end_dt)
    cutoff = get_time_before(end_dt, minutes_before=tolerance_minutes)
    return not df[df['time'] >= cutoff].empty

def _get_lastest_data(df: pd.DataFrame, col: str, end_dt: str):
    """获取最近的数据"""
    has_59 = _has_59min_data(df, end_dt)
    if has_59:
        last = df.iloc[0]
        val = last[col] if col in df.columns else MISSING_VALUE
        return val
    else:
        return MISSING_VALUE

def _process_thp(df: pd.DataFrame,end_dt: str) -> dict:
    """
    温湿压模块：
    - 若存在59min数据，取第一条作为整点值
    - 若不存在，整点值返回 -100
    """
    result = {}
    for col in ('temperature', 'humidity', 'pressure'):
        result[col] = _get_lastest_data(df, col, end_dt)

    return result

def _process_rainfall(df: pd.DataFrame) -> dict:
    """
    单独处理小时雨量数据

    逻辑：
    1. 若整个小时无有效数据，返回 hourly_rainfall=-100, max_instantaneous_rainfall=-100
    2. 若不存在 59min 数据但小时内有数据，取离整点最近的 current_hour_rainfall 作为整点雨量
    3. 只要小时内有 instantaneous_rainfall，就提取最大瞬时降水
    """
    result = {}

    has_rain_col = 'current_hour_rainfall' in df.columns
    has_inst_col = 'instantaneous_rainfall' in df.columns

    if not has_rain_col and not has_inst_col:
        return {'hourly_rainfall': -100.0, 'max_instantaneous_rainfall': -100.0}

    if has_rain_col:
        valid_mask = (
            df['current_hour_rainfall'].notna() &
            (df['current_hour_rainfall'] >= 0) &
            (df['current_hour_rainfall'] != -100.0)
        )
        valid_rain = df[valid_mask].copy()
        last = valid_rain.iloc[0]
        result['hourly_total_rainfall'] = last['current_hour_rainfall']

    return result

def _process_wind(df: pd.DataFrame, end_dt: str) -> dict:
    """
    获取离整点最近的平均风速、风向数据，作为小时整点的风速、风向数据。
    """
    result = {}
    for col in ('instant_speed','instant_level','instant_angle','instant_direction',\
                'avg_speed_2m', 'avg_level_2m', 'avg_angle_2m','avg_direction_2m',\
                'avg_speed_10m', 'avg_level_10m','avg_angle_10m','avg_direction_10m'):
        result[col] = _get_lastest_data(df, col, end_dt)

    return result

def _get_extremes_with_time(df: pd.DataFrame, col: str, label: str, addition_cols: dict = {},
                            target_time_col:str = 'time', get_min: bool = False) -> dict:
    """
    提取指定列的极值及出现时间，并可在最大值出现时刻附带读取其他列的值。

    参数:
        df:             含 time_dt 列的 DataFrame
        col:            主要分析列名
        label:          结果键前缀
        addition_cols: 在最大值行额外读取的列，格式 {结果键: 源列名}
        get_min:        是否同时提取最小值（默认 True）

    返回 dict 键名：
        {label}_max / {label}_max_time
        {label}_min / {label}_min_time  （get_min=True 时）
        addition_cols 中指定的各键（若对应列存在且值有效）
    """
    result = {}
    if col not in df.columns:
        result[f'max_{label}'] = MISSING_VALUE
        result[f'max_{label}_time'] = None
        if get_min:
            result[f'min_{label}'] = MISSING_VALUE
            result[f'min_{label}_time'] = None
    
        return result

    valid = df[[col, target_time_col]].dropna(subset=[col])
    valid = valid[valid[col] != -100.0]
    if valid.empty:
        return result

    max_idx = valid[col].idxmax()
    result[f'max_{label}']      = valid.loc[max_idx, col]
    result[f'max_{label}_time'] = valid.loc[max_idx, target_time_col]

    if get_min:
        min_idx = valid[col].idxmin()
        result[f'min_{label}']      = valid.loc[min_idx, col]
        result[f'min_{label}_time'] = valid.loc[min_idx, target_time_col]
    
    for col, label in addition_cols.items():
        if col in df.columns:
            val = df.loc[max_idx, col]
            if pd.notna(val) and val != -100.0:
                result[f'max_{label}'] = val
            else:
                result[f'max_{label}'] = MISSING_VALUE

    return result


def process_hour_stats(hour_str: str) -> dict | None:
    """
    提取一个小时区间内的气象统计数据（含出现时间）。

    参数:
        hour_str: 10 位字符串，格式 'YYYYMMDDHH'，表示该小时整点时刻。
                  例如 '2026032501' 表示查询 2026-03-25 00:00 ~ 01:00 的数据。

    返回字段:
        max_temperature / max_temperature_time  -- 小时最高气温及出现时间
        min_temperature / min_temperature_time  -- 小时最低气温及出现时间
        max_humidity    / max_humidity_time     -- 小时最高湿度及出现时间
        min_humidity    / min_humidity_time     -- 小时最低湿度及出现时间
        max_pressure    / max_pressure_time     -- 小时最高气压及出现时间
        min_pressure    / min_pressure_time     -- 小时最低气压及出现时间
        max_instantaneous_rainfall              -- 最大分钟雨量（最大分雨）
        max_instantaneous_rainfall_time         -- 最大分雨出现时间
        max_speed                          -- 小时最大风速
        max_level                          -- 小时最大风力
        max_direction                      -- 最大风力出现时的风向
        max_angle                          -- 最大风力出现时的风向角
        max_wind_time                     -- 最大风速出现时间
    """
    end = normalize_time(hour_str)
    start = get_hour_start(end)
    print(f"查询时间范围: {start} ~ {end}")

    df = query_time_range(start=start, end=end, bucket_name='weather_1m', method='weather')
    if df is None or df.empty:
        logger.warning(f"时间段 {start} ~ {end} 无数据，跳过处理")
        return None

    df = df.sort_values('time', ascending=False).reset_index(drop=True)

    result = {'hour': hour_str}

    # ── 温湿压最高/最低及出现时间 ─────────────────────────────────────────
    for col in ('temperature', 'humidity', 'pressure'):
        result.update(_get_extremes_with_time(df, col, col, get_min=True))

    # ── 小时总雨量 & 最大分雨（含出现时间）────────────────────────────────
    result.update(_get_extremes_with_time(df, 'instantaneous_rainfall', 'instantaneous_rainfall'))

    # ── 最大风力、风向及出现时间 ─────────────────────────────────────────
    wind_res = _get_extremes_with_time(df, 'max_speed', 'wind', target_time_col='max_wind_time',\
                addition_cols={'max_level': 'level', 'max_direction': 'direction', 'max_angle': 'angle'})
    result.update(wind_res)

    return result

def process(hour_str: str):
    """
    处理一个小时区间的原始数据，提取各项小时统计量，并写入 weather_1h。

    参数:
        hour_str: 10位字符串，格式 'YYYYMMDDHH'，表示该小时的整点时刻。
                  例如 '2026032501' 表示查询 2026-03-25 00:00 ~ 01:00 的数据，
                  整点时刻记录时间戳为 2026-03-25 01:00。

    提取的字段:
        temperature          -- 整点气温（区间内最后一条记录，如 01:59）
        humidity             -- 整点湿度（区间内最后一条记录）
        pressure             -- 整点气压（区间内最后一条记录）
        hourly_total_rainfall      -- 小时雨量（区间内最后一条 current_hour_rainfall）
        intant_level      -- 整点风级
        intant_speed      -- 整点风速
        intant_angle      -- 整点风向角
        intant_direction  -- 整点风向（中文）
        avg_level_2m      -- 整点前 2 分钟内平均风级
        avg_speed_2m      -- 整点前 2 分钟内平均风速
        avg_angle_2m      -- 整点前 2 分钟内平均风向角
        avg_direction_2m  -- 整点前 2 分钟内平均风向（中文）
        avg_level_10m     -- 整点前 10 分钟内平均风级
        avg_speed_10m     -- 整点前 10 分钟内平均风速
        avg_angle_10m     -- 整点前 10 分钟内平均风向角
        avg_direction_10m -- 整点前 10 分钟内平均风向（中文）
    """
    end = normalize_time(hour_str)
    start = get_hour_start(end)

    df = query_time_range(start=start, end=end, bucket_name='weather_1m', method='weather')
    if df is None or df.empty:
        logger.warning(f"时间段 {start} ~ {end} 无数据，跳过处理")
        return None

    # 将 time 列解析为 datetime（本地时间），按时间升序排列
    df = df.sort_values('time', ascending=False).reset_index(drop=False)

    # 整点时间戳取 end（如 02:00），存为 UTC
    result = {'time': to_utc(end)}

    # ── 温湿压 & 最高/最低气温 ──────────────────────────────────────────
    result.update(_process_thp(df, end))

    # ── 小时雨量 & 最大瞬时降水 ────────────────────────────────────────
    result.update(_process_rainfall(df))

    # ── 风 ─────────────────────────────────────────────────────────────
    result.update(_process_wind(df, end))

    result.update(process_hour_stats(hour_str))
    logger.info(f"查询成功")
    #write_hour_data(result)
    return result


if __name__ == "__main__":

    result = process('202604030100')
    if result:
        print("\n小时统计结果（含出现时间）：")
        for k, v in result.items():
            print(f"  {k}: {v}")

    
