# HiFi Align — whole-slide multiplex registration (fork of HiFiAlignmentTool)

This repository is a fork of [jhausserlab/HiFiAlignmentTool](https://github.com/jhausserlab/HiFiAlignmentTool).
It adds **HiFi Align**, a desktop application and a rewritten registration engine for aligning the rounds of
multiplex fluorescence imaging (one CZI or OME-TIFF file per round) on **whole slides of more than
100,000 × 20,000 pixels**, which the original scripts cannot load in memory.

The original command-line scripts (`main.py`, `image_registration/`) are still here, with a few bug fixes
(see [Changes to the original scripts](#changes-to-the-original-scripts)). Their documentation is in
[README_original.md](README_original.md).

A detailed user guide (in French) is in [GUIDE_HiFiAlign.md](GUIDE_HiFiAlign.md).

---

## Contents

- [What is new](#what-is-new)
- [Installation](#installation)
- [Launching](#launching)
- [Workflow](#workflow)
- [Output files](#output-files)
- [How the registration works](#how-the-registration-works)
- [Performance](#performance)
- [Command line](#command-line)
- [Project files](#project-files)
- [Code layout](#code-layout)
- [Changes to the original scripts](#changes-to-the-original-scripts)
- [Known limitations](#known-limitations)
- [Credits](#credits)

---

## What is new

| | Original scripts | HiFi Align |
|---|---|---|
| Interface | command line + `channel_name.csv` | desktop application (PySide6), plus a command line for batch runs |
| Memory | whole images in RAM (~52 GB for 16,000 × 21,000 px) | **out-of-core**: only the regions being processed are read; never the whole slide |
| Image size | limited by RAM | tested on slides of ~94,000 × 24,000 px per round, 6 rounds |
| Output | one image for the whole slide | **one image per tissue section** (detected automatically, editable), or the whole slide |
| Registration | rigid (pystackreg) at a single scale | coarse → rigid → **non-rigid** (local tissue deformation), robust to the fading of DAPI between rounds |
| Markers | assigned by **channel position** in the CSV | assigned by **channel name** read from the file metadata |
| Speed | single process | multiple processes for registration and warping, multithreaded compressed writing |
| Output format | OME-TIFF, optional pyramid | tiled, compressed (lossless), pyramidal OME-TIFF with marker names and pixel size in the metadata |
| Quality control | none | before/after overlays, correlation, deformation and warnings for every section × round, saved as PNG + CSV |
| Reuse | — | saved projects, markers table import/export, batch processing of several slides |
| Languages / themes | — | French or English; light, dark or system theme |

---

## Installation

Python 3.10 in a conda environment is recommended (that is what was tested):

```bash
conda create -n multiplex python=3.10
conda activate multiplex
python -m pip install -r requirements.txt
```

Main dependencies: `aicspylibczi` (CZI reading), `tifffile` + `zarr` 2.x + `imagecodecs` (TIFF reading and
writing), `opencv-python-headless`, `scikit-image`, `scipy`, `pystackreg`, `PySide6` (interface).

---

## Launching

From the repository folder:

```bash
python -m hifialign                       # open the interface
python -m hifialign gui my_slide.hifi.json # open a saved project
```

On macOS, `Lancer HiFiAlign.command` can be double-clicked in the Finder (the first time: right-click → Open).
It points to `/opt/miniconda3/envs/multiplex/bin/python`; edit that line if your Python is elsewhere.

---

## Workflow

The application is organised in five steps (left sidebar, shortcuts ⌘1–⌘5), plus a batch page.

1. **Images**: add one file per round (button, or drag and drop files or a folder). Channels, image size and
   pixel size are read from the metadata. The round marked ★ is the reference; the order of the list is the
   order of the channels in the final image. Optional background image (with a multiplier), subtracted channel by
   channel (same channel name) after registration.
2. **Markers**: a rounds × channels table using the real channel names of the files. Type the marker of each
   channel; an empty cell means the channel is not exported. The final channel list is previewed on the right.
   The table can be exported to CSV and re-imported for another slide acquired the same way: rounds are matched by
   name, and by row order when the names differ (for example file names with other dates); the matching is shown
   for checking. The legacy `channel_name.csv` can also be imported.
3. **Sections**: the tissue sections are detected on the reference channel of the reference round. Each section
   produces its own final image and is registered independently. Rectangles can be moved, drawn, renamed or
   disabled; "Whole slide" produces a single image.
4. **Options**: output folder and base name (`<name>_S01.ome.tif`, …), pyramid, compression, output resolution,
   QC and markers-table export, registration mode (precise / fast), rotation, non-rigid correction and its grid
   spacing, maximum displacement between rounds, number of processes, temporary folder.
5. **Run & QC**: "Register only" computes the registration and the QC so they can be checked before writing the
   images; "Generate images" then reuses that registration. The QC table shows, for each section × round, the
   shift, rotation, correlation before/after, rigid patches, maximum local deformation and warnings (rows to be
   checked are highlighted). Clicking a row shows the before/after overlay (magenta = reference, green = round).
   When a project that was already registered is reopened, the saved QC is loaded again.

**Batch**: a queue of project files processed one after the other. "Create projects from folders" clones the
current project (markers, options) for other slides: one folder per slide, files assigned to rounds in
alphabetical order, sections detected again.

The theme (light / dark / same as the system) and the language (French / English) are chosen at the bottom of the
sidebar or in the View menu. Everything is translated, including the log and the QC warnings.

---

## Output files

| File | Content |
|---|---|
| `<name>_S01.ome.tif`, … | Final image per section: tiled (512 px), pyramidal, lossless-compressed (zlib by default) OME-TIFF, BigTIFF, with marker names and pixel size in the OME metadata. |
| `<name>_S01_channels.txt` | Channel names in order. |
| `<name>_QC/` | Before/after overlays (`<section>_<round>.png`) and `registration_qc.csv`. |
| `<name>_QC/<name>_markers.csv` | Markers table, re-importable for another slide (optional, on by default). |
| `<name>_project.hifi.json` | Copy of the project including the computed transforms (traceability). |

---

## How the registration works

All coordinates are in the full-resolution pixel space of the reference round. For each section and each round,
the transform from reference to round is

    M(x) = A · (x − D(x))

where `A` is a rigid (rotation + translation) matrix and `D` a smooth displacement field sampled on a regular grid
and bilinearly interpolated.

**Region reads.** CZI files are read with `aicspylibczi.read_mosaic` on the region of interest only, at the
required scale (OME-TIFF files are read through `tifffile` + `zarr`, using their pyramid levels when present).
Each section is read once per round; the
reference data are prepared once per section and shared between worker processes through a memory-mapped file on a
local disk.

**Modality-robust features.** In practice DAPI changes appearance from one round to the next (sharp nuclei in the
first rounds, then mostly autofluorescence). Two representations are compared and, at each step, the more reliable
one is kept:

- *structure*: nuclei removed by a grey-level morphological opening (~8 µm), log transform, band-pass
  (difference of Gaussians, 3–40 µm), robust normalisation (median / MAD). What remains are vessels, holes, cracks,
  tissue borders and grey/white matter contrast.
- *raw*: nuclei kept (band-pass from 1 µm), best when both rounds have sharp DAPI.

**Steps.**

1. **Coarse localisation** at low resolution (1/16 by default): normalised cross-correlation template matching
   (`cv2.matchTemplate`) inside a search window (500 µm by default). The representation with the most distinctive
   peak is used. An optional rotation estimate (`pystackreg`, rigid body) is accepted only if it improves the
   correlation, which avoids being trapped by the tile-shading grid that is identical in every round.
2. **Rigid refinement**: sub-pixel phase correlation (`skimage.registration.phase_cross_correlation`) on up to 25
   tissue patches, then a robust rigid fit (RANSAC, `EuclideanTransform`).
3. **Non-rigid correction** (optional, on by default): local shifts measured on a grid (400 µm spacing), outliers
   rejected with an adaptive tolerance, missing nodes filled from their neighbours, field smoothed.
   *Precise* mode: measurements at 1/2 resolution, 2 iterations. *Fast* mode: 1/4 resolution, 1 iteration, grid
   twice as coarse.

**Warping and writing.** Each output channel is warped in horizontal strips by worker processes (`cv2.remap` on
blocks ≤ 8192 px, the mapping being computed on a sub-grid and interpolated) into a memory-mapped file in the
temporary folder (2 bytes × channels × pixels of the section). The pyramidal OME-TIFF is then written by `tifffile`
with multithreaded compression, first as `.part` then renamed, so an interrupted run never leaves a truncated image.

**Rounds missing from a section.** If a round was not scanned over a section (common when the scan areas differ
between rounds), its channels are left at 0 in that section's image and a warning is shown; the channel list stays
the same for all sections.

**Channel names.** `DAPI` also matches `DAPI_2`, `DAPI-1`, etc. (suffixes added by the acquisition software).

---

## Performance

Measured on an Apple M4 Pro (14 cores, 48 GB RAM), slide of 6 rounds × 4 channels, ~94,000 × 24,000 px per round
(CZI files of 1–2 GB, JPEG-XR compressed), 2 tissue sections, precise mode with non-rigid correction:

- **about 5 min 20 s in total** (registration + warping + writing of the two final images) with the CZI files read
  from a network share over a wired connection;
- reading the CZI files over the network is the bottleneck: on a slower connection the same run took ~23 min;
- memory use is bounded by design: registration jobs are scheduled according to a RAM budget (60 % of the
  physical memory by default), and warping works on strips.

Accuracy:

- synthetic slides with a known transform: maximum error ≤ 0.4 px (≤ 0.13 µm) in precise mode, ~1–1.5 µm in
  fast mode;
- real slide, checked with independent local measurements: median residual 0.3–1.6 µm depending on the round,
  including rounds with faded DAPI and torn or deformed tissue (local deformations of up to ~40 µm corrected).

Tips: put the temporary folder on a fast local disk (not a network share or a synced cloud folder); the output
folder can be on a network share.

---

## Command line

Saved projects can be processed without the interface, for example on a server:

```bash
python -m hifialign run slide1.hifi.json slide2.hifi.json
python -m hifialign run slide1.hifi.json --register-only   # registration + QC only
python -m hifialign run slide1.hifi.json --write-only      # reuse the saved registration
python -m hifialign run slide1.hifi.json --lang en          # log language (fr or en)
```

The computed transforms are saved back into the project file.

---

## Project files

A project (`*.hifi.json`) stores everything needed to reproduce a run: image paths and round names, channel →
marker table, reference round and channel, background, sections, all options, and the computed transforms with a
signature of the settings they depend on (if the images, sections or registration options change, the transforms
are marked as outdated and recomputed).

---

## Code layout

```
hifialign/
  __main__.py      entry point: GUI or command line (run / --register-only / --write-only / --lang)
  project.py       project model (rounds, channels, sections, options), JSON save/load, CSV import/export
  sources.py       region readers for CZI (aicspylibczi) and OME-TIFF (tifffile + zarr), metadata
  sections.py      automatic detection of tissue sections on a low-resolution overview
  registration.py  features, coarse / rigid / non-rigid registration, QC overlays
  transform.py     rigid + displacement-field transform, block-wise warping
  pipeline.py      validation, parallel registration, warping, pyramidal OME-TIFF writing, QC export
  naming.py        tolerant channel-name matching (DAPI ↔ DAPI_2)
  i18n.py          translation function; i18n_en.py: English strings
  gui/
    app.py         main window, sidebar, menus, theme and language switching
    tabs.py        Images, Markers and Options pages
    sections_tab.py Sections page (overview with editable rectangles)
    run_tab.py     Run & QC page, Batch page
    theme.py       light / dark palettes and stylesheet
    widgets.py     image viewer and small widgets
GUIDE_HiFiAlign.md       user guide (French)
Lancer HiFiAlign.command macOS launcher
main.py, image_registration/  original scripts (see README_original.md)
```

---

## Changes to the original scripts

The original pipeline (`main.py`) was fixed so that it runs with current library versions:

- `image_registration/czi.py`: the CZI path was joined twice when opening the file.
- `image_registration/image_processing.py`: `TiffWriter.save` (removed from recent `tifffile`) replaced by
  `TiffWriter.write`; the background file is looked up as `.czi`, then `.tif` / `.tiff`, with a clear error if
  none exists.
- `image_registration/registration.py`: channel names are stripped of trailing whitespace / newline characters
  before being written to the OME metadata.

Note for users of the original scripts: CZI files do not necessarily store channels in the order assumed by the
example `channel_name.csv` (the test files store Cy7, Cy5, Cy3, EGFP, DAPI). The original scripts assign markers
**by position**, so a CSV written in another order silently mislabels channels. HiFi Align assigns markers **by
channel name**.

---

## Known limitations

- Developed and tested on macOS (Apple Silicon) with Python 3.10; Windows and Linux have not been tested.
- Fast mode is less accurate (~1–2 µm); use precise mode for single-cell analyses.
- The non-rigid correction needs tissue structure; on very uniform or very small sections some grid points may
  remain unreliable (reported in the QC).
- The test images shipped in `czi/` are too small for the patch-based refinement; they are only useful to check
  that the pipeline runs end to end.

---

## Credits

- Original tool: [HiFiAlignmentTool](https://github.com/jhausserlab/HiFiAlignmentTool) (jhausserlab). See the
  upstream repository for its licence.
- HiFi Align (interface, out-of-core engine, non-rigid registration, translations and the changes listed above)
  was developed in this fork with the assistance of Claude Code (Anthropic).
