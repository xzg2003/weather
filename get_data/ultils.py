from datetime import datetime, timedelta

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
    hour_start = dt.replace(minute=0, second=0)
    return  hour_start.strftime('%Y-%m-%d %H:%M:%S')