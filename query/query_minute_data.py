# 获取分钟级别的数据
from query_data import query_time_range
from ultils import *
if __name__=="__main__":
    start = '2026-04-03 00:00'
    end = '2026-04-03 01:00' 
    df = query_time_range(start=normalize_time(start), end=normalize_time(end), \
                          bucket_name='weather_1m', method='weather')
    print(df)