from __future__ import annotations

from dataclasses import dataclass

from .config import CurrentConfig


@dataclass(frozen=True)
class CurrentSample:
    channel: str
    adc: int
    voltage_v: float
    raw_current_a: float
    current_a: float
    noise_floor_applied: bool
    ct_voltage_full_scale_v: float
    ct_current_full_scale_a: float


def apply_noise_floor(current_a: float, cfg: CurrentConfig) -> tuple[float, bool]:
    if not cfg.noise_floor_enabled or abs(current_a) >= cfg.noise_floor_a:
        return current_a, False

    if cfg.noise_floor_mode == "scale":
        return current_a * cfg.noise_floor_scale, True
    return 0.0, True


def parse_sensor_line(line: str, cfg: CurrentConfig) -> CurrentSample | None:
    text = line.strip()
    if ":" not in text:
        return None

    channel_text, rest = text.split(":", 1)
    channel = channel_text.strip().upper()
    if channel not in cfg.channels:
        return None

    try:
        parts = rest.strip().split()
        if len(parts) < 2:
            return None

        adc = int(parts[0])
        voltage_v = float(parts[1].replace("V", ""))
        ct_voltage_full_scale_v, ct_current_full_scale_a = cfg.ct_calibration(channel)
        raw_current_a = (
            voltage_v / ct_voltage_full_scale_v
        ) * ct_current_full_scale_a
        current_a, applied = apply_noise_floor(raw_current_a, cfg)
        return CurrentSample(
            channel=channel,
            adc=adc,
            voltage_v=voltage_v,
            raw_current_a=raw_current_a,
            current_a=current_a,
            noise_floor_applied=applied,
            ct_voltage_full_scale_v=ct_voltage_full_scale_v,
            ct_current_full_scale_a=ct_current_full_scale_a,
        )
    except (TypeError, ValueError):
        return None
