from __future__ import annotations

import time

import serial

from .config import CurrentConfig
from .csv_control import ToggleableCsvSink
from .mqtt_pipeline import MQTTCurrentPipeline
from .sensor import parse_sensor_line
from .serial_device import open_serial


class CurrentRuntime:
    def __init__(self, cfg: CurrentConfig):
        self.cfg = cfg
        self.csv_sink = ToggleableCsvSink(cfg)
        self.mqtt = MQTTCurrentPipeline(cfg, self._set_csv_enabled)
        self.serial_handle = None
        self.serial_device = None
        self.sequence = 0
        self.samples = 0
        self.parse_errors = 0
        self.reconnects = 0
        self.last_status_t = 0.0
        self.latest_current: dict[str, float] = {}
        self.stopping = False

    def _set_csv_enabled(self, enabled: bool, command_id: str) -> dict:
        result = self.csv_sink.set_enabled(enabled, command_id)
        return {**self.csv_sink.status(), **result}

    def start(self) -> None:
        self.mqtt.start()
        while not self.stopping:
            try:
                self._connect_serial()
                break
            except KeyboardInterrupt:
                raise
            except Exception as exc:
                print(
                    f"[Serial] connection failed: {exc}; retrying in "
                    f"{self.cfg.reconnect_interval_sec:g} seconds",
                    flush=True,
                )
                time.sleep(self.cfg.reconnect_interval_sec)
        self.mqtt.publish_csv_status(self.csv_sink.status())

    def _connect_serial(self) -> None:
        self.serial_handle, self.serial_device = open_serial(self.cfg)
        device = self.serial_device
        print(
            f"[Serial] connected: {device.port} | {device.description} | {device.hwid}",
            flush=True,
        )

    def _reconnect_serial(self) -> None:
        if self.serial_handle is not None:
            try:
                self.serial_handle.close()
            except Exception:
                pass
        self.serial_handle = None
        self.serial_device = None

        while not self.stopping:
            try:
                self._connect_serial()
                self.reconnects += 1
                return
            except KeyboardInterrupt:
                raise
            except Exception as exc:
                print(
                    f"[Serial] reconnect failed: {exc}; retrying in "
                    f"{self.cfg.reconnect_interval_sec:g} seconds",
                    flush=True,
                )
                time.sleep(self.cfg.reconnect_interval_sec)

    def run(self) -> None:
        while not self.stopping:
            if self.serial_handle is None:
                self._reconnect_serial()
                continue

            try:
                raw = self.serial_handle.readline()
            except (serial.SerialException, OSError) as exc:
                print(f"[Serial] connection lost: {exc}", flush=True)
                self._reconnect_serial()
                continue

            if not raw:
                self._publish_periodic_status()
                continue

            line = raw.decode("utf-8", errors="ignore").strip()
            sample = parse_sensor_line(line, self.cfg)
            if sample is None:
                if any(line.upper().startswith(f"{ch}:") for ch in self.cfg.channels):
                    self.parse_errors += 1
                continue

            timestamp_ns = time.time_ns()
            self.sequence += 1
            self.samples += 1
            self.latest_current[sample.channel] = sample.current_a
            self.mqtt.publish_sample(timestamp_ns, self.sequence, sample)
            self.csv_sink.write(timestamp_ns, self.sequence, sample)
            self._publish_periodic_status()

    def _publish_periodic_status(self) -> None:
        now = time.monotonic()
        if now - self.last_status_t < self.cfg.status_interval_sec:
            return
        self.last_status_t = now
        self.mqtt.publish_status(
            online=True,
            serial_port=None if self.serial_device is None else self.serial_device.port,
            samples=self.samples,
            parse_errors=self.parse_errors,
            reconnects=self.reconnects,
            latest_current_A={
                channel: round(value, 9)
                for channel, value in self.latest_current.items()
            },
            csv=self.csv_sink.status(),
        )

    def stop(self) -> None:
        self.stopping = True
        self.csv_sink.close()
        if self.serial_handle is not None:
            try:
                self.serial_handle.close()
            except Exception:
                pass
        self.mqtt.stop()
