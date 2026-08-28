/*
  NeuroGoru combined ESP32 backend

  DS18B20: DATA GPIO4 with a 4.7k resistor from DATA to 3.3V
  MPU6050: SDA GPIO21, SCL GPIO22
  NEO-6M:  TX GPIO16 (ESP32 RX2), RX GPIO17 (ESP32 TX2)
  KY-012:  S GPIO25, + 3.3V, - GND
*/

#include <WiFi.h>
#include <ArduinoOTA.h>
#include <Wire.h>
#include <OneWire.h>
#include <DallasTemperature.h>
#include <TinyGPSPlus.h>
#include <math.h>

const char *AP_NAME = "NeuroGoru-ESP32";
const char *AP_PASSWORD = "NeuroGoru123";
const char *OTA_HOSTNAME = "neurogoru-esp32";
const char *OTA_PASSWORD = "NeuroGoru123";
const uint16_t TCP_PORT = 5010;

const uint8_t DS18B20_PIN = 4;
const uint8_t MPU6050_ADDRESS = 0x68;
const uint8_t GPS_RX_PIN = 16;
const uint8_t GPS_TX_PIN = 17;
const uint8_t BUZZER_PIN = 25;
const uint8_t ONBOARD_LED_PIN = 2;
const uint8_t VIBRATION_MOTOR_PIN = 32;
// The installed module is explicitly marked low-level trigger.
const uint8_t BUZZER_ON_LEVEL = LOW;
const unsigned long ONLINE_LED_INTERVAL_MS = 500;
const unsigned long FENCE_10M_MOTOR_TEST_MS = 1000;

WiFiServer server(TCP_PORT);
WiFiClient dashboardClient;
OneWire oneWire(DS18B20_PIN);
DallasTemperature temperatureSensor(&oneWire);
HardwareSerial gpsSerial(2);
TinyGPSPlus gps;

String receiveBuffer;
bool ds18b20Online = false;
bool mpu6050Online = false;
bool gpsOnline = false;
bool demoCowPositionActive = false;
double demoCowLatitude = 0.0;
double demoCowLongitude = 0.0;
uint8_t ds18b20FailureCount = 0;
uint8_t mpu6050FailureCount = 0;
unsigned long lastGpsByteMs = 0;
unsigned long lastTelemetryMs = 0;
unsigned long lastHeartbeatMs = 0;
unsigned long lastTemperatureAlertMs = 0;
unsigned long lastOnlineLedMs = 0;
bool onlineLedState = false;
bool fenceBuzzerActive = false;
unsigned long vibrationMotorUntilMs = 0;

// Deadline demo mode: a strong shake is treated as a simulated fall.
// This is intentionally separate from the ML prototype and must not be
// described as validated real-cattle fall detection.
const float DEMO_SHAKE_DELTA_G = 0.75f;
const float DEMO_IMPACT_G = 1.80f;
const unsigned long DEMO_MPU_SAMPLE_MS = 50;
const unsigned long DEMO_FALL_COOLDOWN_MS = 10000;
const unsigned long DEMO_BUZZER_MS = 2500;
unsigned long lastDemoMpuSampleMs = 0;
unsigned long lastDemoFallAlertMs = 0;
unsigned long demoFallBuzzerUntilMs = 0;
float previousDemoAx = 0.0f;
float previousDemoAy = 0.0f;
float previousDemoAz = 0.0f;
bool previousDemoSampleValid = false;

void setBuzzer(bool enabled) {
  digitalWrite(BUZZER_PIN, enabled ? BUZZER_ON_LEVEL : !BUZZER_ON_LEVEL);
}

void updateBuzzerOutput() {
  const unsigned long now = millis();
  const bool demoFallActive = now < demoFallBuzzerUntilMs;
  setBuzzer(fenceBuzzerActive || demoFallActive);
}

void setVibrationMotor(bool enabled) {
  // GPIO32 drives the 2N2222A base through the series resistor.
  digitalWrite(VIBRATION_MOTOR_PIN, enabled ? HIGH : LOW);
}

