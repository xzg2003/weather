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

def _to_float_array(s: pd.Series) -> np.ndarray:
    return pd.to_numeric(s, errors="coerce").astype(float).to_numpy()

def _safe_savefig(fig, output_path: str, dpi: int = 150):
    try:
        fig.savefig(output_path, dpi=dpi, bbox_inches="tight")
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
        locator = mdates.MinuteLocator(interval=15, tz=tz)
        formatter = mdates.DateFormatter("%H:%M", tz=tz)
        rotation = 0
    elif span_hours <= 24:
        locator = mdates.HourLocator(interval=1, tz=tz)
        formatter = mdates.DateFormatter("%m-%d %H:%M", tz=tz)
        rotation = 30
    elif span_days <= 7:
        locator = mdates.HourLocator(interval=6, tz=tz)
        formatter = mdates.DateFormatter("%m-%d %H:%M", tz=tz)
        rotation = 30
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

def generate_rain_chart(
    start_time: str,
    end_time: str,
    output_path: str = "static/rain.png",
    db_level: str = "minute",
):
    url = "http://47.114.121.245:8086"
    token = "gYOZtC9oKJjoHkjIKMVxbeOuSoX2dsTfGvTKtaERmVN7b3FcecbqWAzJEyLb_uNSzRhFqpas9YcGzvgmajTjIA=="
    org = "USTC"

    if db_level == "hour":
        bucket = "weather_1h"
        measurement = "weather"
        field = "hourly_total_rainfall"
        title = "小时雨量（北京时间 UTC+8）"
        y_label = "雨量 (mm)"
        bar_label = "小时雨量"
        is_hour = True
    else:
        bucket = "weather_1m"
        measurement = "weather"
        field = "instantaneous_rainfall"
        title = "分雨 / 时次累计（北京时间 UTC+8）"
        y_label = "分雨 (mm)"
        bar_label = "分雨"
        line_label = "时次累计"
        is_hour = False

    client = InfluxDBClient(url=url, token=token, org=org)
    query_api = client.query_api()

    query = f'''
from(bucket: "{bucket}")
  |> range(start: {start_time}, stop: {end_time})
  |> filter(fn: (r) => r._measurement == "{measurement}")
  |> filter(fn: (r) => r._field == "{field}")
'''
    tables = query_api.query(query, org=org)

    data_map = defaultdict(dict)
    for table in tables:
        for record in table.records:
            ts = record.get_time()
            data_map[ts][field] = record.get_value()

    if len(data_map) == 0:
        client.close()
        raise ValueError("No data returned. 数据库中没有该区间的降雨数据！")

    rows = []
    for ts in sorted(data_map.keys()):
        rows.append({"time": ts, field: data_map[ts].get(field)})

    df = pd.DataFrame(rows)
    df["time"] = pd.to_datetime(df["time"], utc=True, errors="coerce")
    df[field] = pd.to_numeric(df[field], errors="coerce")
    df = df.dropna(subset=["time"]).sort_values("time").reset_index(drop=True)

    times_local = df["time"].dt.tz_convert(BJ_TZ)

    rain = _to_float_array(df[field]).copy()
    rain = np.where(np.isclose(rain, -100.0, atol=1e-6), np.nan, rain)
    rain = np.where(np.isfinite(rain) & (rain < 0), 0.0, rain)

    # 按小时分组累计，每到整点重置为0
    cum = np.zeros(len(rain))
    current_cum = 0.0
    prev_dh = None
    for i in range(len(rain)):
        val = rain[i] if np.isfinite(rain[i]) else 0.0
        t = times_local.iloc[i]
        this_dh = (t.year, t.month, t.day, t.hour)
        if prev_dh is not None and this_dh != prev_dh:
            current_cum = 0.0
        current_cum += val
        cum[i] = current_cum
        prev_dh = this_dh

    fig, ax = plt.subplots(figsize=(14, 3.2))

    start_local = pd.to_datetime(start_time, utc=True).tz_convert(BJ_TZ)
    end_local = pd.to_datetime(end_time, utc=True).tz_convert(BJ_TZ)
    ax.set_xlim(start_local, end_local)

    if len(times_local) >= 2:
        dx = (mdates.date2num(times_local.iloc[1]) - mdates.date2num(times_local.iloc[0]))
        width = max(dx * 0.5, 0.0005) if is_hour else max(dx * 0.8, 0.0005)
    else:
        width = 0.01

    ax.bar(times_local, np.nan_to_num(rain, nan=0.0), width=width, color="#1E88E5", alpha=0.85, label=bar_label)

    max_rain = float(np.nanmax(rain)) if np.any(np.isfinite(rain)) else 0.0
    ax.set_ylim(0, max(1.0, max_rain * 1.2))

    if not is_hour:
        ax2 = ax.twinx()
        ax2.plot(times_local, cum, color="#263238", lw=1.6, label=line_label)
        max_cum = float(np.nanmax(cum)) if len(cum) else 0.0
        ax2.set_ylim(0, max(1.0, max_cum * 1.2))
        ax2.set_ylabel("累计 (mm)", fontsize=11, fontproperties=zh_font)
        lines, labels = ax.get_legend_handles_labels()
        lines2, labels2 = ax2.get_legend_handles_labels()
        ax.legend(lines + lines2, labels + labels2, loc="upper left", fontsize=10, prop=zh_font)

        # 根据查询区间长度动态计算标注间隔（分钟）
        span_minutes = (end_local - start_local).total_seconds() / 60.0
        span_hours = span_minutes / 60.0
        span_days = span_hours / 24.0
        if span_minutes <= 60:
            label_interval_min = 2
        elif span_hours <= 3:
            label_interval_min = 4
        elif span_hours <= 12:
            label_interval_min = 7
        elif span_hours <= 24:
            label_interval_min = 12
        elif span_days <= 7:
            label_interval_min = 45
        else:
            label_interval_min = 120

        last_label_time = None
        for i in range(len(times_local)):
            val = cum[i]
            if val <= 0 or not np.isfinite(val):
                continue
            t = times_local.iloc[i]
            # 在每小时重置前的峰值强制标注
            is_peak = (i < len(times_local) - 1 and cum[i + 1] < cum[i])
            if last_label_time is not None:
                dt_min = (t - last_label_time).total_seconds() / 60.0
                if dt_min < label_interval_min and not is_peak:
                    continue
            ax2.annotate(
                f"{val:.1f}",
                xy=(mdates.date2num(t.to_pydatetime()), float(val)),
                xycoords=ax2.transData,
                xytext=(0, 5),
                textcoords="offset points",
                ha="center", va="bottom",
                fontsize=9, color="#263238",
                clip_on=True,
                bbox=dict(boxstyle="round,pad=0.1", fc="white", ec="none", alpha=0.7),
            )
            last_label_time = t
    else:
        ax.legend(loc="upper left", fontsize=10, prop=zh_font)

    ax.set_ylabel(y_label, fontsize=11, fontproperties=zh_font)
    ax.set_title(title, fontsize=12, fontproperties=zh_font)
    ax.grid(True, linestyle="--", alpha=0.3)

    fig.canvas.draw()
    for i in range(len(times_local)):
        if not (np.isfinite(rain[i]) and rain[i] > 0):
            continue
        ax.annotate(
            f"{rain[i]:.1f}",
            xy=(times_local.iloc[i], float(rain[i])),
            xytext=(0, 5),
            textcoords="offset points",
            ha="center", va="bottom",
            fontsize=8,
            color="#1E88E5",
            clip_on=True,
            bbox=dict(boxstyle="round,pad=0.1", fc="white", ec="none", alpha=0.6),
        )

    # ✅ 动态 x 轴刻度（对 ax 生效）
    _apply_smart_time_axis(ax, start_time, end_time, tz=BJ_TZ)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    plt.tight_layout()
    _safe_savefig(fig, output_path, dpi=150)
    plt.close(fig)
    client.close()
    return output_path