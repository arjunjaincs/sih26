"""
PRAMAAN v1 — Training & Data Integrity Corpus Generator.

Generates a small, deterministic, realistic CV dataset corpus for validating
the actual DI-01 through DI-05 detectors across 9 distinct integrity scenarios:

  1. 01_clean_baseline           -- Genuinely clean baseline dataset
  2. 02_exact_duplicate          -- Byte-identical clones (DI-01 exact)
  3. 03_near_duplicate           -- Perceptually similar images (DI-01 near)
  4. 04_label_flip               -- Contradictory labels on near-duplicates (DI-02 conflict)
  5. 05_systematic_mislabelling   -- Repeated label inconsistencies across multiple samples (DI-02)
  6. 06_recurring_pattern        -- Localized recurring corner patch (DI-03)
  7. 07_ood_distribution         -- Multivariate feature & photometric outliers (DI-04)
  8. 08_contributor_concentration -- Disproportionate defect concentration (DI-05)
  9. 09_mixed_scenario           -- Multi-anomaly unified assessment (DI-01..DI-05)

Design Principles:
  - Deterministic: master seed + scenario seeds produce reproducible datasets.
  - Strict Isolation: ground_truth.json is NEVER stored in input/ or archives.
  - Zero Leakage: production metadata contains only legitimate operational fields.
  - Offline: zero network or external dataset dependencies.
  - Claim Discipline: ground truth records injected modifications; does not claim malice.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import random
import shutil
import sqlite3
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import imagehash
import numpy as np
from PIL import Image, ImageDraw

from backend.detectors.base import DetectorContext
from backend.detectors.data.di01_duplicates import DI01DuplicateDetector
from backend.detectors.data.di02_label_integrity import DI02LabelIntegrityDetector
from backend.detectors.data.di03_trigger_anomaly import DI03TriggerAnomalyDetector
from backend.detectors.data.di04_ood_distribution import DI04DistributionOODDetector
from backend.detectors.data.di05_contributor_risk import DI05ContributorRiskDetector
from backend.detectors.runner import run_detector
from backend.domain.entities import Assessment
from backend.domain.enums import DatasetFormat
from backend.infra.crypto import hash_file
from backend.infra.db import AssessmentRepository, open_db
from backend.infra.ingestion import ingest_image_directory, register_dataset

log = logging.getLogger("corpus_generator")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

DEFAULT_CORPUS_ROOT = Path("data/corpus")
_FIXED_ZIP_DATE = (2026, 1, 1, 0, 0, 0)
_IMAGE_SIZE = (128, 128)

# Standard contributors
CONTRIBUTORS = ("sensor_alpha", "sensor_beta", "pipeline_gamma")
EXTENDED_CONTRIBUTORS = ("sensor_alpha", "sensor_beta", "sensor_gamma", "sensor_delta")


# ---------------------------------------------------------------------------
# Procedural Image Synthesis
# ---------------------------------------------------------------------------

def _draw_canvas(
    seed: int,
    idx: int,
    label: str,
    width: int = 128,
    height: int = 128,
    margin: int = 16,
    pattern_mode: str = "normal",
) -> Image.Image:
    """
    Generate a procedural image with guaranteed clean margins (variance 0.0 in corners),
    distinct composition to avoid unintended pHash collisions, and harmonized photometric
    statistics to keep statistical distribution detector (DI-04) quiet on clean images.
    """
    rng = random.Random(seed)
    lum = 90 + (idx * 23 + rng.randint(0, 15)) % 75
    bg_color = (lum, (lum + 25 * (idx % 3)) % 256, (lum + 50 * ((idx + 1) % 3)) % 256)
    img = Image.new("RGB", (width, height), color=bg_color)
    draw = ImageDraw.Draw(img)

    # Safe drawing boundary: stays strictly inside margins so 16x16 corners have 0.0 variance
    min_x, max_x = margin + 2, width - margin - 2
    min_y, max_y = margin + 2, height - margin - 2

    if pattern_mode == "horizontal_centroid":
        for y in range(min_y + 8, max_y - 8, 14):
            draw.line([(min_x + 4, y), (max_x - 4, y)], fill=(rng.randint(150, 210), rng.randint(150, 210), rng.randint(150, 210)), width=3)
        draw.rectangle([min_x + 10, height // 2 - 10, max_x - 10, height // 2 + 10], fill=(190, 60, 60))
        draw.ellipse([min_x + 15, height // 2 + 8, min_x + 35, height // 2 + 28], fill=(35, 35, 35))
        draw.ellipse([max_x - 35, height // 2 + 8, max_x - 15, height // 2 + 28], fill=(35, 35, 35))
    elif pattern_mode == "vertical_centroid":
        for x in range(min_x + 8, max_x - 8, 14):
            draw.line([(x, min_y + 4), (x, max_y - 4)], fill=(rng.randint(150, 210), rng.randint(150, 210), rng.randint(150, 210)), width=3)
        cx = width // 2
        draw.ellipse([cx - 8, min_y + 10, cx + 8, min_y + 26], fill=(220, 180, 140))
        draw.line([(cx, min_y + 26), (cx, min_y + 68)], fill=(55, 95, 190), width=6)
        draw.line([(cx, min_y + 68), (cx - 10, max_y - 6)], fill=(35, 35, 35), width=4)
        draw.line([(cx, min_y + 68), (cx + 10, max_y - 6)], fill=(35, 35, 35), width=4)
    elif label == "vehicle":
        mode = idx % 5
        bx = min_x + rng.randint(2, 18)
        by = min_y + rng.randint(20, 40)
        bw = min(rng.randint(45, 60), max_x - bx - 2)
        bh = min(rng.randint(20, 26), max_y - by - 2)
        color = (rng.randint(60, 190), rng.randint(60, 190), rng.randint(60, 190))
        win_color = (160, 180, 200)
        wheel_color = (35, 35, 35)

        if mode == 0:  # Sedan
            draw.rectangle([bx, by, bx + bw, by + bh], fill=color)
            draw.rectangle([bx + 10, by - 10, bx + bw - 10, by], fill=win_color)
            draw.ellipse([bx + 8, by + bh - 4, bx + 20, by + bh + 8], fill=wheel_color)
            draw.ellipse([bx + bw - 20, by + bh - 4, bx + bw - 8, by + bh + 8], fill=wheel_color)
        elif mode == 1:  # Truck / van
            draw.rectangle([bx, by - 8, bx + bw, by + bh], fill=color)
            draw.rectangle([bx + bw - 14, by - 6, bx + bw - 2, by + 4], fill=win_color)
            draw.ellipse([bx + 10, by + bh - 4, bx + 22, by + bh + 8], fill=wheel_color)
            draw.ellipse([bx + bw - 22, by + bh - 4, bx + bw - 10, by + bh + 8], fill=wheel_color)
        elif mode == 2:  # Coupe / wedge
            draw.polygon([(bx, by + bh), (bx + 12, by - 6), (bx + bw - 10, by), (bx + bw, by + bh)], fill=color)
            draw.ellipse([bx + 10, by + bh - 4, bx + 22, by + bh + 8], fill=wheel_color)
            draw.ellipse([bx + bw - 22, by + bh - 4, bx + bw - 10, by + bh + 8], fill=wheel_color)
        elif mode == 3:  # Bus with window row
            draw.rectangle([bx, by - 10, bx + bw, by + bh], fill=color)
            for wx in range(bx + 4, bx + bw - 8, 12):
                draw.rectangle([wx, by - 8, wx + 7, by - 2], fill=win_color)
            draw.ellipse([bx + 10, by + bh - 4, bx + 22, by + bh + 8], fill=wheel_color)
            draw.ellipse([bx + bw - 22, by + bh - 4, bx + bw - 10, by + bh + 8], fill=wheel_color)
        else:  # Pickup
            draw.rectangle([bx, by + 4, bx + bw, by + bh], fill=color)
            draw.rectangle([bx + 6, by - 6, bx + bw // 2, by + 4], fill=color)
            draw.ellipse([bx + 10, by + bh - 4, bx + 22, by + bh + 8], fill=wheel_color)
            draw.ellipse([bx + bw - 22, by + bh - 4, bx + bw - 10, by + bh + 8], fill=wheel_color)
    else:  # pedestrian
        cx = min_x + 15 + (idx * 19 + rng.randint(0, 10)) % (max_x - min_x - 30)
        head_y = min_y + 10 + rng.randint(0, 15)
        head_rad = rng.randint(7, 9)
        skin = (220 + rng.randint(-10, 10), 180 + rng.randint(-10, 10), 140 + rng.randint(-10, 10))
        draw.ellipse([cx - head_rad, head_y, cx + head_rad, head_y + 2 * head_rad], fill=skin)
        torso_color = (rng.randint(60, 190), rng.randint(60, 190), rng.randint(60, 190))
        torso_len = rng.randint(30, 38)
        torso_y = head_y + 2 * head_rad
        draw.rectangle([cx - 12, torso_y, cx + 12, torso_y + torso_len], fill=torso_color)
        draw.rectangle([cx - 14, torso_y + torso_len // 2, cx + 14, torso_y + torso_len // 2 + 5], fill=(40, 40, 40))
        leg_bottom = min(torso_y + torso_len + 28, max_y - 2)
        draw.line([(cx - 5, torso_y + torso_len), (cx - 8, leg_bottom)], fill=(35, 35, 40), width=4)
        draw.line([(cx + 5, torso_y + torso_len), (cx + 8, leg_bottom)], fill=(35, 35, 40), width=4)

    return img


def _generate_distinct_clean_image(
    start_seed: int,
    idx: int,
    label: str,
    existing_hashes: list[imagehash.ImageHash],
    min_hamming_dist: int = 12,
    pattern_mode: str = "normal",
) -> tuple[Image.Image, imagehash.ImageHash]:
    """
    Generate an image guaranteed to have pHash distance > min_hamming_dist from all existing hashes.
    Uses deterministic rejection sampling starting from start_seed.
    """
    seed_offset = 0
    while True:
        candidate_seed = start_seed + seed_offset * 101
        img = _draw_canvas(candidate_seed, idx, label, pattern_mode=pattern_mode)
        h = imagehash.phash(img)
        if all((h - eh) >= min_hamming_dist for eh in existing_hashes):
            return img, h
        seed_offset += 1


def _create_near_duplicate_shift(img: Image.Image, px_shift: int = 1) -> Image.Image:
    """Create near-duplicate with ~6 bits Hamming distance (triggers DI-01, quiet on DI-02)."""
    res = Image.new("RGB", img.size, (80, 80, 80))
    res.paste(img, (px_shift, 0))
    return res


def _create_near_duplicate_subtle(img: Image.Image, seed: int = 1) -> Image.Image:
    """
    Create near-duplicate with 1 <= Hamming distance <= 4 bits without inflating file size.
    Triggers DI-02 when paired with conflicting label, keeps DI-04 quiet.
    """
    h0 = imagehash.phash(img)
    w, h = img.size
    cx, cy = w // 2, h // 2
    for offset in [0, -10, 10, -15, 15]:
        for rad in [6, 8, 10, 12, 14]:
            for fill in [(160, 100, 100), (90, 160, 110), (150, 150, 80), (80, 80, 160)]:
                res = img.copy()
                draw = ImageDraw.Draw(res)
                draw.ellipse([cx + offset - rad, cy + offset - rad, cx + offset + rad, cy + offset + rad], fill=fill)
                h1 = imagehash.phash(res)
                dist = h0 - h1
                if 1 <= dist <= 4:
                    return res
    return _create_near_duplicate_shift(img, px_shift=1)


def _inject_corner_checkerboard(img: Image.Image, pw: int = 16) -> Image.Image:
    """Inject high-contrast 16x16 checkerboard pattern in bottom-right corner for DI-03."""
    res = img.copy()
    draw = ImageDraw.Draw(res)
    w, h = res.size
    x0, y0 = w - pw, h - pw
    cell = 4
    for bx in range(x0, w, cell):
        for by in range(y0, h, cell):
            fill = (255, 255, 0) if ((bx - x0) // cell + (by - y0) // cell) % 2 == 0 else (0, 0, 0)
            draw.rectangle([bx, by, min(bx + cell - 1, w - 1), min(by + cell - 1, h - 1)], fill=fill)
    return res


# ---------------------------------------------------------------------------
# Manifest & Archive Helpers
# ---------------------------------------------------------------------------

def _write_deterministic_zip(source_dir: Path, zip_dest: Path) -> None:
    """Create a deterministic ZIP archive from files inside source_dir."""
    zip_dest.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_dest, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(source_dir):
            dirs.sort()
            for f in sorted(files):
                full_path = Path(root) / f
                rel_path = full_path.relative_to(source_dir)
                zi = zipfile.ZipInfo(filename=str(rel_path).replace("\\", "/"), date_time=_FIXED_ZIP_DATE)
                zi.compress_type = zipfile.ZIP_DEFLATED
                with open(full_path, "rb") as src:
                    zf.writestr(zi, src.read())


def _build_manifests(
    scenario_id: str,
    samples_info: list[dict[str, Any]],
    output_input_dir: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build production dataset_manifest.json and dual-compatible metadata.json."""
    categories = [{"id": 1, "name": "vehicle"}, {"id": 2, "name": "pedestrian"}]
    cat_to_id = {c["name"]: c["id"] for c in categories}

    coco_images = []
    coco_annotations = []
    contributors_map = {}
    labels_map = {}

    for idx, s in enumerate(samples_info, start=1):
        fn = s["file_name"]
        lbl = s["label"]
        contrib = s["contributor"]

        contributors_map[fn] = contrib
        labels_map[fn] = [lbl]

        coco_images.append({
            "id": idx,
            "file_name": fn,
            "width": s["width"],
            "height": s["height"],
            "contributor": contrib,
        })
        if lbl in cat_to_id:
            coco_annotations.append({
                "id": idx,
                "image_id": idx,
                "category_id": cat_to_id[lbl],
            })

    manifest = {
        "manifest_version": "1.0.0",
        "dataset_name": f"scenario_{scenario_id}",
        "dataset_format": "image_dir",
        "total_samples": len(samples_info),
        "created_at": "2026-09-12T00:00:00Z",
        "samples": [
            {
                "sample_id": s["sample_id"],
                "file_name": s["file_name"],
                "relative_path": f"images/{s['file_name']}",
                "label": s["label"],
                "contributor": s["contributor"],
                "width": s["width"],
                "height": s["height"],
                "sha256": s["sha256"],
            }
            for s in samples_info
        ],
        "info": {
            "description": f"PRAMAAN scenario {scenario_id} manifest",
            "version": "1.0.0",
        },
        "images": coco_images,
        "annotations": coco_annotations,
        "categories": categories,
    }

    metadata = {
        "info": {
            "description": f"PRAMAAN scenario {scenario_id} metadata",
            "version": "1.0.0",
            "contributor": "PRAMAAN Corpus Generator",
        },
        "contributors": contributors_map,
        "labels": labels_map,
        "categories": categories,
        "images": coco_images,
        "annotations": coco_annotations,
    }

    (output_input_dir / "dataset_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (output_input_dir / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    return manifest, metadata


# ---------------------------------------------------------------------------
# Scenario Generators
# ---------------------------------------------------------------------------

def generate_scenario_01_clean(dest_dir: Path, seed: int = 42001) -> dict[str, Any]:
    """SCEN-01: Genuinely clean baseline with no anomalies across all detectors."""
    input_dir = dest_dir / "input"
    images_dir = input_dir / "images"
    gt_dir = dest_dir / "ground_truth"
    images_dir.mkdir(parents=True, exist_ok=True)
    gt_dir.mkdir(parents=True, exist_ok=True)

    samples_info = []
    existing_hashes: list[imagehash.ImageHash] = []

    # 5 clean vehicles, 5 clean pedestrians with guaranteed pHash distance > 10
    for i in range(5):
        fn = f"clean_veh_{i:02d}.png"
        img, h = _generate_distinct_clean_image(seed + i * 100, i, "vehicle", existing_hashes, min_hamming_dist=12)
        existing_hashes.append(h)
        p = images_dir / fn
        img.save(p, "PNG")
        samples_info.append({
            "sample_id": f"s01_v{i:02d}", "file_name": fn, "label": "vehicle",
            "contributor": CONTRIBUTORS[i % 3], "width": 128, "height": 128, "sha256": hash_file(p),
        })

    for i in range(5):
        fn = f"clean_ped_{i:02d}.png"
        img, h = _generate_distinct_clean_image(seed + 500 + i * 100, i + 5, "pedestrian", existing_hashes, min_hamming_dist=12)
        existing_hashes.append(h)
        p = images_dir / fn
        img.save(p, "PNG")
        samples_info.append({
            "sample_id": f"s01_p{i:02d}", "file_name": fn, "label": "pedestrian",
            "contributor": CONTRIBUTORS[(i + 1) % 3], "width": 128, "height": 128, "sha256": hash_file(p),
        })

    _build_manifests("01_clean_baseline", samples_info, input_dir)

    ground_truth = {
        "scenario_id": "01_clean_baseline",
        "title": "Clean Baseline",
        "description": "Clean dataset with no intentional duplicates, conflicts, or outliers.",
        "generation_seed": seed,
        "total_samples": len(samples_info),
        "affected_samples": [],
        "anomaly_present": False,
        "expected_detectors": {
            "di01_duplicates": {"expected": False, "expected_risk": "NONE"},
            "di02_label_integrity": {"expected": False, "expected_risk": "NONE"},
            "di03_trigger_anomaly": {"expected": False, "expected_risk": "NONE"},
            "di04_ood_distribution": {"expected": False, "expected_risk": "NONE"},
            "di05_contributor_risk": {"expected": False, "expected_risk": "NONE"},
        },
        "expected_overall_risk": "NONE",
        "known_limitations": ["Heuristic sensitivity bounds false positive margin."],
    }
    (gt_dir / "ground_truth.json").write_text(json.dumps(ground_truth, indent=2), encoding="utf-8")

    zip_path = dest_dir / "scenario_01_clean_baseline.zip"
    _write_deterministic_zip(input_dir, zip_path)
    return ground_truth


def generate_scenario_02_exact_duplicate(dest_dir: Path, seed: int = 42002) -> dict[str, Any]:
    """SCEN-02: Exact byte-identical clones triggering DI-01."""
    input_dir = dest_dir / "input"
    images_dir = input_dir / "images"
    gt_dir = dest_dir / "ground_truth"
    images_dir.mkdir(parents=True, exist_ok=True)
    gt_dir.mkdir(parents=True, exist_ok=True)

    samples_info = []
    existing_hashes: list[imagehash.ImageHash] = []

    # 6 clean controls (3 vehicle, 3 pedestrian)
    for i in range(3):
        fn = f"ctrl_veh_{i:02d}.png"
        img, h = _generate_distinct_clean_image(seed + i * 100, i, "vehicle", existing_hashes, min_hamming_dist=12)
        existing_hashes.append(h)
        p = images_dir / fn
        img.save(p, "PNG")
        samples_info.append({
            "sample_id": f"s02_cv{i:02d}", "file_name": fn, "label": "vehicle",
            "contributor": CONTRIBUTORS[i % 3], "width": 128, "height": 128, "sha256": hash_file(p),
        })

    for i in range(3):
        fn = f"ctrl_ped_{i:02d}.png"
        img, h = _generate_distinct_clean_image(seed + 300 + i * 100, i + 3, "pedestrian", existing_hashes, min_hamming_dist=12)
        existing_hashes.append(h)
        p = images_dir / fn
        img.save(p, "PNG")
        samples_info.append({
            "sample_id": f"s02_cp{i:02d}", "file_name": fn, "label": "pedestrian",
            "contributor": CONTRIBUTORS[(i + 1) % 3], "width": 128, "height": 128, "sha256": hash_file(p),
        })

    # Cluster 1: Exact duplicate vehicle pair
    img_v, h_v_obj = _generate_distinct_clean_image(seed + 700, 6, "vehicle", existing_hashes, min_hamming_dist=12)
    existing_hashes.append(h_v_obj)
    p_v1 = images_dir / "dup_veh_orig.png"
    p_v2 = images_dir / "dup_veh_clone.png"
    img_v.save(p_v1, "PNG")
    shutil.copy2(p_v1, p_v2)
    h_v = hash_file(p_v1)

    samples_info.append({
        "sample_id": "s02_dv1", "file_name": "dup_veh_orig.png", "label": "vehicle",
        "contributor": "sensor_alpha", "width": 128, "height": 128, "sha256": h_v,
    })
    samples_info.append({
        "sample_id": "s02_dv2", "file_name": "dup_veh_clone.png", "label": "vehicle",
        "contributor": "sensor_beta", "width": 128, "height": 128, "sha256": h_v,
    })

    # Cluster 2: Exact duplicate pedestrian pair
    img_p, h_p_obj = _generate_distinct_clean_image(seed + 800, 7, "pedestrian", existing_hashes, min_hamming_dist=12)
    existing_hashes.append(h_p_obj)
    p_p1 = images_dir / "dup_ped_orig.png"
    p_p2 = images_dir / "dup_ped_clone.png"
    img_p.save(p_p1, "PNG")
    shutil.copy2(p_p1, p_p2)
    h_p = hash_file(p_p1)

    samples_info.append({
        "sample_id": "s02_dp1", "file_name": "dup_ped_orig.png", "label": "pedestrian",
        "contributor": "sensor_gamma", "width": 128, "height": 128, "sha256": h_p,
    })
    samples_info.append({
        "sample_id": "s02_dp2", "file_name": "dup_ped_clone.png", "label": "pedestrian",
        "contributor": "sensor_delta", "width": 128, "height": 128, "sha256": h_p,
    })

    _build_manifests("02_exact_duplicate", samples_info, input_dir)

    ground_truth = {
        "scenario_id": "02_exact_duplicate",
        "title": "Exact Duplicate Injection",
        "description": "Two exact duplicate clusters (SHA-256 byte equality).",
        "generation_seed": seed,
        "total_samples": len(samples_info),
        "affected_samples": ["dup_veh_orig.png", "dup_veh_clone.png", "dup_ped_orig.png", "dup_ped_clone.png"],
        "anomaly_present": True,
        "expected_detectors": {
            "di01_duplicates": {"expected": True, "expected_risk": "MEDIUM", "clusters": 2},
            "di02_label_integrity": {"expected": False, "expected_risk": "NONE"},
            "di03_trigger_anomaly": {"expected": False, "expected_risk": "NONE"},
            "di04_ood_distribution": {"expected": False, "expected_risk": "NONE"},
            "di05_contributor_risk": {"expected": False, "expected_risk": "NONE"},
        },
        "expected_overall_risk": "MEDIUM",
        "known_limitations": ["SHA-256 equality proves byte match; does not prove flooding intent."],
    }
    (gt_dir / "ground_truth.json").write_text(json.dumps(ground_truth, indent=2), encoding="utf-8")

    zip_path = dest_dir / "scenario_02_exact_duplicate.zip"
    _write_deterministic_zip(input_dir, zip_path)
    return ground_truth


def generate_scenario_03_near_duplicate(dest_dir: Path, seed: int = 42003) -> dict[str, Any]:
    """SCEN-03: Visually similar near-duplicates (pHash dist ~6 bits, DI-01 near)."""
    input_dir = dest_dir / "input"
    images_dir = input_dir / "images"
    gt_dir = dest_dir / "ground_truth"
    images_dir.mkdir(parents=True, exist_ok=True)
    gt_dir.mkdir(parents=True, exist_ok=True)

    samples_info = []
    existing_hashes: list[imagehash.ImageHash] = []

    # 6 clean controls
    for i in range(3):
        fn = f"ctrl_veh_{i:02d}.png"
        img, h = _generate_distinct_clean_image(seed + i * 100, i, "vehicle", existing_hashes, min_hamming_dist=12)
        existing_hashes.append(h)
        p = images_dir / fn
        img.save(p, "PNG")
        samples_info.append({
            "sample_id": f"s03_cv{i:02d}", "file_name": fn, "label": "vehicle",
            "contributor": CONTRIBUTORS[i % 3], "width": 128, "height": 128, "sha256": hash_file(p),
        })

    for i in range(3):
        fn = f"ctrl_ped_{i:02d}.png"
        img, h = _generate_distinct_clean_image(seed + 300 + i * 100, i + 3, "pedestrian", existing_hashes, min_hamming_dist=12)
        existing_hashes.append(h)
        p = images_dir / fn
        img.save(p, "PNG")
        samples_info.append({
            "sample_id": f"s03_cp{i:02d}", "file_name": fn, "label": "pedestrian",
            "contributor": CONTRIBUTORS[(i + 1) % 3], "width": 128, "height": 128, "sha256": hash_file(p),
        })

    # Cluster 1: Near-duplicate vehicle (1px shift -> pHash dist 6 bits)
    v_orig, h_v_obj = _generate_distinct_clean_image(seed + 700, 6, "vehicle", existing_hashes, min_hamming_dist=12)
    existing_hashes.append(h_v_obj)
    v_near = _create_near_duplicate_shift(v_orig, px_shift=1)
    p_v1 = images_dir / "near_veh_anchor.png"
    p_v2 = images_dir / "near_veh_variant.png"
    v_orig.save(p_v1, "PNG")
    v_near.save(p_v2, "PNG")

    dist_v = int(imagehash.phash(v_orig) - imagehash.phash(v_near))
    samples_info.append({
        "sample_id": "s03_nv1", "file_name": "near_veh_anchor.png", "label": "vehicle",
        "contributor": "sensor_alpha", "width": 128, "height": 128, "sha256": hash_file(p_v1),
    })
    samples_info.append({
        "sample_id": "s03_nv2", "file_name": "near_veh_variant.png", "label": "vehicle",
        "contributor": "sensor_beta", "width": 128, "height": 128, "sha256": hash_file(p_v2),
    })

    # Cluster 2: Near-duplicate pedestrian (1px shift -> pHash dist 6 bits)
    p_orig, h_p_obj = _generate_distinct_clean_image(seed + 800, 7, "pedestrian", existing_hashes, min_hamming_dist=12)
    existing_hashes.append(h_p_obj)
    p_near = _create_near_duplicate_shift(p_orig, px_shift=1)
    p_p1 = images_dir / "near_ped_anchor.png"
    p_p2 = images_dir / "near_ped_variant.png"
    p_orig.save(p_p1, "PNG")
    p_near.save(p_p2, "PNG")

    dist_p = int(imagehash.phash(p_orig) - imagehash.phash(p_near))
    samples_info.append({
        "sample_id": "s03_np1", "file_name": "near_ped_anchor.png", "label": "pedestrian",
        "contributor": "sensor_gamma", "width": 128, "height": 128, "sha256": hash_file(p_p1),
    })
    samples_info.append({
        "sample_id": "s03_np2", "file_name": "near_ped_variant.png", "label": "pedestrian",
        "contributor": "sensor_delta", "width": 128, "height": 128, "sha256": hash_file(p_p2),
    })

    _build_manifests("03_near_duplicate", samples_info, input_dir)

    ground_truth = {
        "scenario_id": "03_near_duplicate",
        "title": "Near-Duplicate Candidate Injection",
        "description": "Two perceptually similar near-duplicate clusters with different SHA-256.",
        "generation_seed": seed,
        "measured_hamming_distances": {"vehicle_cluster": dist_v, "pedestrian_cluster": dist_p},
        "total_samples": len(samples_info),
        "affected_samples": ["near_veh_anchor.png", "near_veh_variant.png", "near_ped_anchor.png", "near_ped_variant.png"],
        "anomaly_present": True,
        "expected_detectors": {
            "di01_duplicates": {"expected": True, "expected_risk": "LOW", "clusters": 2},
            "di02_label_integrity": {"expected": False, "expected_risk": "NONE"},
            "di03_trigger_anomaly": {"expected": False, "expected_risk": "NONE"},
            "di04_ood_distribution": {"expected": False, "expected_risk": "NONE"},
            "di05_contributor_risk": {"expected": False, "expected_risk": "NONE"},
        },
        "expected_overall_risk": "LOW",
        "known_limitations": ["Candidate relationship based on pHash threshold; requires analyst disposition."],
    }
    (gt_dir / "ground_truth.json").write_text(json.dumps(ground_truth, indent=2), encoding="utf-8")

    zip_path = dest_dir / "scenario_03_near_duplicate.zip"
    _write_deterministic_zip(input_dir, zip_path)
    return ground_truth


def generate_scenario_04_label_flip(dest_dir: Path, seed: int = 42004) -> dict[str, Any]:
    """SCEN-04: Contradictory labels on near-duplicate samples (DI-02 conflict)."""
    input_dir = dest_dir / "input"
    images_dir = input_dir / "images"
    gt_dir = dest_dir / "ground_truth"
    images_dir.mkdir(parents=True, exist_ok=True)
    gt_dir.mkdir(parents=True, exist_ok=True)

    samples_info = []
    existing_hashes: list[imagehash.ImageHash] = []

    # 8 clean controls (4 vehicle, 4 pedestrian)
    for i in range(4):
        fn = f"ctrl_veh_{i:02d}.png"
        img, h = _generate_distinct_clean_image(seed + i * 100, i, "vehicle", existing_hashes, min_hamming_dist=12)
        existing_hashes.append(h)
        p = images_dir / fn
        img.save(p, "PNG")
        samples_info.append({
            "sample_id": f"s04_cv{i:02d}", "file_name": fn, "label": "vehicle",
            "contributor": CONTRIBUTORS[i % 3], "width": 128, "height": 128, "sha256": hash_file(p),
        })

    for i in range(4):
        fn = f"ctrl_ped_{i:02d}.png"
        img, h = _generate_distinct_clean_image(seed + 400 + i * 100, i + 4, "pedestrian", existing_hashes, min_hamming_dist=12)
        existing_hashes.append(h)
        p = images_dir / fn
        img.save(p, "PNG")
        samples_info.append({
            "sample_id": f"s04_cp{i:02d}", "file_name": fn, "label": "pedestrian",
            "contributor": CONTRIBUTORS[(i + 1) % 3], "width": 128, "height": 128, "sha256": hash_file(p),
        })

    # Conflicting pair: base vehicle image + subtle near copy (pHash dist ~2 bits <= 4), with opposite label!
    base_img, h_b = _generate_distinct_clean_image(seed + 800, 8, "vehicle", existing_hashes, min_hamming_dist=12)
    existing_hashes.append(h_b)
    conflict_img = _create_near_duplicate_subtle(base_img, seed=seed)

    p1 = images_dir / "flip_base_veh.png"
    p2 = images_dir / "flip_conflict_ped.png"
    base_img.save(p1, "PNG")
    conflict_img.save(p2, "PNG")

    dist = int(imagehash.phash(base_img) - imagehash.phash(conflict_img))

    # Assigned to different contributors so DI-05 remains quiet (fc = 1 each < 2)
    samples_info.append({
        "sample_id": "s04_f1", "file_name": "flip_base_veh.png", "label": "vehicle",
        "contributor": "sensor_alpha", "width": 128, "height": 128, "sha256": hash_file(p1),
    })
    samples_info.append({
        "sample_id": "s04_f2", "file_name": "flip_conflict_ped.png", "label": "pedestrian",  # CONTRADICTION!
        "contributor": "sensor_beta", "width": 128, "height": 128, "sha256": hash_file(p2),
    })

    _build_manifests("04_label_flip", samples_info, input_dir)

    ground_truth = {
        "scenario_id": "04_label_flip",
        "title": "Pairwise Label Contradiction",
        "description": "Near-identical images carrying conflicting disjoint class labels.",
        "generation_seed": seed,
        "measured_hamming_distance": dist,
        "total_samples": len(samples_info),
        "affected_samples": ["flip_base_veh.png", "flip_conflict_ped.png"],
        "anomaly_present": True,
        "expected_detectors": {
            "di02_label_integrity": {"expected": True, "expected_risk": "HIGH", "conflicts": 1},
            "di01_duplicates": {"expected": True, "expected_risk": "LOW"},
            "di03_trigger_anomaly": {"expected": False, "expected_risk": "NONE"},
            "di04_ood_distribution": {"expected": False, "expected_risk": "NONE"},
            "di05_contributor_risk": {"expected": False, "expected_risk": "NONE"},
        },
        "expected_overall_risk": "HIGH",
        "known_limitations": ["Visual similarity with disjoint labels indicates labeling contradiction, not adversary origin."],
    }
    (gt_dir / "ground_truth.json").write_text(json.dumps(ground_truth, indent=2), encoding="utf-8")

    zip_path = dest_dir / "scenario_04_label_flip.zip"
    _write_deterministic_zip(input_dir, zip_path)
    return ground_truth


def generate_scenario_05_systematic_mislabelling(dest_dir: Path, seed: int = 42005) -> dict[str, Any]:
    """
    SCEN-05: Repeated, systematic label inconsistency across multiple samples.
    Exercises DI-02 label integrity producing multiple conflict findings.
    """
    input_dir = dest_dir / "input"
    images_dir = input_dir / "images"
    gt_dir = dest_dir / "ground_truth"
    images_dir.mkdir(parents=True, exist_ok=True)
    gt_dir.mkdir(parents=True, exist_ok=True)

    samples_info = []
    existing_hashes: list[imagehash.ImageHash] = []

    # 6 clean distinct vehicles
    for i in range(6):
        fn = f"sys_veh_{i:02d}.png"
        img, h = _generate_distinct_clean_image(seed + i * 100, i, "vehicle", existing_hashes, min_hamming_dist=12)
        existing_hashes.append(h)
        p = images_dir / fn
        img.save(p, "PNG")
        samples_info.append({
            "sample_id": f"s05_v{i:02d}", "file_name": fn, "label": "vehicle",
            "contributor": CONTRIBUTORS[i % 3], "width": 128, "height": 128, "sha256": hash_file(p),
        })

    # 4 clean distinct pedestrians
    clean_peds = []
    for i in range(4):
        fn = f"sys_ped_{i:02d}.png"
        img, h = _generate_distinct_clean_image(seed + 600 + i * 100, i + 6, "pedestrian", existing_hashes, min_hamming_dist=12)
        existing_hashes.append(h)
        p = images_dir / fn
        img.save(p, "PNG")
        clean_peds.append(img)
        samples_info.append({
            "sample_id": f"s05_p{i:02d}", "file_name": fn, "label": "pedestrian",
            "contributor": f"cam_vendor_{i:02d}", "width": 128, "height": 128, "sha256": hash_file(p),
        })

    # 3 systematically mislabeled samples (pedestrian appearance, labeled 'vehicle')
    # Derived from clean pedestrians with subtle mod (dist <= 4)
    # Distributed across distinct contributors so DI-05 remains quiet (fc = 1 each)
    mislabeled_contribs = ("labeling_node_a", "labeling_node_b", "labeling_node_c")
    mislabeled_filenames = []
    for i in range(3):
        fn = f"sys_mislabeled_{i:02d}.png"
        mod = _create_near_duplicate_subtle(clean_peds[i], seed=seed + i)
        p = images_dir / fn
        mod.save(p, "PNG")
        mislabeled_filenames.append(fn)
        samples_info.append({
            "sample_id": f"s05_m{i:02d}", "file_name": fn, "label": "vehicle",  # MISLABELLED!
            "contributor": mislabeled_contribs[i], "width": 128, "height": 128, "sha256": hash_file(p),
        })

    _build_manifests("05_systematic_mislabelling", samples_info, input_dir)

    ground_truth = {
        "scenario_id": "05_systematic_mislabelling",
        "title": "Systematic Mislabelling",
        "description": "Repeated label corruption where multiple samples with pedestrian features are labeled vehicle.",
        "generation_seed": seed,
        "total_samples": len(samples_info),
        "affected_samples": mislabeled_filenames,
        "anomaly_present": True,
        "expected_detectors": {
            "di02_label_integrity": {"expected": True, "expected_risk": "HIGH", "min_findings": 2},
            "di01_duplicates": {"expected": True, "expected_risk": "LOW"},
            "di03_trigger_anomaly": {"expected": False, "expected_risk": "NONE"},
            "di04_ood_distribution": {"expected": False, "expected_risk": "NONE"},
            "di05_contributor_risk": {"expected": False, "expected_risk": "NONE"},
        },
        "expected_overall_risk": "HIGH",
        "known_limitations": ["Provides stronger evidence of persistent mislabelling than an isolated error."],
    }
    (gt_dir / "ground_truth.json").write_text(json.dumps(ground_truth, indent=2), encoding="utf-8")

    zip_path = dest_dir / "scenario_05_systematic_mislabelling.zip"
    _write_deterministic_zip(input_dir, zip_path)
    return ground_truth


def generate_scenario_06_recurring_pattern(dest_dir: Path, seed: int = 42006) -> dict[str, Any]:
    """SCEN-06: Controlled recurring localized visual pattern across distinct images (DI-03)."""
    input_dir = dest_dir / "input"
    images_dir = input_dir / "images"
    gt_dir = dest_dir / "ground_truth"
    images_dir.mkdir(parents=True, exist_ok=True)
    gt_dir.mkdir(parents=True, exist_ok=True)

    samples_info = []
    existing_hashes: list[imagehash.ImageHash] = []

    # 8 clean distinct images (4 vehicle, 4 pedestrian)
    for i in range(4):
        fn = f"pat_clean_veh_{i:02d}.png"
        img, h = _generate_distinct_clean_image(seed + i * 100, i, "vehicle", existing_hashes, min_hamming_dist=12)
        existing_hashes.append(h)
        p = images_dir / fn
        img.save(p, "PNG")
        samples_info.append({
            "sample_id": f"s06_cv{i:02d}", "file_name": fn, "label": "vehicle",
            "contributor": EXTENDED_CONTRIBUTORS[i % 4], "width": 128, "height": 128, "sha256": hash_file(p),
        })

    for i in range(4):
        fn = f"pat_clean_ped_{i:02d}.png"
        img, h = _generate_distinct_clean_image(seed + 400 + i * 100, i + 4, "pedestrian", existing_hashes, min_hamming_dist=12)
        existing_hashes.append(h)
        p = images_dir / fn
        img.save(p, "PNG")
        samples_info.append({
            "sample_id": f"s06_cp{i:02d}", "file_name": fn, "label": "pedestrian",
            "contributor": EXTENDED_CONTRIBUTORS[(i + 1) % 4], "width": 128, "height": 128, "sha256": hash_file(p),
        })

    # 4 distinct images with injected bottom-right recurring checkerboard
    # Distributed across 4 distinct contributors (1 injected sample each -> fc = 1 < 2, so DI-05 remains quiet)
    injected_filenames = []
    for i in range(2):
        fn = f"pat_injected_veh_{i:02d}.png"
        raw, h = _generate_distinct_clean_image(seed + 800 + i * 100, i + 8, "vehicle", existing_hashes, min_hamming_dist=12)
        existing_hashes.append(h)
        inj = _inject_corner_checkerboard(raw, pw=16)
        p = images_dir / fn
        inj.save(p, "PNG")
        injected_filenames.append(fn)
        contrib = EXTENDED_CONTRIBUTORS[i]  # sensor_alpha, sensor_beta
        samples_info.append({
            "sample_id": f"s06_iv{i:02d}", "file_name": fn, "label": "vehicle",
            "contributor": contrib, "width": 128, "height": 128, "sha256": hash_file(p),
        })

    for i in range(2):
        fn = f"pat_injected_ped_{i:02d}.png"
        raw, h = _generate_distinct_clean_image(seed + 1000 + i * 100, i + 10, "pedestrian", existing_hashes, min_hamming_dist=12)
        existing_hashes.append(h)
        inj = _inject_corner_checkerboard(raw, pw=16)
        p = images_dir / fn
        inj.save(p, "PNG")
        injected_filenames.append(fn)
        contrib = EXTENDED_CONTRIBUTORS[i + 2]  # sensor_gamma, sensor_delta
        samples_info.append({
            "sample_id": f"s06_ip{i:02d}", "file_name": fn, "label": "pedestrian",
            "contributor": contrib, "width": 128, "height": 128, "sha256": hash_file(p),
        })

    _build_manifests("06_recurring_pattern", samples_info, input_dir)

    ground_truth = {
        "scenario_id": "06_recurring_pattern",
        "title": "Controlled Recurring Localized Visual Pattern",
        "description": "High-contrast 16x16 checkerboard injected in the bottom-right corner across 4 distinct images.",
        "generation_seed": seed,
        "trigger_location": "bottom_right",
        "patch_size_px": 16,
        "total_samples": len(samples_info),
        "affected_samples": injected_filenames,
        "anomaly_present": True,
        "expected_detectors": {
            "di03_trigger_anomaly": {"expected": True, "expected_risk": "HIGH", "location": "bottom_right"},
            "di01_duplicates": {"expected": False, "expected_risk": "NONE"},
            "di02_label_integrity": {"expected": False, "expected_risk": "NONE"},
            "di04_ood_distribution": {"expected": False, "expected_risk": "NONE"},
            "di05_contributor_risk": {"expected": False, "expected_risk": "NONE"},
        },
        "expected_overall_risk": "HIGH",
        "known_limitations": [
            "DI-03 detects recurring localized spatial patterns; it does not prove a malicious backdoor."
        ],
    }
    (gt_dir / "ground_truth.json").write_text(json.dumps(ground_truth, indent=2), encoding="utf-8")

    zip_path = dest_dir / "scenario_06_recurring_pattern.zip"
    _write_deterministic_zip(input_dir, zip_path)
    return ground_truth


def generate_scenario_07_ood_distribution(dest_dir: Path, seed: int = 42007) -> dict[str, Any]:
    """SCEN-07: Statistical multivariate distribution outliers (DI-04)."""
    input_dir = dest_dir / "input"
    images_dir = input_dir / "images"
    gt_dir = dest_dir / "ground_truth"
    images_dir.mkdir(parents=True, exist_ok=True)
    gt_dir.mkdir(parents=True, exist_ok=True)

    samples_info = []
    existing_hashes: list[imagehash.ImageHash] = []

    # 10 in-distribution images (128x128, aspect ratio 1.0, balanced photometric stats)
    for i in range(5):
        fn = f"in_dist_veh_{i:02d}.png"
        img, h = _generate_distinct_clean_image(seed + i * 100, i, "vehicle", existing_hashes, min_hamming_dist=12)
        existing_hashes.append(h)
        p = images_dir / fn
        img.save(p, "PNG")
        samples_info.append({
            "sample_id": f"s07_v{i:02d}", "file_name": fn, "label": "vehicle",
            "contributor": CONTRIBUTORS[i % 3], "width": 128, "height": 128, "sha256": hash_file(p),
        })

    for i in range(5):
        fn = f"in_dist_ped_{i:02d}.png"
        img, h = _generate_distinct_clean_image(seed + 500 + i * 100, i + 5, "pedestrian", existing_hashes, min_hamming_dist=12)
        existing_hashes.append(h)
        p = images_dir / fn
        img.save(p, "PNG")
        samples_info.append({
            "sample_id": f"s07_p{i:02d}", "file_name": fn, "label": "pedestrian",
            "contributor": CONTRIBUTORS[(i + 1) % 3], "width": 128, "height": 128, "sha256": hash_file(p),
        })

    # Outlier 1: Tall aspect ratio (32x128) + saturated red channel with asymmetric pattern
    img_tall = Image.new("RGB", (32, 128), color=(240, 20, 20))
    d_t = ImageDraw.Draw(img_tall)
    d_t.ellipse([4, 10, 28, 40], fill=(255, 220, 100))
    p_tall = images_dir / "ood_tall_red.png"
    img_tall.save(p_tall, "PNG")
    samples_info.append({
        "sample_id": "s07_ood1", "file_name": "ood_tall_red.png", "label": "vehicle",
        "contributor": "sensor_alpha", "width": 32, "height": 128, "sha256": hash_file(p_tall),
    })

    # Outlier 2: Wide aspect ratio (128x32) + saturated blue channel with diagonal pattern
    img_wide = Image.new("RGB", (128, 32), color=(20, 20, 240))
    d_w = ImageDraw.Draw(img_wide)
    for x in range(10, 118, 16):
        d_w.line([(x, 4), (x + 8, 28)], fill=(100, 220, 255), width=3)
    p_wide = images_dir / "ood_wide_blue.png"
    img_wide.save(p_wide, "PNG")
    samples_info.append({
        "sample_id": "s07_ood2", "file_name": "ood_wide_blue.png", "label": "vehicle",
        "contributor": "sensor_beta", "width": 128, "height": 32, "sha256": hash_file(p_wide),
    })

    _build_manifests("07_ood_distribution", samples_info, input_dir)

    ground_truth = {
        "scenario_id": "07_ood_distribution",
        "title": "Multivariate Statistical Distribution Outliers",
        "description": "Geometric aspect ratio and photometric color channel distribution divergence.",
        "generation_seed": seed,
        "total_samples": len(samples_info),
        "affected_samples": ["ood_tall_red.png", "ood_wide_blue.png"],
        "anomaly_present": True,
        "expected_detectors": {
            "di04_ood_distribution": {"expected": True, "expected_risk": "MEDIUM", "outliers": 2},
            "di01_duplicates": {"expected": False, "expected_risk": "NONE"},
            "di02_label_integrity": {"expected": False, "expected_risk": "NONE"},
            "di03_trigger_anomaly": {"expected": False, "expected_risk": "NONE"},
            "di05_contributor_risk": {"expected": False, "expected_risk": "NONE"},
        },
        "expected_overall_risk": "MEDIUM",
        "known_limitations": [
            "DI-04 detects the low-level statistical distribution representation implemented in v1; it does not provide semantic OOD guarantees."
        ],
    }
    (gt_dir / "ground_truth.json").write_text(json.dumps(ground_truth, indent=2), encoding="utf-8")

    zip_path = dest_dir / "scenario_07_ood_distribution.zip"
    _write_deterministic_zip(input_dir, zip_path)
    return ground_truth


def generate_scenario_08_contributor_concentration(dest_dir: Path, seed: int = 42008) -> dict[str, Any]:
    """
    SCEN-08: Disproportionate defect concentration associated with one contributor.
    Exercises DI-05 aggregating upstream detector findings.
    """
    input_dir = dest_dir / "input"
    images_dir = input_dir / "images"
    gt_dir = dest_dir / "ground_truth"
    images_dir.mkdir(parents=True, exist_ok=True)
    gt_dir.mkdir(parents=True, exist_ok=True)

    samples_info = []
    existing_hashes: list[imagehash.ImageHash] = []

    # sensor_alpha: 4 samples, 0 defects
    for i in range(4):
        fn = f"alpha_clean_{i:02d}.png"
        img, h = _generate_distinct_clean_image(seed + i * 100, i, "vehicle", existing_hashes, min_hamming_dist=12)
        existing_hashes.append(h)
        p = images_dir / fn
        img.save(p, "PNG")
        samples_info.append({
            "sample_id": f"s08_a{i:02d}", "file_name": fn, "label": "vehicle",
            "contributor": "sensor_alpha", "width": 128, "height": 128, "sha256": hash_file(p),
        })

    # sensor_beta: 4 samples, 0 defects
    for i in range(4):
        fn = f"beta_clean_{i:02d}.png"
        img, h = _generate_distinct_clean_image(seed + 400 + i * 100, i + 4, "pedestrian", existing_hashes, min_hamming_dist=12)
        existing_hashes.append(h)
        p = images_dir / fn
        img.save(p, "PNG")
        samples_info.append({
            "sample_id": f"s08_b{i:02d}", "file_name": fn, "label": "pedestrian",
            "contributor": "sensor_beta", "width": 128, "height": 128, "sha256": hash_file(p),
        })

    # pipeline_gamma: 4 samples, 3 flagged defects (defect rate 75% >= 50% and fc >= 3 -> Severity.HIGH in DI-05)
    # Defect 1 & 2: Exact duplicate pair (DI-01)
    g_dup, h_gd = _generate_distinct_clean_image(seed + 800, 8, "vehicle", existing_hashes, min_hamming_dist=12)
    existing_hashes.append(h_gd)
    p_g1 = images_dir / "gamma_dup_orig.png"
    p_g2 = images_dir / "gamma_dup_clone.png"
    g_dup.save(p_g1, "PNG")
    shutil.copy2(p_g1, p_g2)
    h_g = hash_file(p_g1)

    samples_info.append({
        "sample_id": "s08_g1", "file_name": "gamma_dup_orig.png", "label": "vehicle",
        "contributor": "pipeline_gamma", "width": 128, "height": 128, "sha256": h_g,
    })
    samples_info.append({
        "sample_id": "s08_g2", "file_name": "gamma_dup_clone.png", "label": "vehicle",
        "contributor": "pipeline_gamma", "width": 128, "height": 128, "sha256": h_g,
    })

    # Defect 3: Near duplicate with contradictory label (DI-02)
    p_orig, h_po = _generate_distinct_clean_image(seed + 900, 9, "pedestrian", existing_hashes, min_hamming_dist=12)
    existing_hashes.append(h_po)
    p_conflict = _create_near_duplicate_subtle(p_orig, seed=seed)
    p_g3 = images_dir / "gamma_ped_base.png"
    p_g4 = images_dir / "gamma_ped_flipped.png"
    p_orig.save(p_g3, "PNG")
    p_conflict.save(p_g4, "PNG")

    samples_info.append({
        "sample_id": "s08_g3", "file_name": "gamma_ped_base.png", "label": "pedestrian",
        "contributor": "pipeline_gamma", "width": 128, "height": 128, "sha256": hash_file(p_g3),
    })
    samples_info.append({
        "sample_id": "s08_g4", "file_name": "gamma_ped_flipped.png", "label": "vehicle",  # Conflict!
        "contributor": "pipeline_gamma", "width": 128, "height": 128, "sha256": hash_file(p_g4),
    })

    _build_manifests("08_contributor_concentration", samples_info, input_dir)

    ground_truth = {
        "scenario_id": "08_contributor_concentration",
        "title": "Disproportionate Contributor Defect Concentration",
        "description": "Controlled defects concentrated in contributor 'pipeline_gamma' (defect rate 75%).",
        "generation_seed": seed,
        "flagged_contributor": "pipeline_gamma",
        "expected_contributor_defect_rate": 0.75,
        "total_samples": len(samples_info),
        "affected_samples": ["gamma_dup_orig.png", "gamma_dup_clone.png", "gamma_ped_base.png", "gamma_ped_flipped.png"],
        "anomaly_present": True,
        "expected_detectors": {
            "di05_contributor_risk": {"expected": True, "expected_risk": "HIGH", "target": "pipeline_gamma"},
            "di01_duplicates": {"expected": True, "expected_risk": "MEDIUM"},
            "di02_label_integrity": {"expected": True, "expected_risk": "HIGH"},
            "di03_trigger_anomaly": {"expected": False, "expected_risk": "NONE"},
            "di04_ood_distribution": {"expected": False, "expected_risk": "NONE"},
        },
        "expected_overall_risk": "HIGH",
        "known_limitations": [
            "DI-05 requires contributor attribution. Observed concentration does not prove intentional insider threat."
        ],
    }
    (gt_dir / "ground_truth.json").write_text(json.dumps(ground_truth, indent=2), encoding="utf-8")

    zip_path = dest_dir / "scenario_08_contributor_concentration.zip"
    _write_deterministic_zip(input_dir, zip_path)
    return ground_truth


def generate_scenario_09_mixed_scenario(dest_dir: Path, seed: int = 42009) -> dict[str, Any]:
    """
    SCEN-09: Mixed scenario combining multiple controlled anomalies:
      - Exact duplicate (DI-01)
      - Label conflict (DI-02)
      - Recurring localized corner pattern (DI-03)
      - Statistical distribution outlier (DI-04)
      - Contributor concentration in pipeline_gamma (DI-05)
    """
    input_dir = dest_dir / "input"
    images_dir = input_dir / "images"
    gt_dir = dest_dir / "ground_truth"
    images_dir.mkdir(parents=True, exist_ok=True)
    gt_dir.mkdir(parents=True, exist_ok=True)

    samples_info = []
    existing_hashes: list[imagehash.ImageHash] = []

    # 1. Clean baseline controls (sensor_alpha: 4 samples, sensor_beta: 4 samples)
    for i in range(4):
        fn = f"mix_clean_a_{i:02d}.png"
        img, h = _generate_distinct_clean_image(seed + i * 100, i, "vehicle", existing_hashes, min_hamming_dist=12)
        existing_hashes.append(h)
        p = images_dir / fn
        img.save(p, "PNG")
        samples_info.append({
            "sample_id": f"s09_ca{i:02d}", "file_name": fn, "label": "vehicle",
            "contributor": "sensor_alpha", "width": 128, "height": 128, "sha256": hash_file(p),
        })

    for i in range(4):
        fn = f"mix_clean_b_{i:02d}.png"
        img, h = _generate_distinct_clean_image(seed + 400 + i * 100, i + 4, "pedestrian", existing_hashes, min_hamming_dist=12)
        existing_hashes.append(h)
        p = images_dir / fn
        img.save(p, "PNG")
        samples_info.append({
            "sample_id": f"s09_cb{i:02d}", "file_name": fn, "label": "pedestrian",
            "contributor": "sensor_beta", "width": 128, "height": 128, "sha256": hash_file(p),
        })

    # 2. Injected recurring corner pattern across 4 distinct images (DI-03)
    # Distributed across sensor_alpha (2) and sensor_beta (2)
    for i in range(2):
        fn = f"mix_trig_a_{i:02d}.png"
        raw, h = _generate_distinct_clean_image(seed + 800 + i * 100, i + 8, "vehicle", existing_hashes, min_hamming_dist=12)
        existing_hashes.append(h)
        inj = _inject_corner_checkerboard(raw, pw=16)
        p = images_dir / fn
        inj.save(p, "PNG")
        samples_info.append({
            "sample_id": f"s09_ta{i:02d}", "file_name": fn, "label": "vehicle",
            "contributor": "sensor_alpha", "width": 128, "height": 128, "sha256": hash_file(p),
        })

    for i in range(2):
        fn = f"mix_trig_b_{i:02d}.png"
        raw, h = _generate_distinct_clean_image(seed + 1000 + i * 100, i + 10, "pedestrian", existing_hashes, min_hamming_dist=12)
        existing_hashes.append(h)
        inj = _inject_corner_checkerboard(raw, pw=16)
        p = images_dir / fn
        inj.save(p, "PNG")
        samples_info.append({
            "sample_id": f"s09_tb{i:02d}", "file_name": fn, "label": "pedestrian",
            "contributor": "sensor_beta", "width": 128, "height": 128, "sha256": hash_file(p),
        })

    # 3. Contributor pipeline_gamma: 6 samples containing exact duplicates, label conflict, and OOD
    # Exact duplicate pair (DI-01)
    g_dup, h_gd = _generate_distinct_clean_image(seed + 1200, 12, "vehicle", existing_hashes, min_hamming_dist=12)
    existing_hashes.append(h_gd)
    p_g1 = images_dir / "mix_gamma_dup_orig.png"
    p_g2 = images_dir / "mix_gamma_dup_clone.png"
    g_dup.save(p_g1, "PNG")
    shutil.copy2(p_g1, p_g2)
    h_g = hash_file(p_g1)

    samples_info.append({
        "sample_id": "s09_gd1", "file_name": "mix_gamma_dup_orig.png", "label": "vehicle",
        "contributor": "pipeline_gamma", "width": 128, "height": 128, "sha256": h_g,
    })
    samples_info.append({
        "sample_id": "s09_gd2", "file_name": "mix_gamma_dup_clone.png", "label": "vehicle",
        "contributor": "pipeline_gamma", "width": 128, "height": 128, "sha256": h_g,
    })

    # Label conflict pair (DI-02)
    p_base, h_pb = _generate_distinct_clean_image(seed + 1300, 13, "pedestrian", existing_hashes, min_hamming_dist=12)
    existing_hashes.append(h_pb)
    p_flip = _create_near_duplicate_subtle(p_base, seed=seed)
    p_g3 = images_dir / "mix_gamma_flip_base.png"
    p_g4 = images_dir / "mix_gamma_flip_conflict.png"
    p_base.save(p_g3, "PNG")
    p_flip.save(p_g4, "PNG")

    samples_info.append({
        "sample_id": "s09_gf1", "file_name": "mix_gamma_flip_base.png", "label": "pedestrian",
        "contributor": "pipeline_gamma", "width": 128, "height": 128, "sha256": hash_file(p_g3),
    })
    samples_info.append({
        "sample_id": "s09_gf2", "file_name": "mix_gamma_flip_conflict.png", "label": "vehicle",  # Conflict!
        "contributor": "pipeline_gamma", "width": 128, "height": 128, "sha256": hash_file(p_g4),
    })

    # Statistical distribution outlier (DI-04)
    img_ood = Image.new("RGB", (32, 128), color=(240, 20, 20))
    d_ood = ImageDraw.Draw(img_ood)
    d_ood.ellipse([4, 10, 28, 40], fill=(255, 220, 100))
    p_g5 = images_dir / "mix_gamma_ood_tall.png"
    img_ood.save(p_g5, "PNG")
    samples_info.append({
        "sample_id": "s09_good", "file_name": "mix_gamma_ood_tall.png", "label": "vehicle",
        "contributor": "pipeline_gamma", "width": 32, "height": 128, "sha256": hash_file(p_g5),
    })

    # Clean control for pipeline_gamma
    img_gclean, h_gc = _generate_distinct_clean_image(seed + 1400, 14, "vehicle", existing_hashes, min_hamming_dist=12)
    existing_hashes.append(h_gc)
    p_g6 = images_dir / "mix_gamma_clean.png"
    img_gclean.save(p_g6, "PNG")
    samples_info.append({
        "sample_id": "s09_gc", "file_name": "mix_gamma_clean.png", "label": "vehicle",
        "contributor": "pipeline_gamma", "width": 128, "height": 128, "sha256": hash_file(p_g6),
    })

    _build_manifests("09_mixed_scenario", samples_info, input_dir)

    ground_truth = {
        "scenario_id": "09_mixed_scenario",
        "title": "Unified Mixed Integrity Scenario",
        "description": "Combines duplicates (DI-01), label flip (DI-02), recurring pattern (DI-03), OOD (DI-04), and contributor concentration (DI-05).",
        "generation_seed": seed,
        "total_samples": len(samples_info),
        "affected_samples": [
            "mix_trig_a_00.png", "mix_trig_a_01.png", "mix_trig_b_00.png", "mix_trig_b_01.png",
            "mix_gamma_dup_orig.png", "mix_gamma_dup_clone.png",
            "mix_gamma_flip_base.png", "mix_gamma_flip_conflict.png",
            "mix_gamma_ood_tall.png",
        ],
        "anomaly_present": True,
        "expected_detectors": {
            "di01_duplicates": {"expected": True, "expected_risk": "MEDIUM"},
            "di02_label_integrity": {"expected": True, "expected_risk": "HIGH"},
            "di03_trigger_anomaly": {"expected": True, "expected_risk": "HIGH"},
            "di04_ood_distribution": {"expected": True, "expected_risk": "MEDIUM"},
            "di05_contributor_risk": {"expected": True, "expected_risk": "HIGH"},
        },
        "expected_overall_risk": "HIGH",
        "known_limitations": ["Multi-finding assessment demonstrates orthogonal detector capabilities."],
    }
    (gt_dir / "ground_truth.json").write_text(json.dumps(ground_truth, indent=2), encoding="utf-8")

    zip_path = dest_dir / "scenario_09_mixed_scenario.zip"
    _write_deterministic_zip(input_dir, zip_path)
    return ground_truth


# ---------------------------------------------------------------------------
# Corpus Master Generator
# ---------------------------------------------------------------------------

SCENARIOS: list[tuple[str, Any]] = [
    ("01_clean_baseline", generate_scenario_01_clean),
    ("02_exact_duplicate", generate_scenario_02_exact_duplicate),
    ("03_near_duplicate", generate_scenario_03_near_duplicate),
    ("04_label_flip", generate_scenario_04_label_flip),
    ("05_systematic_mislabelling", generate_scenario_05_systematic_mislabelling),
    ("06_recurring_pattern", generate_scenario_06_recurring_pattern),
    ("07_ood_distribution", generate_scenario_07_ood_distribution),
    ("08_contributor_concentration", generate_scenario_08_contributor_concentration),
    ("09_mixed_scenario", generate_scenario_09_mixed_scenario),
]


def generate_corpus(output_dir: Path, master_seed: int = 42) -> dict[str, Any]:
    """Generate all 9 scenarios and the global corpus manifest."""
    scenarios_dir = output_dir / "scenarios"
    scenarios_dir.mkdir(parents=True, exist_ok=True)

    manifest_entries = []
    total_images_all = 0

    log.info("Generating PRAMAAN corpus at %s (master seed: %d)", output_dir, master_seed)

    for idx, (s_name, gen_func) in enumerate(SCENARIOS, start=1):
        s_dir = scenarios_dir / s_name
        s_seed = master_seed * 1000 + idx
        gt = gen_func(s_dir, seed=s_seed)
        n_samples = gt["total_samples"]
        total_images_all += n_samples

        manifest_entries.append({
            "scenario_id": s_name,
            "title": gt["title"],
            "total_samples": n_samples,
            "anomaly_present": gt["anomaly_present"],
            "expected_overall_risk": gt["expected_overall_risk"],
            "input_dir": f"scenarios/{s_name}/input",
            "ground_truth_path": f"scenarios/{s_name}/ground_truth/ground_truth.json",
            "zip_path": f"scenarios/{s_name}/scenario_{s_name}.zip",
        })
        log.info("Generated %s: %d samples", s_name, n_samples)

    corpus_manifest = {
        "manifest_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "master_seed": master_seed,
        "total_scenarios": len(SCENARIOS),
        "total_images": total_images_all,
        "scenarios": manifest_entries,
    }

    (output_dir / "corpus_manifest.json").write_text(
        json.dumps(corpus_manifest, indent=2), encoding="utf-8"
    )
    log.info("Corpus generation complete: %d scenarios, %d total images", len(SCENARIOS), total_images_all)
    return corpus_manifest


# ---------------------------------------------------------------------------
# In-Memory Validation Harness
# ---------------------------------------------------------------------------

def validate_scenario_against_detectors(scenario_path: Path) -> dict[str, Any]:
    """
    Run actual detectors against a scenario's input directory using a temp SQLite DB.
    Verifies that the actual detectors produce findings consistent with qualitative expectations.
    """
    input_dir = scenario_path / "input"
    gt_file = scenario_path / "ground_truth" / "ground_truth.json"

    assert input_dir.is_dir(), f"Missing input directory: {input_dir}"
    assert gt_file.is_file(), f"Missing ground truth file: {gt_file}"

    gt = json.loads(gt_file.read_text(encoding="utf-8"))

    # Create temporary database for validation
    conn = open_db(Path(":memory:"))

    try:
        assess = Assessment(title=f"Validation {scenario_path.name}")
        AssessmentRepository(conn).insert(assess)
        a_id = assess.assessment_id

        # Register and ingest dataset
        asset, dataset = register_dataset(a_id, scenario_path.name, input_dir, DatasetFormat.IMAGE_DIR, conn)
        res = ingest_image_directory(input_dir, dataset.dataset_id, conn)

        ds_id = dataset.dataset_id

        # Run all 5 detectors in sequence
        ctx = DetectorContext(assessment_id=a_id, asset_id=ds_id, conn=conn)
        d1 = run_detector(DI01DuplicateDetector(), ctx, conn)
        d2 = run_detector(DI02LabelIntegrityDetector(), ctx, conn)
        d3 = run_detector(DI03TriggerAnomalyDetector(), ctx, conn)
        d4 = run_detector(DI04DistributionOODDetector(), ctx, conn)
        d5 = run_detector(DI05ContributorRiskDetector(), ctx, conn)

        detector_results = {
            "di01_duplicates": {"risk": d1.risk_level.value, "findings_count": len(d1.findings)},
            "di02_label_integrity": {"risk": d2.risk_level.value, "findings_count": len(d2.findings)},
            "di03_trigger_anomaly": {"risk": d3.risk_level.value, "findings_count": len(d3.findings)},
            "di04_ood_distribution": {"risk": d4.risk_level.value, "findings_count": len(d4.findings)},
            "di05_contributor_risk": {"risk": d5.risk_level.value, "findings_count": len(d5.findings)},
        }

        # Check qualitative expectations
        passed = True
        failures = []

        for det_key, exp in gt.get("expected_detectors", {}).items():
            actual = detector_results.get(det_key, {})
            expected_flag = exp.get("expected", False)
            actual_count = actual.get("findings_count", 0)

            if expected_flag and actual_count == 0:
                passed = False
                failures.append(f"{det_key}: expected findings, got 0")
            elif not expected_flag and actual_count > 0:
                # Legitimate cross-detector interactions:
                # 1. DI-01 fires on DI-02 near-duplicate label conflicts (perceptual similarity is real)
                # 2. DI-05 fires if any upstream detector flags >= 2 samples from a single contributor
                is_legitimate_interaction = False
                if det_key == "di01_duplicates" and detector_results["di02_label_integrity"]["findings_count"] > 0:
                    is_legitimate_interaction = True
                if det_key == "di05_contributor_risk" and exp.get("allow_upstream_trigger", False):
                    is_legitimate_interaction = True

                if not is_legitimate_interaction:
                    passed = False
                    failures.append(f"{det_key}: expected 0 findings, got {actual_count}")

        return {
            "scenario": scenario_path.name,
            "samples_ingested": res.samples_ingested,
            "passed": passed,
            "detector_results": detector_results,
            "failures": failures,
        }
    finally:
        conn.close()


def validate_all_scenarios(corpus_dir: Path) -> list[dict[str, Any]]:
    """Validate all generated scenarios in corpus_dir."""
    scenarios_dir = corpus_dir / "scenarios"
    results = []
    for s_name, _ in SCENARIOS:
        s_path = scenarios_dir / s_name
        r = validate_scenario_against_detectors(s_path)
        status = "PASSED" if r["passed"] else "FAILED"
        log.info("Validation %s: %s (detectors: %s)", s_name, status, r["detector_results"])
        results.append(r)
    return results


# ---------------------------------------------------------------------------
# CLI Entrypoint
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="PRAMAAN v1 Corpus Generator")
    parser.add_argument("--output", "-o", type=Path, default=Path("data/corpus"), help="Output directory")
    parser.add_argument("--seed", "-s", type=int, default=42, help="Master deterministic seed")
    parser.add_argument("--validate", "-v", action="store_true", help="Run in-memory detector validation")
    args = parser.parse_args()

    generate_corpus(args.output, master_seed=args.seed)

    if args.validate:
        log.info("Running post-generation validation against actual detectors...")
        val_results = validate_all_scenarios(args.output)
        failed = [r for r in val_results if not r["passed"]]
        if failed:
            log.error("Validation failed for %d scenarios: %s", len(failed), [f["scenario"] for f in failed])
            raise SystemExit(1)
        log.info("All %d scenarios validated successfully against actual detectors!", len(val_results))


if __name__ == "__main__":
    main()
