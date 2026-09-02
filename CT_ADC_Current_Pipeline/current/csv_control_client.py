from __future__ import annotations

import argparse
import json
import time
import uuid
from dataclasses import replace

from .config import CurrentConfig
from .mqtt_pipeline import make_mqtt_client


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Turn current CSV recording on or off"
    )
    parser.add_argument("state", choices=["on", "off"])
    parser.add_argument("--equipment")
    parser.add_argument("--mqtt-host")
    parser.add_argument("--mqtt-port", type=int)
    args = parser.parse_args()

    base = CurrentConfig.from_env()
    cfg = replace(
        base,
        equipment_name=args.equipment or base.equipment_name,
        mqtt_host=args.mqtt_host or base.mqtt_host,
        mqtt_port=args.mqtt_port or base.mqtt_port,
    ).validated()

    command_id = str(uuid.uuid4())
    client = make_mqtt_client(
        f"{cfg.mqtt_client_id}_csv_control_{uuid.uuid4().hex[:8]}"
    )
    if cfg.mqtt_user:
        client.username_pw_set(cfg.mqtt_user, cfg.mqtt_password)

    response: dict | None = None

    def on_connect(c, _u, _f, reason_code, _p=None):
        if int(reason_code) != 0:
            return
        c.subscribe(cfg.topic_csv_status, qos=1)
        payload = {"enabled": args.state == "on", "command_id": command_id}
        c.publish(cfg.topic_csv_control, json.dumps(payload), qos=1, retain=False)

    def on_message(_c, _u, msg):
        nonlocal response
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
            if payload.get("command_id") == command_id:
                response = payload
        except Exception:
            pass

    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(cfg.mqtt_host, cfg.mqtt_port, keepalive=cfg.mqtt_keepalive_sec)
    client.loop_start()
    deadline = time.monotonic() + 5
    while response is None and time.monotonic() < deadline:
        time.sleep(0.05)
    client.disconnect()
    client.loop_stop()

    if response is None:
        print("No matching status acknowledgement was received.")
        return 1
    print(json.dumps(response, indent=2))
    return 0 if response.get("result") == "applied" else 1


if __name__ == "__main__":
    raise SystemExit(main())
