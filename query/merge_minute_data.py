from __future__ import annotations

import math

import pandas as pd
from query_data import query_time_range
from ultils import *

MISSING_VALUE = -100.0
MIN_VALID_WIND_POINTS_2MIN = 30
MIN_VALID_WIND_POINTS_10MIN = 150

def _query_bucket(start: str, end: str, bucket_name: str, method: str) -> pd.DataFrame:
    df = query_time_range(
        start=start,
        end=end,
        verbose=False,
        bucket_name=bucket_name,
        method=method,
    )
    if df is None or df.empty:
        return pd.DataFrame()
    return df

# 返回时间序列
def _numeric_series(df: pd.DataFrame, column: str) -> pd.Series:
    if df.empty or column not in df.columns:
        return pd.Series(dtype=float)

    series = pd.to_numeric(df[column], errors="coerce").dropna()
    series = series[series != MISSING_VALUE]
    return series.reset_index(drop=True)

# 返回最近的值
def _latest_value(df: pd.DataFrame, column: str) -> float:
    if df.empty or column not in df.columns:
        return MISSING_VALUE

    value = pd.to_numeric(pd.Series([df.iloc[0][column]]), errors="coerce").iloc[0]
    if pd.isna(value) or value == MISSING_VALUE:
        return MISSING_VALUE
    return float(value)

# 保留小数
def _round_value(value: float, digits: int = 1) -> float:
    if value == MISSING_VALUE or pd.isna(value):
        return MISSING_VALUE
    return round(float(value), digits)

def get_wind_angle(time_str: str, id: int) -> dict:
    time_instant = get_time_before(time_str, seconds_before=5)
    time_1m = get_time_before(time_str, minutes_before=1)
    time_2m = get_time_before(time_str, minutes_before=2)
    time_10m = get_time_before(time_str, minutes_before=10)

    wind_sock_instant = _query_bucket(time_instant, time_str, "wind_sock_1s", "wind")
    wind_sock_1m = _query_bucket(time_1m, time_str, "wind_sock_1s", "wind")
    wind_sock_2m = _query_bucket(time_2m, time_str, "wind_sock_1s", "wind")
    wind_sock_10m = _query_bucket(time_10m, time_str, "wind_sock_1s", "wind")

    angles_instant = _numeric_series(wind_sock_instant, "wind_angle")
    angles_1m = _numeric_series(wind_sock_1m, "wind_angle")
    angles_2m = _numeric_series(wind_sock_2m, "wind_angle")
    angles_10m = _numeric_series(wind_sock_10m, "wind_angle")

    if angles_instant.empty:
        instant_angle = MISSING_VALUE
        instant_direction = "未知"
    else:
        instant_angle = _round_value(float(angles_instant.mean()))
        instant_direction = wind_direction_angle_to_direction(instant_angle)

    if angles_1m.empty or id is None:
        max_angle = MISSING_VALUE
        max_direction = "未知"
    else:
        try:
            current_time = normalize_time(wind_sock_1m.loc[id,'time'])
            current_time_instant = get_time_before(current_time, seconds_before=5)
            wind_sock_instant = _query_bucket(current_time_instant,current_time,"wind_sock_1s","wind")
            angle_instant = _numeric_series(wind_sock_instant,"wind_angle")
            max_angle = _round_value(float(angle_instant.mean()))
            max_direction = wind_direction_angle_to_direction(max_angle)
        except Exception:
            max_angle = MISSING_VALUE
            max_direction = "未知"

    if len(angles_2m) > MIN_VALID_WIND_POINTS_2MIN:
        avg_angle_2m = _round_value(float(angles_2m.mean()))
        avg_direction_2m = wind_direction_angle_to_direction(avg_angle_2m)
    else:
        avg_angle_2m = MISSING_VALUE
        avg_direction_2m = "未知"

    if len(angles_10m) > MIN_VALID_WIND_POINTS_10MIN:
        avg_angle_10m = _round_value(float(angles_10m.mean()))
        avg_direction_10m = wind_direction_angle_to_direction(avg_angle_10m)
    else:
        avg_angle_10m = MISSING_VALUE
        avg_direction_10m = "未知"

    return {
        "instant_angle": instant_angle,
        "instant_direction": instant_direction,
        "max_angle": max_angle,
        "max_direction": max_direction,
        "avg_angle_2m": avg_angle_2m,
        "avg_direction_2m": avg_direction_2m,
        "avg_angle_10m": avg_angle_10m,
        "avg_direction_10m": avg_direction_10m,
    }


