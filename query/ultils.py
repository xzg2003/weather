from datetime import datetime, timedelta, timezone


# 按优先级依次尝试的输入格式
_TIME_FORMATS = [
    '%Y-%m-%d %H:%M:%S',  # 2026-03-25 01:00:00
    '%Y-%m-%d %H:%M',     # 2026-03-25 01:00
    '%Y%m%d %H:%M:%S',    # 20260325 01:00:00
    '%Y%m%d %H:%M',       # 20260325 01:00
    '%Y%m%d%H%M%S',       # 20260325010000
    '%Y%m%d%H%M',         # 202603250100
    '%Y%m%d%H',           # 2026032501
    '%Y%m%d',             # 20260325  → 当天 00:00:00
    '%Y-%m-%d',           # 2026-03-25 → 当天 00:00:00
]

def normalize_time(t) -> str:
    """
    将各种格式的时间输入统一转换为 'YYYY-MM-DD HH:MM:SS' 字符串。

    支持的输入类型：
        - datetime 对象
        - 字符串：见 _TIME_FORMATS 列表中所列格式
        - int / float：Unix 时间戳（秒）

    返回:
        格式为 'YYYY-MM-DD HH:MM:SS' 的字符串

    异常:
        ValueError: 无法识别输入格式时抛出
    """
    if isinstance(t, datetime):
        return t.strftime('%Y-%m-%d %H:%M:%S')

    if isinstance(t, (int, float)):
        return datetime.fromtimestamp(t).strftime('%Y-%m-%d %H:%M:%S')

    if isinstance(t, str):
        t = t.strip()
        for fmt in _TIME_FORMATS:
            try:
                return datetime.strptime(t, fmt).strftime('%Y-%m-%d %H:%M:%S')
            except ValueError:
                continue
        raise ValueError(f"无法识别的时间格式: {t!r}")

    raise TypeError(f"不支持的时间类型: {type(t).__name__}")


def crc16(data):
        crc = 0xFFFF
        for pos in data:
            crc ^= pos
            for i in range(8):
                if crc & 1:
                    crc >>= 1
                    crc ^= 0xA001
                else:
                    crc >>= 1
        return crc


def get_time_before(time_str, minutes_before=0, seconds_before=0):
    """
    输入时间 YYYY-MM-DD HH:MM:SS，获取任意分钟前的时刻以及当前的整点小时
    
    参数:
        time_str: 时间字符串，格式为 'YYYY-MM-DD HH:MM:SS'
        minutes_before: 向前推移多少分钟（默认为0）
    
    返回:
        time_before: 指定分钟前的时刻
    """
    # 解析输入时间
    dt = datetime.strptime(time_str, '%Y-%m-%d %H:%M:%S')
    
    # 获取分钟前的时刻
    time_before = dt - timedelta(minutes=minutes_before,seconds=seconds_before)
    
    return time_before.strftime('%Y-%m-%d %H:%M:%S')

def get_hour_start(time_str):
    """
    输入时间 YYYY-MM-DD HH:MM，获取当前的整点小时
    
    参数:
        time_str: 时间字符串，格式为 'YYYY-MM-DD HH:MM'
    
    返回:
        hour_start: 当前的整点小时，格式为 'YYYY-MM-DD HH:00:00'
    """
    # 解析输入时间
    dt = datetime.strptime(time_str, '%Y-%m-%d %H:%M:%S')
    
    # 获取整点小时（将分钟和秒数设为0）
    if dt.minute == 0:
        dt = dt - timedelta(minutes=60)
        hour_start = dt.replace(second=0)
    else:
        hour_start = dt.replace(minute=0,second=0)
    return  hour_start.strftime('%Y-%m-%d %H:%M:%S')

def to_utc(value) -> datetime:
    return datetime.strptime(normalize_time(value),"%Y-%m-%d %H:%M:%S").astimezone(timezone.utc)

def wind_speed_to_scale(speed):
    """
    将风速（m/s）转换为风级（扩展到16级）
    
    参数:
        speed: 风速，单位为 m/s
    
    返回:
        scale: 风级，0-16
    """
    if speed < 0.3:
        return 0
    elif speed < 1.6:
        return 1
    elif speed < 3.4:
        return 2
    elif speed < 5.5:
        return 3
    elif speed < 8.0:
        return 4
    elif speed < 10.8:
        return 5
    elif speed < 13.9:
        return 6
    elif speed < 17.2:
        return 7
    elif speed < 20.8:
        return 8
    elif speed < 24.5:
        return 9
    elif speed < 28.5:
        return 10
    elif speed < 32.7:
        return 11
    elif speed < 37.0:
        return 12
    elif speed < 41.5:
        return 13
    elif speed < 46.2:
        return 14
    elif speed < 51.0:
        return 15
    else:
        return 16


def wind_direction_angle_to_direction(angle):
    """
    将风向角（度数）转换为风向（中文）
    
    参数:
        angle: 风向角，单位为度，0° 为北
    
    返回:
        direction: 风向字符串，如 '北', '东北', '东', '东南', '南', '西南', '西', '西北'
    """
    directions = ['北', '北东北', '东北', '东东北', '东', '东东南', '东南', '南东南', '南', '南西南', '西南', '西西南', '西', '西北西', '西北', '北西北']
    index = round(angle / 22.5) % 16
    return directions[index]