void runVibrationMotorFor(unsigned long durationMs) {
  vibrationMotorUntilMs = millis() + durationMs;
  setVibrationMotor(true);
}

void updateVibrationMotor() {
  // Fail-safe default: unless an explicit 10 m test timer is active, drive
  // GPIO32 LOW on every loop pass.
  if (vibrationMotorUntilMs == 0) {
    setVibrationMotor(false);
    return;
  }
  if (static_cast<long>(millis() - vibrationMotorUntilMs) >= 0) {
    vibrationMotorUntilMs = 0;
    setVibrationMotor(false);
    Serial.println("VIBRATION MOTOR: test complete, motor OFF");
  }
}

double fenceLatitude = 23.8376;
double fenceLongitude = 90.3576;
double fenceRadiusMeters = 250.0;

void sendLine(const String &message) {
  if (dashboardClient && dashboardClient.connected()) dashboardClient.println(message);
  Serial.println(message);
}

bool initializeMpu6050() {
  Wire.beginTransmission(MPU6050_ADDRESS);
  Wire.write(0x6B);
  Wire.write(0x00);
  if (Wire.endTransmission() != 0) return false;
  delay(50);
  Wire.beginTransmission(MPU6050_ADDRESS);
  Wire.write(0x75);
  if (Wire.endTransmission(false) != 0) return false;
  if (Wire.requestFrom(MPU6050_ADDRESS, (uint8_t)1) != 1) return false;
  return Wire.read() == 0x68;
}

bool readMpu6050(float &ax, float &ay, float &az) {
  Wire.beginTransmission(MPU6050_ADDRESS);
  Wire.write(0x3B);
  if (Wire.endTransmission(false) != 0) return false;
  if (Wire.requestFrom(MPU6050_ADDRESS, (uint8_t)6) != 6) return false;
  int16_t rawAx = (Wire.read() << 8) | Wire.read();
  int16_t rawAy = (Wire.read() << 8) | Wire.read();
  int16_t rawAz = (Wire.read() << 8) | Wire.read();
  ax = rawAx / 16384.0f;
  ay = rawAy / 16384.0f;
  az = rawAz / 16384.0f;
  return true;
}

void checkDemoFallDetection() {
  if (millis() - lastDemoMpuSampleMs < DEMO_MPU_SAMPLE_MS) return;
  lastDemoMpuSampleMs = millis();

  float ax = 0.0f, ay = 0.0f, az = 0.0f;
  if (!readMpu6050(ax, ay, az)) {
    previousDemoSampleValid = false;
    return;
  }

  float magnitude = sqrtf(ax * ax + ay * ay + az * az);
  float delta = 0.0f;
  if (previousDemoSampleValid) {
    float dx = ax - previousDemoAx;
    float dy = ay - previousDemoAy;
    float dz = az - previousDemoAz;
    delta = sqrtf(dx * dx + dy * dy + dz * dz);
  }

  previousDemoAx = ax;
  previousDemoAy = ay;
  previousDemoAz = az;

  bool cooldownFinished = lastDemoFallAlertMs == 0 ||
      millis() - lastDemoFallAlertMs >= DEMO_FALL_COOLDOWN_MS;
  bool strongShake = previousDemoSampleValid &&
      (delta >= DEMO_SHAKE_DELTA_G || magnitude >= DEMO_IMPACT_G);
  previousDemoSampleValid = true;

  if (strongShake && cooldownFinished) {
    lastDemoFallAlertMs = millis();
    demoFallBuzzerUntilMs = millis() + DEMO_BUZZER_MS;
    setBuzzer(true);
    sendLine("ALERT:FALL_DEMO:EMERGENCY - simulated cattle fall detected from MPU6050 shake. Verify the animal immediately.");
    Serial.println("DEMO_FALL_VALUES: magnitude=" + String(magnitude, 2) +
                   "g delta=" + String(delta, 2) + "g");
  }
}

