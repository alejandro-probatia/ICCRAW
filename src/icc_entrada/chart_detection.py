from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
import os
import numpy as np
import cv2

from .models import ChartDetectionResult, PatchDetection, Point2
from .utils import read_image


def detect_chart(image_path: Path, chart_type: str = "colorchecker24") -> ChartDetectionResult:
    image = read_image(image_path)
    h, w = image.shape[:2]
    bgr8 = np.clip(_to_display(image)[:, :, ::-1] * 255.0, 0, 255).astype(np.uint8)

    quad = _find_chart_quad(bgr8)
    warnings: list[str] = []

    if quad is None:
        quad = np.array(
            [[0.05 * w, 0.05 * h], [0.95 * w, 0.05 * h], [0.95 * w, 0.95 * h], [0.05 * w, 0.95 * h]],
            dtype=np.float32,
        )
        warnings.append("no se detecto contorno de carta; usando bbox de fallback")

    quad = _order_points_clockwise(quad)

    chart_type = chart_type.lower()
    if chart_type == "it8":
        cols, rows = 12, 10
    else:
        chart_type = "colorchecker24"
        cols, rows = 6, 4

    dst = np.array([[0, 0], [cols * 100, 0], [cols * 100, rows * 100], [0, rows * 100]], dtype=np.float32)
    H = cv2.getPerspectiveTransform(quad.astype(np.float32), dst)
    H_inv = np.linalg.inv(H)

    warped = cv2.warpPerspective(bgr8, H, (cols * 100, rows * 100), flags=cv2.INTER_LINEAR)

    # Try to orient ColorChecker: lowest saturation row should be bottom row.
    if chart_type == "colorchecker24" and os.environ.get("ICC_ENABLE_ROTATION", "0") == "1":
        k = _estimate_rotation_colorchecker(warped)
        if k != 0:
            warnings.append(f"rotacion corregida automaticamente: {k * 90} grados")
        warped = np.rot90(warped, k)
        H_inv = _compose_inverse_rotation(H_inv, cols * 100, rows * 100, k)

    patches = _build_patch_geometry(H_inv, cols, rows)

    clipped_ratio = float(np.mean(np.any(image >= 0.999, axis=2)))
    if clipped_ratio > 0.01:
        warnings.append(f"clipping detectado: {clipped_ratio * 100:.2f}% pixeles")

    confidence = _confidence_score(quad, w, h, cols / rows)

    chart_polygon = [Point2(float(x), float(y)) for x, y in quad]
    result = ChartDetectionResult(
        chart_type=chart_type,
        confidence_score=confidence,
        valid_patch_ratio=1.0,
        homography=[float(v) for v in H.flatten().tolist()],
        chart_polygon=chart_polygon,
        patches=patches,
        warnings=warnings,
    )
    return result


def draw_detection_overlay(image_path: Path, detection: ChartDetectionResult, out_preview: Path) -> None:
    image = read_image(image_path)
    bgr8 = np.clip(_to_display(image)[:, :, ::-1] * 255.0, 0, 255).astype(np.uint8)

    chart = np.array([[p.x, p.y] for p in detection.chart_polygon], dtype=np.int32)
    cv2.polylines(bgr8, [chart], isClosed=True, color=(0, 255, 0), thickness=2)

    for patch in detection.patches:
        poly = np.array([[p.x, p.y] for p in patch.sample_region], dtype=np.int32)
        cv2.polylines(bgr8, [poly], isClosed=True, color=(0, 128, 255), thickness=1)

    out_preview.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out_preview), bgr8)


