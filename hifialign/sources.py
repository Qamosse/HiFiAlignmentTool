"""Lazy, region-based access to multiplex round images (CZI or TIFF).

All coordinates are *global full-resolution pixel coordinates* of the file:
for CZI this is the mosaic coordinate system (which may not start at 0,0),
for TIFF it is simply (0, 0, width, height).

Nothing here ever loads a whole slide in memory: every read is a region,
optionally downscaled.
"""
from __future__ import annotations

import os
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass

import cv2
import numpy as np


@dataclass(frozen=True)
class BBox:
    x: int
    y: int
    w: int
    h: int

    @property
    def x2(self) -> int:
        return self.x + self.w

    @property
    def y2(self) -> int:
        return self.y + self.h

    def intersect(self, other: "BBox") -> "BBox | None":
        x1, y1 = max(self.x, other.x), max(self.y, other.y)
        x2, y2 = min(self.x2, other.x2), min(self.y2, other.y2)
        if x2 <= x1 or y2 <= y1:
            return None
        return BBox(x1, y1, x2 - x1, y2 - y1)

    def expand(self, m: int) -> "BBox":
        return BBox(self.x - m, self.y - m, self.w + 2 * m, self.h + 2 * m)

    def to_list(self):
        return [int(self.x), int(self.y), int(self.w), int(self.h)]


def _scaled_shape(w: int, h: int, scale: float) -> tuple[int, int]:
    return max(1, int(round(h * scale))), max(1, int(round(w * scale)))


class ImageSource:
    """Common interface. Subclasses implement _read_inside()."""

    path: str
    channels: list[str]
    pixel_size_um: float | None
    bbox: BBox
    dtype = np.uint16

    def channel_index(self, name: str) -> int:
        from .naming import find_channel
        try:
            return find_channel(self.channels, name)
        except KeyError as e:
            raise KeyError(f'{os.path.basename(self.path)} : {e.args[0]}') from None

    # -- public -----------------------------------------------------------
    def read(self, channel: int, region: BBox | None = None, scale: float = 1.0) -> np.ndarray:
        """Read one channel over `region` (global coords), zero-padded outside the image,
        resampled by `scale` (<=1). Returns a 2D uint16 array of shape round(h*scale), round(w*scale)."""
        region = region or self.bbox
        out_h, out_w = _scaled_shape(region.w, region.h, scale)
        inside = region.intersect(self.bbox)
        if inside is None:
            return np.zeros((out_h, out_w), self.dtype)
        if inside == region:
            img = self._read_inside(channel, region, scale)
            if img.shape != (out_h, out_w):
                img = cv2.resize(img, (out_w, out_h), interpolation=cv2.INTER_AREA)
            return img
        # partially outside: read the inside part and paste it into a zero canvas
        canvas = np.zeros((out_h, out_w), self.dtype)
        ox = int(round((inside.x - region.x) * scale))
        oy = int(round((inside.y - region.y) * scale))
        ph, pw = _scaled_shape(inside.w, inside.h, scale)
        ph, pw = min(ph, out_h - oy), min(pw, out_w - ox)
        if ph <= 0 or pw <= 0:
            return canvas
        part = self._read_inside(channel, inside, scale)
        if part.shape != (ph, pw):
            part = cv2.resize(part, (pw, ph), interpolation=cv2.INTER_AREA)
        canvas[oy:oy + ph, ox:ox + pw] = part
        return canvas

    def overview(self, channel: int, max_dim: int = 2048) -> tuple[np.ndarray, float]:
        """Low-resolution view of the whole image. Returns (image, scale)."""
        scale = min(1.0, max_dim / max(self.bbox.w, self.bbox.h))
        return self.read(channel, self.bbox, scale), scale

    def has_data(self, region: BBox) -> bool:
        """True if the file has acquired pixels inside `region` (mosaic scenes are taken into account)."""
        boxes = list(getattr(self, 'scenes', {}).values()) or [self.bbox]
        return any(b.intersect(region) is not None for b in boxes)

    def info(self) -> dict:
        return dict(path=self.path, channels=list(self.channels), pixel_size_um=self.pixel_size_um,
                    bbox=self.bbox.to_list())

    def close(self):
        pass

    def _read_inside(self, channel: int, region: BBox, scale: float) -> np.ndarray:
        raise NotImplementedError


class CziSource(ImageSource):
    def __init__(self, path: str):
        import aicspylibczi
        self.path = os.path.abspath(path)
        self._czi = aicspylibczi.CziFile(self.path)
        dims = self._czi.get_dims_shape()[0]
        if 'C' not in dims:
            raise ValueError(f'{path}: image has no channel dimension')
        n_c = dims['C'][1] - dims['C'][0]
        meta = self._czi.meta
        names = [ch.get('Name') or ch.get('Id') for ch in
                 meta.findall('.//Metadata/Information/Image/Dimensions/Channels/Channel')]
        if len(names) != n_c:
            names = [f'C{i}' for i in range(n_c)]
        self.channels = names
        self.pixel_size_um = None
        for d in meta.findall('.//Metadata/Scaling/Items/Distance'):
            if d.get('Id') == 'X' and d.find('Value') is not None:
                self.pixel_size_um = float(d.find('Value').text) * 1e6
        self.is_mosaic = self._czi.is_mosaic()
        if self.is_mosaic:
            bb = self._czi.get_mosaic_bounding_box()
            self.bbox = BBox(bb.x, bb.y, bb.w, bb.h)
        else:
            self.bbox = BBox(0, 0, dims['X'][1], dims['Y'][1])
        self.scenes: dict[int, BBox] = {}
        if self.is_mosaic:
            try:
                for k, bb in self._czi.get_all_mosaic_scene_bounding_boxes().items():
                    self.scenes[int(k)] = BBox(bb.x, bb.y, bb.w, bb.h)
            except Exception:
                pass

    def _read_inside(self, channel, region, scale):
        if self.is_mosaic:
            img = self._czi.read_mosaic(region=(region.x, region.y, region.w, region.h),
                                        scale_factor=scale, C=channel)
            img = np.squeeze(img)
        else:
            img, _ = self._czi.read_image(C=channel)
            img = np.squeeze(img)[region.y - self.bbox.y:region.y2 - self.bbox.y,
                                  region.x - self.bbox.x:region.x2 - self.bbox.x]
            if scale != 1.0:
                h, w = _scaled_shape(region.w, region.h, scale)
                img = cv2.resize(img, (w, h), interpolation=cv2.INTER_AREA)
        if img.dtype != np.uint16:
            img = np.clip(img, 0, 65535).astype(np.uint16)
        return np.ascontiguousarray(img)


