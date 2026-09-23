/*
  NeuroGoru combined ESP32 backend

  DS18B20: DATA GPIO13 with a 4.7k resistor from DATA to 3.3V
  MPU6050: SDA GPIO21, SCL GPIO22
  NEO-6M:  TX GPIO5 (ESP32 RX2), RX GPIO17 (ESP32 TX2)
  Passive buzzer: GPIO15 to GND
  MX1508: IN1 GPIO26, IN2 GPIO25
*/

#include <WiFi.h>
#include <ArduinoOTA.h>
#include <Wire.h>
#include <OneWire.h>
#include <DallasTemperature.h>
#include <TinyGPSPlus.h>
#include <Adafruit_MPU6050.h>
#include <math.h>

const char *AP_NAME = "NeuroGoru-ESP32";
const char *AP_PASSWORD = "NeuroGoru123";
const char *OTA_HOSTNAME = "neurogoru-esp32";
const char *OTA_PASSWORD = "NeuroGoru123";
const uint16_t TCP_PORT = 5010;

const uint8_t DS18B20_PIN = 13;
uint8_t mpu6050Address = 0x68;
const uint8_t GPS_RX_PIN = 5;
const uint8_t GPS_TX_PIN = 17;
const uint8_t BUZZER_PIN = 15;
const uint8_t ONBOARD_LED_PIN = 2;
const uint8_t MOTOR_IN1_PIN = 26;
const uint8_t MOTOR_IN2_PIN = 25;
const unsigned long ONLINE_LED_INTERVAL_MS = 500;
const unsigned long DS18B20_RETRY_MS = 5000;
const unsigned long MPU6050_RETRY_MS = 5000;
const unsigned long GEOFENCE_CHECK_INTERVAL_MS = 1000;
const unsigned long GPS_MAX_AGE_MS = 5000;
const uint8_t MIN_GPS_SATELLITES = 4;
const uint8_t OUTSIDE_SAMPLES_TO_ALARM = 3;
const double MIN_FENCE_RADIUS_METERS = 5.0;

WiFiServer server(TCP_PORT);
WiFiClient dashboardClient;
OneWire oneWire(DS18B20_PIN);
DallasTemperature temperatureSensor(&oneWire);
HardwareSerial gpsSerial(2);
TinyGPSPlus gps;
Adafruit_MPU6050 mpu;

String receiveBuffer;
bool ds18b20Online = false;
bool mpu6050Online = false;
bool gpsOnline = false;
bool hasStoredGpsFix = false;
double storedGpsLatitude = 0.0;
double storedGpsLongitude = 0.0;
double storedGpsAltitude = 0.0;
unsigned long storedGpsFixAtMs = 0;
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
unsigned long lastDs18b20RetryMs = 0;
unsigned long lastMpu6050RetryMs = 0;
bool onlineLedState = false;
bool fenceBuzzerActive = false;
bool fenceAlarmActive = false;
bool buzzerOutputActive = false;
bool fenceSet = false;
uint8_t outsideFenceSamples = 0;
unsigned long lastGeofenceCheckMs = 0;

// Gentle box-test fall mode: calibrate the normal gravity direction, then
// detect a sustained orientation change. No hard impact is required.
// This is intentionally separate from the ML prototype and must not be
// described as validated real-cattle fall detection.
const float DEMO_FALL_TILT_DEGREES = 25.0f;
const float DEMO_FALL_RECOVERY_DEGREES = 12.0f;
const uint8_t DEMO_FALL_TILT_SAMPLES_REQUIRED = 8;
const uint8_t DEMO_FALL_RECOVERY_SAMPLES_REQUIRED = 12;
const uint8_t DEMO_BASELINE_SAMPLES_REQUIRED = 40;
// Demonstration thresholds: a short, gentle drop should produce a small
// low-gravity dip followed by a landing pulse. Requiring that sequence avoids
// treating ordinary movement as a fall.
const float DEMO_DROP_LOW_RATIO = 0.98f;
const float DEMO_DROP_LANDING_RATIO = 1.02f;
const uint8_t DEMO_DROP_LOW_SAMPLES_REQUIRED = 1;
const unsigned long DEMO_DROP_WINDOW_MS = 1500;
const unsigned long DEMO_MPU_SAMPLE_MS = 10;
const unsigned long DEMO_FALL_COOLDOWN_MS = 5000;
const unsigned long DEMO_FALL_SETTLE_MS = 2000;
unsigned long lastDemoMpuSampleMs = 0;
unsigned long lastDemoFallAlertMs = 0;
float baselineAx = 0.0f, baselineAy = 0.0f, baselineAz = 0.0f;
uint8_t baselineSampleCount = 0;
uint8_t tiltSampleCount = 0;
uint8_t recoverySampleCount = 0;
bool fallTiltLatched = false;
bool demoDropStarted = false;
unsigned long demoDropStartedMs = 0;
uint8_t demoDropLowSampleCount = 0;
float previousDemoAx = 0.0f;
float previousDemoAy = 0.0f;
float previousDemoAz = 0.0f;
bool previousDemoSampleValid = false;

