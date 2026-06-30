#include "esp_camera.h"
#include <WiFi.h>
#include <HTTPClient.h>

const char* ssid = "techcamp.academy";
const char* password = "123456789";
const char* serverUrl = "http://172.20.10.4:5000/predict";

void setup() {
  Serial.begin(115200);

  WiFi.begin(ssid, password);
  Serial.println("Connecting Wifi...");

  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }

  Serial.println("\nWLAN verbunden: " + WiFi.localIP().toString());

  camera_config_t config;
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer = LEDC_TIMER_0;
  config.pin_d0 = 5;
  config.pin_d1 = 18;
  config.pin_d2 = 19;
  config.pin_d3 = 21;
  config.pin_d4 = 36;
  config.pin_d5 = 39;
  config.pin_d6 = 34;
  config.pin_d7 = 35;
  config.pin_xclk = 0;
  config.pin_pclk = 22;
  config.pin_vsync = 25;
  config.pin_href = 23;
  config.pin_sscb_sda = 26;
  config.pin_sscb_scl = 27;
  config.pin_pwdn = 32;
  config.pin_reset = -1;
  config.xclk_freq_hz = 20000000;
  config.pixel_format = PIXFORMAT_JPEG;
  config.frame_size = FRAMESIZE_CIF;
  config.jpeg_quality = 12;
  config.fb_count = 1;

  if (esp_camera_init(&config) != ESP_OK) {
    Serial.println("Kamera konnte nicht gestartet werden!");
    while (true);
  }

  sensor_t* s = esp_camera_sensor_get();
  s->set_brightness(s, 0);
  s->set_contrast(s, 1);
  s->set_saturation(s, 1);
  s->set_whitebal(s, 1);
  s->set_awb_gain(s, 1);
  s->set_wb_mode(s, 0);
  s->set_exposure_ctrl(s, 1);
  s->set_aec2(s, 1);
  s->set_ae_level(s, 0);
  s->set_gain_ctrl(s, 1);
  s->set_agc_gain(s, 0);
  s->set_lenc(s, 1);

  for (int i = 0; i < 5; i++) {
    camera_fb_t* fb = esp_camera_fb_get();

    if (fb) {
      esp_camera_fb_return(fb);
    }

    delay(100);
  }

  Serial.println("Kamera bereit.");
}

void loop() {
  camera_fb_t* fb = esp_camera_fb_get();

  if (!fb) {
    Serial.println("Kein Kamerabild empfangen.");
    return;
  }

  HTTPClient http;
  http.begin(serverUrl);
  http.addHeader("Content-Type", "application/octet-stream");

  int httpResponseCode = http.POST(fb->buf, fb->len);

  if (httpResponseCode > 0) {
    String response = http.getString();
    Serial.println("Antwort: " + response);

    if (response.indexOf("gray") != -1) {
      Serial.println(">>> Farbe erkannt: GRAY");
    } else if (response.indexOf("orange") != -1) {
      Serial.println(">>> Farbe erkannt: ORANGE");
    } else if (response.indexOf("black") != -1) {
      Serial.println(">>> Farbe erkannt: BLACK");
    } else {
      Serial.println(">>> Kein stabiles Ergebnis");
    }
  } else {
    Serial.println("HTTP-Fehler: " + String(httpResponseCode));
  }

  http.end();
  esp_camera_fb_return(fb);

  delay(300);
}