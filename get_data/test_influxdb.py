"""
InfluxDB 连接测试脚本
用于验证 InfluxDB 配置是否正确
"""

import os
import sys
from datetime import datetime
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

# 读取配置
INFLUXDB_URL = os.getenv('INFLUXDB_URL', 'http://localhost:8086')
INFLUXDB_TOKEN = os.getenv('INFLUXDB_TOKEN', 'ln7NNOLrHk8y8w0KjE3nzR_qEXQBLANoZJMFPdMxsznISkpR1hOZt_CaZ0juIYU7Fwjft34NrO7061koydqolg==')
INFLUXDB_ORG = os.getenv('INFLUXDB_ORG', 'USTC')
INFLUXDB_BUCKET = os.getenv('INFLUXDB_BUCKET', 'weather_1s')

def test_connection():
    """测试 InfluxDB 连接"""
    print("=" * 50)
    print("InfluxDB 连接测试")
    print("=" * 50)
    print(f"\n配置信息：")
    print(f"  URL: {INFLUXDB_URL}")
    print(f"  Organization: {INFLUXDB_ORG}")
    print(f"  Bucket: {INFLUXDB_BUCKET}")
    print(f"  Token: {INFLUXDB_TOKEN[:20]}..." if len(INFLUXDB_TOKEN) > 20 else f"  Token: {INFLUXDB_TOKEN}")
    print()

    # 检查配置
    if INFLUXDB_TOKEN == 'your-token-here':
        print("❌ 错误：请先在 config.env 中配置正确的 Token")
        print("   1. 访问 http://localhost:8086")
        print("   2. 完成初始化配置")
        print("   3. 复制 Token 到 config.env 文件")
        return False

    try:
        # 连接 InfluxDB
        print("正在连接 InfluxDB...")
        client = InfluxDBClient(
            url=INFLUXDB_URL,
            token=INFLUXDB_TOKEN,
            org=INFLUXDB_ORG
        )

        # 测试连接
        health = client.health()
        if health.status == "pass":
            print("✓ InfluxDB 连接成功！")
            print(f"  版本: {health.version}")
        else:
            print(f"❌ InfluxDB 健康检查失败: {health.status}")
            return False

        # 测试写入数据
        print("\n正在测试写入数据...")
        write_api = client.write_api(write_options=SYNCHRONOUS)

        test_point = Point("weather") \
            .tag("location", "test_station") \
            .field("temperature", 25.5) \
            .field("humidity", 60.0) \
            .field("pressure", 1013) \
            .time(datetime.utcnow())

        write_api.write(bucket=INFLUXDB_BUCKET, record=test_point)
        print("✓ 测试数据写入成功！")

        # 测试查询数据
        print("\n正在测试查询数据...")
        query_api = client.query_api()
        query = f'''
        from(bucket: "{INFLUXDB_BUCKET}")
          |> range(start: -1h)
          |> filter(fn: (r) => r["_measurement"] == "weather")
          |> filter(fn: (r) => r["location"] == "test_station")
          |> limit(n: 1)
        '''

        result = query_api.query(query=query)
        if result:
            print("✓ 数据查询成功！")
            print(f"  查询到 {len(result)} 个表")
        else:
            print("⚠ 查询结果为空（这是正常的，如果这是首次测试）")

        # 关闭连接
        client.close()

        print("\n" + "=" * 50)
        print("✓ 所有测试通过！InfluxDB 配置正确！")
        print("=" * 50)
        print("\n现在可以运行 weather_collector.py 开始采集数据了。")
        return True

    except Exception as e:
        print(f"\n❌ 连接失败: {e}")
        print("\n请检查：")
        print("  1. InfluxDB 是否正在运行（运行 influxdb/start_influxdb.bat）")
        print("  2. Token 是否正确")
        print("  3. Organization 和 Bucket 名称是否正确")
        print("  4. 防火墙是否阻止了连接")
        return False

if __name__ == "__main__":
    success = test_connection()
    sys.exit(0 if success else 1)
