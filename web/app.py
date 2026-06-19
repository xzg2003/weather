import sys
sys.path.append('.')
from flask import Flask, render_template, request, send_file, jsonify
from datetime import datetime, timezone, timedelta
from draw_pic.draw import generate_windbarb
from draw_pic.draw_temp_dewpoint import generate_temp_dewpoint
from draw_pic.draw_humidity import generate_humidity_chart
from draw_pic.draw_pressure import generate_pressure_chart
from draw_pic.draw_rain import generate_rain_chart
import os
import traceback
import csv
import tempfile

try:
    from query.query_data import query_time_range
except Exception:
    query_time_range = None

app = Flask(__name__)
LOCAL_TZ = timezone(timedelta(hours=8))  # 按需修改

def parse_frontend_time(s: str) -> datetime:
    s = (s or "").strip()
    fmts = [
        "%Y-%m-%dT%H:%M",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d %H:%M:%S",
        "%Y/%m/%d %H:%M",
        "%Y/%m/%d %H:%M:%S",
    ]
    for f in fmts:
        try:
            return datetime.strptime(s, f)
        except ValueError:
            continue
    raise ValueError(f"unsupported time format: {s}")

def to_utc_rfc3339(local_naive_dt: datetime) -> str:
    local_dt = local_naive_dt.replace(tzinfo=LOCAL_TZ)
    utc_dt = local_dt.astimezone(timezone.utc)
    return utc_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

def _validate_and_convert():
    start_raw = request.args.get("start", "")
    end_raw = request.args.get("end", "")
    db_level = request.args.get("db", "minute")

    if not start_raw or not end_raw:
        return None, None, None, (jsonify({"error": "missing start/end"}), 400)

    try:
        s_dt = parse_frontend_time(start_raw)
        e_dt = parse_frontend_time(end_raw)
        if s_dt >= e_dt:
            return None, None, None, (jsonify({"error": "start must be earlier than end"}), 400)

        start_utc = to_utc_rfc3339(s_dt)
        end_utc = to_utc_rfc3339(e_dt)
        return start_utc, end_utc, db_level, None
    except ValueError as e:
        return None, None, None, (jsonify({"error": str(e)}), 400)

@app.route("/")
def home():
    return render_template("index.html")

def _safe_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

def _latest_from_csv(csv_path: str):
    if not os.path.exists(csv_path):
        return None

    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        if not rows:
            return None
        return rows[-1]

def _normalize_realtime_payload(raw: dict) -> dict:
    """
    将不同来源（Influx/CSV）的字段统一为前端看板所需键名。
    """
    raw = raw or {}
    return {
        "time": raw.get("time"),
        "temperature": _safe_float(raw.get("temperature")),
        "humidity": _safe_float(raw.get("humidity")),
        "pressure": _safe_float(raw.get("pressure")),
        "wind_speed": _safe_float(raw.get("wind_speed", raw.get("instant_speed"))),
        "avg_speed_2m": _safe_float(raw.get("avg_speed_2m", raw.get("wind_speed_2min"))),
        "avg_speed_10m": _safe_float(raw.get("avg_speed_10m", raw.get("wind_speed_10min"))),
        "wind_direction": raw.get("wind_direction", raw.get("instant_direction")),
        "wind_angle": _safe_float(raw.get("wind_angle", raw.get("instant_angle"))),
        "wind_level": _safe_float(raw.get("wind_level", raw.get("instant_level"))),
        "max_wind_speed": _safe_float(raw.get("max_wind", raw.get("max_speed"))),
        "max_wind_level": _safe_float(raw.get("max_wind_level", raw.get("max_level"))),
        "max_wind_direction": raw.get("max_wind_direction", raw.get("max_direction")),
        "max_wind_angle": _safe_float(raw.get("max_wind_angle", raw.get("max_angle"))),
        "instantaneous_rainfall": _safe_float(raw.get("instantaneous_rainfall")),
        "current_hour_rainfall": _safe_float(raw.get("current_hour_rainfall")),
    }

