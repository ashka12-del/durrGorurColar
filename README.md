# NeuroGoru UI

PySide6 desktop dashboard for the NeuroGoru ESP32 livestock monitor. The app has
exactly five sections: Dashboard, GPS Map, Alerts, History, and About.

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe main.py
```

Telemetry is read from the ESP32 over local Wi-Fi/TCP and retained in session history.

## ESP32 connection

The dashboard now monitors an ESP32 Wi-Fi TCP endpoint, reconnects automatically,
and shows connection changes and incoming newline-delimited messages in the event
registry and popup notifications. Configure the address before starting:

```powershell
$env:NEUROGORU_ESP32_HOST="192.168.4.1"
$env:NEUROGORU_ESP32_PORT="5010"
.venv\Scripts\python.exe main.py
```

The ESP32 server should send each alert or telemetry message terminated by `\n`.

Telemetry format:

```text
TELEMETRY:{"latitude":23.8376,"longitude":90.3576,"altitude":12.4,"temperature":38.6,"fence_distance":87.2,"fence_status":"inside"}
```

Fence updates are sent back as `SET_FENCE:latitude,longitude,radius` and acknowledged
with `ACK:FENCE:UPDATED`. Assign the real GPS readings to `currentLatitude`,
`currentLongitude`, and `currentAltitude`. The DS18B20 temperature is read automatically.

### Arduino IDE firmware

Open `NEUROGORU_ESP32_BACKEND.ino` in Arduino IDE, select the correct ESP32
board and COM port, then upload it. Connect the PC to the `NeuroGoru-ESP32`
Wi-Fi network with password `NeuroGoru123`, then start this dashboard. The
default dashboard address already matches the firmware (`192.168.4.1:5010`).

The combined firmware also reads DS18B20, MPU6050, and NEO-6M GPS. Install
these Arduino libraries from **Tools > Manage Libraries** before compiling:

- OneWire by Paul Stoffregen
- DallasTemperature by Miles Burton
- TinyGPSPlus by Mikal Hart

`WiFi` and `Wire` are included with the ESP32 board package.

Use the combined sketch in `NEUROGORU_ESP32_BACKEND/NEUROGORU_ESP32_BACKEND.ino`.
Before compiling, install these Arduino IDE libraries through Library Manager:

- `OneWire` by Paul Stoffregen
- `DallasTemperature` by Miles Burton

DS18B20 connections:

- VCC to ESP32 3.3V
- GND to ESP32 GND
- DATA to ESP32 GPIO 4
- 4.7 kΩ pull-up resistor between DATA and 3.3V if the module has no built-in resistor

Change `DS18B20_DATA_PIN` in the sketch if another ESP32 GPIO is used. Temperature
is transmitted every second even while the GPS does not yet have a valid fix.

MPU6050 connections:

- VCC to ESP32 3.3V
- GND to ESP32 GND
- SDA to ESP32 GPIO 21
- SCL to ESP32 GPIO 22

KY-012 active buzzer connections:

- `S` to ESP32 GPIO 25
- `+` to ESP32 3.3V
- `-` to ESP32 GND

The buzzer turns on when the valid GPS location moves outside the configured
virtual-fence radius and turns off after returning inside. For example, with a
50 m radius it sounds when the cattle is more than 50 m from the fence center.

The dashboard status strip shows ESP32, MPU6050, DS18B20, and NEO-6M GPS connectivity.
Temperature and acceleration X/Y/Z update once per second. If your wiring uses
different pins, change `MPU_SDA_PIN`, `MPU_SCL_PIN`, or `DS18B20_DATA_PIN`.
