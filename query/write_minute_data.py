# 将分钟数据写入分钟数据库
from __future__ import annotations

import logging
import math
import os
import sys
from datetime import datetime, timedelta, timezone
from numbers import Real

from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS
from ultils import *
from merge_minute_data import merge_minute_data

#INFLUXDB_URL = os.getenv("INFLUXDB_URL", "http://localhost:8086")
#INFLUXDB_TOKEN = os.getenv(
#    "INFLUXDB_TOKEN",
#    "ln7NNOLrHk8y8w0KjE3nzR_qEXQBLANoZJMFPdMxsznISkpR1hOZt_CaZ0juIYU7Fwjft34NrO7061koydqolg==",
#)
INFLUXDB_URL = os.getenv("INFLUXDB_URL", "http://47.114.121.245:8086")
INFLUXDB_TOKEN = os.getenv(
    "INFLUXDB_TOKEN",
    "gYOZtC9oKJjoHkjIKMVxbeOuSoX2dsTfGvTKtaERmVN7b3FcecbqWAzJEyLb_uNSzRhFqpas9YcGzvgmajTjIA==",
)
INFLUXDB_ORG = os.getenv("INFLUXDB_ORG", "USTC")
INFLUXDB_BUCKET = os.getenv("INFLUXDB_BUCKET", "weather_1m")
MEASUREMENT = "weather"
LOCATION_TAG_KEY = "location"
LOCATION_TAG_VALUE = "station_1"
LOCAL_TIMEZONE = datetime.now().astimezone().tzinfo or timezone(timedelta(hours=8))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("weather_data.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


def _iter_fields(minute_data: dict):
    for key, value in minute_data.items():
        if key == "time" or value is None:
            continue

        if isinstance(value, str):
            yield key, value
            continue

        if isinstance(value, Real) and not isinstance(value, bool):
            numeric = float(value)
            if math.isnan(numeric):
                continue
            yield key, numeric


def _delete_existing_minute_data(
    client: InfluxDBClient,
    minute_time,
    bucket_name: str,
) -> None:
    start_time = normalize_time(minute_time)
    stop_time = get_time_before(start_time, seconds_before=-1)
    predicate = (
        f'_measurement="{MEASUREMENT}" AND '
        f'{LOCATION_TAG_KEY}="{LOCATION_TAG_VALUE}"'
    )

    client.delete_api().delete(
        start=to_utc(start_time),
        stop=to_utc(stop_time),
        predicate=predicate,
        bucket=bucket_name,
        org=INFLUXDB_ORG,
    )


def write_minute_data(
    minute_data: dict,
    bucket_name: str = INFLUXDB_BUCKET,
    overwrite: bool = True,
) -> bool:
    if "time" not in minute_data:
        raise ValueError("minute_data 必须包含 time 字段")

    client = None
    try:
        client = InfluxDBClient(
            url=INFLUXDB_URL,
            token=INFLUXDB_TOKEN,
            org=INFLUXDB_ORG,
        )
        write_api = client.write_api(write_options=SYNCHRONOUS)

        if overwrite:
            _delete_existing_minute_data(client, minute_data["time"], bucket_name)

        point = Point(MEASUREMENT).tag(LOCATION_TAG_KEY, LOCATION_TAG_VALUE)
        for key, value in _iter_fields(minute_data):
            point = point.field(key, value)
        point = point.time(to_utc(minute_data["time"]))

        write_api.write(bucket=bucket_name, record=point)
        logger.info(f"分钟数据写入成功: {minute_data['time']}")
        return True
    except Exception as exc:
        logger.error(f"分钟数据写入失败: {exc}")
        return False
    finally:
        if client is not None:
            client.close()


def build_minute_data(minute_str: str) -> dict:
    normalized_time = normalize_time(minute_str)
    minute_data = merge_minute_data(normalized_time)
    minute_data["time"] = normalized_time
    return minute_data

def process(
    minute_str: str,
    write: bool = True,
    bucket_name: str = INFLUXDB_BUCKET,
) -> dict:
    minute_data = build_minute_data(minute_str)

    if write:
        write_minute_data(minute_data, bucket_name=bucket_name)
    return minute_data


if __name__ == "__main__":
    args = [arg for arg in sys.argv[1:] if arg != "--no-write"]
    write = True
    for i in range(60):
        target_time = f'2026-04-03 00:{i}'
        result = process(target_time, write=write)
    #for key, value in result.items():
    #    print(f"{key}: {value}")