def _send_generated_png(generator, filename: str, start_utc: str, end_utc: str, db_level: str):
    os.makedirs("static", exist_ok=True)
    tmp = tempfile.NamedTemporaryFile(
        prefix=f"{filename}_",
        suffix=".png",
        dir="static",
        delete=False,
    )
    output_path = tmp.name
    tmp.close()

    generator(start_utc, end_utc, output_path, db_level=db_level)
    if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
        raise RuntimeError("image not generated")

    response = send_file(output_path, mimetype="image/png", max_age=0)
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"

    @response.call_on_close
    def _cleanup_generated_png():
        try:
            os.remove(output_path)
        except OSError:
            pass

    return response

@app.route("/api/realtime")
def api_realtime():
    minutes = request.args.get("minutes", "5")
    try:
        minutes = int(minutes)
        if minutes <= 0:
            raise ValueError("minutes must be positive")
    except ValueError:
        return jsonify({"error": "minutes must be a positive integer"}), 400

    data = None
    source = "csv"

    # 优先从 InfluxDB 查询最近数据；失败时回退到本地 CSV。
    if query_time_range is not None:
        try:
            df = query_time_range(minutes=minutes, bucket_name="weather_1m", method="weather")
            #print(df[['max_angle','max_level']])
            if df is not None and not df.empty:
                latest = df.iloc[0].to_dict()
                data = _normalize_realtime_payload(latest)
                #print(data['max_wind_angle'])
                #source = "influxdb"
        except Exception:
            pass

    if data is None:
        latest = _latest_from_csv("queried_weather_data.csv")
        if latest is None:
            return jsonify({"error": "no realtime data available"}), 404
        data = _normalize_realtime_payload(latest)
        

    return jsonify({
        "ok": True,
        #"source": source,
        "server_time": datetime.now(LOCAL_TZ).strftime("%Y-%m-%d %H:%M:%S"),
        "data": data
    })

@app.route("/windbarb")
def windbarb():
    start_utc, end_utc, db_level, err = _validate_and_convert()
    if err: return err
    try:
        return _send_generated_png(generate_windbarb, "windbarb", start_utc, end_utc, db_level)
    except ValueError as e:
        print("[windbarb] ValueError:", str(e))
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        print("[windbarb] Exception:", str(e))
        traceback.print_exc()
        return jsonify({"error": f"server error: {str(e)}"}), 500

@app.route("/temp_dewpoint")
def temp_dewpoint():
    start_utc, end_utc, db_level, err = _validate_and_convert()
    if err: return err
    try:
        return _send_generated_png(generate_temp_dewpoint, "temp_dewpoint", start_utc, end_utc, db_level)
    except ValueError as e:
        print("[temp_dewpoint] ValueError:", str(e))
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        print("[temp_dewpoint] Exception:", str(e))
        traceback.print_exc()
        return jsonify({"error": f"server error: {str(e)}"}), 500

@app.route("/humidity")
def humidity():
    start_utc, end_utc, db_level, err = _validate_and_convert()
    if err: return err
    try:
        return _send_generated_png(generate_humidity_chart, "humidity", start_utc, end_utc, db_level)
    except ValueError as e:
        print("[humidity] ValueError:", str(e))
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        print("[humidity] Exception:", str(e))
        traceback.print_exc()
        return jsonify({"error": f"server error: {str(e)}"}), 500

@app.route("/pressure")
def pressure():
    start_utc, end_utc, db_level, err = _validate_and_convert()
    if err: return err
    try:
        return _send_generated_png(generate_pressure_chart, "pressure", start_utc, end_utc, db_level)
    except ValueError as e:
        print("[pressure] ValueError:", str(e))
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        print("[pressure] Exception:", str(e))
        traceback.print_exc()
        return jsonify({"error": f"server error: {str(e)}"}), 500

# ✅ 新增：分雨图
@app.route("/rain")
def rain():
    start_utc, end_utc, db_level, err = _validate_and_convert()
    if err: return err
    try:
        return _send_generated_png(generate_rain_chart, "rain", start_utc, end_utc, db_level)
    except ValueError as e:
        print("[rain] ValueError:", str(e))
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        print("[rain] Exception:", str(e))
        traceback.print_exc()
        return jsonify({"error": f"server error: {str(e)}"}), 500

if __name__ == "__main__":
    os.makedirs("static", exist_ok=True)
    app.run(host="0.0.0.0", port=8000, debug=True)
