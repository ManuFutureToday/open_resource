from __future__ import annotations

import signal

from .config import CurrentConfig


# Keep runtime imports out of --help and CLI validation so the configuration
# can be inspected before pyserial or the MQTT runtime is installed.
CurrentRuntime = None


def _load_runtime_class():
    global CurrentRuntime
    if CurrentRuntime is None:
        from .runtime import CurrentRuntime as runtime_class

        CurrentRuntime = runtime_class
    return CurrentRuntime


def main() -> int:
    cfg = CurrentConfig.from_args()
    try:
        runtime = _load_runtime_class()(cfg)
    except Exception as exc:
        print(f"[Fatal] {type(exc).__name__}: {exc}", flush=True)
        return 2

    stopping = False

    def handle_stop(_signal_number, _frame) -> None:
        nonlocal stopping
        if stopping:
            return
        stopping = True
        print("[Signal] stopping current service...", flush=True)
        runtime.stop()

    signal.signal(signal.SIGINT, handle_stop)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, handle_stop)

    try:
        runtime.start()
        device = runtime.serial_device
        print("========================================", flush=True)
        print("CURRENT SENSOR MQTT PIPELINE STARTED", flush=True)
        print(f"Equipment: {cfg.equipment_name}", flush=True)
        print(f"Serial   : {device.port if device else 'unknown'}", flush=True)
        print(f"Channels : {', '.join(cfg.channels)}", flush=True)
        print(f"MQTT     : {cfg.mqtt_host}:{cfg.mqtt_port}", flush=True)
        print(f"Root     : {cfg.topic_root}", flush=True)
        print(f"Data Dir : {cfg.data_dir}", flush=True)
        print(f"CSV Rec  : {'ON' if cfg.csv_enabled else 'OFF'} at startup", flush=True)
        print(
            f"Noise    : {'ON' if cfg.noise_floor_enabled else 'OFF'} "
            f"(< {cfg.noise_floor_a:g} A, {cfg.noise_floor_mode})",
            flush=True,
        )
        print("========================================", flush=True)
        runtime.run()
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        print(f"[Fatal] {type(exc).__name__}: {exc}", flush=True)
        return 2
    finally:
        if not stopping:
            runtime.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