double distanceMeters(double lat1, double lon1, double lat2, double lon2) {
  const double earthRadius = 6371000.0;
  double p1 = lat1 * DEG_TO_RAD;
  double p2 = lat2 * DEG_TO_RAD;
  double dp = (lat2 - lat1) * DEG_TO_RAD;
  double dl = (lon2 - lon1) * DEG_TO_RAD;
  double a = sin(dp / 2) * sin(dp / 2) + cos(p1) * cos(p2) * sin(dl / 2) * sin(dl / 2);
  return earthRadius * 2.0 * atan2(sqrt(a), sqrt(1.0 - a));
}

void sendSensorStatus() {
  sendLine(ds18b20Online ? "STATUS:DS18B20:ONLINE" : "ERROR:DS18B20:DISCONNECTED");
  sendLine(mpu6050Online ? "STATUS:MPU6050:ONLINE" : "ERROR:MPU6050:DISCONNECTED");
  sendLine(gpsOnline ? "STATUS:GPS:ONLINE" : "ERROR:GPS:DISCONNECTED");
}

void updateSensorState(bool newDsState, bool newMpuState, bool newGpsState) {
  if (newDsState != ds18b20Online) {
    ds18b20Online = newDsState;
    sendLine(ds18b20Online ? "STATUS:DS18B20:ONLINE" : "ERROR:DS18B20:DISCONNECTED");
  }
  if (newMpuState != mpu6050Online) {
    mpu6050Online = newMpuState;
    sendLine(mpu6050Online ? "STATUS:MPU6050:ONLINE" : "ERROR:MPU6050:DISCONNECTED");
  }
  if (newGpsState != gpsOnline) {
    gpsOnline = newGpsState;
    sendLine(gpsOnline ? "STATUS:GPS:ONLINE" : "ERROR:GPS:DISCONNECTED");
  }
}

void handleCommand(String command) {
  command.trim();
  if (!command.length()) return;
  if (command == "PING") sendLine("ACK:PONG");
  else if (command == "STATUS?") {
    sendLine("STATUS:ESP32:ONLINE");
    sendSensorStatus();
  } else if (command.startsWith("SET_FENCE:")) {
    String values = command.substring(10);
    int firstComma = values.indexOf(',');
    int secondComma = values.indexOf(',', firstComma + 1);
    if (firstComma > 0 && secondComma > firstComma) {
      fenceLatitude = values.substring(0, firstComma).toDouble();
      fenceLongitude = values.substring(firstComma + 1, secondComma).toDouble();
      fenceRadiusMeters = values.substring(secondComma + 1).toDouble();
      sendLine("ACK:FENCE:UPDATED");
      // Bench test requested by the UI: applying exactly 10.0 m runs the
      // motor for one second even when GPS does not yet have a valid fix.
      if (fabs(fenceRadiusMeters - 10.0) < 0.05) {
        runVibrationMotorFor(FENCE_10M_MOTOR_TEST_MS);
        sendLine("ACK:MOTOR:TESTING_1000MS");
        Serial.println("VIBRATION MOTOR: 10 m fence test started");
      } else {
        vibrationMotorUntilMs = 0;
        setVibrationMotor(false);
        sendLine("ACK:MOTOR:OFF");
      }
    } else sendLine("ALERT:Invalid fence command");
  } else if (command == "DEMO_COW:OFF") {
    demoCowPositionActive = false;
    sendLine("ACK:DEMO_COW:OFF");
  } else if (command.startsWith("DEMO_COW:")) {
    String values = command.substring(9);
    int comma = values.indexOf(',');
    if (comma > 0) {
      demoCowLatitude = values.substring(0, comma).toDouble();
      demoCowLongitude = values.substring(comma + 1).toDouble();
      demoCowPositionActive = true;
      sendLine("ACK:DEMO_COW:UPDATED");
    } else sendLine("ALERT:Invalid demo cow position");
  } else if (command == "TEST_ALERT") sendLine("ALERT:Test alert from ESP32");
  else sendLine("ACK:RECEIVED:" + command);
}