void setBuzzer(bool enabled) {
  if (buzzerOutputActive == enabled) return;
  buzzerOutputActive = enabled;
  if (enabled) tone(BUZZER_PIN, 2000);
  else noTone(BUZZER_PIN);
}

// Exact MX1508 motor control used by Fahim4588/Cow_Collar.
void motor(bool on) {
  digitalWrite(MOTOR_IN1_PIN, on ? HIGH : LOW);
  digitalWrite(MOTOR_IN2_PIN, LOW);
}

void updateBuzzerOutput() {
  // The passive buzzer is reserved exclusively for fence-boundary warnings.
  setBuzzer(fenceBuzzerActive);
}

double fenceLatitude = 23.8376;
double fenceLongitude = 90.3576;
double fenceRadiusMeters = 250.0;
String fenceShape = "circle";

void setAlarm(bool enabled) {
  const bool stateChanged = fenceAlarmActive != enabled;
  fenceAlarmActive = enabled;
  fenceBuzzerActive = enabled;
  motor(enabled);
  updateBuzzerOutput();
  if (!stateChanged) return;
  sendLine(enabled
      ? "ALERT:GEOFENCE:Outside fence - buzzer and vibration enabled"
      : "STATUS:GEOFENCE:Inside fence - alarm stopped");
}

void sendLine(const String &message) {
  if (dashboardClient && dashboardClient.connected()) dashboardClient.println(message);
  Serial.println(message);
}

bool initializeMpu6050() {
  if (mpu.begin(0x68, &Wire)) {
    mpu6050Address = 0x68;
    mpu.setAccelerometerRange(MPU6050_RANGE_8_G);
    mpu.setFilterBandwidth(MPU6050_BAND_21_HZ);
    return true;
  }
  if (mpu.begin(0x69, &Wire)) {
    mpu6050Address = 0x69;
    mpu.setAccelerometerRange(MPU6050_RANGE_8_G);
    mpu.setFilterBandwidth(MPU6050_BAND_21_HZ);
    return true;
  }
  return false;
}

bool readMpu6050(float &ax, float &ay, float &az) {
  sensors_event_t acceleration, gyro, temperature;
  if (!mpu.getEvent(&acceleration, &gyro, &temperature)) return false;
  ax = acceleration.acceleration.x / SENSORS_GRAVITY_STANDARD;
  ay = acceleration.acceleration.y / SENSORS_GRAVITY_STANDARD;
  az = acceleration.acceleration.z / SENSORS_GRAVITY_STANDARD;
  return true;
}

