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
zh_font = matplotlib.font_manager.FontProperties(fname="Arial_Unicode_MS.ttf")
#matplotlib.rcParams['font.sans-serif'] = ["Noto Sans CJK SC"]
#matplotlib.rcParams['axes.unicode_minus'] = False
PLOT_LAYOUT = {"left": 0.075, "right": 0.94, "top": 0.86, "bottom": 0.22}

def _to_float_array(s: pd.Series) -> np.ndarray:
    return pd.to_numeric(s, errors="coerce").astype(float).to_numpy()


def _pick_series(df: pd.DataFrame, candidates: list[str]) -> pd.Series:
    for c in candidates:
        if c in df.columns:
            return df[c]
    return pd.Series(dtype=float)


def _safe_savefig(fig, output_path: str, dpi: int = 150):
    try:
        fig.savefig(output_path, dpi=dpi)
    except BaseException as exc:
        if exc.__class__.__name__ == "Done":
            fig.savefig(output_path, dpi=dpi)
        else:
            raise


def _finite_max(*arrays: np.ndarray) -> float:
    finite_values = []
    for arr in arrays:
        arr = np.asarray(arr, dtype=float)
        finite = arr[np.isfinite(arr)]
        if finite.size:
            finite_values.append(float(np.nanmax(finite)))
    return max(finite_values) if finite_values else np.nan


