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
from sensors.sensor_base import MinuteIntervalSensor

logger = logging.getLogger(__name__)


class TemperatureSensor(MinuteIntervalSensor):
    influxdb_bucket = os.getenv('INFLUXDB_BUCKET', 'thp_1m')

    def __init__(self):
        super().__init__()
        self.port = 'COM3'
        self.baudrate = 9600

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

        frame = bytearray([0x01, 0x03, 0x00, 0x00, 0x00, 0x03])
        crc = crc16(frame)
        frame += struct.pack('<H', crc)
        ser.write(frame)
        response = ser.read(10)
        ser.close()

        if len(response) >= 9:
            temperature = int.from_bytes(response[3:5], byteorder='big', signed=True) / 10
            humidity = int.from_bytes(response[5:7], byteorder='big', signed=False) / 10
            hpa = int.from_bytes(response[7:9], byteorder='big', signed=False) / 10
            self.data = {
                "temperature": temperature,
                "humidity": humidity,
                "pressure": hpa
            }
        else:
            raise ValueError(f"响应帧长度不足: {len(response)} bytes")

    def _build_influxdb_point(self, data: dict, ts) -> Point:
        point = Point("weather").tag("location", "station_1")
        if 'temperature' in data:
            point = point.field("temperature", float(data['temperature']))
        if 'humidity' in data:
            point = point.field("humidity", float(data['humidity']))
        if 'pressure' in data:
            point = point.field("pressure", float(data['pressure']))
        return point.time(ts)


if __name__ == "__main__":
    sensor = TemperatureSensor()
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
