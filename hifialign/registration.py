"""Registration of one round onto the reference round, for one region (section).

A transform maps *reference-global* full-res pixel coordinates to *moving-global*
ones (see transform.py): rigid matrix A + optional smooth displacement field.

Everything is done on modality-robust "structure" images (see `features`), because
DAPI may look very different between rounds (crisp nuclei vs. faded DAPI dominated by
tissue autofluorescence). Two representations are always tried and the best one kept:
'structure' (nuclei erased) and 'raw' (nuclei kept).

I/O strategy: the region is read ONCE per round at the working scale `sp`
(0.5 precise / 0.25 fast) and the feature images are computed once over the whole
region (in bands, to bound memory). The reference data is computed once per section
and shared between worker processes through memory-mapped files. Patches are then
just slices of these arrays.

Steps:
  1. coarse: template matching at low resolution inside a search window (+ rotation by
     pystackreg, kept only if it improves the match);
  2. rigid refinement: phase correlation on patches + robust (RANSAC) rigid fit;
  3. non-rigid (optional): local displacements measured on a regular grid, outliers
     rejected, gaps filled, smoothed -> displacement field.
"""
from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, field

import cv2
import numpy as np
from pystackreg import StackReg
from skimage.measure import ransac
from skimage.registration import phase_cross_correlation
from skimage.transform import EuclideanTransform

from .sources import BBox, ImageSource
from .transform import Field, Transform
from .i18n import tr

KINDS = ('structure', 'raw')


# ---------------------------------------------------------------------- matrices
def T(tx, ty):
    return np.array([[1, 0, tx], [0, 1, ty], [0, 0, 1]], float)


def S(s):
    return np.array([[s, 0, 0], [0, s, 0], [0, 0, 1]], float)


def apply(A, pts):
    pts = np.asarray(pts, float)
    return (A[:2, :2] @ pts.T).T + A[:2, 2]


def rotation_deg(A) -> float:
    return math.degrees(math.atan2(A[1, 0], A[0, 0]))


def warp_into(src_img, src_origin, src_scale, A, out_origin, out_scale, out_shape, interp=cv2.INTER_LINEAR):
    """Resample `src_img` (a region of the moving image whose top-left is `src_origin` in moving-global
    coords, sampled at `src_scale`) into an output grid whose pixel (u, v) is at reference-global
    out_origin + (u, v) / out_scale."""
    M = S(src_scale) @ T(-src_origin[0], -src_origin[1]) @ A @ T(out_origin[0], out_origin[1]) @ S(1 / out_scale)
    h, w = out_shape
    return cv2.warpAffine(src_img, M[:2], (w, h), flags=interp | cv2.WARP_INVERSE_MAP,
                          borderMode=cv2.BORDER_CONSTANT, borderValue=0)


def source_region_for(A, out_origin, out_scale, out_shape, margin=4) -> BBox:
    """Moving-global bbox needed to compute an output block (rigid case)."""
    h, w = out_shape
    corners = np.array([[0, 0], [w, 0], [0, h], [w, h]], float) / out_scale + np.asarray(out_origin, float)
    m = apply(A, corners)
    x1, y1 = np.floor(m.min(0)).astype(int) - margin
    x2, y2 = np.ceil(m.max(0)).astype(int) + margin
    return BBox(int(x1), int(y1), int(x2 - x1), int(y2 - y1))


# ---------------------------------------------------------------------- features
def _params(px_um, kind):
    s1 = max(0.7, (3.0 if kind == 'structure' else 1.0) / px_um)
    s2 = max(3 * s1, 40.0 / px_um)
    r = int(round(8.0 / px_um)) if kind == 'structure' else 0     # nucleus radius (opening)
    return s1, s2, r


