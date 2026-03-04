import argparse
import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import pandas as pd
from dotenv import load_dotenv
from insightface.app import FaceAnalysis
from sklearn.cluster import DBSCAN

load_dotenv()

INPUT_DIR = Path(os.getenv("INPUT_DIR", "./input"))
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", "./output"))
REVIEW_DIR = Path(os.getenv("REVIEW_DIR", "./review"))
DATA_DIR = Path(os.getenv("DATA_DIR", "./data"))

ASSIGN_THRESHOLD = float(os.getenv("ASSIGN_THRESHOLD", "0.45"))
MIN_FACE_SIZE = int(os.getenv("MIN_FACE_SIZE", "60"))
DBSCAN_EPS = float(os.getenv("DBSCAN_EPS", "0.65"))
DBSCAN_MIN_SAMPLES = int(os.getenv("DBSCAN_MIN_SAMPLES", "4"))
ORT_PROVIDERS = [x.strip() for x in os.getenv("ORT_PROVIDERS", "CPUExecutionProvider").split(",") if x.strip()]

EMB_FILE = DATA_DIR / "student_embeddings.json"
CLUSTER_MAP_FILE = DATA_DIR / "cluster_name_map.json"
REPORT_FILE = DATA_DIR / "last_run_report.csv"

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}


@dataclass
class FaceRecord:
    image_path: Path
    bbox: tuple[int, int, int, int]
    embedding: np.ndarray


def ensure_dirs():
    for p in [INPUT_DIR, OUTPUT_DIR, REVIEW_DIR, DATA_DIR]:
        p.mkdir(parents=True, exist_ok=True)


def list_images(folder: Path) -> list[Path]:
    out = []
    for p in folder.rglob("*"):
        if p.is_file() and p.suffix.lower() in IMAGE_EXTS:
            out.append(p)
    return sorted(out)


def l2_normalize(v: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(v)
    if n == 0:
        return v
    return v / n


def get_face_app() -> FaceAnalysis:
    app = FaceAnalysis(name="buffalo_l", providers=ORT_PROVIDERS)
    app.prepare(ctx_id=0, det_size=(640, 640))
    return app


def extract_faces(images: list[Path], app: FaceAnalysis) -> list[FaceRecord]:
    records: list[FaceRecord] = []
    for img_path in images:
        img = cv2.imread(str(img_path))
        if img is None:
            continue
        faces = app.get(img)
        if not faces:
            continue

        # choose biggest face per image for MVP
        faces_sorted = sorted(faces, key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]), reverse=True)
        f = faces_sorted[0]
        x1, y1, x2, y2 = [int(v) for v in f.bbox]
        if min(x2 - x1, y2 - y1) < MIN_FACE_SIZE:
            continue

        emb = l2_normalize(np.array(f.embedding, dtype=np.float32))
        records.append(FaceRecord(image_path=img_path, bbox=(x1, y1, x2, y2), embedding=emb))
    return records


