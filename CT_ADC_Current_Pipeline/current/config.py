from __future__ import annotations

import argparse
import os
import re
import socket
import unicodedata
from dataclasses import dataclass
from pathlib import Path


DEFAULT_EQUIPMENT_NAME = "yornew_CNC"
DEFAULT_CHANNELS = ("CH4",)

# Hardware and storage defaults are edited here rather than in crontab.
DEFAULT_SERIAL_MATCH = "AUTO"
DEFAULT_BAUD = 115_200
DEFAULT_DATA_DIR = (
    Path.home() / "CT_ADC_Current_Pipeline" / "current_data"
    if os.name == "nt"
    else Path("/home/pi/CT_ADC_Current_Pipeline/current_data")
)


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    normalized = value.strip().casefold()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean value, got {value!r}")


def _env_text(
    primary: str,
    default: str,
    *,
    aliases: tuple[str, ...] = (),
) -> str:
    for name in (primary, *aliases):
        value = os.getenv(name)
        if value is not None:
            return value
    return default


def _slug(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold().strip()
    normalized = re.sub(r"[^a-z0-9]+", "_", normalized)
    return normalized.strip("_") or "unnamed"


def _parse_channels(value: str) -> tuple[str, ...]:
    channels: list[str] = []
    seen: set[str] = set()
    for item in re.split(r"[,;\s]+", value.strip()):
        if not item:
            continue
        channel = item.upper()
        if not re.fullmatch(r"CH\d+", channel):
            raise ValueError(
                "CURRENT_CHANNELS entries must use names such as CH4 or CH5"
            )
        if channel not in seen:
            channels.append(channel)
            seen.add(channel)
    if not channels:
        raise ValueError("CURRENT_CHANNELS must select at least one channel")
    return tuple(channels)


def _channels_from_env() -> tuple[str, ...]:
    value = _env_text(
        "CURRENT_CHANNELS",
        ",".join(DEFAULT_CHANNELS),
        aliases=("CURRENT_CHANNEL",),
    )
    return _parse_channels(value)




def _default_client_id() -> str:
    hostname = re.sub(r"[^a-zA-Z0-9_-]+", "-", socket.gethostname()).strip("-")
    return f"current-{hostname or 'publisher'}"


@dataclass(frozen=True)
class CurrentConfig:
    """Validated configuration for one ADC current-sensor service."""

    equipment_name: str = DEFAULT_EQUIPMENT_NAME
    channels: tuple[str, ...] = DEFAULT_CHANNELS

    serial_port: str = ""
    serial_match: str = DEFAULT_SERIAL_MATCH
    baud: int = DEFAULT_BAUD
    serial_timeout_sec: float = 1.0
    reconnect_interval_sec: float = 2.0

    ct_channel_calibrations: tuple[tuple[str, float, float], ...] = ()

    noise_floor_enabled: bool = False
    noise_floor_a: float = 0.01
    noise_floor_mode: str = "zero"
    noise_floor_scale: float = 0.0

    csv_enabled: bool = False
    data_dir: Path = DEFAULT_DATA_DIR
    csv_segment_sec: float = 60.0
    csv_fsync_every_rows: int = 100

    mqtt_enabled: bool = True
    mqtt_host: str = "localhost"
    mqtt_port: int = 1883
    mqtt_user: str = ""
    mqtt_password: str = ""
    mqtt_client_id: str = "current-publisher"
    mqtt_keepalive_sec: int = 60
    mqtt_qos: int = 1
    mqtt_topic_root: str = ""
    status_interval_sec: float = 10.0

    @classmethod
    def from_env(
        cls,
        *,
        equipment_name: str | None = None,
        channels: tuple[str, ...] | None = None,
        serial_port: str | None = None,
        serial_match: str | None = None,
        topic_root: str | None = None,
        mqtt_host: str | None = None,
        mqtt_port: int | None = None,
    ) -> "CurrentConfig":
        env_equipment = _env_text(
            "EQUIPMENT_NAME",
            DEFAULT_EQUIPMENT_NAME,
            aliases=("CURRENT_EQUIPMENT_NAME",),
        )
        resolved_equipment = (
            equipment_name if equipment_name is not None else env_equipment
        ).strip()
        resolved_channels = channels if channels is not None else _channels_from_env()

        channel_calibrations: list[tuple[str, float, float]] = []
        for channel in resolved_channels:
            voltage_name = f"CURRENT_{channel}_CT_V_FULL"
            current_name = f"CURRENT_{channel}_CT_I_FULL"
            voltage_value = os.getenv(voltage_name)
            current_value = os.getenv(current_name)
            if voltage_value is None or current_value is None:
                missing = [
                    name
                    for name, value in (
                        (voltage_name, voltage_value),
                        (current_name, current_value),
                    )
                    if value is None
                ]
                raise ValueError(
                    f"missing CT calibration for {channel}: {', '.join(missing)}"
                )
            channel_calibrations.append(
                (channel, float(voltage_value), float(current_value))
            )

        cfg = cls(
            equipment_name=resolved_equipment,
            channels=resolved_channels,
            serial_port=(
                serial_port
                if serial_port is not None
                else os.getenv("CURRENT_SERIAL_PORT", "")
            ).strip(),
            serial_match=(
                serial_match if serial_match is not None else DEFAULT_SERIAL_MATCH
            ).strip(),
            baud=DEFAULT_BAUD,
            serial_timeout_sec=float(os.getenv("CURRENT_SERIAL_TIMEOUT_SEC", "1")),
            reconnect_interval_sec=float(
                os.getenv("CURRENT_RECONNECT_INTERVAL_SEC", "2")
            ),
            ct_channel_calibrations=tuple(channel_calibrations),
            noise_floor_enabled=_env_bool("CURRENT_NOISE_FLOOR_ENABLED", False),
            noise_floor_a=float(os.getenv("CURRENT_NOISE_FLOOR_A", "0.01")),
            noise_floor_mode=os.getenv(
                "CURRENT_NOISE_FLOOR_MODE", "zero"
            ).strip().casefold(),
            noise_floor_scale=float(os.getenv("CURRENT_NOISE_FLOOR_SCALE", "0.0")),
            csv_enabled=_env_bool("CURRENT_CSV_ENABLED", False),
            data_dir=DEFAULT_DATA_DIR,
            csv_segment_sec=float(os.getenv("CURRENT_CSV_SEGMENT_SEC", "60")),
            csv_fsync_every_rows=int(
                os.getenv("CURRENT_CSV_FSYNC_EVERY_ROWS", "100")
            ),
            mqtt_enabled=_env_bool("MQTT_ENABLED", True),
            mqtt_host=(
                mqtt_host if mqtt_host is not None else os.getenv("MQTT_HOST", "localhost")
            ).strip(),
            mqtt_port=(
                int(mqtt_port)
                if mqtt_port is not None
                else int(os.getenv("MQTT_PORT", "1883"))
            ),
            mqtt_user=os.getenv("MQTT_USER", ""),
            mqtt_password=os.getenv("MQTT_PASSWORD", ""),
            mqtt_client_id=os.getenv(
                "MQTT_CURRENT_CLIENT_ID", _default_client_id()
            ).strip(),
            mqtt_keepalive_sec=int(os.getenv("MQTT_KEEPALIVE_SEC", "60")),
            mqtt_qos=int(os.getenv("MQTT_CURRENT_QOS", "1")),
            mqtt_topic_root=(
                topic_root
                if topic_root is not None
                else os.getenv("MQTT_CURRENT_TOPIC_ROOT", "")
            ).strip(),
            status_interval_sec=float(
                os.getenv("CURRENT_STATUS_INTERVAL_SEC", "10")
            ),
        )
        cfg.validate()
        return cfg

    @classmethod
    def from_args(cls, argv: list[str] | None = None) -> "CurrentConfig":
        parser = argparse.ArgumentParser(
            prog="python -m current",
            description="Read selected ADC current channels and publish them over MQTT.",
        )
        parser.add_argument(
            "--equipment",
            metavar="NAME",
            help="equipment identity (overrides EQUIPMENT_NAME)",
        )
        parser.add_argument(
            "--channels",
            metavar="LIST",
            help="comma-separated ADC channels such as CH4 or CH4,CH5",
        )
        parser.add_argument("--port", metavar="PORT", help="exact serial port")
        parser.add_argument(
            "--device-match",
            metavar="TEXT",
            help="serial-device discovery substring",
        )
        parser.add_argument(
            "--topic-root",
            metavar="TOPIC",
            help="base MQTT root before the channel name",
        )
        parser.add_argument("--mqtt-host", metavar="HOST", help="MQTT broker host")
        parser.add_argument(
            "--mqtt-port", metavar="PORT", type=int, help="MQTT broker TCP port"
        )
        args = parser.parse_args(argv)
        return cls.from_env(
            equipment_name=args.equipment,
            channels=_parse_channels(args.channels) if args.channels else None,
            serial_port=args.port,
            serial_match=args.device_match,
            topic_root=args.topic_root,
            mqtt_host=args.mqtt_host,
            mqtt_port=args.mqtt_port,
        )

    @property
    def equipment_slug(self) -> str:
        return _slug(self.equipment_name)

    @property
    def topic_root(self) -> str:
        if self.mqtt_topic_root:
            return self.mqtt_topic_root.strip().strip("/")
        return f"{self.equipment_slug}/current"

    def ct_calibration(self, channel: str) -> tuple[float, float]:
        target = channel.upper()
        for item_channel, voltage_v, current_a in self.ct_channel_calibrations:
            if item_channel == target:
                return voltage_v, current_a
        raise ValueError(f"no CT calibration configured for {target}")

    def topic_rms(self, channel: str) -> str:
        return f"{self.topic_root}/{_slug(channel)}/rms"

    def topic_voltage(self, channel: str) -> str:
        return f"{self.topic_root}/{_slug(channel)}/voltage"

    @property
    def topic_metadata(self) -> str:
        return f"{self.topic_root}/metadata"

    @property
    def topic_status(self) -> str:
        return f"{self.topic_root}/status"

    @property
    def topic_csv_control(self) -> str:
        return f"{self.topic_root}/control/csv"

    @property
    def topic_csv_status(self) -> str:
        return f"{self.topic_root}/status/csv"

    def final_csv_dir(self, channel: str) -> Path:
        return self.data_dir / self.equipment_slug / _slug(channel) / "csv"

    def staging_csv_dir(self, channel: str) -> Path:
        return self.data_dir / ".staging" / self.equipment_slug / _slug(channel) / "csv"

    def validate(self) -> None:
        if not self.equipment_name:
            raise ValueError("EQUIPMENT_NAME must not be empty")
        if not self.channels:
            raise ValueError("CURRENT_CHANNELS must select at least one channel")
        for channel in self.channels:
            if not re.fullmatch(r"CH\d+", channel):
                raise ValueError(f"invalid current channel: {channel!r}")
        if self.baud <= 0:
            raise ValueError("DEFAULT_BAUD must be positive")
        if self.serial_timeout_sec <= 0 or self.reconnect_interval_sec <= 0:
            raise ValueError("serial timings must be positive")
        calibrated_channels = {item[0] for item in self.ct_channel_calibrations}
        missing_calibrations = [
            channel for channel in self.channels if channel not in calibrated_channels
        ]
        if missing_calibrations:
            raise ValueError(
                "missing CT calibration for selected channels: "
                + ", ".join(missing_calibrations)
            )
        for channel, voltage_v, current_a in self.ct_channel_calibrations:
            if channel not in self.channels:
                raise ValueError(f"CT calibration references unselected channel: {channel}")
            if voltage_v <= 0 or current_a <= 0:
                raise ValueError(f"CT full-scale values for {channel} must be positive")
        if self.noise_floor_a < 0:
            raise ValueError("CURRENT_NOISE_FLOOR_A must be non-negative")
        if self.noise_floor_mode not in {"zero", "scale"}:
            raise ValueError("CURRENT_NOISE_FLOOR_MODE must be 'zero' or 'scale'")
        if not 0.0 <= self.noise_floor_scale <= 1.0:
            raise ValueError("CURRENT_NOISE_FLOOR_SCALE must be between 0 and 1")
        if self.csv_segment_sec <= 0 or self.csv_fsync_every_rows <= 0:
            raise ValueError("CSV segment and fsync settings must be positive")
        if not self.mqtt_host or not self.mqtt_client_id:
            raise ValueError("MQTT host and client id must not be empty")
        if not 1 <= self.mqtt_port <= 65_535:
            raise ValueError("MQTT_PORT is outside the valid TCP port range")
        if self.mqtt_qos not in {1, 2}:
            raise ValueError("MQTT_CURRENT_QOS must be 1 or 2")

    def validated(self) -> "CurrentConfig":
        self.validate()
        return self
