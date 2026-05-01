"""
查询离当前时间最近的分钟数据，作为实况数据。
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd

from query_data import query_time_range
from ultils import normalize_time

DEFAULT_BUCKET = "weather_1m"
DEFAULT_MEASUREMENT = "weather"
DEFAULT_SEARCH_MINUTES = 10000
DEFAULT_STALE_MINUTES = 10
DB_TIME_FORMAT = "%Y%m%d %H:%M:%S"

def query_live_data(
    target_time=None,
    search_minutes: int = DEFAULT_SEARCH_MINUTES,
    stale_minutes: int = DEFAULT_STALE_MINUTES,
    bucket_name: str = DEFAULT_BUCKET,
    method: str = DEFAULT_MEASUREMENT,
    verbose: bool = False,
) -> dict | None:
    """
    查询离 target_time 最近的一条分钟数据，作为实况数据。

    参数:
        target_time: 目标时间，默认使用当前时间
        search_minutes: 向前查询最近多少分钟的数据
        stale_minutes: 超过多少分钟认为实况数据不新鲜
        bucket_name: InfluxDB bucket 名称
        method: measurement 名称
        verbose: 是否打印 query_time_range 的详细日志
    """
    if search_minutes <= 0:
        raise ValueError("search_minutes 必须为正整数")
    if stale_minutes < 0:
        raise ValueError("stale_minutes 不能小于 0")
    df = None
    
    if target_time is None:
        target_time = datetime.now()
        target_dt = normalize_time(target_time)
        df = query_time_range(
            minutes=search_minutes,
            verbose=verbose,
            bucket_name=bucket_name,
            method=method,
        )
    else:
        target_dt = normalize_time(target_time)
        start_dt = target_dt - timedelta(minutes=search_minutes)
        end_dt = target_dt + timedelta(minutes=search_minutes)
        df = query_time_range(
            start=start_dt.strftime("%Y-%m-%d %H:%M:%S"),
            end=end_dt.strftime("%Y-%m-%d %H:%M:%S"),
            verbose=verbose,
            bucket_name=bucket_name,
            method=method,
        )
    
    if df is not None:
        return df.iloc[0]
    else:
        return None


def process(
    search_minutes: int = DEFAULT_SEARCH_MINUTES,
    stale_minutes: int = DEFAULT_STALE_MINUTES,
    bucket_name: str = DEFAULT_BUCKET,
    method: str = DEFAULT_MEASUREMENT,
    verbose: bool = False,
) -> dict | None:
    return query_live_data(
        search_minutes=search_minutes,
        stale_minutes=stale_minutes,
        bucket_name=bucket_name,
        method=method,
        verbose=verbose,
    )


if __name__ == "__main__":
    result = process(verbose=True)
    if result is None:
        print("未查询到可用的实况数据")
    else:
        print("实况数据:")
        for key, value in result.items():
            print(f"  {key}: {value}")
