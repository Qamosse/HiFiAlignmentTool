"""End-to-end processing: validation -> registration -> warping -> pyramidal OME-TIFF.

Heavy work runs in a pool of worker *processes* (one job = one section x round
registration, or one output strip of one channel). Every job reads only the
region it needs, so memory stays bounded whatever the slide size. Warped strips
are written into a temporary memory-mapped file on a local disk, which is then
written out as a tiled, compressed, pyramidal OME-TIFF (multithreaded).
"""
from __future__ import annotations

import concurrent.futures as cf
import csv
import json
import math
import multiprocessing as mp
import os
import shutil
import threading
import time
import uuid
from dataclasses import dataclass

import cv2
import numpy as np

from .naming import channel_matches
from .project import Project, RegistrationOptions, SectionSpec
from .registration import (Preloaded, RegistrationResult, estimate_job_bytes, mov_box_for, ref_box_for,
                           register_region, working_scale)
from .transform import Transform
from .sources import BBox, open_source
from .i18n import tr


class Cancelled(Exception):
    pass


# ============================================================================ worker side
_SOURCES: dict = {}


def _worker_init():
    cv2.setNumThreads(1)
    try:
        from threadpoolctl import threadpool_limits  # optional
        threadpool_limits(1)
    except Exception:
        pass


def _src(path):
    s = _SOURCES.get(path)
    if s is None:
        s = open_source(path)
        _SOURCES[path] = s
    return s


def _job_prepare_reference(ref_path, chname, region, opts_dict, px, out_dir):
    """Read the reference region once (working scale) + feature images, save them for the other jobs."""
    opts = RegistrationOptions(**opts_dict)
    src = _src(ref_path)
    pre = Preloaded.read(src, src.channel_index(chname), ref_box_for(BBox(*region), opts, px),
                         working_scale(opts), px)
    pre.save(out_dir)
    return out_dir


def _job_register(ref_dir, mov_path, mov_chname, region, opts_dict, px):
    opts = RegistrationOptions(**opts_dict)
    region = BBox(*region)
    ref = Preloaded.load(ref_dir)
    src = _src(mov_path)
    mov = Preloaded.read(src, src.channel_index(mov_chname), mov_box_for(region, opts, px),
                         working_scale(opts), px)
    return register_region(ref, mov, region, opts, px)


def _job_warp(task):
    """Warp one strip of one output channel and write it into the memmap."""
    (mm_path, mm_shape, k, r0, r1, origin, scale,
     src_path, ch_name, A, bg) = task
    src = _src(src_path)
    ch = src.channel_index(ch_name)
    xf = Transform.from_json(A)
    out_shape = (r1 - r0, mm_shape[2])
    o = (origin[0], origin[1] + r0 / scale)
    box = xf.source_region(o, scale, out_shape, margin=int(math.ceil(2 / scale)) + 2)
    img = src.read(ch, box, scale)
    out = xf.warp(img, (box.x, box.y), scale, o, scale, out_shape)
    del img
    if bg is not None:
        bg_path, bg_ch, bg_A, mult = bg
        bsrc = _src(bg_path)
        btr = Transform.from_json(bg_A)
        bbox_ = btr.source_region(o, scale, out_shape, margin=int(math.ceil(2 / scale)) + 2)
        bimg = bsrc.read(bsrc.channel_index(bg_ch), bbox_, scale)
        bw = btr.warp(bimg, (bbox_.x, bbox_.y), scale, o, scale, out_shape).astype(np.float32)
        out = np.clip(out.astype(np.float32) - mult * bw, 0, 65535).astype(np.uint16)
    mm = np.memmap(mm_path, dtype=np.uint16, mode='r+', shape=tuple(mm_shape))
    mm[k, r0:r1, :] = out
    mm.flush()
    del mm
    return r1 - r0


# ============================================================================ main side
@dataclass
class Callbacks:
    log: callable = print
    progress: callable = lambda stage, done, total: None   # stage: str
    qc: callable = lambda section, round_label, result: None  # RegistrationResult


def auto_workers(perf) -> int:
    if perf.workers and perf.workers > 0:
        return int(perf.workers)
    n = os.cpu_count() or 4
    return max(1, min(n - 2, 12))


