import os
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import cv2
import requests
from dotenv import load_dotenv
from ultralytics import YOLO

load_dotenv()

CAMERA_NAME = os.getenv("CAMERA_NAME", "Imou-Cam")
RTSP_URL = os.getenv("RTSP_URL", "").strip()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

PERSON_MODEL_PATH = os.getenv("PERSON_MODEL", "yolov8n.pt").strip()
FIRE_SMOKE_MODEL_PATH = os.getenv("FIRE_SMOKE_MODEL", "").strip()
FIRE_LABELS = {x.strip().lower() for x in os.getenv("FIRE_LABELS", "fire,smoke").split(",") if x.strip()}

PERSON_CONF = float(os.getenv("PERSON_CONF", "0.55"))
FIRE_SMOKE_CONF = float(os.getenv("FIRE_SMOKE_CONF", "0.45"))
CONSECUTIVE_FRAMES = max(1, int(os.getenv("CONSECUTIVE_FRAMES", "3")))
ALERT_COOLDOWN_SECONDS = max(5, int(os.getenv("ALERT_COOLDOWN_SECONDS", "60")))
FRAME_SKIP = max(1, int(os.getenv("FRAME_SKIP", "2")))

SNAPSHOT_DIR = Path(os.getenv("SNAPSHOT_DIR", "./snapshots"))
SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)

OFFICE_HOUR_START = int(os.getenv("OFFICE_HOUR_START", "8"))
OFFICE_HOUR_END = int(os.getenv("OFFICE_HOUR_END", "18"))
ALERT_PERSON_OUTSIDE_OFFICE_HOURS = os.getenv("ALERT_PERSON_OUTSIDE_OFFICE_HOURS", "false").lower() in {"1", "true", "yes", "on"}


def _check_required_env():
    missing = []
    if not RTSP_URL:
        missing.append("RTSP_URL")
    if not TELEGRAM_BOT_TOKEN:
        missing.append("TELEGRAM_BOT_TOKEN")
    if not TELEGRAM_CHAT_ID:
        missing.append("TELEGRAM_CHAT_ID")
    if missing:
        raise RuntimeError(f"Missing required env: {', '.join(missing)}")


def _is_outside_office_hours() -> bool:
    now_h = datetime.now().hour
    return not (OFFICE_HOUR_START <= now_h < OFFICE_HOUR_END)


def _send_telegram_photo(caption: str, image_path: Path):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    with image_path.open("rb") as f:
        files = {"photo": f}
        data = {"chat_id": TELEGRAM_CHAT_ID, "caption": caption}
        r = requests.post(url, data=data, files=files, timeout=20)
        r.raise_for_status()


def _save_snapshot(frame, prefix: str) -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = SNAPSHOT_DIR / f"{prefix}_{ts}.jpg"
    cv2.imwrite(str(out), frame)
    return out


def _extract_labels(result, conf_threshold: float) -> list[str]:
    labels = []
    names = result.names
    for b in result.boxes:
        conf = float(b.conf[0])
        if conf < conf_threshold:
            continue
        cls_id = int(b.cls[0])
        labels.append(str(names.get(cls_id, cls_id)).lower())
    return labels


def main():
    _check_required_env()

    print(f"Loading person model: {PERSON_MODEL_PATH}")
    person_model = YOLO(PERSON_MODEL_PATH)

    fire_model = None
    if FIRE_SMOKE_MODEL_PATH:
        print(f"Loading fire/smoke model: {FIRE_SMOKE_MODEL_PATH}")
        fire_model = YOLO(FIRE_SMOKE_MODEL_PATH)
    else:
        print("FIRE_SMOKE_MODEL empty -> fire/smoke detection disabled (person only)")

    cap = cv2.VideoCapture(RTSP_URL)
    if not cap.isOpened():
        raise RuntimeError("Cannot open RTSP stream")

    hit_count = defaultdict(int)
    last_alert = defaultdict(lambda: 0.0)

    frame_i = 0
    print("Monitoring started...")

    while True:
        ok, frame = cap.read()
        if not ok:
            print("Frame read failed, retrying in 1s...")
            time.sleep(1)
            continue

        frame_i += 1
        if frame_i % FRAME_SKIP != 0:
            continue

        events = []

        person_res = person_model.predict(frame, verbose=False)
        person_labels = _extract_labels(person_res[0], PERSON_CONF)
        if "person" in person_labels:
            if (not ALERT_PERSON_OUTSIDE_OFFICE_HOURS) or _is_outside_office_hours():
                events.append("person")

        if fire_model is not None:
            fire_res = fire_model.predict(frame, verbose=False)
            fs_labels = _extract_labels(fire_res[0], FIRE_SMOKE_CONF)
            for lbl in fs_labels:
                if lbl in FIRE_LABELS:
                    events.append(lbl)

        # update counters
        current_set = set(events)
        for key in ["person", "fire", "smoke"]:
            if key in current_set:
                hit_count[key] += 1
            else:
                hit_count[key] = 0

        for ev in list(current_set):
            if hit_count[ev] < CONSECUTIVE_FRAMES:
                continue

            now = time.time()
            if now - last_alert[ev] < ALERT_COOLDOWN_SECONDS:
                continue

            snapshot = _save_snapshot(frame, ev)
            caption = (
                f"🚨 {ev.upper()} ALERT\n"
                f"Camera: {CAMERA_NAME}\n"
                f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
            try:
                _send_telegram_photo(caption, snapshot)
                print(f"Alert sent: {ev} -> {snapshot.name}")
                last_alert[ev] = now
            except Exception as e:
                print(f"Failed to send Telegram alert ({ev}): {e}")


if __name__ == "__main__":
    main()
