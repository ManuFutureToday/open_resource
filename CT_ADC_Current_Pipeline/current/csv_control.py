from __future__ import annotations

import threading

from .config import CurrentConfig
from .csv_roll_writer import CsvRollWriter
from .sensor import CurrentSample


class ToggleableCsvSink:
    """Apply one ON/OFF state to rolling CSV writers for selected channels."""

    def __init__(self, cfg: CurrentConfig):
        self.cfg = cfg
        self.writers = {
            channel: CsvRollWriter(cfg, channel)
            for channel in cfg.channels
        }
        self._lock = threading.Lock()
        self._desired_enabled = bool(cfg.csv_enabled)
        self._last_command_id: str | None = None

    @property
    def desired_enabled(self) -> bool:
        with self._lock:
            return self._desired_enabled

    def set_enabled(self, enabled: bool, command_id: str | None = None) -> dict:
        with self._lock:
            changed = self._desired_enabled != bool(enabled)
            self._desired_enabled = bool(enabled)
            self._last_command_id = command_id
            finalized: list[str] = []
            if not self._desired_enabled:
                for writer in self.writers.values():
                    path = writer.close()
                    if path is not None:
                        finalized.append(str(path))
            return {
                "enabled": self._desired_enabled,
                "changed": changed,
                "recording": any(writer.recording for writer in self.writers.values()),
                "command_id": command_id,
                "finalized_files": finalized,
            }

    def write(self, timestamp_ns: int, sequence: int, sample: CurrentSample) -> None:
        with self._lock:
            if not self._desired_enabled:
                return
            self.writers[sample.channel].write(timestamp_ns, sequence, sample)

    def status(self) -> dict:
        with self._lock:
            return {
                "schema": "current.csv-status.v1",
                "desired_enabled": self._desired_enabled,
                "recording": any(writer.recording for writer in self.writers.values()),
                "last_command_id": self._last_command_id,
                "directories": {
                    channel: str(self.cfg.final_csv_dir(channel))
                    for channel in self.cfg.channels
                },
                "segment_sec": self.cfg.csv_segment_sec,
            }

    def close(self) -> None:
        with self._lock:
            for writer in self.writers.values():
                writer.close()
