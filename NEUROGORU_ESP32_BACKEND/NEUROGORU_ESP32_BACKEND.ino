/*
  NeuroGoru combined ESP32 backend

  DS18B20: DATA GPIO4 with a 4.7k resistor from DATA to 3.3V
  MPU6050: SDA GPIO21, SCL GPIO22
  NEO-6M:  TX GPIO16 (ESP32 RX2), RX GPIO17 (ESP32 TX2)
  KY-012:  S GPIO25, + 3.3V, - GND
*/

#include <WiFi.h>
#include <Wire.h>
#include <OneWire.h>
#include <DallasTemperature.h>
#include <TinyGPSPlus.h>
#include <math.h>

const char *AP_NAME = "NeuroGoru-ESP32";
const char *AP_PASSWORD = "NeuroGoru123";
const uint16_t TCP_PORT = 5010;

const uint8_t DS18B20_PIN = 4;
const uint8_t MPU6050_ADDRESS = 0x68;
const uint8_t GPS_RX_PIN = 16;
const uint8_t GPS_TX_PIN = 17;
const uint8_t BUZZER_PIN = 25;

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
uint8_t ds18b20FailureCount = 0;
uint8_t mpu6050FailureCount = 0;
unsigned long lastGpsByteMs = 0;
unsigned long lastTelemetryMs = 0;
unsigned long lastHeartbeatMs = 0;
unsigned long lastTemperatureAlertMs = 0;

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
    } else sendLine("ALERT:Invalid fence command");
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
  double latitude = gpsValid ? gps.location.lat() : 0.0;
  double longitude = gpsValid ? gps.location.lng() : 0.0;
  double altitude = gps.altitude.isValid() ? gps.altitude.meters() : 0.0;
  double signedFenceDistance = 0.0;
  String fenceStatus = "waiting";
  bool fenceBreached = false;
  if (gpsValid) {
    double centerDistance = distanceMeters(latitude, longitude, fenceLatitude, fenceLongitude);
    signedFenceDistance = fenceRadiusMeters - centerDistance;
    fenceBreached = signedFenceDistance < 0;
    fenceStatus = fenceBreached ? "outside" : "inside";
  }
  digitalWrite(BUZZER_PIN, fenceBreached ? HIGH : LOW);

  String json = "TELEMETRY:{";
  json += "\"latitude\":" + String(gpsValid ? latitude : 0.0, 6);
  json += ",\"longitude\":" + String(gpsValid ? longitude : 0.0, 6);
  json += ",\"altitude\":" + String(altitude, 1);
  json += ",\"temperature\":" + String(temperatureValid ? temperature : 0.0, 2);
  json += ",\"acceleration_x\":" + String(mpuValid ? ax : 0.0, 3);
  json += ",\"acceleration_y\":" + String(mpuValid ? ay : 0.0, 3);
  json += ",\"acceleration_z\":" + String(mpuValid ? az : 0.0, 3);
  json += ",\"fence_distance\":" + String(signedFenceDistance, 1);
  json += ",\"fence_status\":\"" + fenceStatus + "\"";
  json += ",\"gps_valid\":" + String(gpsValid ? "true" : "false");
  json += "}";
  sendLine(json);

  if (temperatureValid && temperature >= 40.0f && millis() - lastTemperatureAlertMs >= 30000) {
    lastTemperatureAlertMs = millis();
    sendLine("ALERT:High cattle temperature: " + String(temperature, 1) + " C");
  }
}

void setup() {
  Serial.begin(115200);
  pinMode(BUZZER_PIN, OUTPUT);
  digitalWrite(BUZZER_PIN, LOW);
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

  Serial.println("NeuroGoru combined backend ready");
  Serial.println("Wi-Fi: " + String(AP_NAME));
  Serial.println("Password: " + String(AP_PASSWORD));
  Serial.println("IP: " + WiFi.softAPIP().toString());
  Serial.println("TCP port: " + String(TCP_PORT));
  Serial.println("DS18B20: " + String(ds18b20Online ? "DETECTED" : "NOT DETECTED"));
  Serial.println("MPU6050: " + String(mpu6050Online ? "DETECTED" : "NOT DETECTED"));
  Serial.println("GPS: WAITING FOR SERIAL DATA");
}

void loop() {
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
  if (millis() - lastTelemetryMs >= 2000) {
    lastTelemetryMs = millis();
    sendTelemetry();
  }
  delay(2);
}