void sendTelemetry() {
  temperatureSensor.requestTemperatures();
  float temperature = temperatureSensor.getTempCByIndex(0);
  bool temperatureValid = temperature != DEVICE_DISCONNECTED_C && temperature > -55.0f && temperature < 125.0f;

  float ax = 0, ay = 0, az = 0;
  bool mpuValid = readMpu6050(ax, ay, az);

  // Do not mark a sensor offline because of one temporary bad read.
  ds18b20FailureCount = temperatureValid ? 0 : min(10, ds18b20FailureCount + 1);
  mpu6050FailureCount = mpuValid ? 0 : min(10, mpu6050FailureCount + 1);
  bool stableDsState = temperatureValid || (ds18b20Online && ds18b20FailureCount < 3);
  bool stableMpuState = mpuValid || (mpu6050Online && mpu6050FailureCount < 3);
  bool currentGpsState = lastGpsByteMs != 0 && millis() - lastGpsByteMs < 5000;
  updateSensorState(stableDsState, stableMpuState, currentGpsState);

  bool gpsValid = gps.location.isValid() && gps.location.age() < 5000;
  bool positionValid = gpsValid || demoCowPositionActive;
  uint32_t gpsSatellites = (currentGpsState && gps.satellites.isValid())
      ? gps.satellites.value()
      : 0;
  double latitude = demoCowPositionActive ? demoCowLatitude : (gpsValid ? gps.location.lat() : 0.0);
  double longitude = demoCowPositionActive ? demoCowLongitude : (gpsValid ? gps.location.lng() : 0.0);
  double altitude = gps.altitude.isValid() ? gps.altitude.meters() : 0.0;
  double signedFenceDistance = 0.0;
  String fenceStatus = "waiting";
  bool fenceBreached = false;
  if (positionValid) {
    double centerDistance = distanceMeters(latitude, longitude, fenceLatitude, fenceLongitude);
    signedFenceDistance = fenceRadiusMeters - centerDistance;
    // Treat the boundary itself as a breach for the indoor demonstration.
    fenceBreached = signedFenceDistance <= 0;
    fenceStatus = fenceBreached ? "outside" : "inside";
  }
  fenceBuzzerActive = fenceBreached;
  updateBuzzerOutput();

  String json = "TELEMETRY:{";
  json += "\"latitude\":" + String(positionValid ? latitude : 0.0, 8);
  json += ",\"longitude\":" + String(positionValid ? longitude : 0.0, 8);
  json += ",\"altitude\":" + String(altitude, 1);
  json += ",\"temperature\":" + String(temperatureValid ? temperature : 0.0, 2);
  json += ",\"acceleration_x\":" + String(mpuValid ? ax : 0.0, 3);
  json += ",\"acceleration_y\":" + String(mpuValid ? ay : 0.0, 3);
  json += ",\"acceleration_z\":" + String(mpuValid ? az : 0.0, 3);
  json += ",\"fence_distance\":" + String(signedFenceDistance, 1);
  json += ",\"fence_status\":\"" + fenceStatus + "\"";
  json += ",\"gps_detected\":" + String(currentGpsState ? "true" : "false");
  json += ",\"gps_valid\":" + String(gpsValid ? "true" : "false");
  json += ",\"gps_satellites\":" + String(gpsSatellites);
  json += ",\"position_valid\":" + String(positionValid ? "true" : "false");
  json += ",\"demo_position_active\":" + String(demoCowPositionActive ? "true" : "false");
  json += "}";
  sendLine(json);

  if (temperatureValid && temperature >= 40.0f && millis() - lastTemperatureAlertMs >= 30000) {
    lastTemperatureAlertMs = millis();
    sendLine("ALERT:High cattle temperature: " + String(temperature, 1) + " C");
  }
}

