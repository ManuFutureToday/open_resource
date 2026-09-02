from __future__ import annotations

import csv
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import TextIO

from .config import CurrentConfig
from .sensor import CurrentSample


class CsvRollWriter:
    """Write one selected current channel to safely finalized rolling CSV files."""

    HEADER = [
        "timestamp_utc",
        "timestamp_ns",
        "sequence",
        "channel",
        "adc",
        "voltage_V",
        "raw_current_A",
        "current_A",
        "noise_floor_applied",
        "ct_voltage_full_scale_V",
        "ct_current_full_scale_A",
    ]

    def __init__(self, cfg: CurrentConfig, channel: str):
        self.cfg = cfg
        self.channel = channel
        self._fp: TextIO | None = None
        self._writer: csv.writer | None = None
        self._opened_ns = 0
        self._rows = 0
        self._counter = 0
        self._staging_path: Path | None = None

    @property
    def recording(self) -> bool:
        return self._fp is not None

    def _open(self, timestamp_ns: int) -> None:
        staging_dir = self.cfg.staging_csv_dir(self.channel)
        final_dir = self.cfg.final_csv_dir(self.channel)
        staging_dir.mkdir(parents=True, exist_ok=True)
        final_dir.mkdir(parents=True, exist_ok=True)

        self._counter += 1
        stamp = datetime.fromtimestamp(timestamp_ns / 1e9, tz=timezone.utc).strftime(
            "%Y%m%dT%H%M%S.%fZ"
        )
        name = f"{stamp}_{self._counter:06d}.csv"
        self._staging_path = staging_dir / name
        self._fp = self._staging_path.open("w", newline="", encoding="utf-8")
        self._writer = csv.writer(self._fp)
        self._writer.writerow(self.HEADER)
        self._fp.flush()
        self._opened_ns = timestamp_ns
        self._rows = 0

    def _finalize(self) -> Path | None:
        if self._fp is None or self._staging_path is None:
            return None

        fp = self._fp
        staging_path = self._staging_path
        self._fp = None
        self._writer = None
        self._staging_path = None

        fp.flush()
        os.fsync(fp.fileno())
        fp.close()

        final_path = self.cfg.final_csv_dir(self.channel) / staging_path.name
        staging_path.replace(final_path)
        return final_path

    def write(
        self,
        timestamp_ns: int,
        sequence: int,
        sample: CurrentSample,
    ) -> Path | None:
        finalized: Path | None = None
        segment_ns = int(self.cfg.csv_segment_sec * 1e9)
        if self._fp is None:
            self._open(timestamp_ns)
        elif timestamp_ns - self._opened_ns >= segment_ns:
            finalized = self._finalize()
            self._open(timestamp_ns)

        assert self._writer is not None
        assert self._fp is not None
        stamp = datetime.fromtimestamp(timestamp_ns / 1e9, tz=timezone.utc).isoformat()
        self._writer.writerow(
            [
                stamp,
                timestamp_ns,
                sequence,
                sample.channel,
                sample.adc,
                f"{sample.voltage_v:.9f}",
                f"{sample.raw_current_a:.9f}",
                f"{sample.current_a:.9f}",
                int(sample.noise_floor_applied),
                f"{sample.ct_voltage_full_scale_v:.9f}",
                f"{sample.ct_current_full_scale_a:.9f}",
            ]
        )
        self._rows += 1
        if self._rows % self.cfg.csv_fsync_every_rows == 0:
            self._fp.flush()
            os.fsync(self._fp.fileno())
        return finalized

    def close(self) -> Path | None:
        return self._finalize()