def _set_padded_xlim(ax, start_local, end_local):
    span_seconds = max((end_local - start_local).total_seconds(), 60.0)
    x_pad = pd.Timedelta(seconds=max(span_seconds * 0.04, 30.0))
    ax.set_xlim(start_local - x_pad, end_local + x_pad)


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
    max_s = _to_float_array(_pick_series(df, ["max_speed", "max_wind"]))
    max_d = _to_float_array(_pick_series(df, ["max_angle"]))
    avg2m_s = _to_float_array(_pick_series(df, speed_2m_fields))
    avg2m_d = _to_float_array(_pick_series(df, angle_2m_fields))
    avg10m_s = _to_float_array(_pick_series(df, speed_10m_fields))
    avg10m_d = _to_float_array(_pick_series(df, angle_10m_fields))

    fig, ax = plt.subplots(figsize=(14, 3.2))

    start_local = pd.to_datetime(start_time, utc=True).tz_convert(tz)
    end_local = pd.to_datetime(end_time, utc=True).tz_convert(tz)
    _set_padded_xlim(ax, start_local, end_local)

    ax.plot(times_local, inst_s, color="gray", lw=1.2, label="瞬时风", zorder=2)
    ax.plot(times_local, max_s, color="red", lw=1.2, label="极大风", zorder=2)
    ax.plot(times_local, avg2m_s, color="orange", lw=2.0, label="2min平均风", zorder=2)
    ax.plot(times_local, avg10m_s, color="green", lw=2.2, label="10min平均风", zorder=2)

    # ===== barbs：x 转 mdates 浮点；过滤 NaN/inf =====
    # 中国气象标准：短划=2m/s, 长划=4m/s, 三角旗=20m/s
    barb_inc = {'half': 2, 'full': 4, 'flag': 20}
    barb_step = 1 if db_level == "hour" else 2
    valid1 = np.isfinite(inst_s) & np.isfinite(inst_d) & (inst_s > 0) & times_local.notna().to_numpy()
    x1 = np.asarray(mdates.date2num(times_local[valid1].to_numpy()), dtype=float)
    y1 = np.asarray(inst_s[valid1], dtype=float)
    u1 = np.asarray(inst_s[valid1] * np.sin(np.deg2rad(inst_d[valid1])), dtype=float)
    v1 = np.asarray(inst_s[valid1] * np.cos(np.deg2rad(inst_d[valid1])), dtype=float)
    m1 = np.isfinite(x1) & np.isfinite(y1) & np.isfinite(u1) & np.isfinite(v1)
    if np.any(m1):
        ax.barbs(x1[m1][::barb_step], y1[m1][::barb_step], u1[m1][::barb_step], v1[m1][::barb_step],
                 length=7, barbcolor="gray", linewidth=0.8, alpha=0.7, zorder=5,
                 barb_increments=barb_inc)

    valid2 = np.isfinite(avg2m_s) & np.isfinite(avg2m_d) & (avg2m_s > 0) & times_local.notna().to_numpy()
    x2 = np.asarray(mdates.date2num(times_local[valid2].to_numpy()), dtype=float)
    y2 = np.asarray(avg2m_s[valid2], dtype=float)
    u2 = np.asarray(avg2m_s[valid2] * np.sin(np.deg2rad(avg2m_d[valid2])), dtype=float)
    v2 = np.asarray(avg2m_s[valid2] * np.cos(np.deg2rad(avg2m_d[valid2])), dtype=float)
    m2 = np.isfinite(x2) & np.isfinite(y2) & np.isfinite(u2) & np.isfinite(v2)
    if np.any(m2):
        ax.barbs(x2[m2][::barb_step], y2[m2][::barb_step], u2[m2][::barb_step], v2[m2][::barb_step],
                 length=7, barbcolor="orange", linewidth=0.8, alpha=0.7, zorder=5,
                 barb_increments=barb_inc)

    valid3 = np.isfinite(avg10m_s) & np.isfinite(avg10m_d) & (avg10m_s > 0) & times_local.notna().to_numpy()
    x3 = np.asarray(mdates.date2num(times_local[valid3].to_numpy()), dtype=float)
    y3 = np.asarray(avg10m_s[valid3], dtype=float)
    u3 = np.asarray(avg10m_s[valid3] * np.sin(np.deg2rad(avg10m_d[valid3])), dtype=float)
    v3 = np.asarray(avg10m_s[valid3] * np.cos(np.deg2rad(avg10m_d[valid3])), dtype=float)
    m3 = np.isfinite(x3) & np.isfinite(y3) & np.isfinite(u3) & np.isfinite(v3)
    if np.any(m3):
        ax.barbs(x3[m3][::barb_step], y3[m3][::barb_step], u3[m3][::barb_step], v3[m3][::barb_step],
                 length=7, barbcolor="green", linewidth=0.8, alpha=0.7, zorder=5,
                 barb_increments=barb_inc)

    # 极大风风羽（红色）
    valid_max = np.isfinite(max_s) & np.isfinite(max_d) & (max_s > 0) & times_local.notna().to_numpy()
    x_max = np.asarray(mdates.date2num(times_local[valid_max].to_numpy()), dtype=float)
    y_max = np.asarray(max_s[valid_max], dtype=float)
    u_max = np.asarray(max_s[valid_max] * np.sin(np.deg2rad(max_d[valid_max])), dtype=float)
    v_max = np.asarray(max_s[valid_max] * np.cos(np.deg2rad(max_d[valid_max])), dtype=float)
    m_max = np.isfinite(x_max) & np.isfinite(y_max) & np.isfinite(u_max) & np.isfinite(v_max)
    if np.any(m_max):
        ax.barbs(x_max[m_max][::barb_step], y_max[m_max][::barb_step], u_max[m_max][::barb_step], v_max[m_max][::barb_step],
                 length=7, barbcolor="red", linewidth=0.8, alpha=0.7, zorder=5,
                 barb_increments=barb_inc)

    ax.set_ylabel("风速 (m/s)", fontsize=11, fontproperties=zh_font)
    ax.set_title("风羽图（北京时间 UTC+8）", fontsize=12, fontproperties=zh_font)
    ax.legend(loc="upper left", fontsize=10, prop=zh_font)
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
        locator = mdates.HourLocator(interval=1, tz=tz)
        formatter = mdates.DateFormatter("%H:%M", tz=tz)
        rotation = 0
    elif span_hours <= 12:  # 6~12小时
        locator = mdates.HourLocator(interval=2, tz=tz)
        formatter = mdates.DateFormatter("%m-%d %H:%M", tz=tz)
        rotation = 35
    elif span_hours <= 24:  # 12~24小时
        locator = mdates.HourLocator(interval=4, tz=tz)
        formatter = mdates.DateFormatter("%m-%d %H:%M", tz=tz)
        rotation = 35
    elif span_days <= 7:    # 1~7天
        locator = mdates.HourLocator(interval=8, tz=tz)
        formatter = mdates.DateFormatter("%m-%d %H:%M", tz=tz)
        rotation = 35
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

    ymax = _finite_max(inst_s, avg2m_s, avg10m_s, max_s)
    if np.isfinite(ymax) and ymax > 0:
        lower_pad = max(ymax * 0.12, 0.8)
        upper_pad = max(ymax * 0.35, 1.5)
        ax.set_ylim(-lower_pad, ymax + upper_pad)
    else:
        ax.set_ylim(0, 1)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig.subplots_adjust(**PLOT_LAYOUT)
    _safe_savefig(fig, output_path, dpi=150)
    plt.close(fig)
    client.close()

    return output_path