def get_wind_speed(time_str: str) -> dict:
    time_instant = get_time_before(time_str, seconds_before=5)
    time_1m = get_time_before(time_str, minutes_before=1)
    time_2m = get_time_before(time_str, minutes_before=2)
    time_10m = get_time_before(time_str, minutes_before=10)

    wind_speed_instant = _query_bucket(time_instant, time_str, "wind_speed_1s", "wind")
    wind_speed_1m = _query_bucket(time_1m, time_str, "wind_speed_1s", "wind")
    wind_speed_2m = _query_bucket(time_2m, time_str, "wind_speed_1s", "wind")
    wind_speed_10m = _query_bucket(time_10m, time_str, "wind_speed_1s", "wind")

    speed_instant = _numeric_series(wind_speed_instant, "wind_speed")
    speed_1m = _numeric_series(wind_speed_1m, "wind_speed")
    speed_2m = _numeric_series(wind_speed_2m, "wind_speed")
    speed_10m = _numeric_series(wind_speed_10m, "wind_speed")

    if speed_instant.empty:
        instant_speed = MISSING_VALUE
        instant_level = MISSING_VALUE
    else:
        instant_speed = _round_value(float(speed_instant.mean()))
        instant_level = wind_speed_to_scale(instant_speed)   

    if speed_1m.empty:
        max_speed = MISSING_VALUE
        max_level = MISSING_VALUE
        max_time = str(-100)
        max_idx = None
    else:
        max_speed = MISSING_VALUE
        max_level = MISSING_VALUE
        max_time = str(-100)
        max_idx = None
        # 获取每个时刻的瞬时风力并取最大
        for idx, row in wind_speed_1m.iterrows():
            current_time = normalize_time(row['time'])
            current_time_instant = get_time_before(current_time,seconds_before=5)
            wind_speed_instant = _query_bucket(current_time_instant,current_time,"wind_speed_1s","wind")
            speed_instant = _numeric_series(wind_speed_instant,"wind_speed")
            instant_speed_1 = _round_value(float(speed_instant.mean()))
            if instant_speed_1 > max_speed:
                max_speed = instant_speed_1
                max_idx = idx
                max_time = wind_speed_1m.loc[max_idx,'time']
                max_level = wind_speed_to_scale(max_speed)
            #wind_speed_1m.loc[id,'instant_speed'] = 

    if len(speed_2m) < MIN_VALID_WIND_POINTS_2MIN:
        avg_speed_2m = MISSING_VALUE
        avg_level_2m = MISSING_VALUE
    else:
        avg_speed_2m = _round_value(float(speed_2m.mean()))
        avg_level_2m = wind_speed_to_scale(avg_speed_2m)

    if len(speed_10m) < MIN_VALID_WIND_POINTS_10MIN:
        avg_speed_10m = MISSING_VALUE
        avg_level_10m = MISSING_VALUE
    else:
        avg_speed_10m = _round_value(float(speed_10m.mean()))
        avg_level_10m = wind_speed_to_scale(avg_speed_10m)

    return {
        "instant_speed": instant_speed,
        "instant_level": instant_level,
        "max_speed": max_speed,
        "max_level": max_level,
        "max_wind_time": max_time,
        "avg_speed_2m": avg_speed_2m,
        "avg_level_2m": avg_level_2m,
        "avg_speed_10m": avg_speed_10m,
        "avg_level_10m": avg_level_10m,
    }, max_idx


def get_thp(time_str: str) -> dict:
    time_1m = get_time_before(time_str, minutes_before=1)
    thp = _query_bucket(time_1m, time_str, "thp_1m", "weather")

    temperature = _round_value(_latest_value(thp, "temperature"))
    humidity = _round_value(_latest_value(thp, "humidity"))
    pressure = _round_value(_latest_value(thp, "pressure"))

    return {
        "temperature": temperature,
        "humidity": humidity,
        "pressure": pressure,
    }


def get_rain(time_str: str) -> dict:
    time_1m = get_time_before(time_str, minutes_before=1)
    time_hour = get_hour_start(time_str)

    rain_1m = _query_bucket(time_1m, time_str, "rain_1m", "weather")
    rain_hour = _query_bucket(time_hour, time_str, "rain_1m", "weather")

    instantaneous_rainfall = _round_value(_latest_value(rain_1m, "instantaneous_rainfall"))

    hour_rain = _numeric_series(rain_hour, "instantaneous_rainfall")
    current_hour_rainfall = _round_value(hour_rain.sum()) if not hour_rain.empty else MISSING_VALUE

    return {
        "instantaneous_rainfall": instantaneous_rainfall,
        "current_hour_rainfall": current_hour_rainfall,
    }

def merge_minute_data(time_str: str) -> dict:
    minute_data = {"time": time_str}
    minute_data.update(get_thp(time_str))
    minute_data.update(get_rain(time_str))
    speed, id = get_wind_speed(time_str) 
    minute_data.update(speed)
    minute_data.update(get_wind_angle(time_str, id))
    return minute_data


if __name__ == "__main__":
    merged = merge_minute_data("2026-04-03 00:59:00")
    for key, value in merged.items():
        print(f"{key}: {value}")
