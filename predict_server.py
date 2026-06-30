from flask import Flask, request, jsonify
import numpy as np
import cv2
import tensorflow as tf
from threading import Thread
from collections import deque
import os
import json
import serial
import time

app = Flask(__name__)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(SCRIPT_DIR, "detection_model.h5")
COCO_JSON_PATH = os.path.join(SCRIPT_DIR, "annotations.json")

if not os.path.exists(MODEL_PATH):
    raise FileNotFoundError(
        f"detection_model.h5 nicht gefunden unter:\n{MODEL_PATH}\n"
        f"Bitte die trainierte Datei in denselben Ordner wie dieses Skript legen."
    )

model = tf.keras.models.load_model(MODEL_PATH, compile=False)
print(f"Modell geladen : {MODEL_PATH}")
print(f"Input shape    : {model.input_shape}")

if os.path.exists(COCO_JSON_PATH):
    with open(COCO_JSON_PATH) as f:
        coco = json.load(f)

    categories = sorted(coco["categories"], key=lambda c: c["id"])
    short_to_full = {"g": "gray", "o": "orange", "b": "black"}

    label_map = {
        cat["id"]: short_to_full.get(cat["name"].lower(), cat["name"])
        for cat in categories
    }

    print("Label-Mapping aus annotations.json:")
else:
    label_map = {0: "gray", 1: "orange", 2: "black"}
    print("annotations.json nicht gefunden – Standard Label-Mapping:")

for idx, name in label_map.items():
    print(f"  id {idx} → {name}")

COLOR_MAP = {
    "gray": (180, 180, 180),
    "orange": (0, 140, 255),
    "black": (60, 60, 60),
    "uncertain": (0, 215, 255),
    "checking": (0, 215, 255),
    "no_object": (0, 255, 255),
}

IMG_SIZE = 96
CONFIDENCE_THRESHOLD = 0.65
BLACK_CONFIDENCE_THRESHOLD = 0.55
CROP_MARGIN = 0.20
STABLE_FRAMES = 3


# Robot serial settings
SERIAL_PORT = "COM4"
BAUD_RATE = 115200

# Prevent sending many commands while the same cube is still visible.
ROBOT_COMMAND_COOLDOWN_SECONDS = 8.0

robot_serial = None
last_robot_command_time = 0.0

try:
    robot_serial = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
    time.sleep(2)  # ESP32 resets when serial opens
    print(f"Robot ESP32 verbunden auf {SERIAL_PORT}")
except Exception as e:
    print(f"Warnung: Robot ESP32 konnte nicht auf {SERIAL_PORT} verbunden werden.")
    print(f"Fehler: {e}")
    print("Der Server erkennt Farben weiter, sendet aber keine Roboterbefehle.")

latest_display = None

prediction_history = deque(maxlen=STABLE_FRAMES)
stable_label = "no_object"
stable_score = 0.0


def _center_crop_fallback(img_bgr, ratio=0.35):
    h, w = img_bgr.shape[:2]
    new_h = int(h * ratio)
    new_w = int(w * ratio)

    y1 = (h - new_h) // 2
    x1 = (w - new_w) // 2

    return img_bgr[y1:y1 + new_h, x1:x1 + new_w], None


def _crop_from_contours(img_bgr):
    h, w = img_bgr.shape[:2]

    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)

    edges = cv2.Canny(blurred, 25, 90)

    kernel = np.ones((5, 5), np.uint8)
    edges = cv2.dilate(edges, kernel, iterations=2)
    edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel, iterations=2)

    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    min_area = h * w * 0.01
    max_area = h * w * 0.55

    valid = []

    for c in contours:
        area = cv2.contourArea(c)

        if area < min_area or area > max_area:
            continue

        x, y, bw, bh = cv2.boundingRect(c)

        if bw < 25 or bh < 25:
            continue

        ratio = bw / float(bh)

        if 0.45 <= ratio <= 2.2:
            valid.append(c)

    if not valid:
        return None, None

    largest = max(valid, key=cv2.contourArea)
    x, y, bw, bh = cv2.boundingRect(largest)

    mx = int(bw * CROP_MARGIN)
    my = int(bh * CROP_MARGIN)

    x1 = max(0, x - mx)
    y1 = max(0, y - my)
    x2 = min(w, x + bw + mx)
    y2 = min(h, y + bh + my)

    crop = img_bgr[y1:y2, x1:x2]

    if crop.size == 0:
        return None, None

    return crop, (x1, y1, x2, y2)