def _find_chart_quad(bgr8: np.ndarray) -> np.ndarray | None:
    gray = cv2.cvtColor(bgr8, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(gray, 40, 130)
    edges = cv2.dilate(edges, np.ones((3, 3), np.uint8), iterations=1)

    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None

    best = None
    best_score = -1e9

    area_img = bgr8.shape[0] * bgr8.shape[1]

    for cnt in contours:
        peri = cv2.arcLength(cnt, True)
        approx = cv2.approxPolyDP(cnt, 0.02 * peri, True)
        if len(approx) != 4:
            continue
        if not cv2.isContourConvex(approx):
            continue

        pts = approx[:, 0, :].astype(np.float32)
        area = cv2.contourArea(pts)
        if area < 0.02 * area_img:
            continue

        rect = cv2.minAreaRect(pts)
        rw, rh = rect[1]
        if rw <= 0 or rh <= 0:
            continue
        ratio = max(rw, rh) / min(rw, rh)
        ratio_penalty = abs(ratio - 1.5)

        score = area / area_img - 0.2 * ratio_penalty
        if score > best_score:
            best_score = score
            best = pts

    return best


def _order_points_clockwise(pts: np.ndarray) -> np.ndarray:
    s = pts.sum(axis=1)
    diff = np.diff(pts, axis=1).reshape(-1)

    tl = pts[np.argmin(s)]
    br = pts[np.argmax(s)]
    tr = pts[np.argmin(diff)]
    bl = pts[np.argmax(diff)]

    return np.array([tl, tr, br, bl], dtype=np.float32)


def _build_patch_geometry(H_inv: np.ndarray, cols: int, rows: int) -> list[PatchDetection]:
    patches: list[PatchDetection] = []

    for r in range(rows):
        for c in range(cols):
            patch_id = f"P{(r * cols + c + 1):02d}"
            x0 = c / cols
            y0 = r / rows
            x1 = (c + 1) / cols
            y1 = (r + 1) / rows

            poly_norm = np.array(
                [[x0, y0], [x1, y0], [x1, y1], [x0, y1]],
                dtype=np.float32,
            )
            sample_norm = _shrink_poly_norm(poly_norm, 0.18)

            poly = _norm_to_img(poly_norm, H_inv, cols * 100, rows * 100)
            sample = _norm_to_img(sample_norm, H_inv, cols * 100, rows * 100)

            patches.append(
                PatchDetection(
                    patch_id=patch_id,
                    polygon=[Point2(float(x), float(y)) for x, y in poly],
                    sample_region=[Point2(float(x), float(y)) for x, y in sample],
                )
            )

    return patches


def _norm_to_img(poly_norm: np.ndarray, H_inv: np.ndarray, width: int, height: int) -> np.ndarray:
    pts = np.array([[x * width, y * height] for x, y in poly_norm], dtype=np.float32)
    pts_h = np.concatenate([pts, np.ones((pts.shape[0], 1), dtype=np.float32)], axis=1)
    out = (H_inv @ pts_h.T).T
    out = out[:, :2] / out[:, 2:3]
    return out


def _shrink_poly_norm(poly: np.ndarray, margin_ratio: float) -> np.ndarray:
    center = np.mean(poly, axis=0)
    return center + (poly - center) * (1.0 - margin_ratio)


def _estimate_rotation_colorchecker(warped_bgr: np.ndarray) -> int:
    best_k = 0
    best_score = -1e9
    for k in range(4):
        img = np.rot90(warped_bgr, k)
        # Ensure horizontal board for scoring (rows=4, cols=6)
        if img.shape[0] > img.shape[1]:
            img = np.rot90(img, 1)
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        sat = hsv[:, :, 1].astype(np.float32) / 255.0
        lum = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0

        patch_sat = _grid_patch_means(sat, rows=4, cols=6)
        patch_lum = _grid_patch_means(lum, rows=4, cols=6)

        row_sat = patch_sat.mean(axis=1)
        row_lum = patch_lum[3]
        monotonic = -np.maximum(0.0, np.diff(row_lum)).sum()
        score = (row_sat.mean() - row_sat[3]) * 3.0 + monotonic
        if score > best_score:
            best_score = score
            best_k = k
    return best_k


def _grid_patch_means(image: np.ndarray, rows: int, cols: int) -> np.ndarray:
    h, w = image.shape[:2]
    out = np.zeros((rows, cols), dtype=np.float32)
    for r in range(rows):
        for c in range(cols):
            y0 = int((r + 0.2) * h / rows)
            y1 = int((r + 0.8) * h / rows)
            x0 = int((c + 0.2) * w / cols)
            x1 = int((c + 0.8) * w / cols)
            patch = image[y0:y1, x0:x1]
            out[r, c] = float(np.mean(patch)) if patch.size else 0.0
    return out


def _compose_inverse_rotation(H_inv: np.ndarray, width: int, height: int, k: int) -> np.ndarray:
    # Map oriented canonical coordinates back to original canonical orientation.
    if k == 0:
        T = np.eye(3, dtype=np.float32)
    elif k == 1:
        T = np.array([[0, -1, width], [1, 0, 0], [0, 0, 1]], dtype=np.float32)
    elif k == 2:
        T = np.array([[-1, 0, width], [0, -1, height], [0, 0, 1]], dtype=np.float32)
    else:
        T = np.array([[0, 1, 0], [-1, 0, height], [0, 0, 1]], dtype=np.float32)
    return H_inv @ T


def _confidence_score(quad: np.ndarray, width: int, height: int, expected_ratio: float) -> float:
    area = cv2.contourArea(quad)
    area_ratio = area / float(width * height)
    rect = cv2.minAreaRect(quad.astype(np.float32))
    rw, rh = rect[1]
    if rw <= 0 or rh <= 0:
        return 0.0
    ratio = max(rw, rh) / min(rw, rh)
    ratio_error = abs(ratio - expected_ratio)
    score = 0.5 * min(1.0, area_ratio / 0.3) + 0.5 * max(0.0, 1.0 - ratio_error)
    return float(np.clip(score, 0.0, 1.0))


def _to_display(image_linear: np.ndarray) -> np.ndarray:
    a = 0.055
    out = np.where(
        image_linear <= 0.0031308,
        12.92 * image_linear,
        (1 + a) * np.power(np.clip(image_linear, 0.0, 1.0), 1 / 2.4) - a,
    )
    return np.clip(out, 0.0, 1.0)