def run_bootstrap_unlabeled():
    ensure_dirs()
    app = get_face_app()
    images = list_images(INPUT_DIR)
    if not images:
        print("No images in input folder.")
        return

    recs = extract_faces(images, app)
    if not recs:
        print("No usable faces detected.")
        return

    X = np.stack([r.embedding for r in recs])
    clusterer = DBSCAN(eps=DBSCAN_EPS, min_samples=DBSCAN_MIN_SAMPLES, metric="cosine")
    labels = clusterer.fit_predict(X)

    rows = []
    cluster_map = {}
    for i, (rec, label) in enumerate(zip(recs, labels)):
        label_name = f"cluster_{label}" if label >= 0 else "cluster_noise"
        cluster_dir = OUTPUT_DIR / "bootstrap_clusters" / label_name
        cluster_dir.mkdir(parents=True, exist_ok=True)
        target = cluster_dir / f"{i:05d}_{rec.image_path.name}"
        shutil.copy2(rec.image_path, target)

        rows.append({
            "image": str(rec.image_path),
            "cluster": label_name,
            "copied_to": str(target),
        })

        if label >= 0:
            cluster_map.setdefault(label_name, []).append(rec.embedding)

    # save average embedding per cluster
    cluster_avg = {}
    for k, emb_list in cluster_map.items():
        avg = l2_normalize(np.mean(np.stack(emb_list), axis=0)).tolist()
        cluster_avg[k] = avg

    (DATA_DIR / "bootstrap_cluster_embeddings.json").write_text(
        json.dumps(cluster_avg, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    pd.DataFrame(rows).to_csv(DATA_DIR / "bootstrap_index.csv", index=False)

    if not CLUSTER_MAP_FILE.exists():
        CLUSTER_MAP_FILE.write_text("{}", encoding="utf-8")

    print("Bootstrap complete.")
    print("1) Open output/bootstrap_clusters and rename/decide cluster -> student name")
    print(f"2) Write mapping to {CLUSTER_MAP_FILE} (example: {{\"cluster_0\": \"Nguyen Van A\"}})")
    print("3) Run: python main.py build-profiles")


def run_build_profiles_from_mapping():
    ensure_dirs()
    emb_path = DATA_DIR / "bootstrap_cluster_embeddings.json"
    if not emb_path.exists() or not CLUSTER_MAP_FILE.exists():
        raise RuntimeError("Missing bootstrap embeddings or cluster map file.")

    cluster_emb = json.loads(emb_path.read_text(encoding="utf-8"))
    name_map = json.loads(CLUSTER_MAP_FILE.read_text(encoding="utf-8"))

    profiles: dict[str, list[float]] = {}
    for cluster_name, student_name in name_map.items():
        if cluster_name not in cluster_emb:
            continue
        profiles[student_name] = cluster_emb[cluster_name]

    EMB_FILE.write_text(json.dumps(profiles, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved {len(profiles)} student profiles -> {EMB_FILE}")


def cosine_distance(a: np.ndarray, b: np.ndarray) -> float:
    return float(1.0 - np.dot(a, b))


def run_weekly_assign():
    ensure_dirs()
    if not EMB_FILE.exists():
        raise RuntimeError("No student embeddings yet. Run bootstrap + build-profiles first.")

    profiles_raw: dict[str, Any] = json.loads(EMB_FILE.read_text(encoding="utf-8"))
    profiles = {k: l2_normalize(np.array(v, dtype=np.float32)) for k, v in profiles_raw.items()}

    app = get_face_app()
    images = list_images(INPUT_DIR)
    if not images:
        print("No images in input folder.")
        return

    recs = extract_faces(images, app)
    rows = []

    for rec in recs:
        best_name = None
        best_dist = 999.0
        for name, emb in profiles.items():
            d = cosine_distance(rec.embedding, emb)
            if d < best_dist:
                best_dist = d
                best_name = name

        if best_name is not None and best_dist <= ASSIGN_THRESHOLD:
            out_dir = OUTPUT_DIR / best_name
            out_dir.mkdir(parents=True, exist_ok=True)
            target = out_dir / rec.image_path.name
            shutil.copy2(rec.image_path, target)
            status = "assigned"
            out_path = target
        else:
            REVIEW_DIR.mkdir(parents=True, exist_ok=True)
            target = REVIEW_DIR / rec.image_path.name
            shutil.copy2(rec.image_path, target)
            status = "review"
            out_path = target

        rows.append(
            {
                "image": str(rec.image_path),
                "predicted_student": best_name,
                "distance": round(best_dist, 4),
                "status": status,
                "output": str(out_path),
            }
        )

    pd.DataFrame(rows).to_csv(REPORT_FILE, index=False)
    assigned = sum(1 for r in rows if r["status"] == "assigned")
    print(f"Weekly assign done. assigned={assigned}, review={len(rows)-assigned}")
    print(f"Report: {REPORT_FILE}")


def main():
    parser = argparse.ArgumentParser(description="Student face sorter MVP")
    parser.add_argument("mode", choices=["bootstrap", "build-profiles", "weekly"])
    args = parser.parse_args()

    if args.mode == "bootstrap":
        run_bootstrap_unlabeled()
    elif args.mode == "build-profiles":
        run_build_profiles_from_mapping()
    elif args.mode == "weekly":
        run_weekly_assign()


if __name__ == "__main__":
    main()