void setup() {
  // Configure the motor output before Serial, Wi-Fi, or sensors so the
  // transistor cannot remain enabled during application startup.
  digitalWrite(VIBRATION_MOTOR_PIN, LOW);
  pinMode(VIBRATION_MOTOR_PIN, OUTPUT);
  setVibrationMotor(false);
  vibrationMotorUntilMs = 0;

  Serial.begin(115200);
  pinMode(ONBOARD_LED_PIN, OUTPUT);
  digitalWrite(ONBOARD_LED_PIN, LOW);
  // Write the inactive level before enabling the output to avoid a low pulse.
  digitalWrite(BUZZER_PIN, !BUZZER_ON_LEVEL);
  pinMode(BUZZER_PIN, OUTPUT);
  setBuzzer(false);
  Wire.begin(21, 22);
  temperatureSensor.begin();
  gpsSerial.begin(9600, SERIAL_8N1, GPS_RX_PIN, GPS_TX_PIN);
  ds18b20Online = temperatureSensor.getDeviceCount() > 0;
  mpu6050Online = initializeMpu6050();

  WiFi.mode(WIFI_AP);
  if (!WiFi.softAP(AP_NAME, AP_PASSWORD)) {
    Serial.println("ERROR: Wi-Fi access point could not start");
    return;
  }
  server.begin();
  server.setNoDelay(true);

  ArduinoOTA.setHostname(OTA_HOSTNAME);
  ArduinoOTA.setPassword(OTA_PASSWORD);
  ArduinoOTA.onStart([]() {
    setBuzzer(false);
    Serial.println("OTA update starting; buzzer forced OFF");
  });
  ArduinoOTA.onEnd([]() {
    setBuzzer(false);
    Serial.println("OTA update complete");
  });
  ArduinoOTA.onError([](ota_error_t error) {
    setBuzzer(false);
    Serial.printf("OTA error %u\n", error);
  });
  ArduinoOTA.begin();

  Serial.println("NeuroGoru combined backend ready");
  Serial.println("Wi-Fi: " + String(AP_NAME));
  Serial.println("Password: " + String(AP_PASSWORD));
  Serial.println("IP: " + WiFi.softAPIP().toString());
  Serial.println("TCP port: " + String(TCP_PORT));
  Serial.println("OTA hostname: " + String(OTA_HOSTNAME));
  Serial.println("DS18B20: " + String(ds18b20Online ? "DETECTED" : "NOT DETECTED"));
  Serial.println("MPU6050: " + String(mpu6050Online ? "DETECTED" : "NOT DETECTED"));
  Serial.println("DEMO FALL DETECTION: SHAKE MPU6050 TO TRIGGER EMERGENCY ALERT");
  Serial.println("GPS: WAITING FOR SERIAL DATA");
}

void loop() {
  ArduinoOTA.handle();

  if (millis() - lastOnlineLedMs >= ONLINE_LED_INTERVAL_MS) {
    lastOnlineLedMs = millis();
    onlineLedState = !onlineLedState;
    digitalWrite(ONBOARD_LED_PIN, onlineLedState ? HIGH : LOW);
  }

  while (gpsSerial.available()) {
    gps.encode(gpsSerial.read());
    lastGpsByteMs = millis();
  }

  // Only accept a client when no dashboard is currently connected. Calling
  // stop() for every available() result causes an online/offline loop.
  if (!dashboardClient || !dashboardClient.connected()) {
    WiFiClient incoming = server.available();
    if (incoming) {
      dashboardClient = incoming;
      dashboardClient.setNoDelay(true);
      receiveBuffer = "";
      // A UI connection must never start the motor.
      vibrationMotorUntilMs = 0;
      setVibrationMotor(false);
      sendLine("HELLO:NEUROGORU_ESP32");
      sendLine("STATUS:ESP32:ONLINE");
      sendSensorStatus();
    }
  }

  if (dashboardClient && dashboardClient.connected()) {
    while (dashboardClient.available()) {
      char value = static_cast<char>(dashboardClient.read());
      if (value == '\n') {
        handleCommand(receiveBuffer);
        receiveBuffer = "";
      } else if (value != '\r' && receiveBuffer.length() < 256) receiveBuffer += value;
    }

    if (millis() - lastHeartbeatMs >= 10000) {
      lastHeartbeatMs = millis();
      sendLine("HEARTBEAT:ESP32:OK");
    }
  }

  // Sensor monitoring and the buzzer must keep working even when the
  // dashboard/laptop is disconnected.
  if (mpu6050Online) checkDemoFallDetection();

  if (millis() - lastTelemetryMs >= 2000) {
    lastTelemetryMs = millis();
    sendTelemetry();
  }
  updateBuzzerOutput();
  updateVibrationMotor();
  delay(2);
}
