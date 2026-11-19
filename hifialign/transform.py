"""Rigid + smooth non-rigid transform between a round and the reference round.

Mapping (reference-global full-res pixel -> moving-global full-res pixel):

        M(x) = A · (x − D(x))

A is a 3x3 rigid matrix, D a smooth displacement field sampled on a regular grid
(reference-global coordinates, full-res pixels), bilinearly interpolated.
Without a field, M is just A.
"""
from __future__ import annotations

import cv2
import numpy as np
from scipy.ndimage import map_coordinates

from .sources import BBox


class Field:
    def __init__(self, x0: float, y0: float, step: float, dx: np.ndarray, dy: np.ndarray):
        self.x0, self.y0, self.step = float(x0), float(y0), float(step)
        self.dx = np.asarray(dx, np.float32)
        self.dy = np.asarray(dy, np.float32)

    @classmethod
    def zeros(cls, region: BBox, step: float) -> 'Field':
        nx = max(2, int(np.ceil(region.w / step)) + 1)
        ny = max(2, int(np.ceil(region.h / step)) + 1)
        # centre the grid on the region
        x0 = region.x + (region.w - (nx - 1) * step) / 2
        y0 = region.y + (region.h - (ny - 1) * step) / 2
        z = np.zeros((ny, nx), np.float32)
        return cls(x0, y0, step, z, z.copy())

    def nodes(self):
        ny, nx = self.dx.shape
        xs = self.x0 + np.arange(nx) * self.step
        ys = self.y0 + np.arange(ny) * self.step
        return np.meshgrid(xs, ys)

    def sample(self, x: np.ndarray, y: np.ndarray):
        gx = (np.asarray(x, np.float64) - self.x0) / self.step
        gy = (np.asarray(y, np.float64) - self.y0) / self.step
        c = np.array([gy.ravel(), gx.ravel()])
        dx = map_coordinates(self.dx, c, order=1, mode='nearest').reshape(np.shape(x))
        dy = map_coordinates(self.dy, c, order=1, mode='nearest').reshape(np.shape(x))
        return dx, dy

    def max_um(self, px_um: float) -> float:
        return float(np.hypot(self.dx - np.median(self.dx), self.dy - np.median(self.dy)).max() * px_um)

    def to_json(self):
        return dict(x0=self.x0, y0=self.y0, step=self.step, dx=np.round(self.dx, 3).tolist(),
                    dy=np.round(self.dy, 3).tolist())

    @classmethod
    def from_json(cls, d):
        return None if d is None else cls(d['x0'], d['y0'], d['step'], np.array(d['dx']), np.array(d['dy']))


class Transform:
    def __init__(self, A, field: Field | None = None):
        self.A = np.asarray(A, float)
        self.field = field

    # ---- (de)serialisation; a bare 3x3 list is accepted for backward compatibility
    def to_json(self):
        return {'A': self.A.tolist(), 'field': self.field.to_json() if self.field is not None else None}

    @classmethod
    def from_json(cls, d):
        if d is None:
            return None
        if isinstance(d, dict):
            return cls(d['A'], Field.from_json(d.get('field')))
        return cls(d)

    # ---- mapping
    def map(self, x: np.ndarray, y: np.ndarray):
        x = np.asarray(x, np.float64)
        y = np.asarray(y, np.float64)
        if self.field is not None:
            dx, dy = self.field.sample(x, y)
            x, y = x - dx, y - dy
        A = self.A
        return A[0, 0] * x + A[0, 1] * y + A[0, 2], A[1, 0] * x + A[1, 1] * y + A[1, 2]

    def _grid(self, out_origin, out_scale, out_shape, sub):
        h, w = out_shape
        us = np.append(np.arange(0, w, sub, dtype=np.float64), w - 1) if w > 1 else np.zeros(1)
        vs = np.append(np.arange(0, h, sub, dtype=np.float64), h - 1) if h > 1 else np.zeros(1)
        U, V = np.meshgrid(us, vs)
        return U, V, self.map(out_origin[0] + U / out_scale, out_origin[1] + V / out_scale)

    def source_region(self, out_origin, out_scale, out_shape, margin=4) -> BBox:
        """Moving-global bbox needed to compute an output block."""
        h, w = out_shape
        sub = max(16, int(max(h, w) / 32))
        _, _, (mx, my) = self._grid(out_origin, out_scale, out_shape, sub)
        x1, y1 = int(np.floor(mx.min())) - margin, int(np.floor(my.min())) - margin
        x2, y2 = int(np.ceil(mx.max())) + margin, int(np.ceil(my.max())) + margin
        return BBox(x1, y1, x2 - x1, y2 - y1)

    def warp(self, src_img, src_origin, src_scale, out_origin, out_scale, out_shape, interp=cv2.INTER_LINEAR):
        """Resample `src_img` (moving-global region starting at src_origin, sampled at src_scale) onto the
        output grid whose pixel (u, v) is the reference-global point out_origin + (u, v) / out_scale."""
        h, w = out_shape
        if self.field is None:
            from .registration import warp_into
            return warp_into(src_img, src_origin, src_scale, self.A, out_origin, out_scale, out_shape, interp)
        out = np.zeros((h, w), src_img.dtype)
        # cv2.remap needs blocks < 32767 px; the mapping is smooth so it is computed on a sub-grid
        # and bilinearly upsampled (exact for the affine part).
        B = 8192
        sub = 16
        for y0 in range(0, h, B):
            for x0 in range(0, w, B):
                bh, bw = min(B, h - y0), min(B, w - x0)
                o = (out_origin[0] + x0 / out_scale, out_origin[1] + y0 / out_scale)
                U, V, (mx, my) = self._grid(o, out_scale, (bh, bw), sub)
                sx = ((mx - src_origin[0]) * src_scale).astype(np.float32)
                sy = ((my - src_origin[1]) * src_scale).astype(np.float32)
                if sx.shape != (bh, bw):
                    # grid nodes are at 0, sub, 2sub, ..., last -> resize with corner alignment
                    sx = _upsample(sx, U[0], V[:, 0], bw, bh)
                    sy = _upsample(sy, U[0], V[:, 0], bw, bh)
                out[y0:y0 + bh, x0:x0 + bw] = cv2.remap(src_img, sx, sy, interp, borderMode=cv2.BORDER_CONSTANT,
                                                        borderValue=0)
        return out


def _upsample(g, us, vs, w, h):
    """Bilinear interpolation of grid values g (at columns us, rows vs) to every pixel of a w x h block."""
    xi = np.interp(np.arange(w), us, np.arange(len(us))).astype(np.float32)
    yi = np.interp(np.arange(h), vs, np.arange(len(vs))).astype(np.float32)
    mx, my = np.meshgrid(xi, yi)
    return cv2.remap(g.astype(np.float32), mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