def _crop_from_hsv(img_bgr):
    h, w = img_bgr.shape[:2]

    hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
    V = hsv[:, :, 2]

    mask_orange = cv2.inRange(
        hsv,
        np.array([5, 60, 60]),
        np.array([25, 255, 255])
    )

    mask_dark = cv2.inRange(V, 0, 145)
    mask = cv2.bitwise_or(mask_orange, mask_dark)

    kernel = np.ones((5, 5), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    min_area = h * w * 0.01
    max_area = h * w * 0.50

    valid = []

    for c in contours:
        area = cv2.contourArea(c)

        if area < min_area or area > max_area:
            continue

        x, y, bw, bh = cv2.boundingRect(c)

        if bw < 25 or bh < 25:
            continue

        ratio = bw / float(bh)

        if 0.45 <= ratio <= 2.2:
            valid.append(c)

    if not valid:
        return None, None

    largest = max(valid, key=cv2.contourArea)
    x, y, bw, bh = cv2.boundingRect(largest)

    mx = int(bw * CROP_MARGIN)
    my = int(bh * CROP_MARGIN)

    x1 = max(0, x - mx)
    y1 = max(0, y - my)
    x2 = min(w, x + bw + mx)
    y2 = min(h, y + bh + my)

    crop = img_bgr[y1:y2, x1:x2]

    if crop.size == 0:
        return None, None

    return crop, (x1, y1, x2, y2)


def find_object_crop(img_bgr):
    crop, bbox = _crop_from_contours(img_bgr)

    if crop is not None:
        return crop, bbox

    crop, bbox = _crop_from_hsv(img_bgr)

    if crop is not None:
        return crop, bbox

    return _center_crop_fallback(img_bgr)


def brightness_stats(img_bgr):
    hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
    V = hsv[:, :, 2]

    mean_v = float(np.mean(V))
    dark_ratio = np.count_nonzero(V < 80) / V.size

    return mean_v, dark_ratio


def gray_index():
    for idx, name in label_map.items():
        if name == "gray":
            return idx

    return None


def predict_color(img_bgr):
    if img_bgr is None or img_bgr.size == 0:
        return None, 0.0, None, None

    crop, bbox = find_object_crop(img_bgr)

    crop_rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
    resized = cv2.resize(crop_rgb, (IMG_SIZE, IMG_SIZE), interpolation=cv2.INTER_AREA)
    inp = np.expand_dims(resized, axis=0).astype(np.float32) / 255.0

    out = model.predict(inp, verbose=0)[0]
    pred_idx = int(np.argmax(out))
    score = float(np.max(out))
    label = label_map.get(pred_idx, "unknown")

    mean_v, dark_ratio = brightness_stats(crop)

    if label == "black":
        if mean_v > 115 and dark_ratio < 0.30:
            idx = gray_index()

            if idx is not None:
                out = out.copy()
                out[idx] = max(out[idx], score)
                label = "gray"
                score = float(out[idx])

        elif score >= BLACK_CONFIDENCE_THRESHOLD:
            return "black", score, out, bbox

    if score < CONFIDENCE_THRESHOLD:
        return "checking", score, out, bbox

    return label, score, out, bbox


def send_to_robot(label):
    global last_robot_command_time

    if robot_serial is None:
        return False

    command_map = {
        "orange": "O",
        "gray": "G",
        "black": "B"
    }

    if label not in command_map:
        return False

    now = time.time()

    if now - last_robot_command_time < ROBOT_COMMAND_COOLDOWN_SECONDS:
        return False

    command = command_map[label]
    robot_serial.write((command + "\n").encode())
    last_robot_command_time = now

    print(f"An Roboter gesendet: {command} fuer {label}")
    return True


def apply_stability_filter(raw_label, raw_score):
    global stable_label, stable_score, prediction_history

    if raw_label in ["gray", "orange", "black"]:
        prediction_history.append(raw_label)

        if len(prediction_history) == STABLE_FRAMES and len(set(prediction_history)) == 1:
            stable_label = raw_label
            stable_score = raw_score
            return stable_label, stable_score, True

        if stable_label != "no_object" and raw_label == stable_label:
            return stable_label, stable_score, True

        return "checking", raw_score, False

    if raw_label == "no_object":
        prediction_history.clear()
        stable_label = "no_object"
        stable_score = 0.0
        return "no_object", 0.0, False

    return "checking", raw_score, False


@app.route("/predict", methods=["POST"])
def predict():
    global latest_display

    img_data = request.data
    img_array = np.frombuffer(img_data, dtype=np.uint8)
    img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)

    if img is None:
        return jsonify({"error": "Bild konnte nicht dekodiert werden"}), 400

    display_img = img.copy()

    raw_label, raw_score, raw, bbox = predict_color(img)
    label, score, is_stable = apply_stability_filter(raw_label, raw_score)

    sent_to_robot = False
    if is_stable and label in ["orange", "gray", "black"]:
        sent_to_robot = send_to_robot(label)

    score_pct = round(score * 100, 1)
    color = COLOR_MAP.get(label, (255, 255, 255))

    h, w = display_img.shape[:2]

    if bbox is not None:
        x1, y1, x2, y2 = bbox

        cv2.rectangle(display_img, (x1, y1), (x2, y2), color, 3)

        cv2.putText(
            display_img,
            "object",
            (x1, max(20, y1 - 8)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            color,
            1,
        )

    else:
        ny = int(h * (1 - 0.35) / 2)
        nx = int(w * (1 - 0.35) / 2)

        cv2.rectangle(display_img, (nx, ny), (w - nx, h - ny), (150, 150, 150), 2)

        cv2.putText(
            display_img,
            "center fallback",
            (nx, max(20, ny - 5)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            (150, 150, 150),
            1,
        )

    if label == "checking":
        title = f"CHECKING ({score_pct}%)"
    elif label == "no_object":
        title = "NO_OBJECT (0%)"
    else:
        title = f"{label.upper()} ({score_pct}%)"

    cv2.putText(
        display_img,
        title,
        (10, 40),
        cv2.FONT_HERSHEY_SIMPLEX,
        1.2,
        color,
        3,
    )

    if raw is not None:
        for i in range(len(raw)):
            lbl = label_map.get(i, str(i))
            val = float(raw[i])
            pct = round(val * 100, 1)
            bar_color = COLOR_MAP.get(lbl, (200, 200, 200))

            cv2.putText(
                display_img,
                f"{lbl}: {pct}%",
                (10, h - 15 - i * 28),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                bar_color,
                2,
            )

    latest_display = display_img

    if raw is not None:
        scores_pct = {
            label_map.get(i, str(i)): f"{round(float(raw[i]) * 100, 1)}%"
            for i in range(len(raw))
        }

        print(
            f"Raw: {str(raw_label).upper():10s} ({round(raw_score * 100, 1)}%)  "
            f"Shown: {str(label).upper():10s} ({score_pct}%)  "
            f"Stable={is_stable}  bbox={bbox}  |  {scores_pct}"
        )

    return jsonify({
        "result": label,
        "score": f"{score_pct}%",
        "stable": is_stable,
        "sent_to_robot": sent_to_robot
    })


def show_loop():
    global latest_display

    while True:
        if latest_display is not None:
            cv2.imshow("Wuerfel Farberkennung - Live", latest_display)

        if cv2.waitKey(1) & 0xFF == 27:
            break

    cv2.destroyAllWindows()


if __name__ == "__main__":
    Thread(target=show_loop, daemon=True).start()

    print("=" * 52)
    print("  Wuerfel Farberkennung - Lokaler Server")
    print(f"  Min. Confidence : {int(CONFIDENCE_THRESHOLD * 100)}%")
    print(f"  Black Confidence: {int(BLACK_CONFIDENCE_THRESHOLD * 100)}%")
    print(f"  Stable Frames   : {STABLE_FRAMES}")
    print("  Klassen         : gray | orange | black")
    print("  Server          : http://0.0.0.0:5000/predict")
    print("  ESC im Fenster  -> Server beenden")
    print("=" * 52)

    app.run(host="0.0.0.0", port=5000, threaded=True)