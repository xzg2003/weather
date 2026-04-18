import logging
import os
import threading
from datetime import datetime, timezone
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS
import numpy as np

from sensors.temperature import TemperatureSensor
from sensors.rain import RainSensor
from sensors.windsock import WindSockSensor
from sensors.windspeed import WindSpeedSensor

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('weather_data.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

INFLUXDB_URL = os.getenv('INFLUXDB_URL', 'http://localhost:8086')
INFLUXDB_TOKEN = os.getenv('INFLUXDB_TOKEN', 'ln7NNOLrHk8y8w0KjE3nzR_qEXQBLANoZJMFPdMxsznISkpR1hOZt_CaZ0juIYU7Fwjft34NrO7061koydqolg==')
INFLUXDB_ORG = os.getenv('INFLUXDB_ORG', 'USTC')
INFLUXDB_BUCKET = os.getenv('INFLUXDB_BUCKET', 'weather_1min')

TRIGGER_SECOND = 50


class WeatherStation:
    def __init__(self):
        self._influx_client = None
        self._write_api = None
        self._stop_event = threading.Event()

        self.temp_sensor = TemperatureSensor()
        self.rain_sensor = RainSensor()
        self.windsock_sensor = WindSockSensor()
        self.windspeed_sensor = WindSpeedSensor()

    def _connect_influxdb(self):
        try:
            self._influx_client = InfluxDBClient(
                url=INFLUXDB_URL, token=INFLUXDB_TOKEN, org=INFLUXDB_ORG
            )
            self._write_api = self._influx_client.write_api(write_options=SYNCHRONOUS)
            logger.info("综合 InfluxDB 连接成功")
            return True
        except Exception as e:
            logger.error(f"综合 InfluxDB 连接失败: {e}")
            return False

    def _write_summary(self, data: dict, ts):
        if not self._write_api:
            return
        try:
            point = Point("weather").tag("location", "station_1")
            for key, val in data.items():
                if isinstance(val, str):
                    point = point.field(key, val)
                elif not (isinstance(val, float) and np.isnan(val)):
                    point = point.field(key, float(val))
            point = point.time(ts)
            self._write_api.write(bucket=INFLUXDB_BUCKET, record=point)
            logger.info(f"综合数据写入成功: {data}")
        except Exception as e:
            logger.error(f"综合数据写入失败: {e}")

    def run(self):
        logger.info("气象数据采集程序启动")

        if not self._connect_influxdb():
            logger.error("无法连接综合 InfluxDB，程序退出")
            return

        self.windsock_sensor.start(write_influxdb=True)
        self.windspeed_sensor.start(write_influxdb=True)
        self.temp_sensor.start(write_influxdb=True)
        self.rain_sensor.start(write_influxdb=True)

        try:
            while True:
                pass
        except KeyboardInterrupt:
            logger.info("接收到中断信号，程序退出")
        finally:
            self._stop_event.set()
            self.windsock_sensor.stop()
            self.windspeed_sensor.stop()
            self.temp_sensor.stop()
            self.rain_sensor.stop()
            if self._influx_client:
                self._influx_client.close()
            logger.info("资源已释放，程序退出")


if __name__ == "__main__":
    station = WeatherStation()
    station.run()
