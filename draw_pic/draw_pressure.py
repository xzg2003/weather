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
#matplotlib.rcParams["font.sans-serif"] = ["Noto Sans CJK SC"]
#matplotlib.rcParams["axes.unicode_minus"] = False

BJ_TZ = ZoneInfo("Asia/Shanghai")
PLOT_LAYOUT = {"left": 0.075, "right": 0.94, "top": 0.86, "bottom": 0.22}

def _to_float_array(s: pd.Series) -> np.ndarray:
    return pd.to_numeric(s, errors="coerce").astype(float).to_numpy()

def _safe_savefig(fig, output_path: str, dpi: int = 150):
    try:
        fig.savefig(output_path, dpi=dpi)
    except BaseException as exc:
        if exc.__class__.__name__ == "Done":
            fig.savefig(output_path, dpi=dpi)
        else:
            raise

def _set_padded_xlim(ax, start_local, end_local):
    span_seconds = max((end_local - start_local).total_seconds(), 60.0)
    x_pad = pd.Timedelta(seconds=max(span_seconds * 0.04, 30.0))
    ax.set_xlim(start_local - x_pad, end_local + x_pad)

def _apply_smart_time_axis(ax, start_time: str, end_time: str, tz=BJ_TZ):
    start_local = pd.to_datetime(start_time, utc=True).tz_convert(tz)
    end_local = pd.to_datetime(end_time, utc=True).tz_convert(tz)

    span_seconds = (end_local - start_local).total_seconds()
    span_minutes = span_seconds / 60.0
    span_hours = span_minutes / 60.0
    span_days = span_hours / 24.0

    if span_minutes <= 60:
        locator = mdates.MinuteLocator(interval=5, tz=tz)
        formatter = mdates.DateFormatter("%H:%M", tz=tz)
        rotation = 0
    elif span_hours <= 6:
        locator = mdates.HourLocator(interval=1, tz=tz)
        formatter = mdates.DateFormatter("%H:%M", tz=tz)
        rotation = 0
    elif span_hours <= 12:
        locator = mdates.HourLocator(interval=2, tz=tz)
        formatter = mdates.DateFormatter("%m-%d %H:%M", tz=tz)
        rotation = 35
    elif span_hours <= 24:
        locator = mdates.HourLocator(interval=4, tz=tz)
        formatter = mdates.DateFormatter("%m-%d %H:%M", tz=tz)
        rotation = 35
    elif span_days <= 7:
        locator = mdates.HourLocator(interval=8, tz=tz)
        formatter = mdates.DateFormatter("%m-%d %H:%M", tz=tz)
        rotation = 35
    elif span_days <= 31:
        locator = mdates.DayLocator(interval=1, tz=tz)
        formatter = mdates.DateFormatter("%m-%d", tz=tz)
        rotation = 30
    else:
        locator = mdates.WeekdayLocator(interval=1, tz=tz)
        formatter = mdates.DateFormatter("%Y-%m-%d", tz=tz)
        rotation = 30

    ax.xaxis.set_major_locator(locator)
    ax.xaxis.set_major_formatter(formatter)
    ax.locator_params(axis="x", nbins=10)
    plt.xticks(rotation=rotation)

def generate_pressure_chart(
    start_time: str,
    end_time: str,
    output_path: str = "static/pressure.png",
    db_level: str = "minute",
):
    url = "http://47.114.121.245:8086"
    token = "gYOZtC9oKJjoHkjIKMVxbeOuSoX2dsTfGvTKtaERmVN7b3FcecbqWAzJEyLb_uNSzRhFqpas9YcGzvgmajTjIA=="
    org = "USTC"

    if db_level == "hour":
        bucket = "weather_1h"
        measurement = "weather"  # ✅ 修正：小时库 measurement
    else:
        bucket = "weather_1m"
        measurement = "weather"

    client = InfluxDBClient(url=url, token=token, org=org)
    query_api = client.query_api()

    query = f'''
from(bucket: "{bucket}")
  |> range(start: {start_time}, stop: {end_time})
  |> filter(fn: (r) => r._measurement == "{measurement}")
  |> filter(fn: (r) => r._field == "pressure")
'''
    tables = query_api.query(query, org=org)

    data_map = defaultdict(dict)
    for table in tables:
        for record in table.records:
            ts = record.get_time()
            data_map[ts]["pressure"] = record.get_value()

    if len(data_map) == 0:
        client.close()
        raise ValueError("No data returned. 数据库中没有该区间的 pressure 数据！")

    rows = []
    for ts in sorted(data_map.keys()):
        rows.append({"time": ts, **data_map[ts]})

    df = pd.DataFrame(rows)
    if "pressure" not in df.columns:
        df["pressure"] = np.nan

    df["time"] = pd.to_datetime(df["time"], utc=True, errors="coerce")
    df = df.sort_values("time").reset_index(drop=True)
    times_local = df["time"].dt.tz_convert(BJ_TZ)

    pressure = _to_float_array(df["pressure"]).copy()
    pressure = np.where(np.isclose(pressure, -100.0, atol=1e-6), np.nan, pressure)

    fig, ax = plt.subplots(figsize=(14, 3.2))

    start_local = pd.to_datetime(start_time, utc=True).tz_convert(BJ_TZ)
    end_local = pd.to_datetime(end_time, utc=True).tz_convert(BJ_TZ)
    _set_padded_xlim(ax, start_local, end_local)

    ax.plot(times_local, pressure, color="#000000", lw=1.6, label="压强")

    if np.any(np.isfinite(pressure)):
        ymin = float(np.nanmin(pressure))
        ymax = float(np.nanmax(pressure))
        pad = (ymax - ymin) * 0.15 if ymax > ymin else 1.0
        ax.set_ylim(ymin - pad, ymax + pad)

    # ===== 方案1：按像素间隔防重叠标注 =====
    fig.canvas.draw()
    min_px = 30
    last_x_px = None
    for i in range(len(times_local)):
        if not np.isfinite(pressure[i]):
            continue
        xdata = mdates.date2num(times_local.iloc[i].to_pydatetime())
        x_px = ax.transData.transform((xdata, float(pressure[i])))[0]
        if last_x_px is None or (x_px - last_x_px) >= min_px:
            ax.annotate(
                f"{pressure[i]:.1f}",
                xy=(times_local.iloc[i], float(pressure[i])),
                xytext=(0, 8),
                textcoords="offset points",
                ha="center",
                fontsize=8,
                color="#000000",
                clip_on=True,
                bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="none", alpha=0.6),
            )
            last_x_px = x_px

    ax.set_ylabel("气压", fontsize=11, fontproperties=zh_font)
    ax.set_title("压强（北京时间 UTC+8）", fontsize=12, fontproperties=zh_font)
    ax.legend(loc="upper left", fontsize=10, prop=zh_font)
    ax.grid(True, linestyle="--", alpha=0.3)

    # ✅ 动态 x 轴刻度
    _apply_smart_time_axis(ax, start_time, end_time, tz=BJ_TZ)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig.subplots_adjust(**PLOT_LAYOUT)
    _safe_savefig(fig, output_path, dpi=150)
    plt.close(fig)
    client.close()

    return output_path
