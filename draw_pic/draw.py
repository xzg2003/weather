# -*- coding: utf-8 -*-
import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from influxdb_client import InfluxDBClient
from collections import defaultdict
from zoneinfo import ZoneInfo

matplotlib.rcParams['font.sans-serif'] = ['SimHei']
matplotlib.rcParams['axes.unicode_minus'] = False


def _to_float_array(s: pd.Series) -> np.ndarray:
    return pd.to_numeric(s, errors="coerce").astype(float).to_numpy()


def _pick_series(df: pd.DataFrame, candidates: list[str]) -> pd.Series:
    for c in candidates:
        if c in df.columns:
            return df[c]
    return pd.Series(dtype=float)


def _safe_savefig(fig, output_path: str, dpi: int = 150):
    try:
        fig.savefig(output_path, dpi=dpi, bbox_inches="tight")
    except BaseException as exc:
        if exc.__class__.__name__ == "Done":
            fig.savefig(output_path, dpi=dpi)
        else:
            raise


def generate_windbarb(
    start_time: str,
    end_time: str,
    output_path: str = "static/windbarb.png",
    db_level: str = "minute",
):
    url = "http://47.114.121.245:8086"
    token = "gYOZtC9oKJjoHkjIKMVxbeOuSoX2dsTfGvTKtaERmVN7b3FcecbqWAzJEyLb_uNSzRhFqpas9YcGzvgmajTjIA=="
    org = "USTC"

    if db_level == "hour":
        bucket = "weather_1h"
        measurement = "weather"
        speed_2m_fields = ["wind_speed_2min", "avg_speed_2m"]
        angle_2m_fields = ["wind_angle_2min", "avg_angle_2m"]
        speed_10m_fields = ["wind_speed_10min", "avg_speed_10m"]
        angle_10m_fields = ["wind_angle_10min", "avg_angle_10m"]
    else:
        bucket = "weather_1m"
        measurement = "weather"
        speed_2m_fields = ["avg_speed_2m"]
        angle_2m_fields = ["avg_angle_2m"]
        speed_10m_fields = ["avg_speed_10m"]
        angle_10m_fields = ["avg_angle_10m"]

    client = InfluxDBClient(url=url, token=token, org=org)
    query_api = client.query_api()

    query = f'''
from(bucket: "{bucket}")
  |> range(start: {start_time}, stop: {end_time})
  |> filter(fn: (r) => r._measurement == "{measurement}")
'''
    tables = query_api.query(query, org=org)

    data_map = defaultdict(dict)
    for table in tables:
        for record in table.records:
            ts = record.get_time()
            field = record.get_field()
            value = record.get_value()
            data_map[ts][field] = value

    if len(data_map) == 0:
        client.close()
        raise ValueError("No data returned. 数据库中没有该区间的数据！")

    rows = []
    for ts in sorted(data_map.keys()):
        row = {"time": ts}
        row.update(data_map[ts])
        rows.append(row)

    df = pd.DataFrame(rows)

    df["time"] = pd.to_datetime(df["time"], utc=True, errors="coerce")
    df = df.sort_values("time").reset_index(drop=True)

    tz = ZoneInfo("Asia/Shanghai")
    times_local = df["time"].dt.tz_convert(tz)

    inst_s = _to_float_array(_pick_series(df, ["instant_speed"]))
    inst_d = _to_float_array(_pick_series(df, ["instant_angle"]))

    avg2m_s = _to_float_array(_pick_series(df, speed_2m_fields))
    avg2m_d = _to_float_array(_pick_series(df, angle_2m_fields))
    avg10m_s = _to_float_array(_pick_series(df, speed_10m_fields))
    avg10m_d = _to_float_array(_pick_series(df, angle_10m_fields))

    fig, ax = plt.subplots(figsize=(14, 3.2))

    start_local = pd.to_datetime(start_time, utc=True).tz_convert(tz)
    end_local = pd.to_datetime(end_time, utc=True).tz_convert(tz)
    ax.set_xlim(start_local, end_local)

    ax.plot(times_local, inst_s, color="gray", lw=1.2, label="瞬时风", zorder=2)
    ax.plot(times_local, avg2m_s, color="orange", lw=2.0, label="2min平均风", zorder=2)
    ax.plot(times_local, avg10m_s, color="green", lw=2.2, label="10min平均风", zorder=2)

    # ===== barbs：x 转 mdates 浮点；过滤 NaN/inf =====
    valid1 = np.isfinite(inst_s) & np.isfinite(inst_d) & (inst_s > 0) & times_local.notna().to_numpy()
    x1 = mdates.date2num(times_local[valid1].dt.tz_localize(None).to_numpy())
    y1 = np.asarray(inst_s[valid1], dtype=float)
    u1 = np.asarray(inst_s[valid1] * np.sin(np.deg2rad(inst_d[valid1])), dtype=float)
    v1 = np.asarray(inst_s[valid1] * np.cos(np.deg2rad(inst_d[valid1])), dtype=float)
    m1 = np.isfinite(x1) & np.isfinite(y1) & np.isfinite(u1) & np.isfinite(v1)
    if np.any(m1):
        ax.barbs(x1[m1], y1[m1], u1[m1], v1[m1], length=8, barbcolor="gray", linewidth=1, alpha=0.85, zorder=5)

    valid2 = np.isfinite(avg2m_s) & np.isfinite(avg2m_d) & (avg2m_s > 0) & times_local.notna().to_numpy()
    x2 = mdates.date2num(times_local[valid2].dt.tz_localize(None).to_numpy())
    y2 = np.asarray(avg2m_s[valid2], dtype=float)
    u2 = np.asarray(avg2m_s[valid2] * np.sin(np.deg2rad(avg2m_d[valid2])), dtype=float)
    v2 = np.asarray(avg2m_s[valid2] * np.cos(np.deg2rad(avg2m_d[valid2])), dtype=float)
    m2 = np.isfinite(x2) & np.isfinite(y2) & np.isfinite(u2) & np.isfinite(v2)
    if np.any(m2):
        ax.barbs(x2[m2], y2[m2], u2[m2], v2[m2], length=8, barbcolor="orange", linewidth=1, alpha=0.8, zorder=5)

    valid3 = np.isfinite(avg10m_s) & np.isfinite(avg10m_d) & (avg10m_s > 0) & times_local.notna().to_numpy()
    x3 = mdates.date2num(times_local[valid3].dt.tz_localize(None).to_numpy())
    y3 = np.asarray(avg10m_s[valid3], dtype=float)
    u3 = np.asarray(avg10m_s[valid3] * np.sin(np.deg2rad(avg10m_d[valid3])), dtype=float)
    v3 = np.asarray(avg10m_s[valid3] * np.cos(np.deg2rad(avg10m_d[valid3])), dtype=float)
    m3 = np.isfinite(x3) & np.isfinite(y3) & np.isfinite(u3) & np.isfinite(v3)
    if np.any(m3):
        ax.barbs(x3[m3], y3[m3], u3[m3], v3[m3], length=8, barbcolor="green", linewidth=1, alpha=0.8, zorder=5)

    ax.set_ylabel("风速 (m/s)", fontsize=11)
    ax.set_title("风羽图（北京时间 UTC+8）", fontsize=12)
    ax.legend(loc="upper left", fontsize=10)
    ax.grid(True, linestyle="--", alpha=0.25)

    # ===== x 轴刻度：根据区间长度动态调整，避免重叠 =====
    span_seconds = (end_local - start_local).total_seconds()
    span_minutes = span_seconds / 60.0
    span_hours = span_minutes / 60.0
    span_days = span_hours / 24.0

    if span_minutes <= 60:  # <= 1小时
        locator = mdates.MinuteLocator(interval=5, tz=tz)
        formatter = mdates.DateFormatter("%H:%M", tz=tz)
        rotation = 0
    elif span_hours <= 6:   # 1~6小时
        locator = mdates.MinuteLocator(interval=15, tz=tz)
        formatter = mdates.DateFormatter("%H:%M", tz=tz)
        rotation = 0
    elif span_hours <= 24:  # 6~24小时
        locator = mdates.HourLocator(interval=1, tz=tz)
        formatter = mdates.DateFormatter("%m-%d %H:%M", tz=tz)
        rotation = 30
    elif span_days <= 7:    # 1~7天
        locator = mdates.HourLocator(interval=6, tz=tz)
        formatter = mdates.DateFormatter("%m-%d %H:%M", tz=tz)
        rotation = 30
    elif span_days <= 31:   # 1~31天
        locator = mdates.DayLocator(interval=1, tz=tz)
        formatter = mdates.DateFormatter("%m-%d", tz=tz)
        rotation = 30
    else:                   # > 31天
        locator = mdates.WeekdayLocator(interval=1, tz=tz)
        formatter = mdates.DateFormatter("%Y-%m-%d", tz=tz)
        rotation = 30

    ax.xaxis.set_major_locator(locator)
    ax.xaxis.set_major_formatter(formatter)

    # 兜底：尽量不要让主刻度太多（不会覆盖 locator 类型）
    ax.locator_params(axis="x", nbins=10)

    plt.xticks(rotation=rotation)

    ymax = np.nanmax([np.nanmax(inst_s), np.nanmax(avg2m_s), np.nanmax(avg10m_s)])
    if np.isfinite(ymax) and ymax > 0:
        ax.set_ylim(0, ymax * 1.2)
    else:
        ax.set_ylim(0, 1)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    plt.tight_layout()
    _safe_savefig(fig, output_path, dpi=150)
    plt.close(fig)
    client.close()

    return output_path