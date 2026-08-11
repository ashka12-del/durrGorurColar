HardwareSerial gpsSerial(2);

#define GPS_RX 16  // GPS TX → ESP32 GPIO16
#define GPS_TX 17  // GPS RX → ESP32 GPIO17

void setup() {
  Serial.begin(115200);
  gpsSerial.begin(9600, SERIAL_8N1, GPS_RX, GPS_TX);

  delay(1000);
  Serial.println("NEO-6M connection test started...");
  Serial.println("Waiting for raw GPS data...");
}

void loop() {
  while (gpsSerial.available()) {
    Serial.write(gpsSerial.read());
  }
}