class TiffSource(ImageSource):
    """(Multi-channel) TIFF / OME-TIFF, axes C,Y,X (pyramidal levels are used for overviews)."""

    def __init__(self, path: str):
        import tifffile
        import zarr
        self.path = os.path.abspath(path)
        self._tif = tifffile.TiffFile(self.path)
        series = self._tif.series[0]
        axes = series.axes.upper()
        if not set('YX') <= set(axes):
            raise ValueError(f'{path}: unsupported axes {axes}')
        z = zarr.open(series.aszarr(), mode='r')
        if isinstance(z, zarr.Array):
            self._levels = [z]
        else:  # multiscale group: '0', '1', ...
            self._levels = [z[str(i)] for i in range(len(series.levels))]
        self._axes = axes
        shape = series.shape
        h, w = shape[axes.index('Y')], shape[axes.index('X')]
        n_c = shape[axes.index('C')] if 'C' in axes else (shape[axes.index('S')] if 'S' in axes else 1)
        self.bbox = BBox(0, 0, w, h)
        self.channels, self.pixel_size_um = self._parse_meta(n_c)

    def _parse_meta(self, n_c):
        names, px = [], None
        ome = self._tif.ome_metadata
        if ome:
            try:
                root = ET.fromstring(ome)
                ns = {'o': root.tag.split('}')[0].strip('{')} if root.tag.startswith('{') else {}
                pix = root.find('.//o:Pixels', ns) if ns else root.find('.//Pixels')
                if pix is not None:
                    if pix.get('PhysicalSizeX'):
                        px = float(pix.get('PhysicalSizeX'))
                        unit = pix.get('PhysicalSizeXUnit', 'µm')
                        px *= {'nm': 1e-3, 'mm': 1e3, 'm': 1e6}.get(unit, 1.0)
                    chans = pix.findall('o:Channel', ns) if ns else pix.findall('Channel')
                    names = [(c.get('Name') or '').strip() for c in chans]
            except ET.ParseError:
                pass
        if px is None:
            try:
                page = self._tif.pages[0]
                xres = page.tags.get('XResolution')
                unit = page.tags.get('ResolutionUnit')
                if xres and unit and unit.value in (2, 3):
                    num, den = xres.value
                    ppu = num / den
                    if ppu > 1:
                        px = (25400.0 if unit.value == 2 else 10000.0) / ppu
            except Exception:
                pass
        if len(names) != n_c or not all(names):
            names = [f'C{i}' for i in range(n_c)]
        # make names unique
        seen = {}
        for i, n in enumerate(names):
            if n in seen:
                seen[n] += 1
                names[i] = f'{n}_{seen[n]}'
            else:
                seen[n] = 0
        return names, px

    def _slice(self, arr, channel, y0, y1, x0, x1, step=1):
        idx = []
        for ax in self._axes:
            if ax == 'Y':
                idx.append(slice(y0, y1, step))
            elif ax == 'X':
                idx.append(slice(x0, x1, step))
            elif ax in 'CS':
                idx.append(channel)
            else:
                idx.append(0)
        return np.asarray(arr[tuple(idx)])

    def _read_inside(self, channel, region, scale):
        # choose the coarsest pyramid level that is still >= requested resolution
        lvl_i, lvl_scale = 0, 1.0
        full_w = self.bbox.w
        for i, lv in enumerate(self._levels):
            s = lv.shape[self._axes.index('X')] / full_w
            if s >= scale * 0.999:
                lvl_i, lvl_scale = i, s
        arr = self._levels[lvl_i]
        x0, y0 = int(np.floor(region.x * lvl_scale)), int(np.floor(region.y * lvl_scale))
        x1, y1 = int(np.ceil(region.x2 * lvl_scale)), int(np.ceil(region.y2 * lvl_scale))
        img = self._slice(arr, channel, y0, y1, x0, x1)
        h, w = _scaled_shape(region.w, region.h, scale)
        if img.shape != (h, w):
            img = cv2.resize(img, (w, h), interpolation=cv2.INTER_AREA if scale < lvl_scale else cv2.INTER_LINEAR)
        if img.dtype != np.uint16:
            img = np.clip(img, 0, 65535).astype(np.uint16)
        return np.ascontiguousarray(img)

    def close(self):
        self._tif.close()


def open_source(path: str) -> ImageSource:
    ext = path.lower()
    if ext.endswith('.czi'):
        return CziSource(path)
    if ext.endswith(('.tif', '.tiff')):
        return TiffSource(path)
    raise ValueError(f'Unsupported file type: {path}')


SUPPORTED_EXT = ('.czi', '.tif', '.tiff')


def round_label_from_path(path: str) -> str:
    name = os.path.basename(path)
    name = re.sub(r'\.ome\.tiff?$', '', name, flags=re.I)
    return os.path.splitext(name)[0]
