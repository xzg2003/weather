from flask import Flask, render_template, request, send_file, jsonify
from datetime import datetime, timezone, timedelta
from draw import generate_windbarb
from draw_temp_dewpoint import generate_temp_dewpoint
from draw_humidity import generate_humidity_chart
from draw_pressure import generate_pressure_chart
from draw_rain import generate_rain_chart
import os
import traceback

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

@app.route("/windbarb")
def windbarb():
    start_utc, end_utc, db_level, err = _validate_and_convert()
    if err: return err
    try:
        output_path = "static/windbarb.png"
        generate_windbarb(start_utc, end_utc, output_path, db_level=db_level)
        if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            return jsonify({"error": "image not generated"}), 500
        return send_file(output_path, mimetype="image/png")
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
        output_path = "static/temp_dewpoint.png"
        generate_temp_dewpoint(start_utc, end_utc, output_path, db_level=db_level)
        if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            return jsonify({"error": "image not generated"}), 500
        return send_file(output_path, mimetype="image/png")
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
        output_path = "static/humidity.png"
        generate_humidity_chart(start_utc, end_utc, output_path, db_level=db_level)
        if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            return jsonify({"error": "image not generated"}), 500
        return send_file(output_path, mimetype="image/png")
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
        output_path = "static/pressure.png"
        generate_pressure_chart(start_utc, end_utc, output_path, db_level=db_level)
        if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            return jsonify({"error": "image not generated"}), 500
        return send_file(output_path, mimetype="image/png")
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
        output_path = "static/rain.png"
        generate_rain_chart(start_utc, end_utc, output_path, db_level=db_level)
        if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            return jsonify({"error": "image not generated"}), 500
        return send_file(output_path, mimetype="image/png")
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