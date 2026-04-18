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
from sensors.sensor_base import SecondIntervalSensor

logger = logging.getLogger(__name__)


class WindSpeedSensor(SecondIntervalSensor):
    influxdb_bucket = os.getenv('INFLUXDB_WIND_BUCKET', 'wind_speed_1s')

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

        frame = bytearray([0x03, 0x03, 0x00, 0x00, 0x00, 0x02])
        crc = crc16(frame)
        frame += struct.pack('<H', crc)
        ser.write(frame)
        response = ser.read(10)
        ser.close()

        if len(response) >= 7:
            speed = int.from_bytes(response[3:5], byteorder='big', signed=False) / 10
            level = int.from_bytes(response[5:7], byteorder='big', signed=True)
            self.data = {
                "wind_speed": speed,
                "wind_level": level
            }
        else:
            raise ValueError(f"响应帧长度不足: {len(response)} bytes")

    def _build_influxdb_point(self, data: dict, ts) -> Point:
        point = Point("wind").tag("location", "station_1")
        if 'wind_speed' in data:
            point = point.field("wind_speed", float(data['wind_speed']))
        if 'wind_level' in data:
            point = point.field("wind_level", int(data['wind_level']))
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

    sensor = WindSpeedSensor()

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

