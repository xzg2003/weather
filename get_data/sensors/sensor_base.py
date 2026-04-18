import time
import logging
import os
import threading
from datetime import datetime, timezone
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS
import serial

logger = logging.getLogger(__name__)

INFLUXDB_URL = os.getenv('INFLUXDB_URL', 'http://localhost:8086')
INFLUXDB_TOKEN = os.getenv('INFLUXDB_TOKEN', 'ln7NNOLrHk8y8w0KjE3nzR_qEXQBLANoZJMFPdMxsznISkpR1hOZt_CaZ0juIYU7Fwjft34NrO7061koydqolg==')
INFLUXDB_ORG = os.getenv('INFLUXDB_ORG', 'USTC')

# 串口互斥锁注册表：key=端口名，value=Lock
# 同一串口的所有传感器共用同一把锁，读取时互斥
_port_locks: dict[str, threading.Lock] = {}
_port_locks_meta = threading.Lock()


def _get_port_lock(port: str) -> threading.Lock:
    """返回指定串口对应的锁，不存在则创建。"""
    with _port_locks_meta:
        if port not in _port_locks:
            _port_locks[port] = threading.Lock()
        return _port_locks[port]


class SecondIntervalSensor:
    """
    1s 采样率传感器的后台采集基类。

    子类需实现：
      - influxdb_bucket: str        — 写入目标 bucket 名称
      - read_data()                 — 从硬件读取数据，结果存入 self.data
      - _build_influxdb_point(data, ts) -> Point  — 构造 InfluxDB Point 对象

    可选覆盖：
      - interval: float             — 采集间隔秒数，默认 1.0
    """

    influxdb_bucket: str = ''
    interval: float = 1.0

    def __init__(self):
        self.data = {}
        self._stop_event = threading.Event()
        self._thread = None
        self._influx_client = None
        self._write_api = None
        self._port_lock = None

    # ------------------------------------------------------------------
    # 子类必须实现
    # ------------------------------------------------------------------
    def read_data(self):
        raise NotImplementedError

    def _build_influxdb_point(self, data: dict, ts) -> Point:
        raise NotImplementedError

    # ------------------------------------------------------------------
    # InfluxDB
    # ------------------------------------------------------------------
    def _connect_influxdb(self):
        try:
            self._influx_client = InfluxDBClient(
                url=INFLUXDB_URL,
                token=INFLUXDB_TOKEN,
                org=INFLUXDB_ORG
            )
            self._write_api = self._influx_client.write_api(write_options=SYNCHRONOUS)
            logger.info(f"{self.__class__.__name__} InfluxDB 连接成功")
            return True
        except Exception as e:
            logger.error(f"{self.__class__.__name__} InfluxDB 连接失败: {e}")
            return False

    def _write_to_influxdb(self, data: dict, ts):
        if not self._write_api or not self.influxdb_bucket:
            return
        try:
            point = self._build_influxdb_point(data, ts)
            self._write_api.write(bucket=self.influxdb_bucket, record=point)
        except Exception as e:
            logger.debug(f"{self.__class__.__name__} 数据写入失败: {e}")

    # ------------------------------------------------------------------
    # 后台线程
    # ------------------------------------------------------------------
    def _collection_loop(self):
        logger.info(f"{self.__class__.__name__} 秒级采集线程启动")
        # 延迟获取锁，确保子类 __init__ 已设置 self.port
        if self._port_lock is None and hasattr(self, 'port'):
            self._port_lock = _get_port_lock(self.port)
        _serial_fail_count = 0
        while not self._stop_event.is_set():
            loop_start = time.time()
            ts = datetime.now(timezone.utc)
            try:
                with self._port_lock:
                    self.read_data()
                if _serial_fail_count > 0:
                    logger.info(f"{self.__class__.__name__} 串口恢复正常")
                    _serial_fail_count = 0
                self._write_to_influxdb(self.data, ts)
                print(self.data)
            except serial.SerialException as e:
                _serial_fail_count += 1
                self.data = {}
                if _serial_fail_count == 1 or _serial_fail_count % 60 == 0:
                    logger.warning(
                        f"{self.__class__.__name__} 串口不可用"
                        f"（已失败 {_serial_fail_count} 次）: {e}"
                    )
            except Exception as e:
                logger.debug(f"{self.__class__.__name__} 读取失败: {e}")

            elapsed = time.time() - loop_start
            self._stop_event.wait(max(0.0, self.interval - elapsed))

        logger.info(f"{self.__class__.__name__} 采集线程退出")

    def start(self, write_influxdb=True):
        """启动后台采集线程。"""
        if self._thread and self._thread.is_alive():
            logger.warning(f"{self.__class__.__name__} 采集线程已在运行")
            return
        if write_influxdb:
            self._connect_influxdb()
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._collection_loop,
            daemon=True,
            name=self.__class__.__name__
        )
        self._thread.start()

    def stop(self):
        """停止后台采集线程并释放资源。"""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=3)
            self._thread = None
        if self._influx_client:
            self._influx_client.close()
            self._influx_client = None
            self._write_api = None
        logger.info(f"{self.__class__.__name__} 采集已停止")

    def is_running(self):
        return self._thread is not None and self._thread.is_alive()


