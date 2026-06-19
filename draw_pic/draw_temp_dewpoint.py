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

BJ_TZ = ZoneInfo("Asia/Shanghai")
PLOT_LAYOUT = {"left": 0.075, "right": 0.94, "top": 0.86, "bottom": 0.22}

def _to_float_array(s: pd.Series) -> np.ndarray:
    return pd.to_numeric(s, errors="coerce").astype(float).to_numpy()

def _calc_dewpoint(temp_c: np.ndarray, rh: np.ndarray) -> np.ndarray:
    a = 17.27
    b = 237.7
    rh = np.clip(rh, 0.1, 100.0)
    alpha = ((a * temp_c) / (b + temp_c)) + np.log(rh / 100.0)
    dew = (b * alpha) / (a - alpha)
    return dew

def _set_padded_xlim(ax, start_local, end_local):
    span_seconds = max((end_local - start_local).total_seconds(), 60.0)
    x_pad = pd.Timedelta(seconds=max(span_seconds * 0.04, 30.0))
    ax.set_xlim(start_local - x_pad, end_local + x_pad)

def _safe_savefig(fig, output_path: str, dpi: int = 150):
    try:
        fig.savefig(output_path, dpi=dpi)
    except BaseException as exc:
        if exc.__class__.__name__ == "Done":
            fig.savefig(output_path, dpi=dpi)
        else:
            raise

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

def generate_temp_dewpoint(
    start_time: str,
    end_time: str,
    output_path: str = "static/temp_dewpoint.png",
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
  |> filter(fn: (r) => r._field == "temperature" or r._field == "humidity")
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
    if "temperature" not in df.columns:
        df["temperature"] = np.nan
    if "humidity" not in df.columns:
        df["humidity"] = np.nan

    df["time"] = pd.to_datetime(df["time"], utc=True, errors="coerce")
    df = df.sort_values("time").reset_index(drop=True)
    times_local = df["time"].dt.tz_convert(BJ_TZ)

    temp = _to_float_array(df["temperature"]).copy()
    rh = _to_float_array(df["humidity"]).copy()

    invalid_temp = np.isclose(temp, -100.0, atol=1e-6)
    temp = np.where(invalid_temp, np.nan, temp)
    rh = np.where(invalid_temp, np.nan, rh)

    dew = _calc_dewpoint(temp, rh)

    fig, ax = plt.subplots(figsize=(14, 3.2))

    start_local = pd.to_datetime(start_time, utc=True).tz_convert(BJ_TZ)
    end_local = pd.to_datetime(end_time, utc=True).tz_convert(BJ_TZ)
    _set_padded_xlim(ax, start_local, end_local)

    ax.plot(times_local, temp, color="#ff7f0e", lw=1.6, label="气温")
    ax.plot(times_local, dew, color="#7e57c2", lw=1.6, label="露温")

    all_vals = np.concatenate([temp[np.isfinite(temp)], dew[np.isfinite(dew)]])
    if all_vals.size > 0:
        ymin, ymax = float(np.nanmin(all_vals)), float(np.nanmax(all_vals))
        yrange = max(1e-6, ymax - ymin)
        pad = max(0.6, yrange * 0.3)
        ax.set_ylim(ymin - pad, ymax + pad)

    # ===== 方案1：按像素间隔防重叠标注 =====
    fig.canvas.draw()
    min_px = 30
    last_x_px = None
    for i in range(len(times_local)):
        if not np.isfinite(temp[i]) and not np.isfinite(dew[i]):
            continue

        y_for_px = float(temp[i]) if np.isfinite(temp[i]) else float(dew[i])
        xdata = mdates.date2num(times_local.iloc[i].to_pydatetime())
        x_px = ax.transData.transform((xdata, y_for_px))[0]

        if last_x_px is None or (x_px - last_x_px) >= min_px:
            if np.isfinite(temp[i]):
                ax.annotate(
                    f"{temp[i]:.1f}",
                    xy=(times_local.iloc[i], float(temp[i])),
                    xytext=(0, 8),
                    textcoords="offset points",
                    ha="center",
                    fontsize=8,
                    color="#ff7f0e",
                    clip_on=True,
                    bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="none", alpha=0.6),
                )
            if np.isfinite(dew[i]):
                ax.annotate(
                    f"{dew[i]:.1f}",
                    xy=(times_local.iloc[i], float(dew[i])),
                    xytext=(0, -10),
                    textcoords="offset points",
                    ha="center",
                    fontsize=8,
                    color="#7e57c2",
                    clip_on=True,
                    bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="none", alpha=0.6),
                )
            last_x_px = x_px

    ax.set_ylabel("气温 (°C)", fontsize=11, fontproperties=zh_font)
    ax.set_title("气温 / 露温（北京时间 UTC+8）", fontsize=12, fontproperties=zh_font)
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
