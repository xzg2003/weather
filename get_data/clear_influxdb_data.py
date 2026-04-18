import os
from influxdb_client import InfluxDBClient
from influxdb_client.client.delete_api import DeleteApi

# InfluxDB配置
INFLUXDB_URL = os.getenv('INFLUXDB_URL', 'http://localhost:8086')
INFLUXDB_TOKEN = os.getenv('INFLUXDB_TOKEN', 'ln7NNOLrHk8y8w0KjE3nzR_qEXQBLANoZJMFPdMxsznISkpR1hOZt_CaZ0juIYU7Fwjft34NrO7061koydqolg==')
INFLUXDB_ORG = os.getenv('INFLUXDB_ORG', 'USTC')
INFLUXDB_BUCKET = os.getenv('INFLUXDB_BUCKET', 'weather_1s')

def clear_weather_data():
    """清除 weather measurement 的所有数据"""
    try:
        client = InfluxDBClient(
            url=INFLUXDB_URL,
            token=INFLUXDB_TOKEN,
            org=INFLUXDB_ORG
        )

        delete_api = client.delete_api()

        # 删除从 1970-01-01 到现在的所有 weather measurement 数据
        start = "1970-01-01T00:00:00Z"
        stop = "2030-01-01T00:00:00Z"

        print(f"正在删除 bucket '{INFLUXDB_BUCKET}' 中 measurement 'weather' 的所有数据...")

        delete_api.delete(
            start=start,
            stop=stop,
            predicate='_measurement="weather"',
            bucket=INFLUXDB_BUCKET,
            org=INFLUXDB_ORG
        )

        print("数据删除成功！")
        print("现在可以重新运行 weather_collector.py 写入新数据了")

        client.close()

    except Exception as e:
        print(f"删除数据失败: {e}")

if __name__ == "__main__":
    print("警告：此操作将删除所有气象数据！")
    confirm = input("确认删除？(输入 yes 继续): ")

    if confirm.lower() == 'yes':
        clear_weather_data()
    else:
        print("操作已取消")
