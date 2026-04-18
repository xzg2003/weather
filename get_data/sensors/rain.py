import serial
import struct
import time
import logging
import os
import sys
from influxdb_client import Point
from ultils import crc16
import sys
sys.path.append('.')
from sensors.sensor_base import MinuteIntervalSensor

logger = logging.getLogger(__name__)


class RainSensor(MinuteIntervalSensor):
    influxdb_bucket = os.getenv('INFLUXDB_BUCKET', 'rain_1m')

    def __init__(self):
        super().__init__()
        self.port = 'COM3'
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

        frame = bytearray([0x04, 0x03, 0x00, 0x00, 0x00, 0x09])
        crc = crc16(frame)
        frame += struct.pack('<H', crc)
        ser.write(frame)
        response = ser.read(31)
        ser.close()

        if len(response) >= 15:
            self.data = {
                "instantaneous_rainfall": int.from_bytes(response[5:7], byteorder='big', signed=True) / 10,
                #"current_hour_rainfall": int.from_bytes(response[11:13], byteorder='big', signed=False) / 10,
                #"previous_hour_rainfall": int.from_bytes(response[13:15], byteorder='big', signed=False) / 10
            }
        else:
            raise ValueError(f"响应帧长度不足: {len(response)} bytes")

    def _build_influxdb_point(self, data: dict, ts) -> Point:
        point = Point("weather").tag("location", "station_1")
        if 'instantaneous_rainfall' in data:
            point = point.field("instantaneous_rainfall", float(data['instantaneous_rainfall']))
        if 'current_hour_rainfall' in data:
            point = point.field("current_hour_rainfall", float(data['current_hour_rainfall']))
        if 'previous_hour_rainfall' in data:
            point = point.field("previous_hour_rainfall", float(data['previous_hour_rainfall']))
        return point.time(ts)


if __name__ == "__main__":
    sensor = RainSensor()
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('weather_data.log', encoding='utf-8'),
            logging.StreamHandler()
        ]
    )

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
