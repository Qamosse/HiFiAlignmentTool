"""Project description (what to process and how), saved as JSON (*.hifi.json).

Replaces channel_name.csv: each round lists its *real* channels (read from the
file metadata, in file order) with the marker imaged in each one.
An empty marker means "do not export this channel".
"""
from __future__ import annotations

import csv
import json
import os
import tempfile
from dataclasses import asdict, dataclass, field

from .naming import channel_matches
from .i18n import tr

PROJECT_EXT = '.hifi.json'


@dataclass
class ChannelSpec:
    channel: str          # channel name in the file (e.g. "Cy5", "DAPI")
    marker: str = ''      # marker name; '' = not exported


@dataclass
class RoundSpec:
    path: str
    label: str = ''
    channels: list[ChannelSpec] = field(default_factory=list)
    enabled: bool = True

    def marker_of(self, channel: str) -> str:
        for c in self.channels:
            if c.channel == channel:
                return c.marker
        return ''


@dataclass
class SectionSpec:
    name: str
    x: int
    y: int
    w: int
    h: int
    enabled: bool = True


@dataclass
class RegistrationOptions:
    mode: str = 'precise'          # 'fast' (low-res patches) or 'precise' (full-res patches)
    coarse_scale: float = 0.0625   # scale of the coarse (global) registration
    fast_scale: float = 0.5        # patch refinement scale in 'fast' mode (and 1st pass of 'precise')
    patch_size: int = 1024         # patch size in full-res pixels (precise mode)
    max_patches: int = 25
    search_margin_um: float = 500  # how far a section may have moved between rounds
    use_rotation: bool = True      # rigid (rotation+translation) vs translation only
    nonrigid: bool = True          # correct local tissue deformations with a smooth displacement field
    grid_spacing_um: float = 400.0 # spacing of the deformation grid (precise mode; x2 in fast mode)
    field_patch_um: float = 400.0  # size of the patches used to measure local displacements


@dataclass
class OutputOptions:
    directory: str = ''
    basename: str = 'final_image'
    pyramidal: bool = True
    compression: str = 'zlib'      # 'zlib', 'lzw' or 'none'
    downscale: float = 1.0         # 1.0 = full resolution
    keep_all_reference: bool = False  # keep the reference channel of every round
    fullname: bool = False          # channel names "marker|channel|round"
    qc: bool = True
    markers_csv: bool = True        # copy of the markers table in <basename>_QC/
    tile_size: int = 512


@dataclass
class PerformanceOptions:
    workers: int = 0               # 0 = automatic
    max_ram_gb: float = 0          # 0 = automatic (60 % of RAM)
    temp_dir: str = ''             # '' = system temp folder (local disk)