void checkDemoFallDetection() {
  if (millis() - lastDemoMpuSampleMs < DEMO_MPU_SAMPLE_MS) return;
  lastDemoMpuSampleMs = millis();

  float ax = 0.0f, ay = 0.0f, az = 0.0f;
  if (!readMpu6050(ax, ay, az)) {
    tiltSampleCount = 0;
    recoverySampleCount = 0;
    demoDropLowSampleCount = 0;
    demoDropStarted = false;
    return;
  }

  const float magnitude = sqrtf(ax * ax + ay * ay + az * az);
  if (!isfinite(magnitude) || magnitude < 0.20f || magnitude > 8.0f) {
    tiltSampleCount = 0;
    recoverySampleCount = 0;
    return;
  }

  if (millis() < DEMO_FALL_SETTLE_MS) {
    return;
  }

  if (baselineSampleCount < DEMO_BASELINE_SAMPLES_REQUIRED) {
    baselineAx += ax;
    baselineAy += ay;
    baselineAz += az;
    baselineSampleCount++;
    if (baselineSampleCount == DEMO_BASELINE_SAMPLES_REQUIRED) {
      baselineAx /= DEMO_BASELINE_SAMPLES_REQUIRED;
      baselineAy /= DEMO_BASELINE_SAMPLES_REQUIRED;
      baselineAz /= DEMO_BASELINE_SAMPLES_REQUIRED;
      Serial.println("FALL_TEST: orientation baseline ready; gently lay box on its side");
    }
    return;
  }

  const float baselineMagnitude = sqrtf(
      baselineAx * baselineAx + baselineAy * baselineAy + baselineAz * baselineAz);
  const float dot = ax * baselineAx + ay * baselineAy + az * baselineAz;
  const float cosine = constrain(dot / (magnitude * baselineMagnitude), -1.0f, 1.0f);
  const float tiltDegrees = acosf(cosine) * 180.0f / PI;
  const float gravityRatio = magnitude / baselineMagnitude;
  const bool cooldownFinished = lastDemoFallAlertMs == 0 ||
      millis() - lastDemoFallAlertMs >= DEMO_FALL_COOLDOWN_MS;

  // Gentle-drop detector: first observe a brief reduction in apparent gravity,
  // then a modest landing increase. Ratios make this tolerant of MPU6050 clones
  // whose absolute acceleration scale is inaccurate.
  if (!fallTiltLatched) {
    if (!demoDropStarted) {
      if (gravityRatio <= DEMO_DROP_LOW_RATIO) {
        if (demoDropLowSampleCount < DEMO_DROP_LOW_SAMPLES_REQUIRED) {
          ++demoDropLowSampleCount;
        }
        if (demoDropLowSampleCount >= DEMO_DROP_LOW_SAMPLES_REQUIRED) {
          demoDropStarted = true;
          demoDropStartedMs = millis();
          Serial.println("FALL_TEST: low-gravity phase detected; waiting for landing");
        }
      } else {
        demoDropLowSampleCount = 0;
      }
    } else if (millis() - demoDropStartedMs > DEMO_DROP_WINDOW_MS) {
      demoDropStarted = false;
      demoDropLowSampleCount = 0;
    }
  }

  const bool gentleDropDetected = demoDropStarted &&
      gravityRatio >= DEMO_DROP_LANDING_RATIO &&
      millis() - demoDropStartedMs <= DEMO_DROP_WINDOW_MS;

  if (!fallTiltLatched) {
    if (tiltDegrees >= DEMO_FALL_TILT_DEGREES) {
      if (tiltSampleCount < DEMO_FALL_TILT_SAMPLES_REQUIRED) {
        ++tiltSampleCount;
      }
    } else {
      tiltSampleCount = 0;
    }
  } else {
    if (tiltDegrees <= DEMO_FALL_RECOVERY_DEGREES) {
      if (recoverySampleCount < DEMO_FALL_RECOVERY_SAMPLES_REQUIRED) {
        ++recoverySampleCount;
      }
    } else {
      recoverySampleCount = 0;
    }
    if (recoverySampleCount >= DEMO_FALL_RECOVERY_SAMPLES_REQUIRED) {
      fallTiltLatched = false;
      recoverySampleCount = 0;
      Serial.println("FALL_TEST: normal orientation restored; detector re-armed");
    }
  }

  if (!fallTiltLatched &&
      (tiltSampleCount >= DEMO_FALL_TILT_SAMPLES_REQUIRED || gentleDropDetected) &&
      cooldownFinished) {
    fallTiltLatched = true;
    tiltSampleCount = 0;
    demoDropStarted = false;
    demoDropLowSampleCount = 0;
    lastDemoFallAlertMs = millis();
    sendLine(gentleDropDetected
        ? "ALERT:FALL_DEMO:EMERGENCY - gentle drop and landing detected by MPU6050. Verify the animal immediately."
        : "ALERT:FALL_DEMO:EMERGENCY - sustained cattle-collar tilt detected by MPU6050. Verify the animal immediately.");
    Serial.println("DEMO_FALL_VALUES: tilt=" + String(tiltDegrees, 1) +
        " degrees, gravity_ratio=" + String(gravityRatio, 2));
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

double normalizedFenceDistance(double latitude, double longitude) {
  const double north = (latitude - fenceLatitude) * 111320.0;
  const double east = (longitude - fenceLongitude) * 111320.0 *
      cos(fenceLatitude * DEG_TO_RAD);
  if (fenceShape == "oval") {
    return sqrt(
        (east * east) / (fenceRadiusMeters * fenceRadiusMeters) +
        (north * north) / (0.70 * fenceRadiusMeters * 0.70 * fenceRadiusMeters));
  }
  if (fenceShape == "square") {
    return max(abs(east), abs(north)) / fenceRadiusMeters;
  }
  if (fenceShape == "rectangle") {
    return max(abs(east) / fenceRadiusMeters,
        abs(north) / (0.65 * fenceRadiusMeters));
  }
  return sqrt(east * east + north * north) / fenceRadiusMeters;
}

bool gpsReadyForGeofence() {
  return gps.location.isValid() &&
      gps.location.age() < GPS_MAX_AGE_MS &&
      gps.satellites.isValid() &&
      gps.satellites.value() >= MIN_GPS_SATELLITES;
}

void evaluateGeofence() {
  if (millis() - lastGeofenceCheckMs < GEOFENCE_CHECK_INTERVAL_MS) return;
  lastGeofenceCheckMs = millis();

  if (!fenceSet) {
    outsideFenceSamples = 0;
    setAlarm(false);
    return;
  }

  // Match the reference Cow_Collar behavior: physical alarms are controlled
  // only by a fresh real GPS fix with at least four satellites. The dashboard's
  // demo cow remains visual-only and can never switch the real motor/buzzer.
  if (!gpsReadyForGeofence()) {
    outsideFenceSamples = 0;
      setAlarm(false);
    return;
  }
  const double latitude = gps.location.lat();
  const double longitude = gps.location.lng();

  const double normalizedDistance = normalizedFenceDistance(latitude, longitude);
  if (normalizedDistance > 1.0) {
    // Outside the circle: warn immediately, then start the motor only after
    // three consecutive outside readings to reject a single GPS jump.
    fenceBuzzerActive = true;
    updateBuzzerOutput();
    if (outsideFenceSamples < OUTSIDE_SAMPLES_TO_ALARM) outsideFenceSamples++;
    if (outsideFenceSamples >= OUTSIDE_SAMPLES_TO_ALARM) setAlarm(true);
  } else {
    // Back inside: the motor stops immediately. The buzzer sounds only in the
    // final 20% of the radius (minimum 2 m, maximum 10 m) near the boundary.
    outsideFenceSamples = 0;
    setAlarm(false);
    const double warningDistance = constrain(fenceRadiusMeters * 0.20, 2.0, 10.0);
    fenceBuzzerActive = normalizedDistance >= 1.0 - warningDistance / fenceRadiusMeters;
    updateBuzzerOutput();
  }
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
    int thirdComma = values.indexOf(',', secondComma + 1);
    if (firstComma > 0 && secondComma > firstComma) {
      const double latitude = values.substring(0, firstComma).toDouble();
      const double longitude = values.substring(firstComma + 1, secondComma).toDouble();
      const double radius = values.substring(
          secondComma + 1, thirdComma > secondComma ? thirdComma : values.length()).toDouble();
      String requestedShape = thirdComma > secondComma
          ? values.substring(thirdComma + 1) : "circle";
      requestedShape.toLowerCase();
      const bool validShape = requestedShape == "circle" || requestedShape == "oval" ||
          requestedShape == "square" || requestedShape == "rectangle";
      if (latitude < -90.0 || latitude > 90.0 || longitude < -180.0 ||
          longitude > 180.0 || radius < MIN_FENCE_RADIUS_METERS || radius > 100000.0 || !validShape) {
        sendLine("ALERT:Invalid fence coordinate or radius (minimum 5 m)");
      } else {
        fenceLatitude = latitude;
        fenceLongitude = longitude;
        fenceRadiusMeters = radius;
        fenceShape = requestedShape;
        fenceSet = true;
        outsideFenceSamples = 0;
        setAlarm(false);
        sendLine("ACK:FENCE:UPDATED");
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
  // A DS18B20 connected after boot (or after a loose-wire interruption) must
  // be rediscovered without restarting the ESP32.
  if (!ds18b20Online && millis() - lastDs18b20RetryMs >= DS18B20_RETRY_MS) {
    lastDs18b20RetryMs = millis();
    temperatureSensor.begin();
    if (temperatureSensor.getDeviceCount() > 0) {
      ds18b20FailureCount = 0;
      ds18b20Online = true;
      sendLine("STATUS:DS18B20:ONLINE");
      Serial.println("DS18B20: rediscovered");
    }
  }
  if (!mpu6050Online && millis() - lastMpu6050RetryMs >= MPU6050_RETRY_MS) {
    lastMpu6050RetryMs = millis();
    if (initializeMpu6050()) {
      mpu6050FailureCount = 0;
      mpu6050Online = true;
      sendLine("STATUS:MPU6050:ONLINE");
      Serial.println("MPU6050: rediscovered at I2C address 0x" + String(mpu6050Address, HEX));
    }
  }
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
  if (gpsValid) {
    storedGpsLatitude = gps.location.lat();
    storedGpsLongitude = gps.location.lng();
    if (gps.altitude.isValid()) storedGpsAltitude = gps.altitude.meters();
    storedGpsFixAtMs = millis();
    hasStoredGpsFix = true;
  }
  bool positionValid = gpsValid || hasStoredGpsFix || demoCowPositionActive;
  uint32_t gpsSatellites = (currentGpsState && gps.satellites.isValid())
      ? gps.satellites.value()
      : 0;
  double latitude = demoCowPositionActive ? demoCowLatitude :
      (hasStoredGpsFix ? storedGpsLatitude : 0.0);
  double longitude = demoCowPositionActive ? demoCowLongitude :
      (hasStoredGpsFix ? storedGpsLongitude : 0.0);
  double altitude = demoCowPositionActive ? 0.0 :
      (hasStoredGpsFix ? storedGpsAltitude : 0.0);
  double signedFenceDistance = 0.0;
  String fenceStatus = "waiting";
  bool fenceBreached = false;
  if (positionValid) {
    const double normalizedDistance = normalizedFenceDistance(latitude, longitude);
    signedFenceDistance = (1.0 - normalizedDistance) * fenceRadiusMeters;
    // Treat the boundary itself as a breach for the indoor demonstration.
    fenceBreached = signedFenceDistance <= 0;
    fenceStatus = fenceBreached ? "outside" : "inside";
  }
  String json = "TELEMETRY:{";
  json += "\"latitude\":" + String(positionValid ? latitude : 0.0, 6);
  json += ",\"longitude\":" + String(positionValid ? longitude : 0.0, 6);
  json += ",\"altitude\":" + String(altitude, 1);
  json += ",\"temperature\":" + String(temperatureValid ? temperature : 0.0, 2);
  json += ",\"acceleration_x\":" + String(mpuValid ? ax : 0.0, 3);
  json += ",\"acceleration_y\":" + String(mpuValid ? ay : 0.0, 3);
  json += ",\"acceleration_z\":" + String(mpuValid ? az : 0.0, 3);
  json += ",\"fence_distance\":" + String(signedFenceDistance, 1);
  json += ",\"fence_status\":\"" + fenceStatus + "\"";
  json += ",\"fence_set\":" + String(fenceSet ? "true" : "false");
  json += ",\"fence_latitude\":" + String(fenceLatitude, 8);
  json += ",\"fence_longitude\":" + String(fenceLongitude, 8);
  json += ",\"fence_radius\":" + String(fenceRadiusMeters, 1);
  json += ",\"fence_shape\":\"" + fenceShape + "\"";
  json += ",\"gps_detected\":" + String(currentGpsState ? "true" : "false");
  json += ",\"gps_valid\":" + String(gpsValid ? "true" : "false");
  json += ",\"gps_fix_stored\":" + String(hasStoredGpsFix ? "true" : "false");
  json += ",\"gps_fix_age_seconds\":" + String(hasStoredGpsFix ? (millis() - storedGpsFixAtMs) / 1000UL : 0);
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
  // Start both alarm outputs OFF. Geofence evaluation controls them together.
  pinMode(MOTOR_IN1_PIN, OUTPUT);
  pinMode(MOTOR_IN2_PIN, OUTPUT);
  motor(false);

  Serial.begin(115200);
  pinMode(ONBOARD_LED_PIN, OUTPUT);
  digitalWrite(ONBOARD_LED_PIN, LOW);
  pinMode(BUZZER_PIN, OUTPUT);
  noTone(BUZZER_PIN);
  buzzerOutputActive = false;
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
    setAlarm(false);
    updateBuzzerOutput();
    Serial.println("OTA update starting; alarm outputs forced OFF");
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
  evaluateGeofence();

  if (millis() - lastTelemetryMs >= 2000) {
    lastTelemetryMs = millis();
    sendTelemetry();
  }
  updateBuzzerOutput();
  delay(2);
}
