from __future__ import annotations

import json
import time
from typing import Callable

import paho.mqtt.client as mqtt

from .config import CurrentConfig
from .sensor import CurrentSample


def make_mqtt_client(client_id: str) -> mqtt.Client:
    """Create a client compatible with both Paho MQTT 1.x and 2.x."""
    callback_api = getattr(mqtt, "CallbackAPIVersion", None)
    if callback_api is not None:
        return mqtt.Client(
            callback_api.VERSION2,
            client_id=client_id,
            protocol=mqtt.MQTTv311,
        )
    return mqtt.Client(client_id=client_id, protocol=mqtt.MQTTv311)


class MQTTCurrentPipeline:
    def __init__(
        self,
        cfg: CurrentConfig,
        csv_control_handler: Callable[[bool, str], dict],
    ):
        self.cfg = cfg
        self.csv_control_handler = csv_control_handler
        self.client = make_mqtt_client(cfg.mqtt_client_id)
        self.connected = False

        if cfg.mqtt_user:
            self.client.username_pw_set(cfg.mqtt_user, cfg.mqtt_password)

        self.client.reconnect_delay_set(min_delay=1, max_delay=30)
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message
        self.client.will_set(
            cfg.topic_status,
            json.dumps({"schema": "current.pipeline-status.v1", "online": False}),
            qos=1,
            retain=True,
        )

    def start(self) -> None:
        if not self.cfg.mqtt_enabled:
            return
        self.client.connect_async(
            self.cfg.mqtt_host,
            self.cfg.mqtt_port,
            keepalive=self.cfg.mqtt_keepalive_sec,
        )
        self.client.loop_start()

    def stop(self) -> None:
        if not self.cfg.mqtt_enabled:
            return
        try:
            self.publish_status(online=False)
            self.client.disconnect()
        finally:
            self.client.loop_stop()

    def _on_connect(
        self,
        client,
        _userdata,
        _flags,
        reason_code,
        _properties=None,
    ) -> None:
        self.connected = reason_code == 0
        if not self.connected:
            return
        client.subscribe(self.cfg.topic_csv_control, qos=1)
        self.publish_metadata()
        self.publish_status(online=True)

    def _on_disconnect(
        self,
        _client,
        _userdata,
        _flags,
        _reason_code,
        _properties=None,
    ) -> None:
        self.connected = False

    def _on_message(self, _client, _userdata, message) -> None:
        if message.topic != self.cfg.topic_csv_control or getattr(message, "retain", False):
            return
        try:
            payload = json.loads(message.payload.decode("utf-8"))
            enabled = payload["enabled"]
            command_id = str(payload.get("command_id", "")).strip()
            if not isinstance(enabled, bool) or not command_id:
                raise ValueError("enabled:boolean and command_id:string are required")
            result = self.csv_control_handler(enabled, command_id)
            self.publish_csv_status({**result, "result": "applied"})
        except Exception as exc:
            self.publish_csv_status({"result": "rejected", "error": str(exc)})

    def publish_sample(
        self,
        timestamp_ns: int,
        sequence: int,
        sample: CurrentSample,
    ) -> None:
        if not self.cfg.mqtt_enabled or not self.connected:
            return
        payload = {
            "schema": "current.rms.v1",
            "timestamp_ns": timestamp_ns,
            "sequence": sequence,
            "channel": sample.channel,
            "adc": sample.adc,
            "voltage_V": round(sample.voltage_v, 9),
            "raw_current_A": round(sample.raw_current_a, 9),
            "current_A": round(sample.current_a, 9),
            "noise_floor_applied": sample.noise_floor_applied,
            "ct_voltage_full_scale_V": sample.ct_voltage_full_scale_v,
            "ct_current_full_scale_A": sample.ct_current_full_scale_a,
        }
        self.client.publish(
            self.cfg.topic_rms(sample.channel),
            json.dumps(payload, separators=(",", ":")),
            qos=self.cfg.mqtt_qos,
            retain=False,
        )
        self.client.publish(
            self.cfg.topic_voltage(sample.channel),
            f"{sample.voltage_v:.6f}",
            qos=self.cfg.mqtt_qos,
            retain=False,
        )

    def publish_metadata(self) -> None:
        payload = {
            "schema": "current.metadata.v1",
            "equipment": self.cfg.equipment_name,
            "channels": list(self.cfg.channels),
            "baud": self.cfg.baud,
            "ct_by_channel": {
                channel: {
                    "voltage_full_scale_V": self.cfg.ct_calibration(channel)[0],
                    "current_full_scale_A": self.cfg.ct_calibration(channel)[1],
                }
                for channel in self.cfg.channels
            },
            "noise_floor": {
                "enabled": self.cfg.noise_floor_enabled,
                "threshold_A": self.cfg.noise_floor_a,
                "mode": self.cfg.noise_floor_mode,
                "scale": self.cfg.noise_floor_scale,
            },
            "topics": {
                "channels": {
                    channel: {
                        "rms": self.cfg.topic_rms(channel),
                        "voltage": self.cfg.topic_voltage(channel),
                    }
                    for channel in self.cfg.channels
                },
                "metadata": self.cfg.topic_metadata,
                "status": self.cfg.topic_status,
                "csv_control": self.cfg.topic_csv_control,
                "csv_status": self.cfg.topic_csv_status,
            },
        }
        self.client.publish(
            self.cfg.topic_metadata,
            json.dumps(payload, separators=(",", ":")),
            qos=1,
            retain=True,
        )

    def publish_status(self, *, online: bool, **extra) -> None:
        if not self.cfg.mqtt_enabled:
            return
        payload = {
            "schema": "current.pipeline-status.v1",
            "online": online,
            "timestamp_ns": time.time_ns(),
            "channels": list(self.cfg.channels),
            **extra,
        }
        self.client.publish(
            self.cfg.topic_status,
            json.dumps(payload, separators=(",", ":")),
            qos=1,
            retain=True,
        )

    def publish_csv_status(self, extra: dict) -> None:
        if not self.cfg.mqtt_enabled or not self.connected:
            return
        payload = {"schema": "current.csv-status.v1", **extra}
        self.client.publish(
            self.cfg.topic_csv_status,
            json.dumps(payload, separators=(",", ":")),
            qos=1,
            retain=True,
        )
