from __future__ import annotations

from dataclasses import dataclass

import serial
from serial.tools import list_ports

from .config import CurrentConfig


@dataclass(frozen=True)
class SerialDevice:
    port: str
    description: str
    hwid: str


def list_serial_devices() -> list[SerialDevice]:
    return [
        SerialDevice(
            port=str(item.device),
            description=str(item.description or ""),
            hwid=str(item.hwid or ""),
        )
        for item in list_ports.comports()
    ]


def _device_text(device: SerialDevice) -> str:
    return f"{device.port} {device.description} {device.hwid}".casefold()


def _is_likely_adc_serial(device: SerialDevice) -> bool:
    text = _device_text(device)
    port = device.port.casefold()

    # Common Raspberry Pi and Windows USB-serial identifiers, including the
    # CH340/CH341 family used by several ADC interface boards.
    tokens = (
        "usb",
        "serial",
        "stm",
        "stmicro",
        "ch340",
        "ch341",
        "1a86:7523",
        "1a86:5523",
    )
    return (
        port.startswith("/dev/ttyusb")
        or port.startswith("/dev/ttyacm")
        or any(token in text for token in tokens)
    )


def _format_devices(devices: list[SerialDevice]) -> str:
    if not devices:
        return "none"
    return "; ".join(
        f"{device.port} ({device.description or 'no description'}, {device.hwid or 'no hwid'})"
        for device in devices
    )


def _select_auto(devices: list[SerialDevice]) -> SerialDevice:
    preferred = [device for device in devices if _is_likely_adc_serial(device)]

    if len(preferred) == 1:
        return preferred[0]
    if not preferred and len(devices) == 1:
        return devices[0]
    if not devices:
        raise RuntimeError("No serial device was found")
    if not preferred:
        raise RuntimeError(
            "No likely USB serial ADC was identified. Available serial devices: "
            + _format_devices(devices)
        )

    raise RuntimeError(
        "Serial-device selection is ambiguous. Edit DEFAULT_SERIAL_MATCH in "
        "current/config.py to a unique description, HWID, or port substring. "
        "Candidates: "
        + _format_devices(preferred)
    )


def select_serial_device(cfg: CurrentConfig) -> SerialDevice:
    devices = list_serial_devices()

    # An explicit port always wins and is checked before discovery.
    if cfg.serial_port:
        target = cfg.serial_port.casefold()
        for device in devices:
            if device.port.casefold() == target:
                return device
        raise RuntimeError(f"Configured serial port was not found: {cfg.serial_port}")

    match = cfg.serial_match.strip()
    if not match or match.casefold() == "auto":
        return _select_auto(devices)

    needle = match.casefold()
    matches = [device for device in devices if needle in _device_text(device)]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise RuntimeError(
            f"No serial device matched {match!r}. Available serial devices: "
            + _format_devices(devices)
        )

    raise RuntimeError(
        f"Multiple serial devices matched {match!r}: " + _format_devices(matches)
    )


def open_serial(cfg: CurrentConfig) -> tuple[serial.Serial, SerialDevice]:
    device = select_serial_device(cfg)
    handle = serial.Serial(
        port=device.port,
        baudrate=cfg.baud,
        timeout=cfg.serial_timeout_sec,
    )
    handle.reset_input_buffer()
    return handle, device