class MinuteIntervalSensor:
    """
    分钟级传感器的后台采集基类，在每分钟第 trigger_second 秒采集一次。

    子类需实现：
      - influxdb_bucket: str
      - read_data()
      - _build_influxdb_point(data, ts) -> Point

    可选覆盖：
      - trigger_second: int  — 每分钟第几秒触发采集，默认 50
    """

    influxdb_bucket: str = ''
    trigger_second: int = 50

    def __init__(self):
        self.data = {}
        self._stop_event = threading.Event()
        self._thread = None
        self._influx_client = None
        self._write_api = None
        self._port_lock = None

    def read_data(self):
        raise NotImplementedError

    def _build_influxdb_point(self, data: dict, ts) -> Point:
        raise NotImplementedError

    def _connect_influxdb(self):
        try:
            self._influx_client = InfluxDBClient(
                url=INFLUXDB_URL,
                token=INFLUXDB_TOKEN,
                org=INFLUXDB_ORG
            )
            self._write_api = self._influx_client.write_api(write_options=SYNCHRONOUS)
            logger.info(f"{self.__class__.__name__} InfluxDB 连接成功")
            return True
        except Exception as e:
            logger.error(f"{self.__class__.__name__} InfluxDB 连接失败: {e}")
            return False

    def _write_to_influxdb(self, data: dict, ts):
        if not self._write_api or not self.influxdb_bucket:
            return
        try:
            point = self._build_influxdb_point(data, ts)
            self._write_api.write(bucket=self.influxdb_bucket, record=point)
        except Exception as e:
            logger.debug(f"{self.__class__.__name__} 数据写入失败: {e}")

    def _collection_loop(self):
        logger.info(f"{self.__class__.__name__} 分钟级采集线程启动")
        if self._port_lock is None and hasattr(self, 'port'):
            self._port_lock = _get_port_lock(self.port)
        _serial_fail_count = 0
        while not self._stop_event.is_set():
            now = datetime.now()
            sec = now.second
            if sec < self.trigger_second:
                wait = self.trigger_second - sec
            else:
                wait = 60 - sec + self.trigger_second
            if self._stop_event.wait(wait):
                break

            ts = datetime.now(timezone.utc)
            try:
                with self._port_lock:
                    self.read_data()
                if _serial_fail_count > 0:
                    logger.info(f"{self.__class__.__name__} 串口恢复正常")
                    _serial_fail_count = 0
                self._write_to_influxdb(self.data, ts)
                print(self.data)
            except serial.SerialException as e:
                _serial_fail_count += 1
                self.data = {}
                if _serial_fail_count == 1 or _serial_fail_count % 10 == 0:
                    logger.warning(
                        f"{self.__class__.__name__} 串口不可用"
                        f"（已失败 {_serial_fail_count} 次）: {e}"
                    )
            except Exception as e:
                logger.debug(f"{self.__class__.__name__} 读取失败: {e}")

        logger.info(f"{self.__class__.__name__} 采集线程退出")

    def start(self, write_influxdb=True):
        if self._thread and self._thread.is_alive():
            logger.warning(f"{self.__class__.__name__} 采集线程已在运行")
            return
        if write_influxdb:
            self._connect_influxdb()
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._collection_loop,
            daemon=True,
            name=self.__class__.__name__
        )
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=3)
            self._thread = None
        if self._influx_client:
            self._influx_client.close()
            self._influx_client = None
            self._write_api = None
        logger.info(f"{self.__class__.__name__} 采集已停止")

    def is_running(self):
        return self._thread is not None and self._thread.is_alive()