@dataclass
class Project:
    name: str = 'Nouveau projet'
    rounds: list[RoundSpec] = field(default_factory=list)
    reference_round: int = 0
    reference_channel: str = 'DAPI'
    background_path: str = ''
    background_multiplier: float = 1.0
    pixel_size_um: float = 0.0     # 0 = read from the files
    whole_slide: bool = False      # True = ignore sections, one image for the whole slide
    sections: list[SectionSpec] = field(default_factory=list)
    registration: RegistrationOptions = field(default_factory=RegistrationOptions)
    output: OutputOptions = field(default_factory=OutputOptions)
    performance: PerformanceOptions = field(default_factory=PerformanceOptions)
    # filled by the registration step (per section name -> per round label -> 3x3 matrix)
    transforms: dict = field(default_factory=dict)
    transforms_signature: str = ''

    def registration_signature(self) -> str:
        """Hash of everything the registration depends on (to know if transforms are still valid)."""
        import hashlib
        key = dict(rounds=[(r.path, r.label, r.enabled) for r in self.rounds],
                   ref=(self.reference_round, self.reference_channel.lower()), bg=self.background_path,
                   whole=self.whole_slide, sections=[(s.name, s.x, s.y, s.w, s.h, s.enabled) for s in self.sections],
                   reg=asdict(self.registration), px=self.pixel_size_um)
        return hashlib.sha1(json.dumps(key, sort_keys=True).encode()).hexdigest()

    def transforms_valid(self) -> bool:
        return bool(self.transforms) and self.transforms_signature == self.registration_signature()

    # -- helpers ---------------------------------------------------------------
    def is_ref(self, channel_name: str) -> bool:
        return channel_matches(channel_name, self.reference_channel)

    def active_rounds(self) -> list[RoundSpec]:
        return [r for r in self.rounds if r.enabled]

    def reference(self) -> RoundSpec:
        rounds = self.active_rounds()
        if not rounds:
            raise ValueError(tr('Aucun round actif dans le projet.'))
        idx = min(max(self.reference_round, 0), len(self.rounds) - 1)
        ref = self.rounds[idx]
        return ref if ref.enabled else rounds[0]

    def output_channels(self) -> list[tuple[RoundSpec, ChannelSpec]]:
        """Channels of the final image, in order: reference channel of the reference round first,
        then each round's exported channels (reference channel dropped unless keep_all_reference)."""
        ref_round = self.reference()
        out = []
        for c in ref_round.channels:
            if self.is_ref(c.channel):
                out.append((ref_round, c))
        for r in self.active_rounds():
            for c in r.channels:
                is_ref = self.is_ref(c.channel)
                if is_ref:
                    if r is not ref_round and self.output.keep_all_reference:
                        out.append((r, c))
                    continue
                if c.marker.strip():
                    out.append((r, c))
        return out

    def channel_display_name(self, r: RoundSpec, c: ChannelSpec) -> str:
        marker = c.marker.strip() or c.channel
        if self.output.fullname:
            return f'{marker}|{c.channel}|{r.label}'
        if self.is_ref(c.channel) and r is not self.reference():
            return f'{marker}_{r.label}'
        return marker

    def output_path(self, section_name: str | None) -> str:
        d = self.output.directory or os.getcwd()
        base = self.output.basename or 'final_image'
        name = base if section_name is None else f'{base}_{section_name}'
        return os.path.join(d, name + '.ome.tif')

    def temp_dir(self) -> str:
        return self.performance.temp_dir or tempfile.gettempdir()

    # -- (de)serialisation -----------------------------------------------------------
    def to_dict(self) -> dict:
        d = asdict(self)
        d['version'] = 1
        return d

    @classmethod
    def from_dict(cls, d: dict) -> 'Project':
        d = dict(d)
        d.pop('version', None)
        p = cls()
        for k, v in d.items():
            if k == 'rounds':
                p.rounds = [RoundSpec(path=r['path'], label=r.get('label', ''), enabled=r.get('enabled', True),
                                      channels=[ChannelSpec(**c) for c in r.get('channels', [])]) for r in v]
            elif k == 'sections':
                p.sections = [SectionSpec(**s) for s in v]
            elif k == 'registration':
                p.registration = RegistrationOptions(**{**asdict(RegistrationOptions()), **v})
            elif k == 'output':
                p.output = OutputOptions(**{**asdict(OutputOptions()), **v})
            elif k == 'performance':
                p.performance = PerformanceOptions(**{**asdict(PerformanceOptions()), **v})
            elif hasattr(p, k):
                setattr(p, k, v)
        return p

    def save(self, path: str):
        if not path.endswith(PROJECT_EXT):
            path += PROJECT_EXT
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
        return path

    @classmethod
    def load(cls, path: str) -> 'Project':
        with open(path, encoding='utf-8') as f:
            return cls.from_dict(json.load(f))

    # -- CSV compatibility (channel_name.csv of the original tool) --------------------
    def export_csv(self, path: str):
        cols = []
        for r in self.rounds:
            for c in r.channels:
                if c.channel not in cols:
                    cols.append(c.channel)
        with open(path, 'w', newline='', encoding='utf-8') as f:
            w = csv.writer(f)
            w.writerow(['Filename'] + cols)
            for r in self.rounds:
                row = [r.label]
                for col in cols:
                    m = r.marker_of(col)
                    if not m and self.is_ref(col) and \
                            any(c.channel == col for c in r.channels):
                        m = col
                    row.append(m)
                w.writerow(row)

    def import_csv(self, path: str) -> list[str]:
        """Fill markers from a channel_name.csv. Channels are matched by *name* (column header). Rounds are
        matched by label (first column); CSV rows whose label is not in the project are then paired, in order,
        with the project rounds left unmatched (e.g. another slide whose file names carry other dates).
        Returns warnings."""
        warnings = []
        with open(path, newline='', encoding='utf-8-sig') as f:
            rows = list(csv.reader(f))
        if not rows:
            return [tr('CSV vide')]
        header = [h.strip() for h in rows[0]]
        data = [row for row in rows[1:] if row and row[0].strip()]
        by_label = {r.label: r for r in self.rounds}
        matched = {id(by_label[row[0].strip()]) for row in data if row[0].strip() in by_label}
        free_rounds = [r for r in self.rounds if id(r) not in matched]
        pairs, extra = [], []
        assignment = []
        for row in data:
            label = row[0].strip()
            r = by_label.get(label)
            if r is None:
                if free_rounds:
                    r = free_rounds.pop(0)
                    pairs.append(f'{label} → {r.label}')
                else:
                    extra.append(label)
                    continue
            assignment.append((label, r, row))
        if pairs:
            warnings.append(tr('Noms de rounds différents : association par ordre des lignes, à vérifier :\n  {pairs}',
                               pairs='\n  '.join(pairs)))
        if extra:
            warnings.append(tr('Lignes du CSV sans round correspondant (ignorées) : {labels}',
                               labels=', '.join(extra)))
        if free_rounds:
            warnings.append(tr('Rounds du projet sans ligne dans le CSV (marqueurs inchangés) : {labels}',
                               labels=', '.join(r.label for r in free_rounds)))
        for label, r, row in assignment:
            names_low = {c.channel.lower(): c for c in r.channels}
            for col, val in zip(header[1:], row[1:]):
                val = val.strip()
                c = names_low.get(col.lower())
                if c is None:
                    # tolerate GFP/EGFP style aliases
                    alias = {k for k in names_low if k.endswith(col.lower()) or col.lower().endswith(k)}
                    c = names_low[alias.pop()] if len(alias) == 1 else None
                if c is None:
                    if val:
                        warnings.append(tr('{label} : canal "{col}" (marqueur "{val}") absent du fichier (canaux : {chans})',
                                           label=label, col=col, val=val,
                                           chans=', '.join(x.channel for x in r.channels)))
                    continue
                c.marker = '' if self.is_ref(c.channel) and val == '' else val
        return warnings
