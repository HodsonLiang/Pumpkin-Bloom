"""Coarse candidate search, then full-resolution masked verification.

Outside-image pixels are excluded from the score, not treated as black pixels.
The original API remains available for the scanner's background worker.
"""
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
import math
import cv2
import numpy as np


@dataclass(frozen=True)
class Template:
    name: str
    color: np.ndarray
    mask: np.ndarray
    coarse_color: np.ndarray
    coarse_mask: np.ndarray
    scale_x: float
    scale_y: float


@dataclass(frozen=True)
class Match:
    name: str
    score: float
    visible: float
    x: int
    y: int


def read_image(path, mode=cv2.IMREAD_COLOR):
    """np.fromfile also supports non-ASCII Windows paths."""
    try:
        return cv2.imdecode(np.fromfile(path, dtype=np.uint8), mode)
    except (OSError, cv2.error):
        return None


@lru_cache(maxsize=4)
def _load_templates(signature, scale):
    templates = []
    for filename, _mtime, _size in signature:
        image = read_image(filename, cv2.IMREAD_UNCHANGED)
        if image is None or image.ndim != 3 or image.shape[2] != 4:
            continue
        mask = (image[:, :, 3] > 1).astype(np.uint8)
        if not np.any(mask):
            continue
        x, y, w, h = cv2.boundingRect(mask)
        color = np.ascontiguousarray(image[y:y+h, x:x+w, :3], dtype=np.float32)/255.
        mask = np.ascontiguousarray(mask[y:y+h, x:x+w], dtype=np.float32)
        # Keep at least 16 pixels per axis in candidate templates.
        ratio = min(1., max(scale, 16/min(w, h)))
        cw, ch = max(1, round(w*ratio)), max(1, round(h*ratio))
        cmask = cv2.resize(mask, (cw, ch), interpolation=cv2.INTER_AREA)
        weighted = cv2.resize(color*mask[:, :, None], (cw, ch), interpolation=cv2.INTER_AREA)
        ccolor = weighted / np.maximum(cmask[:, :, None], 1e-6)
        templates.append(Template(Path(filename).name, color, mask, ccolor, cmask, cw/w, ch/h))
    return tuple(templates)


def load_templates(folder, scale=.25):
    signature = tuple((str(p.resolve()), p.stat().st_mtime_ns, p.stat().st_size)
                      for p in sorted(Path(folder).glob('*.png')))
    return _load_templates(signature, scale)


def _scores(image, valid, color, mask, minimum):
    """Masked SQDIFF_NORMED, with position-dependent visible template energy.

    All four correlations are compiled OpenCV operations. Only coarse search
    and small native-resolution candidate ROIs run this calculation.
    """
    energy = np.sum(image*image, axis=2)
    tpl_energy = np.sum(color*color, axis=2)*mask
    image_energy = cv2.matchTemplate(energy, mask, cv2.TM_CCORR)
    visible_energy = cv2.matchTemplate(valid, tpl_energy, cv2.TM_CCORR)
    cross = cv2.matchTemplate(image, color*mask[:, :, None], cv2.TM_CCORR)
    visibility = cv2.matchTemplate(valid, mask, cv2.TM_CCORR)/mask.sum()
    denominator = np.sqrt(np.maximum(image_energy*visible_energy, 0))
    result = np.maximum(image_energy+visible_energy-2*cross, 0)/np.maximum(denominator, 1e-12)
    result[(visibility < minimum) | (denominator < 1e-8) | ~np.isfinite(result)] = np.inf
    return result, np.clip(visibility, 0, 1)


def _window(image, x, y, width, height):
    """Small virtual ROI; never pad the full-resolution screenshot."""
    ih, iw = image.shape[:2]
    window = np.zeros((height, width, 3), np.float32)
    valid = np.zeros((height, width), np.float32)
    left, top, right, bottom = max(0, x), max(0, y), min(iw, x+width), min(ih, y+height)
    if right > left and bottom > top:
        window[top-y:bottom-y, left-x:right-x] = image[top:bottom, left:right]
        valid[top-y:bottom-y, left-x:right-x] = 1
    return window, valid


def match_image(image, templates, threshold=.058, *, min_visible=.65, candidates=8):
    if not 0 < threshold <= 1 or not .1 <= min_visible <= 1 or candidates < 1:
        raise ValueError('Invalid matching threshold, visibility or candidate count.')
    full = np.asarray(image, dtype=np.float32)/255.
    ih, iw = full.shape[:2]
    resized = {}
    for template in templates:
        h, w = template.mask.shape
        ch, cw = template.coarse_mask.shape
        # Use actual resize ratios for consistent coarse/native coordinates.
        target_size = max(1, round(iw*template.scale_x)), max(1, round(ih*template.scale_y))
        if target_size not in resized:
            resized[target_size] = cv2.resize(full, target_size, interpolation=cv2.INTER_AREA)
        small = resized[target_size]
        sx, sy = target_size[0]/iw, target_size[1]/ih
        border_x, border_y = cw-1, ch-1
        padded = cv2.copyMakeBorder(small, border_y, border_y, border_x, border_x, cv2.BORDER_CONSTANT)
        valid = cv2.copyMakeBorder(np.ones(small.shape[:2], np.float32), border_y, border_y, border_x, border_x, cv2.BORDER_CONSTANT)
        scores, _ = _scores(padded, valid, template.coarse_color, template.coarse_mask, max(.1, min_visible-.08))
        radius = max(3, math.ceil(2/min(sx, sy)))
        for _ in range(candidates):
            minimum, _, location, _ = cv2.minMaxLoc(scores)
            # Coarse filtering is deliberately more tolerant; only native score accepts.
            if not math.isfinite(minimum) or minimum > max(.25, threshold*4):
                break
            cx, cy = location
            x, y = round((cx-border_x)/sx), round((cy-border_y)/sy)
            roi, inside = _window(full, x-radius, y-radius, w+2*radius, h+2*radius)
            fine, visible = _scores(roi, inside, template.color, template.mask, min_visible)
            score, _, point, _ = cv2.minMaxLoc(fine)
            if math.isfinite(score) and score <= threshold:
                px, py = point
                return Match(template.name, score, float(visible[py, px]), x-radius+px, y-radius+py)
            # Suppress this candidate neighborhood, not the whole possible icon.
            rx, ry = max(2, cw//8), max(2, ch//8)
            scores[max(0, cy-ry):cy+ry+1, max(0, cx-rx):cx+rx+1] = np.inf
    return None


def check_image_has_target(image_path, templates_folder, threshold=.15):
    image = read_image(image_path)
    if image is None:
        return False, None
    result = match_image(image, load_templates(templates_folder), threshold)
    if result:
        print(f'Found {result.name}: score={result.score:.4f}, visible={result.visible:.0%}')
        return True, result.name
    return False, None