def _blur(g, s):
    """Gaussian blur; large sigmas are computed on a downsampled image (much faster, same result)."""
    if s <= 8:
        return cv2.GaussianBlur(g, (0, 0), s)
    f = max(1, int(s / 4))
    h, w = g.shape
    small = cv2.resize(g, (max(1, w // f), max(1, h // f)), interpolation=cv2.INTER_AREA)
    small = cv2.GaussianBlur(small, (0, 0), s / f)
    return cv2.resize(small, (w, h), interpolation=cv2.INTER_LINEAR)


def _dog(img, px_um, kind):
    """Un-normalised band-pass of log intensity (+ nuclei erased for 'structure')."""
    s1, s2, r = _params(px_um, kind)
    f = img.astype(np.float32)
    if r >= 1:
        k = cv2.getStructuringElement(cv2.MORPH_RECT, (2 * r + 1, 2 * r + 1))
        f = cv2.morphologyEx(f, cv2.MORPH_OPEN, k)
    g = np.log1p(f)
    d = cv2.GaussianBlur(g, (0, 0), s1) - _blur(g, s2)
    valid = img > 0
    edge = cv2.erode(valid.astype(np.uint8), np.ones((3, 3), np.uint8), iterations=max(1, int(s2))) > 0
    return d, edge


def features(img: np.ndarray, px_um: float, kind: str = 'structure') -> np.ndarray:
    """Modality-robust structure image (small images; float32, 0 where not acquired)."""
    if (img > 0).sum() < 50:
        return np.zeros(img.shape, np.float32)
    d, edge = _dog(img, px_um, kind)
    v = d[edge]
    if v.size < 50:
        return np.zeros(img.shape, np.float32)
    med = float(np.median(v))
    mad = float(np.median(np.abs(v - med))) * 1.4826 + 1e-6
    out = np.clip((d - med) / mad, -4, 4).astype(np.float32)
    out[~edge] = 0
    return out


def features_large(img: np.ndarray, px_um: float, kind: str, band: int = 2048) -> np.ndarray:
    """Same as `features` for large images, computed in bands (bounded memory). Returns float16."""
    H, W = img.shape
    s1, s2, r = _params(px_um, kind)
    ov = int(3 * s2 + 2 * r + 8)
    out = np.empty((H, W), np.float16)
    samples = []
    rng = np.random.default_rng(0)
    for y0 in range(0, H, band):
        a, b = max(0, y0 - ov), min(H, y0 + band + ov)
        d, edge = _dog(img[a:b], px_um, kind)
        bh = min(band, H - y0)
        dc, ec = d[y0 - a:y0 - a + bh], edge[y0 - a:y0 - a + bh]
        dc = dc.copy()
        dc[~ec] = np.nan
        out[y0:y0 + bh] = dc
        v = dc[ec]
        if v.size:
            samples.append(rng.choice(v, min(v.size, 200000), replace=False))
    if not samples:
        out[:] = 0
        return out
    v = np.concatenate(samples)
    med = float(np.median(v))
    mad = float(np.median(np.abs(v - med))) * 1.4826 + 1e-6
    for y0 in range(0, H, band):
        x = out[y0:y0 + band].astype(np.float32)
        x = np.clip((x - med) / mad, -4, 4)
        x[np.isnan(x)] = 0
        out[y0:y0 + band] = x
    return out


def display_image(img: np.ndarray, px_um: float) -> np.ndarray:
    """Nuclei-free, log-scaled view in [0, 1] (for QC overlays)."""
    r = int(round(8.0 / px_um))
    f = img.astype(np.float32)
    if r >= 1:
        f = cv2.morphologyEx(f, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (2 * r + 1, 2 * r + 1)))
    g = np.log1p(f)
    v = g[img > 0]
    if v.size < 50:
        return np.zeros(img.shape, np.float32)
    lo, hi = np.percentile(v, [1, 99.5])
    return np.clip((g - lo) / max(hi - lo, 1e-6), 0, 1).astype(np.float32)


def overlay(ref: np.ndarray, mov: np.ndarray, px_um: float = 1.0) -> np.ndarray:
    r = (display_image(ref, px_um) * 255).astype(np.uint8)
    g = (display_image(mov, px_um) * 255).astype(np.uint8)
    return np.dstack([r, g, r])


def ncc(a: np.ndarray, b: np.ndarray, mask: np.ndarray | None = None) -> float:
    a = a.astype(np.float64)
    b = b.astype(np.float64)
    if mask is not None:
        a, b = a[mask], b[mask]
    else:
        a, b = a.ravel(), b.ravel()
    if a.size < 10:
        return float('nan')
    a = a - a.mean()
    b = b - b.mean()
    d = math.sqrt((a * a).sum() * (b * b).sum())
    return float((a * b).sum() / d) if d > 0 else float('nan')


# ---------------------------------------------------------------------- preloaded region
class Preloaded:
    """One channel of a region, read once at scale `sp`, with its feature images."""

    def __init__(self, box: BBox, sp: float, px_full: float, img, feats: dict):
        self.box, self.sp, self.px_full = box, sp, px_full
        self.px = px_full / sp
        self.img = img
        self.feat = feats

    @classmethod
    def read(cls, src: ImageSource, ch: int, box: BBox, sp: float, px_full: float) -> 'Preloaded':
        img = src.read(ch, box, sp)
        feats = {k: features_large(img, px_full / sp, k) for k in KINDS}
        return cls(box, sp, px_full, img, feats)

    # -- sharing between processes through .npy files (memory-mapped, shared page cache)
    def save(self, d: str):
        os.makedirs(d, exist_ok=True)
        np.save(os.path.join(d, 'img.npy'), self.img)
        for k, f in self.feat.items():
            np.save(os.path.join(d, f'feat_{k}.npy'), f)
        with open(os.path.join(d, 'meta.json'), 'w') as fh:
            json.dump(dict(box=self.box.to_list(), sp=self.sp, px_full=self.px_full), fh)

    @classmethod
    def load(cls, d: str) -> 'Preloaded':
        with open(os.path.join(d, 'meta.json')) as fh:
            m = json.load(fh)
        img = np.load(os.path.join(d, 'img.npy'), mmap_mode='r')
        feats = {k: np.load(os.path.join(d, f'feat_{k}.npy'), mmap_mode='r') for k in KINDS}
        return cls(BBox(*m['box']), m['sp'], m['px_full'], img, feats)

    # -- geometry
    def origin(self, i0, j0):
        return (self.box.x + j0 / self.sp, self.box.y + i0 / self.sp)

    def crop(self, arr, gbox: BBox, dtype=np.float32):
        """Crop `arr` (img or a feature image) over a global box, zero-padded. Returns (array, origin)."""
        i0 = int(math.floor((gbox.y - self.box.y) * self.sp))
        j0 = int(math.floor((gbox.x - self.box.x) * self.sp))
        i1 = int(math.ceil((gbox.y2 - self.box.y) * self.sp))
        j1 = int(math.ceil((gbox.x2 - self.box.x) * self.sp))
        out = np.zeros((max(1, i1 - i0), max(1, j1 - j0)), dtype)
        H, W = arr.shape
        a0, b0, a1, b1 = max(0, i0), max(0, j0), min(H, i1), min(W, j1)
        if a1 > a0 and b1 > b0:
            out[a0 - i0:a1 - i0, b0 - j0:b1 - j0] = arr[a0:a1, b0:b1]
        return out, self.origin(i0, j0)

    def lowres(self, gbox: BBox, scale: float):
        """uint16 image of a global box at a coarser scale (area interpolation). Returns (img, origin, scale)."""
        img, o = self.crop(self.img, gbox, np.uint16)
        f = scale / self.sp
        h, w = max(1, int(round(img.shape[0] * f))), max(1, int(round(img.shape[1] * f)))
        small = cv2.resize(img, (w, h), interpolation=cv2.INTER_AREA)
        return small, o, w / img.shape[1] * self.sp


# ---------------------------------------------------------------------- results
@dataclass
class RegistrationResult:
    matrix: list                    # 3x3 rigid part (ref-global -> moving-global)
    ncc_before: float = float('nan')
    ncc_after: float = float('nan')
    n_patches: int = 0
    n_inliers: int = 0
    residual_px: float = float('nan')   # RMS residual of the rigid fit (full-res px)
    shift_px: tuple = (0.0, 0.0)
    rotation_deg: float = 0.0
    warnings: list = field(default_factory=list)
    transform: dict | None = None        # Transform.to_json() (rigid + optional field)
    field_nodes: int = 0                 # grid nodes on tissue
    field_valid: int = 0                 # nodes with a reliable local measurement
    deform_max_um: float = 0.0           # largest local deformation corrected (µm)
    local_resid_um: float = float('nan') # median local residual at the last iteration (µm)
    qc_before: np.ndarray | None = None  # RGB uint8 overlays (ref = magenta, moving = green)
    qc_after: np.ndarray | None = None


def working_scale(opts) -> float:
    return 0.25 if opts.mode == 'fast' else float(opts.fast_scale)


def ref_box_for(region: BBox, opts, pixel_size_um: float) -> BBox:
    pad = int(max(opts.patch_size * 2, opts.field_patch_um / pixel_size_um))
    return region.expand(pad)


def mov_box_for(region: BBox, opts, pixel_size_um: float) -> BBox:
    pad = int(max(opts.patch_size * 2, opts.field_patch_um / pixel_size_um))
    return region.expand(int(round(opts.search_margin_um / pixel_size_um)) + pad)


def estimate_job_bytes(region: BBox, opts, pixel_size_um: float) -> float:
    """Rough peak memory of one registration job (moving round preloaded + reference memmapped)."""
    sp = working_scale(opts)
    mb = mov_box_for(region, opts, pixel_size_um)
    n = mb.w * mb.h * sp * sp
    return n * (2 + 2 * 2) + 6 * 2048 * mb.w * sp * 4 + 3e8


# ---------------------------------------------------------------------- main entry
def register_region(ref: Preloaded, mov: Preloaded, region: BBox, opts, pixel_size_um: float,
                    qc_max_dim: int = 1200) -> RegistrationResult:
    """Register the moving round onto the reference over `region` (reference-global coords)."""
    warnings = []
    fast = opts.mode == 'fast'
    sp = ref.sp
    # ---- 1. coarse ---------------------------------------------------------------
    s = min(sp, opts.coarse_scale)
    s = min(sp, max(s, 300 / max(region.w, region.h)))
    if max(region.w, region.h) * s > 2500:
        s = 2500 / max(region.w, region.h)
    margin = int(round(opts.search_margin_um / pixel_size_um))
    win = region.expand(margin)
    ref_lr, ro, s_r = ref.lowres(region, s)
    mov_lr, mo, s_m = mov.lowres(win, s)
    px_lr = pixel_size_um / s_r
    best = None
    for kind in KINDS:
        fa, fb = features(ref_lr, px_lr, kind), features(mov_lr, px_lr, kind)
        th, tw = fa.shape
        if fb.shape[0] < th or fb.shape[1] < tw:
            fb = cv2.copyMakeBorder(fb, 0, max(0, th - fb.shape[0]), 0, max(0, tw - fb.shape[1]),
                                    cv2.BORDER_CONSTANT, 0)
        res = cv2.matchTemplate(fb, fa, cv2.TM_CCOEFF_NORMED)
        _, p1, _, loc = cv2.minMaxLoc(res)
        r2 = res.copy()
        cv2.circle(r2, loc, max(3, int(60 / px_lr)), -1.0, -1)
        p2 = float(r2.max())
        if best is None or (p1 - p2) > best[0]:
            best = (p1 - p2, kind, fa, fb, p1, loc)
    _, coarse_kind, a, b, score, (px, py) = best
    th, tw = a.shape
    A = T(mo[0] + px / s_m - ro[0], mo[1] + py / s_m - ro[1])
    if score < 0.1:
        warnings.append(tr('Recalage grossier peu fiable (corrélation {score:.2f}).', score=score))
    if opts.use_rotation:
        crop = b[py:py + th, px:px + tw]
        try:
            tm = StackReg(StackReg.RIGID_BODY).register(a, crop)     # ref_lr coords -> crop coords
            cand = T(mo[0] + px / s_m, mo[1] + py / s_m) @ S(1 / s_m) @ tm @ S(s_r) @ T(-ro[0], -ro[1])

            def score_of(M):
                w = warp_into(b, mo, s_m, M, ro, s_r, a.shape)
                return ncc(a, w, (a != 0) & (w != 0))
            # keep the rotation only if it really improves the match (pystackreg can be trapped by the
            # tile-shading grid, which is identical in every round)
            if abs(rotation_deg(cand)) < 20 and score_of(cand) > score_of(A) + 0.005:
                A = cand
        except Exception as e:  # pragma: no cover
            warnings.append(tr('pystackreg a échoué : {e}', e=e))

    tissue_lr = np.abs(features(ref_lr, px_lr, 'structure')) + np.abs(features(ref_lr, px_lr, 'raw'))

    # ---- 2. rigid refinement -------------------------------------------------------
    A, n_patches, n_inliers, resid, w = _refine_rigid(ref, mov, region, A, opts, tissue_lr, s_r, pixel_size_um)
    warnings += w

    # ---- 3. non-rigid --------------------------------------------------------------
    xf = Transform(A)
    fstats = dict(nodes=0, valid=0, resid=float('nan'))
    if opts.nonrigid:
        spacing = opts.grid_spacing_um * (2 if fast else 1) / pixel_size_um
        for _ in range(1 if fast else 2):
            xf, fstats = _estimate_field(ref, mov, region, xf, spacing, opts.field_patch_um / pixel_size_um,
                                         pixel_size_um, tissue_lr, s_r)
        if fstats['nodes'] and fstats['valid'] < 0.3 * fstats['nodes']:
            warnings.append(tr('Déformation locale : seulement {v}/{n} points fiables.', v=fstats['valid'], n=fstats['nodes']))

    # ---- 4. QC -------------------------------------------------------------------
    sq = min(sp, qc_max_dim / max(region.w, region.h))
    ref_q, rqo, sq_r = ref.lowres(region, sq)
    before, _, _ = mov.lowres(region, sq)
    before = cv2.resize(before, (ref_q.shape[1], ref_q.shape[0]), interpolation=cv2.INTER_AREA)
    # moving image at ~2x the QC scale, then warped (limits aliasing)
    gb = xf.source_region(rqo, sq_r, ref_q.shape, margin=int(8 / sq_r))
    mov_q, mqo, sq_m = mov.lowres(gb, min(sp, 2 * sq_r))
    after = xf.warp(mov_q, mqo, sq_m, rqo, sq_r, ref_q.shape)
    pq = pixel_size_um / sq_r
    nb, na = [], []
    for kind in KINDS:
        fr, fb_, fa_ = features(ref_q, pq, kind), features(before, pq, kind), features(after, pq, kind)
        mask = (fr != 0) & (fb_ != 0) & (fa_ != 0)
        nb.append(ncc(fr, fb_, mask))
        na.append(ncc(fr, fa_, mask))
    k = int(np.nanargmax(na)) if np.any(np.isfinite(na)) else 0
    result = RegistrationResult(
        matrix=A.tolist(), ncc_before=nb[k], ncc_after=na[k],
        n_patches=n_patches, n_inliers=n_inliers, residual_px=resid,
        shift_px=(float(A[0, 2] + A[0, 0] * region.x + A[0, 1] * region.y - region.x),
                  float(A[1, 2] + A[1, 0] * region.x + A[1, 1] * region.y - region.y)),
        rotation_deg=rotation_deg(A), warnings=warnings, transform=xf.to_json(),
        field_nodes=fstats['nodes'], field_valid=fstats['valid'],
        deform_max_um=xf.field.max_um(pixel_size_um) if xf.field is not None else 0.0,
        local_resid_um=fstats['resid'] * pixel_size_um,
        qc_before=overlay(ref_q, before, pq), qc_after=overlay(ref_q, after, pq))
    if not result.ncc_after >= 0.25:
        result.warnings.append(tr('Corrélation de structure faible après recalage ({v:.2f}) : à vérifier.', v=result.ncc_after))
    return result


# ---------------------------------------------------------------------- patches
def _pick_patch_centers(tissue_lr: np.ndarray, s: float, region: BBox, patch_full: float, n: int) -> list:
    """Choose up to n patch centres (reference-global coords) on structured tissue, spread over the section."""
    f = tissue_lr
    ph = max(4, int(patch_full * s))
    cands = []
    step = max(ph // 3, 2)
    for y in range(0, max(1, f.shape[0] - ph + 1), step):
        for x in range(0, max(1, f.shape[1] - ph + 1), step):
            blk = f[y:y + ph, x:x + ph]
            if (blk == 0).mean() > 0.3:          # mostly outside the image
                continue
            cands.append((float(blk.mean()), x + ph / 2, y + ph / 2))
    if not cands:
        return []
    vals = np.array([c[0] for c in cands])
    thr = max(0.3 * float(np.percentile(vals, 95)), 1e-4)
    cands = sorted([c for c in cands if c[0] >= thr], reverse=True)
    chosen = []
    min_d = ph * 0.6
    for sc, x, y in cands:
        if all((x - cx) ** 2 + (y - cy) ** 2 >= min_d ** 2 for _, cx, cy in chosen):
            chosen.append((sc, x, y))
        if len(chosen) >= n:
            break
    return [(region.x + x / s, region.y + y / s) for _, x, y in chosen]


def _local_shift(ref_feat, mov_feat):
    """Phase-correlation shift (dx, dy) in sampled px and match quality."""
    win = np.outer(np.hanning(ref_feat.shape[0]), np.hanning(ref_feat.shape[1])).astype(np.float32)
    try:
        shift, _, _ = phase_cross_correlation(ref_feat * win, mov_feat * win, upsample_factor=20,
                                              normalization=None)
    except Exception:
        return None
    dy, dx = shift
    if abs(dx) > ref_feat.shape[1] / 3 or abs(dy) > ref_feat.shape[0] / 3:
        return None
    Ms = np.float32([[1, 0, -dx], [0, 1, -dy]])
    b2 = cv2.warpAffine(mov_feat, Ms, (mov_feat.shape[1], mov_feat.shape[0]),
                        flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP)
    q = ncc(ref_feat, b2, (ref_feat != 0) & (b2 != 0))
    return dx, dy, q


def _measure(ref: Preloaded, mov: Preloaded, xf: Transform, cx: float, cy: float, n: int):
    """Residual shift of the patch centred on (cx, cy): returns (centre, dx_full, dy_full, q) or None."""
    sp = ref.sp
    i0 = int(round((cy - ref.box.y) * sp)) - n // 2
    j0 = int(round((cx - ref.box.x) * sp)) - n // 2
    H, W = ref.img.shape
    if i0 < 0 or j0 < 0 or i0 + n > H or j0 + n > W:
        return None
    if (np.asarray(ref.img[i0:i0 + n, j0:j0 + n]) == 0).mean() > 0.3:
        return None
    o = ref.origin(i0, j0)
    gb = xf.source_region(o, sp, (n, n), margin=int(8 / sp) + 2)
    best = None
    for kind in KINDS:
        fa = np.asarray(ref.feat[kind][i0:i0 + n, j0:j0 + n], np.float32)
        crop, oc = mov.crop(mov.feat[kind], gb)
        w = xf.warp(crop, oc, mov.sp, o, sp, (n, n))
        if (w == 0).mean() > 0.3:
            return None
        m = _local_shift(fa, w)
        if m is not None and np.isfinite(m[2]) and (best is None or m[2] > best[2]):
            best = m
    if best is None:
        return None
    centre = np.array([o[0] + n / (2 * sp), o[1] + n / (2 * sp)])
    return centre, best[0] / sp, best[1] / sp, best[2]


def _refine_rigid(ref, mov, region, A, opts, tissue_lr, s_lr, pixel_size_um):
    warnings = []
    sp = ref.sp
    patch_full = min(float(opts.patch_size) * 2.0, 0.5 * min(region.w, region.h))
    n = max(32, int(patch_full * sp))
    centers = _pick_patch_centers(tissue_lr, s_lr, region, patch_full, opts.max_patches)
    xf = Transform(A)
    src_pts, dst_pts = [], []
    for cx, cy in centers:
        m = _measure(ref, mov, xf, cx, cy, n)
        if m is None or m[3] < 0.15:
            continue
        c, dx, dy, _ = m
        src_pts.append(c)
        dst_pts.append(apply(A, [c - np.array([dx, dy])])[0])
    k = len(src_pts)
    if k < 3:
        warnings.append(tr('Affinage rigide : seulement {k} patch(s) exploitable(s), recalage grossier conservé.', k=k))
        return A, k, 0, float('nan'), warnings
    src_pts, dst_pts = np.array(src_pts), np.array(dst_pts)
    # tolerance: 3 sampled px and some µm (tissue deforms between rounds; the field handles the rest)
    thr = max(3.0 / sp, (25.0 if opts.nonrigid else 8.0) / pixel_size_um)
    if opts.use_rotation:
        model, inl = ransac((src_pts, dst_pts), EuclideanTransform, min_samples=2,
                            residual_threshold=thr, max_trials=1000, rng=0)
        if model is None or inl is None or inl.sum() < 3:
            warnings.append(tr('Affinage rigide : ajustement robuste impossible, recalage grossier conservé.'))
            return A, k, 0, float('nan'), warnings
        model.estimate(src_pts[inl], dst_pts[inl])
        A_new = np.array(model.params, float)
    else:
        d = dst_pts - src_pts
        inl = np.linalg.norm(d - np.median(d, axis=0), axis=1) < thr
        if inl.sum() < 3:
            warnings.append(tr('Affinage rigide : trop peu de patchs concordants.'))
            return A, k, 0, float('nan'), warnings
        t = d[inl].mean(0)
        A_new = T(t[0], t[1])
    res = np.linalg.norm(apply(A_new, src_pts[inl]) - dst_pts[inl], axis=1)
    return A_new, k, int(inl.sum()), float(np.sqrt((res ** 2).mean())), warnings


# ---------------------------------------------------------------------- non-rigid field
def _estimate_field(ref, mov, region, xf: Transform, spacing, patch_full, px_um, tissue_lr, s_lr,
                    qmin=0.25, tol_um=3.0):
    """One iteration: measure residual local shifts on the grid, clean them, add them to the field."""
    fld = xf.field or Field.zeros(region, spacing)
    X, Y = fld.nodes()
    ny, nx = X.shape
    rx = np.full((ny, nx), np.nan)
    ry = np.full((ny, nx), np.nan)
    n = max(32, int(patch_full * ref.sp))
    # nodes on tissue (structure present in the low-res reference)
    ph = max(3, int(patch_full * s_lr))
    means = np.zeros((ny, nx))
    for j in range(ny):
        for i in range(nx):
            x = int((X[j, i] - region.x) * s_lr - ph / 2)
            y = int((Y[j, i] - region.y) * s_lr - ph / 2)
            blk = tissue_lr[max(0, y):max(0, y + ph), max(0, x):max(0, x + ph)]
            if blk.size and (blk != 0).mean() > 0.5:
                means[j, i] = blk.mean()
    thr = 0.3 * np.percentile(means[means > 0], 95) if np.any(means > 0) else np.inf
    tissue = means >= thr
    for j in range(ny):
        for i in range(nx):
            if not tissue[j, i]:
                continue
            m = _measure(ref, mov, xf, X[j, i], Y[j, i], n)
            if m is None or m[3] < qmin:
                continue
            rx[j, i], ry[j, i] = m[1], m[2]
    n_tissue = int(tissue.sum())
    # outlier rejection: each measurement vs. the median of its valid neighbours (or of all nodes when
    # isolated); the tolerance adapts to how much the measurements really vary (min. tol_um µm)
    valid = np.isfinite(rx)
    dev = np.full((ny, nx), np.nan)
    gmx, gmy = (np.nanmedian(rx), np.nanmedian(ry)) if valid.any() else (0.0, 0.0)
    isolated = np.zeros((ny, nx), bool)
    for j in range(ny):
        for i in range(nx):
            if not valid[j, i]:
                continue
            nb = [(jj, ii) for jj in range(j - 1, j + 2) for ii in range(i - 1, i + 2)
                  if (jj, ii) != (j, i) and 0 <= jj < ny and 0 <= ii < nx and valid[jj, ii]]
            if len(nb) >= 2:
                mx = np.median([rx[q] for q in nb])
                my = np.median([ry[q] for q in nb])
            else:
                mx, my = gmx, gmy
                isolated[j, i] = True
            dev[j, i] = np.hypot(rx[j, i] - mx, ry[j, i] - my)
    spread = 1.4826 * np.nanmedian(dev) if np.isfinite(dev).any() else 0.0
    tol = max(tol_um / px_um, 3.0 * spread)
    keep = valid & (dev <= np.where(isolated, 2 * tol, tol))
    rx[~keep] = np.nan
    ry[~keep] = np.nan
    n_valid = int(keep.sum())
    resid = float(np.nanmedian(np.hypot(rx, ry))) if n_valid else float('nan')
    if n_valid == 0:
        return xf, dict(nodes=n_tissue, valid=0, resid=resid)
    rx, ry = _fill(rx), _fill(ry)
    if ny >= 3 and nx >= 3:
        rx = cv2.GaussianBlur(rx.astype(np.float32), (3, 3), 0.7, borderType=cv2.BORDER_REPLICATE)
        ry = cv2.GaussianBlur(ry.astype(np.float32), (3, 3), 0.7, borderType=cv2.BORDER_REPLICATE)
    new = Field(fld.x0, fld.y0, fld.step, fld.dx + rx, fld.dy + ry)
    return Transform(xf.A, new), dict(nodes=n_tissue, valid=n_valid, resid=resid)


def _fill(g):
    """Fill NaNs by repeatedly averaging valid 8-neighbours (smooth extrapolation from measured nodes)."""
    g = g.astype(np.float64).copy()
    if np.all(np.isnan(g)):
        return np.zeros_like(g)
    while np.isnan(g).any():
        nan = np.isnan(g)
        p = np.pad(g, 1, constant_values=np.nan)
        stack = np.stack([p[dy:dy + g.shape[0], dx:dx + g.shape[1]]
                          for dy in range(3) for dx in range(3) if (dy, dx) != (1, 1)])
        cnt = np.sum(~np.isnan(stack), 0)
        mean = np.nansum(stack, 0) / np.maximum(cnt, 1)
        upd = nan & (cnt > 0)
        g[upd] = mean[upd]
    return g
