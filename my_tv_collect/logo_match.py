"""Advisory TV logo matching for captured stream frames.

Matches are evidence only.  Callers must not turn them into automatic publish
or rejection decisions because a source may be mislabeled or change content.
"""
from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np


def load_logo_library(path: Path) -> list[dict]:
    if not path.exists():
        return []
    base = path.parent
    entries = json.loads(path.read_text(encoding="utf-8"))
    library = []
    sift = cv2.SIFT_create()
    for entry in entries:
        template_path = base / entry["file"]
        template = cv2.imread(str(template_path), cv2.IMREAD_GRAYSCALE)
        if template is None:
            continue
        keypoints, descriptors = sift.detectAndCompute(template, None)
        if descriptors is not None and len(keypoints) >= 4:
            library.append({**entry, "path": str(template_path), "keypoints": keypoints,
                            "descriptors": descriptors})
    return library


def corner_images(image):
    height, width = image.shape[:2]
    crop_width, crop_height = max(1, round(width * .36)), max(1, round(height * .32))
    return {
        "左上": image[:crop_height, :crop_width],
        "右上": image[:crop_height, width - crop_width:],
        "左下": image[height - crop_height:, :crop_width],
        "右下": image[height - crop_height:, width - crop_width:],
    }


def match_logo_candidates(frame_path: Path, library: list[dict], min_inliers: int = 8) -> list[dict]:
    """Return geometrically verified candidates, strongest first."""
    image = cv2.imread(str(frame_path), cv2.IMREAD_GRAYSCALE)
    if image is None or not library:
        return []
    sift, matcher = cv2.SIFT_create(), cv2.BFMatcher()
    results = []
    crops = []
    for corner, crop in corner_images(image).items():
        crop_keypoints, crop_descriptors = sift.detectAndCompute(crop, None)
        if crop_descriptors is not None:
            crops.append((corner, crop_keypoints, crop_descriptors))
    for reference in library:
        candidates = []
        for corner, crop_keypoints, crop_descriptors in crops:
            pairs = matcher.knnMatch(reference["descriptors"], crop_descriptors, k=2)
            good = [first for first, second in pairs if first.distance < .72 * second.distance]
            if len(good) < 4:
                continue
            source_points = np.float32([
                reference["keypoints"][match.queryIdx].pt for match in good
            ]).reshape(-1, 1, 2)
            target_points = np.float32([
                crop_keypoints[match.trainIdx].pt for match in good
            ]).reshape(-1, 1, 2)
            _transform, mask = cv2.findHomography(source_points, target_points, cv2.RANSAC, 4.0)
            inliers = int(mask.sum()) if mask is not None else 0
            if inliers >= min_inliers:
                candidates.append({
                    "channel": reference["channel"], "template": reference["file"],
                    "corner": corner, "inliers": inliers, "good_matches": len(good),
                })
        if candidates:
            results.append(max(candidates, key=lambda match: (match["inliers"], match["good_matches"])))
    return sorted(results, key=lambda match: (match["inliers"], match["good_matches"]), reverse=True)


def summarize_logo_matches(expected_channel: str, per_frame: list[list[dict]]) -> tuple[str, str]:
    """Return (supporting summary, review warning), never a rejection verdict."""
    target_count = sum(any(match["channel"] == expected_channel for match in frame_matches)
                       for frame_matches in per_frame)
    channels = {match["channel"] for frame_matches in per_frame for match in frame_matches}
    other_counts = {
        channel: sum(any(match["channel"] == channel for match in frame_matches)
                     for frame_matches in per_frame)
        for channel in channels if channel != expected_channel
    }
    repeated_other = sorted(channel for channel, count in other_counts.items() if count >= 2)
    support = f"目标台标候选：{expected_channel}（{target_count} 个时间帧）" if target_count else ""
    warning = ""
    if repeated_other:
        details = "、".join(f"{channel}（{other_counts[channel]} 帧）" for channel in repeated_other)
        warning = ("多个时间帧检测到其他频道台标候选：" + details +
                   "；可能是频道标签分错或内容切换，必须人工核对")
    return support, warning
