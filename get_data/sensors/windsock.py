import serial
import struct
import time
import logging
import os
import sys
from influxdb_client import Point
import sys
sys.path.append('.')
from ultils import crc16
import numpy as np
from sensors.sensor_base import SecondIntervalSensor

logger = logging.getLogger(__name__)


class WindSockSensor(SecondIntervalSensor):
    influxdb_bucket = os.getenv('INFLUXDB_BUCKET', 'wind_sock_1s')

    def __init__(self):
        super().__init__()
        self.port = 'COM4'
        self.baudrate = 4800

    def read_data(self):
        ser = serial.Serial(
            port=self.port,
            baudrate=self.baudrate,
            bytesize=8,
            parity='N',
            stopbits=1,
            timeout=1
        )
        time.sleep(0.1)
        ser.reset_input_buffer()

        frame = bytearray([0x02, 0x03, 0x00, 0x00, 0x00, 0x08])
        crc = crc16(frame)
        frame += struct.pack('<H', crc)
        ser.write(frame)
        response = ser.read(35)
        ser.close()

        direction = {0: '北', 1: '东北', 2: '东', 3: '东南', 4: '南', 5: '西南', 6: '西', 7: '西北'}
        if len(response) >= 18:
            dir_code = int.from_bytes(response[3:5], byteorder='big', signed=False)
            angle_raw = int.from_bytes(response[13:15], byteorder='big', signed=True) / 10
            self.data = {
                "wind_direction": direction.get(dir_code, "未知"),
                "wind_angle": round((angle_raw + 238) % 360, 1)
            }
        else:
            raise ValueError(f"响应帧长度不足: {len(response)} bytes")

    def _build_influxdb_point(self, data: dict, ts) -> Point:
        point = Point("wind").tag("location", "station_1")
        if 'wind_angle' in data and not np.isnan(data['wind_angle']):
            point = point.field("wind_angle", float(data['wind_angle']))
        if 'wind_direction' in data and not (isinstance(data['wind_direction'], float) and np.isnan(data['wind_direction'])):
            point = point.field("wind_direction", str(data['wind_direction']))
        return point.time(ts)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('weather_data.log', encoding='utf-8'),
            logging.StreamHandler()
        ]
    )

    sensor = WindSockSensor()

    if len(sys.argv) > 1 and sys.argv[1] == '--once':
        sensor.read_data()
        print(sensor.data)
    else:
        sensor.start(write_influxdb=True)
        try:
            while True:
                pass
        except KeyboardInterrupt:
            sensor.stop()
