# CT ADC Current MQTT Pipeline

This package reads selected ADC channels from a serial CT interface, converts each
channel with its explicitly assigned CT calibration, publishes current data over
MQTT, and optionally saves rolling CSV files.

It is designed to run beside the sound pipeline while keeping the two projects
physically separate:

```text
/home/pi/GStreamer_Sound_Pipeline
/home/pi/CT_ADC_Current_Pipeline
```

The two services share only `MQTT_USER`, `MQTT_PASSWORD`, and `EQUIPMENT_NAME`
from crontab.

## Configuration kept in current/config.py

These deployment defaults are intentionally kept in `current/config.py` rather
than crontab:

```python
DEFAULT_SERIAL_MATCH = "AUTO"
DEFAULT_BAUD = 115_200
DEFAULT_DATA_DIR = Path("/home/pi/CT_ADC_Current_Pipeline/current_data")
```

Edit these constants in `current/config.py` when the ADC interface, baud rate, or
storage root needs to change. `AUTO` selects one unambiguous USB serial device,
including STM and CH340/CH341 interfaces. If several USB serial devices are present,
set `DEFAULT_SERIAL_MATCH` to a unique port, description, or HWID substring. These
settings are not read from `CURRENT_SERIAL_MATCH`, `CURRENT_BAUD`, or
`CURRENT_DATA_DIR` environment variables.

## Current crontab settings

Every selected channel must have an explicit CT calibration. There is no generic
CT-ratio fallback.

For CH4 only:

```text
CURRENT_CHANNELS="CH4"
CURRENT_CH4_CT_V_FULL="5.0"
CURRENT_CH4_CT_I_FULL="50.0"
```

For CH4 and CH5:

```text
CURRENT_CHANNELS="CH4,CH5"
CURRENT_CH4_CT_V_FULL="5.0"
CURRENT_CH4_CT_I_FULL="50.0"
CURRENT_CH5_CT_V_FULL="3.0"
CURRENT_CH5_CT_I_FULL="10.0"
```

The conversion for each incoming channel is:

```text
current_A = (voltage_V / CT_voltage_full_scale_V) * CT_current_full_scale_A
```

If a selected channel is missing either calibration value, startup fails instead
of silently applying another channel's CT ratio.

## CSV storage

With `EQUIPMENT_NAME="DED"` and `CURRENT_CHANNELS="CH4"`, CSV files are stored by
default in:

```text
/home/pi/CT_ADC_Current_Pipeline/current_data/ded/ch4/csv/
```

For multiple channels:

```text
/home/pi/CT_ADC_Current_Pipeline/current_data/
└── ded/
    ├── ch4/
    │   └── csv/
    │       └── *.csv
    └── ch5/
        └── csv/
            └── *.csv
```

`CURRENT_CSV_ENABLED=true` starts CSV recording when the service starts.
`CURRENT_CSV_ENABLED=false` leaves MQTT current publication running but does not
save CSV rows.

CSV recording can also be changed while the service is running:

```bash
cd /home/pi/CT_ADC_Current_Pipeline
python3 -m current.csv_control_client on
python3 -m current.csv_control_client off
```

## ADC near-zero suppression

Example:

```text
CURRENT_NOISE_FLOOR_ENABLED=true
CURRENT_NOISE_FLOOR_A="0.01"
CURRENT_NOISE_FLOOR_MODE="zero"
```

A converted current below 0.01 A is published and saved as 0 A while the
unmodified converted value remains available as `raw_current_A`.

## MQTT topics

For DED and CH4:

```text
ded/current/ch4/rms
ded/current/ch4/voltage
ded/current/metadata
ded/current/status
ded/current/control/csv
ded/current/status/csv
```

The MQTT username and password are the same generic `MQTT_USER` and
`MQTT_PASSWORD` used by the sound service.

## Crontab templates

The same two integrated crontab templates are included here and in the sound
package:

```text
crontab.single_microphone.example
crontab.multiple_microphones.example
```

Use the single-microphone template when only one USB microphone is attached. Use
the multiple-microphone template when two sound processes must run with different
logical sensor names and USB paths.

## Installation and manual run

Raspberry Pi:

```bash
cd /home/pi/CT_ADC_Current_Pipeline
python3 -m pip install -r requirements.txt
python3 -m current
```

Windows:

```powershell
cd C:\path\to\CT_ADC_Current_Pipeline
py -m pip install -r requirements.txt
py -m current
```

See:

```text
docs/INSTALL_AND_RUN_MANUAL.md
```
