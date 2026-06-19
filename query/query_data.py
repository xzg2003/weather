"""
查询 InfluxDB 中的气象数据
"""

from influxdb_client import InfluxDBClient
from datetime import datetime, timedelta, timezone
import pandas as pd

# 使用你的配置
INFLUXDB_URL = "http://47.114.121.245:8086"
INFLUXDB_TOKEN = "gYOZtC9oKJjoHkjIKMVxbeOuSoX2dsTfGvTKtaERmVN7b3FcecbqWAzJEyLb_uNSzRhFqpas9YcGzvgmajTjIA=="
INFLUXDB_ORG = "USTC"

def query_time_range(start=None, end=None, minutes=None,  verbose=False, \
                     bucket_name='wind_sock_1s',method='wind'):
    """
    查询指定时间范围的数据，精确到分钟

    参数:
        start: 开始时间，字符串格式 'YYYY-MM-DD HH:MM' 或 datetime 对象（本地时间）
        end:   结束时间，字符串格式 'YYYY-MM-DD HH:MM' 或 datetime 对象（本地时间），默认为当前时间
        minutes: 若不指定 start/end，则查询最近多少分钟的数据
        limit: 限制返回的记录数
        verbose: 是否打印详细信息

    示例:
        query_time_range(minutes=30)                          # 最近30分钟
        query_time_range(start='2025-01-01 08:00')            # 从指定时间到现在
        query_time_range(start='2025-01-01 08:00', end='2025-01-01 09:30')  # 指定区间
    """
    try:
        # 解析时间参数
        fmt = '%Y-%m-%d %H:%M:%S'

        if minutes is not None:
            range_str = f"start: -{minutes}m"
            range_desc = f"最近 {minutes} 分钟"
        elif start is not None:
            if isinstance(start, str):
                start = datetime.strptime(start, fmt).astimezone(timezone.utc)
            else:
                start = start.astimezone(timezone.utc)

            if end is not None:
                if isinstance(end, str):
                    end = datetime.strptime(end, fmt).astimezone(timezone.utc)
                else:
                    end = end.astimezone(timezone.utc)
                range_str = f'start: {start.strftime("%Y-%m-%dT%H:%M:%SZ")}, stop: {end.strftime("%Y-%m-%dT%H:%M:%SZ")}'
                range_desc = f'{start.astimezone().strftime(fmt)} ~ {end.astimezone().strftime(fmt)}'
            else:
                range_str = f'start: {start.strftime("%Y-%m-%dT%H:%M:%SZ")}'
                range_desc = f'{start.astimezone().strftime(fmt)} ~ 现在'
        else:
            range_str = "start: -1h"
            range_desc = "最近 1 小时"

        if verbose:
            print("=" * 60)
            print("查询 InfluxDB 气象数据")
            print("=" * 60)
            print(f"\n连接信息：")
            print(f"  URL: {INFLUXDB_URL}")
            print(f"  Organization: {INFLUXDB_ORG}")
            print(f"  Bucket: {bucket_name}")
            print(f"  查询时间范围: {range_desc}\n")

        # 连接 InfluxDB
        client = InfluxDBClient(
            url=INFLUXDB_URL,
            token=INFLUXDB_TOKEN,
            org=INFLUXDB_ORG
        )

        # 构建查询
        query = f'''
        from(bucket: "{bucket_name}")
          |> range({range_str})
          |> filter(fn: (r) => r["_measurement"] == "{method}")
          |> sort(columns: ["_time"], desc: true)
        '''

        if verbose:
            print("正在查询数据...\n")

        query_api = client.query_api()
        tables = query_api.query(query=query)

        if not tables:
            if verbose:
                print("❌ 未查询到数据")
                print("\n可能的原因：")
                print("  1. 数据采集程序还未运行")
                print("  2. 串口连接失败，未采集到数据")
                print("  3. 数据写入失败")
                print("\n建议：")
                print("  - 检查 weather_data.log 日志文件")
                print("  - 确认串口设备已连接")
                print("  - 运行 python weather_collector.py 开始采集")
            client.close()
            return None

        # 收集数据到字典
        data_dict = {}
        for table in tables:
            for record in table.records:
                time_utc = record.get_time()
                # 转换为本地时间
                time_local = time_utc.astimezone()
                # 格式化为 YYYYMMDD HH:MM:SS
                time_str = time_local.strftime('%Y%m%d %H:%M:%S')
                field = record.get_field()
                value = record.get_value()

                # 使用时间作为键，构建每个时间点的数据
                if time_str not in data_dict:
                    data_dict[time_str] = {'time': time_str}

                data_dict[time_str][field] = value

        # 转换为 DataFrame
        df = pd.DataFrame(list(data_dict.values()))
        
        # 确保列的顺序
        #columns = ['time']
        # 添加所有可能的字段
        #possible_fields = [
        #    'temperature', 'humidity', 'pressure','wind_angle','wind_direction', 'wind_speed', 'wind_level',
        #    'instantaneous_rainfall', 'current_hour_rainfall', 'previous_hour_rainfall',
        #]
        #for col in possible_fields:
        #    if col in df.columns:
        #        columns.append(col)
        #df = df[columns]

        # 按时间排序（降序，最新的在前）
        df = df.sort_values('time', ascending=False).reset_index(drop=True)

        if verbose:
            print("✓ 查询成功！\n")
            #print(df.to_string())
            print(f"\n共查询到 {len(df)} 条记录")
            print("\n✓ 数据库运行正常！")

        client.close()
        #df.to_csv("queried_weather_data.csv", index=False)
        return df

    except Exception as e:
        if verbose:
            print(f"\n❌ 查询失败: {e}")
            print("\n请检查：")
            print("  1. InfluxDB 是否正在运行")
            print("  2. Token 是否正确")
            print("  3. Organization 和 Bucket 名称是否正确")
        return None

if __name__ == "__main__":
    print("=" * 60)
    print("气象数据查询")
    print("=" * 60)
    print("时间格式: YYYY-MM-DD HH:MM（例如 2025-01-01 08:00）")
    print("直接回车跳过表示使用当前时间\n")

    start_input = input("请输入开始时间: ").strip()
    end_input   = input("请输入结束时间: ").strip()

    start = start_input if start_input else None
    end   = end_input   if end_input   else None

    df = query_time_range(start=start, end=end, verbose=True, \
                          bucket_name='weather_1m',method='weather')
    #print(df['avg_direction_2m'],df['instant_direction'])
    if df is not None:
        df[['avg_angle_10m','avg_angle_2m','instant_angle','max_angle','max_wind_time']]\
            .to_csv("queried_weather_data.csv", index=False)
        print(f"\n数据已保存至 queried_weather_data.csv")
