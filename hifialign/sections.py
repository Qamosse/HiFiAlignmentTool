"""Automatic detection of tissue sections on a low-resolution overview of the reference channel."""
from __future__ import annotations

import cv2
import numpy as np
from skimage.filters import threshold_otsu

from .project import SectionSpec
from .sources import BBox, ImageSource


def tissue_mask(img: np.ndarray, sigma_px: float = 2.0) -> np.ndarray:
    """Tissue vs glass. Works in log space so that dim and bright sections are both detected;
    pixels equal to 0 (not acquired) are ignored."""
    valid = img > 0
    f = img.astype(np.float32)
    if sigma_px > 0:
        f = cv2.GaussianBlur(f, (0, 0), sigma_px)
    v = f[valid]
    if v.size < 50:
        return np.zeros(img.shape, bool)
    bg = np.percentile(v, 2)
    g = np.log1p(np.maximum(f - bg, 0))
    try:
        t = threshold_otsu(g[valid])
    except ValueError:
        return np.zeros(img.shape, bool)
    return (g > t) & valid


def detect_sections(src: ImageSource, channel: int, min_area_mm2: float = 0.2,
                    padding_um: float = 150, merge_um: float = 300, max_dim: int = 4096,
                    pixel_size_um: float | None = None) -> tuple[list[SectionSpec], np.ndarray, float]:
    """Returns (sections in global full-res coordinates, overview image, overview scale).
    If the file has several acquisition regions (CZI scenes), each is thresholded on its own."""
    ov, scale = src.overview(channel, max_dim)
    px = pixel_size_um or src.pixel_size_um or 0.325
    px_ov = px / scale                        # µm per overview pixel
    sigma = max(1.0, 10 / px_ov)
    scenes = list(getattr(src, 'scenes', {}).values())
    if len(scenes) > 1:
        mask = np.zeros(ov.shape, bool)
        for sb in scenes:
            x1 = max(0, int((sb.x - src.bbox.x) * scale)); y1 = max(0, int((sb.y - src.bbox.y) * scale))
            x2 = min(ov.shape[1], int(np.ceil((sb.x2 - src.bbox.x) * scale)))
            y2 = min(ov.shape[0], int(np.ceil((sb.y2 - src.bbox.y) * scale)))
            if x2 > x1 and y2 > y1:
                mask[y1:y2, x1:x2] |= tissue_mask(ov[y1:y2, x1:x2], sigma)
    else:
        mask = tissue_mask(ov, sigma)
    # close gaps inside a section (merge fragments closer than merge_um)
    k = max(1, int(round(merge_um / px_ov)))
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * k + 1, 2 * k + 1))
    closed = cv2.morphologyEx(mask.astype(np.uint8), cv2.MORPH_CLOSE, kernel)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(closed, connectivity=8)
    min_area_px = min_area_mm2 * 1e6 / (px_ov ** 2)
    pad = int(round(padding_um / px_ov))
    boxes = []
    for i in range(1, n):
        x, y, w, h, area = stats[i]
        if area < min_area_px:
            continue
        boxes.append([x - pad, y - pad, x + w + pad, y + h + pad])
    boxes = _merge_overlapping(boxes)
    # sort left->right then top->bottom (reading order along the long axis)
    horizontal = ov.shape[1] >= ov.shape[0]
    boxes.sort(key=lambda b: (b[0], b[1]) if horizontal else (b[1], b[0]))
    sections = []
    for i, (x1, y1, x2, y2) in enumerate(boxes, 1):
        gx1 = src.bbox.x + int(np.floor(x1 / scale))
        gy1 = src.bbox.y + int(np.floor(y1 / scale))
        gx2 = src.bbox.x + int(np.ceil(x2 / scale))
        gy2 = src.bbox.y + int(np.ceil(y2 / scale))
        b = BBox(gx1, gy1, gx2 - gx1, gy2 - gy1).intersect(src.bbox)
        if b is not None:
            sections.append(SectionSpec(name=f'S{i:02d}', x=b.x, y=b.y, w=b.w, h=b.h))
    return sections, ov, scale


def _merge_overlapping(boxes):
    boxes = [list(b) for b in boxes]
    changed = True
    while changed:
        changed = False
        out = []
        while boxes:
            a = boxes.pop()
            i = 0
            while i < len(boxes):
                b = boxes[i]
                if a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]:
                    a = [min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3])]
                    boxes.pop(i)
                    changed = True
                else:
                    i += 1
            out.append(a)
        boxes = out
    return boxes