def ram_budget_bytes(perf) -> float:
    try:
        total = os.sysconf('SC_PAGE_SIZE') * os.sysconf('SC_PHYS_PAGES')
    except (ValueError, OSError, AttributeError):
        total = 16e9
    if perf.max_ram_gb and perf.max_ram_gb > 0:
        return perf.max_ram_gb * 1e9
    return 0.6 * total


class Pipeline:
    def __init__(self, project: Project, callbacks: Callbacks | None = None,
                 cancel_event: threading.Event | None = None):
        self.p = project
        self.cb = callbacks or Callbacks()
        self.cancel = cancel_event or threading.Event()
        self._sources = {}
        self.qc_results: dict = {}   # section -> round label -> RegistrationResult

    # ---------------------------------------------------------------- helpers
    def src(self, path):
        if path not in self._sources:
            self._sources[path] = open_source(path)
        return self._sources[path]

    def _check_cancel(self):
        if self.cancel.is_set():
            raise Cancelled()

    def pixel_size(self) -> float:
        if self.p.pixel_size_um and self.p.pixel_size_um > 0:
            return float(self.p.pixel_size_um)
        ref = self.src(self.p.reference().path)
        return float(ref.pixel_size_um or 0.325)

    def sections(self) -> list[SectionSpec | None]:
        if self.p.whole_slide or not [s for s in self.p.sections if s.enabled]:
            return [None]
        return [s for s in self.p.sections if s.enabled]

    def section_bbox(self, s: SectionSpec | None) -> BBox:
        if s is None:
            return self.src(self.p.reference().path).bbox
        return BBox(s.x, s.y, s.w, s.h)

    @staticmethod
    def section_key(s: SectionSpec | None) -> str:
        return '__slide__' if s is None else s.name

    def all_registration_rounds(self):
        """(label, path) of every round to register, background included."""
        out = [(r.label, r.path) for r in self.p.active_rounds()]
        if self.p.background_path:
            out.append(('__background__', self.p.background_path))
        return out

    # ---------------------------------------------------------------- validation
    def validate(self) -> list[str]:
        """Return a list of blocking errors (empty = OK). Warnings are logged."""
        errors = []
        p = self.p
        rounds = p.active_rounds()
        if not rounds:
            return [tr('Aucune image (round) dans le projet.')]
        labels = [r.label for r in rounds]
        if len(set(labels)) != len(labels):
            errors.append(tr('Deux rounds ont le même nom : les noms doivent être uniques.'))
        for r in rounds:
            if not os.path.exists(r.path):
                errors.append(tr('Fichier introuvable : {path}', path=r.path))
                continue
            s = self.src(r.path)
            if not any(channel_matches(c, p.reference_channel) for c in s.channels):
                errors.append(tr('{label} : pas de canal de référence "{ch}" (canaux : {chans})', label=r.label,
                                 ch=p.reference_channel, chans=', '.join(s.channels)))
            file_ch = [c.lower() for c in s.channels]
            for c in r.channels:
                if c.channel.lower() not in file_ch:
                    errors.append(tr('{label} : le canal "{ch}" n\'existe pas dans le fichier.', label=r.label, ch=c.channel))
        if p.background_path:
            if not os.path.exists(p.background_path):
                errors.append(tr('Fichier de fond introuvable : {path}', path=p.background_path))
            else:
                b = self.src(p.background_path)
                if not any(channel_matches(c, p.reference_channel) for c in b.channels):
                    errors.append(tr('Fond : pas de canal de référence "{ch}".', ch=p.reference_channel))
        if not p.output.directory:
            errors.append(tr('Choisissez un dossier de sortie.'))
        elif not os.path.isdir(p.output.directory):
            try:
                os.makedirs(p.output.directory, exist_ok=True)
            except OSError as e:
                errors.append(tr('Dossier de sortie inaccessible : {e}', e=e))
        if not p.output_channels():
            errors.append(tr('Aucun canal à exporter (tous les marqueurs sont vides).'))
        if not (0 < p.output.downscale <= 1):
            errors.append(tr('Le facteur de réduction doit être entre 0 et 1.'))
        return errors

    # ---------------------------------------------------------------- registration
    def register(self, executor=None) -> dict:
        p = self.p
        ref = p.reference()
        px = self.pixel_size()
        jobs = []
        absent = []
        for sec in self.sections():
            region = self.section_bbox(sec)
            for label, path in self.all_registration_rounds():
                if path == ref.path:
                    continue
                if not self.src(path).has_data(region):
                    absent.append((sec, label))
                    continue
                jobs.append((sec, label, path, region))
        total = len(jobs)
        self.cb.log(tr('Recalage : {n} paire(s) section × round à traiter (mode {mode}).', n=total,
                       mode=tr('précis') if p.registration.mode == 'precise' else tr('rapide')))
        transforms = {self.section_key(s): {ref.label: Transform(np.eye(3)).to_json()} for s in self.sections()}
        for sec, label in absent:
            transforms[self.section_key(sec)][label] = None
            name = tr('lame') if sec is None else sec.name
            self.cb.log(tr('  ⚠ {name} / {label} : aucune donnée acquise dans cette zone → canaux laissés vides (0).',
                           name=name, label=label))
            res = RegistrationResult(matrix=None, warnings=[tr('Round non acquis dans cette zone : canaux vides.')])
            self.qc_results.setdefault(self.section_key(sec), {})[label] = res
            self.cb.qc(self.section_key(sec), label, res)
        own = executor is None
        ex = executor or self._executor()
        opts = p.registration.__dict__
        tmp_root = os.path.join(p.temp_dir(), f'hifi_reg_{uuid.uuid4().hex[:8]}')
        try:
            # 1. reference data, once per section (read + structure images), shared through the disk
            secs = sorted({self.section_key(sec): sec for sec, _, _, _ in jobs}.items())
            self.cb.progress(tr('Préparation de la référence'), 0, max(len(secs), 1))
            ref_dirs = {}
            futs = {ex.submit(_job_prepare_reference, ref.path, p.reference_channel,
                              self.section_bbox(sec).to_list(), opts, px,
                              os.path.join(tmp_root, key)): key for key, sec in secs}
            for i, f in enumerate(cf.as_completed(futs), 1):
                self._check_cancel()
                ref_dirs[futs[f]] = f.result()
                self.cb.progress(tr('Préparation de la référence'), i, len(secs))
            # 2. one job per (section, round); concurrency limited by the memory budget
            budget = ram_budget_bytes(p.performance)
            est = max(estimate_job_bytes(region, p.registration, px) for _, _, _, region in jobs) if jobs else 1
            window = max(1, min(auto_workers(p.performance), int(budget // est)))
            self.cb.log(tr('  jusqu\'à {n} recalage(s) en parallèle (~{gb:.1f} Go chacun).', n=window, gb=est / 1e9))
            self.cb.progress(tr('Recalage'), 0, max(total, 1))
            tasks = [(sec, label, path, region) for sec, label, path, region in jobs]
            meta = {}

            def submit(t):
                sec, label, path, region = t
                f = ex.submit(_job_register, ref_dirs[self.section_key(sec)], path, p.reference_channel,
                              region.to_list(), opts, px)
                meta[f] = (sec, label)
                return f
            pending = {submit(t) for t in tasks[:window]}
            queue = tasks[window:]
            done = 0
            while pending:
                finished, pending = cf.wait(pending, return_when=cf.FIRST_COMPLETED)
                for f in finished:
                    if queue:
                        pending.add(submit(queue.pop(0)))
                    self._check_cancel()
                    sec, label = meta[f]
                    res: RegistrationResult = f.result()
                    key = self.section_key(sec)
                    transforms[key][label] = res.transform
                    self.qc_results.setdefault(key, {})[label] = res
                    done += 1
                    self.cb.progress(tr('Recalage'), done, total)
                    name = tr('lame') if sec is None else sec.name
                    self.cb.log(tr('  {name} / {label} : décalage ({sx:+.1f}, {sy:+.1f}) px, rotation {rot:+.3f}°, '
                                   'corrélation {c0:.2f} → {c1:.2f}, {ni}/{np} patchs, résidu {res:.2f} px',
                                   name=name, label=label, sx=res.shift_px[0], sy=res.shift_px[1],
                                   rot=res.rotation_deg, c0=res.ncc_before, c1=res.ncc_after, ni=res.n_inliers,
                                   np=res.n_patches, res=res.residual_px)
                                + (tr(', déformation locale ≤ {d:.1f} µm ({v}/{n} points)', d=res.deform_max_um,
                                      v=res.field_valid, n=res.field_nodes) if res.field_nodes else '')
                                + ''.join(f'\n    ⚠ {w}' for w in res.warnings))
                    self.cb.qc(key, label, res)
        except BaseException:
            if own:
                ex.shutdown(wait=False, cancel_futures=True)
            raise
        finally:
            shutil.rmtree(tmp_root, ignore_errors=True)
        if own:
            ex.shutdown()
        p.transforms = transforms
        p.transforms_signature = p.registration_signature()
        return transforms

    # ---------------------------------------------------------------- writing
    def write_outputs(self, executor=None) -> list[str]:
        p = self.p
        if not p.transforms:
            raise RuntimeError(tr('Recalage non effectué.'))
        outputs = []
        own = executor is None
        ex = executor or self._executor()
        try:
            secs = self.sections()
            for i, sec in enumerate(secs, 1):
                self._check_cancel()
                outputs.append(self._write_section(sec, ex, i, len(secs)))
        except BaseException:
            if own:
                ex.shutdown(wait=False, cancel_futures=True)
            raise
        if own:
            ex.shutdown()
        return outputs

    def _write_section(self, sec, ex, i, n) -> str:
        p = self.p
        key = self.section_key(sec)
        region = self.section_bbox(sec)
        f = p.output.downscale
        H, W = max(1, int(round(region.h * f))), max(1, int(round(region.w * f)))
        chans = p.output_channels()
        C = len(chans)
        name = tr('lame entière') if sec is None else sec.name
        out_path = p.output_path(None if sec is None else sec.name)
        gb = C * H * W * 2 / 1e9
        self.cb.log(tr('Coupe {name} ({i}/{n}) : {C} canaux × {W} × {H} px ({gb:.1f} Go non compressé) → {out}',
                       name=name, i=i, n=n, C=C, W=W, H=H, gb=gb, out=out_path))
        tmp_dir = os.path.join(p.temp_dir(), f'hifi_{uuid.uuid4().hex[:8]}')
        os.makedirs(tmp_dir, exist_ok=True)
        free = shutil.disk_usage(tmp_dir).free / 1e9
        if free < gb * 1.4:
            raise RuntimeError(tr('Espace insuffisant dans le dossier temporaire {d} : {free:.0f} Go libres, '
                                  '~{need:.0f} Go nécessaires.', d=p.temp_dir(), free=free, need=gb * 1.4))
        mm_path = os.path.join(tmp_dir, 'level0.u16')
        try:
            mm = np.memmap(mm_path, dtype=np.uint16, mode='w+', shape=(C, H, W))
            del mm
            # strip height: ~64 MB of output per job, multiple of the tile size
            tile = p.output.tile_size
            rows = max(tile, int(64e6 / (2 * W)) // tile * tile)
            bg_A = p.transforms[key].get('__background__')
            bg_src = self.src(p.background_path) if p.background_path else None
            tasks = []
            empty = set()
            for k, (r, c) in enumerate(chans):
                A = p.transforms[key].get(r.label)
                if A is None:
                    empty.add(r.label)
                    continue        # round not acquired here: channel stays at 0
                bg = None
                if bg_src is not None and bg_A is not None and not p.is_ref(c.channel):
                    if c.channel.lower() in [x.lower() for x in bg_src.channels]:
                        bg = (p.background_path, c.channel, bg_A, float(p.background_multiplier))
                for r0 in range(0, H, rows):
                    tasks.append((mm_path, (C, H, W), k, r0, min(H, r0 + rows), (region.x, region.y), f,
                                  r.path, c.channel, A, bg))
            for lab in sorted(empty):
                self.cb.log(tr('  ⚠ {lab} absent de {name} : ses canaux sont vides (0) dans cette image.', lab=lab, name=name))
            total = len(tasks)
            self.cb.progress(tr('Déformation {name}', name=name), 0, total)
            done = 0
            t0 = time.time()
            for fut in _bounded_map(ex, _job_warp, tasks, window=64):
                self._check_cancel()
                fut.result()
                done += 1
                self.cb.progress(tr('Déformation {name}', name=name), done, total)
            self.cb.log(tr('  canaux recalés en {s:.1f} s', s=time.time() - t0))
            self._check_cancel()
            names = [p.channel_display_name(r, c) for r, c in chans]
            t0 = time.time()
            self._write_ome(mm_path, (C, H, W), out_path, names, self.pixel_size() / f, tmp_dir, name)
            self.cb.log(tr('  OME-TIFF écrit en {s:.1f} s', s=time.time() - t0))
            with open(os.path.splitext(os.path.splitext(out_path)[0])[0] + '_channels.txt', 'w') as fh:
                fh.write('\n'.join(names) + '\n')
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)
        return out_path

    def _write_ome(self, mm_path, shape, out_path, names, px_um, tmp_dir, label):
        import tifffile
        p = self.p
        C, H, W = shape
        data = np.memmap(mm_path, dtype=np.uint16, mode='r', shape=shape)
        comp = {'none': None, 'zlib': 'zlib', 'lzw': 'lzw'}.get(p.output.compression, 'zlib')
        tile = (p.output.tile_size, p.output.tile_size)
        nthreads = max(1, (os.cpu_count() or 4) - 1)
        cv2.setNumThreads(nthreads)
        levels = []
        if p.output.pyramidal:
            h, w = H, W
            while max(h, w) > 2 * p.output.tile_size and len(levels) < 8:
                h, w = (h + 1) // 2, (w + 1) // 2
                levels.append((h, w))
        meta = {'axes': 'CYX', 'Channel': {'Name': names}, 'PhysicalSizeX': px_um, 'PhysicalSizeXUnit': 'µm',
                'PhysicalSizeY': px_um, 'PhysicalSizeYUnit': 'µm', 'Name': os.path.basename(out_path)}
        part = out_path + '.part'
        steps = 1 + len(levels)
        self.cb.progress(tr('Écriture {name}', name=label), 0, steps)
        with tifffile.TiffWriter(part, bigtiff=True, ome=True) as tif:
            opts = dict(tile=tile, compression=comp, photometric='minisblack', maxworkers=nthreads)
            tif.write(data, subifds=len(levels), metadata=meta, **opts)
            self.cb.progress(tr('Écriture {name}', name=label), 1, steps)
            prev, prev_shape = data, (H, W)
            for li, (h, w) in enumerate(levels, 1):
                self._check_cancel()
                lvl_path = os.path.join(tmp_dir, f'level{li}.u16')
                lvl = np.memmap(lvl_path, dtype=np.uint16, mode='w+', shape=(C, h, w))
                for k in range(C):
                    # downsample by 2 in bands to bound memory
                    band = 4096
                    for y0 in range(0, prev_shape[0], band * 2):
                        src = np.asarray(prev[k, y0:y0 + band * 2, :])
                        dh = (src.shape[0] + 1) // 2
                        lvl[k, y0 // 2:y0 // 2 + dh, :] = cv2.resize(src, (w, dh), interpolation=cv2.INTER_AREA)
                lvl.flush()
                tif.write(lvl, subfiletype=1, **opts)
                del prev
                prev, prev_shape = lvl, (h, w)
                self.cb.progress(tr('Écriture {name}', name=label), 1 + li, steps)
            del prev
        os.replace(part, out_path)

    # ---------------------------------------------------------------- QC export
    def export_qc(self) -> str | None:
        p = self.p
        if not self.qc_results:
            return None
        qc_dir = os.path.join(p.output.directory, f'{p.output.basename}_QC')
        os.makedirs(qc_dir, exist_ok=True)
        rows = []
        for key, per_round in self.qc_results.items():
            for label, r in per_round.items():
                tag = f'{key}_{label}'.replace('/', '_')
                if r.qc_before is not None:
                    pair = np.concatenate([r.qc_before, np.full((r.qc_before.shape[0], 8, 3), 255, np.uint8),
                                           r.qc_after], axis=1)
                    cv2.imwrite(os.path.join(qc_dir, f'{tag}.png'), cv2.cvtColor(pair, cv2.COLOR_RGB2BGR))
                rows.append(dict(section=key, round=label, ncc_before=round(r.ncc_before, 4),
                                 ncc_after=round(r.ncc_after, 4), shift_x_px=round(r.shift_px[0], 2),
                                 shift_y_px=round(r.shift_px[1], 2), rotation_deg=round(r.rotation_deg, 4),
                                 patches=r.n_patches, inliers=r.n_inliers,
                                 residual_px=round(r.residual_px, 3) if np.isfinite(r.residual_px) else '',
                                 deform_grid_valid=f'{r.field_valid}/{r.field_nodes}',
                                 deform_max_um=round(r.deform_max_um, 2),
                                 local_resid_um=round(r.local_resid_um, 2) if np.isfinite(r.local_resid_um) else '',
                                 warnings=' | '.join(r.warnings)))
        with open(os.path.join(qc_dir, 'registration_qc.csv'), 'w', newline='', encoding='utf-8') as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        return qc_dir

    def export_markers_csv(self) -> str:
        """Markers table (same format as Markers → Export as CSV), next to the QC, re-importable for another slide."""
        p = self.p
        qc_dir = os.path.join(p.output.directory, f'{p.output.basename}_QC')
        os.makedirs(qc_dir, exist_ok=True)
        path = os.path.join(qc_dir, f'{p.output.basename}_markers.csv')
        p.export_csv(path)
        return path

    # ---------------------------------------------------------------- run all
    def _executor(self):
        return cf.ProcessPoolExecutor(max_workers=auto_workers(self.p.performance),
                                      mp_context=mp.get_context('spawn'), initializer=_worker_init)

    def run(self, do_register=True, do_write=True) -> list[str]:
        t0 = time.time()
        errors = self.validate()
        if errors:
            raise ValueError('\n'.join(errors))
        n = auto_workers(self.p.performance)
        self.cb.log(tr('{n} processus de calcul, dossier temporaire : {d}', n=n, d=self.p.temp_dir()))
        outputs = []
        with self._executor() as ex:
            try:
                if do_register or not self.p.transforms_valid():
                    if not do_register:
                        self.cb.log(tr('Transformations absentes ou obsolètes : nouveau recalage.'))
                    self.register(ex)
                    if self.p.output.qc:
                        d = self.export_qc()
                        if d:
                            self.cb.log(tr('Contrôle qualité enregistré dans {d}', d=d))
                    # keep a copy of the project (with transforms) next to the outputs
                    self.p.save(os.path.join(self.p.output.directory, f'{self.p.output.basename}_project'))
                if do_write:
                    outputs = self.write_outputs(ex)
                if self.p.output.markers_csv:
                    self.cb.log(tr('Tableau des marqueurs enregistré : {path}', path=self.export_markers_csv()))
            except BaseException:
                ex.shutdown(wait=False, cancel_futures=True)
                raise
        self.cb.log(tr('Terminé en {t}.', t=_fmt(time.time() - t0)))
        return outputs


def _bounded_map(ex, fn, tasks, window=64):
    """Submit tasks with at most `window` in flight; yield futures as they complete."""
    it = iter(tasks)
    pending = set()
    for t in it:
        pending.add(ex.submit(fn, t))
        if len(pending) >= window:
            break
    while pending:
        done, pending = cf.wait(pending, return_when=cf.FIRST_COMPLETED)
        for d in done:
            yield d
            nxt = next(it, None)
            if nxt is not None:
                pending.add(ex.submit(fn, nxt))


def _fmt(sec):
    m, s = divmod(int(sec), 60)
    h, m = divmod(m, 60)
    return f'{h} h {m:02d} min {s:02d} s' if h else f'{m} min {s:02d} s'
