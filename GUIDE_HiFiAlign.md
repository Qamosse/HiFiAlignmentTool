# HiFi Align — User guide / Guide d'utilisation

**English** · [Français (version française ci-dessous)](#francais)

<a id="english"></a>

## HiFi Align — user guide

A graphical interface and rewritten engine for registering multiplex images (one CZI or TIFF file per round),
designed for very large whole slides (> 100,000 px). The legacy scripts (`main.py`, `image_registration/`)
still work but are no longer needed.

### Launching

- **Double-click** `Lanch_HiFiAlign.command` in the Finder (the first time: right-click → Open).
- or, in a terminal, from this folder:

```bash
conda run -n multiplex python -m hifialign
```

### Interface

The steps are listed in the left sidebar (shortcuts ⌘1 to ⌘5). At the bottom of the sidebar, or in the
**View** menu:

- **Theme**: light, dark, or same as system (automatically follows macOS light/dark mode).
- **Language**: French or English. Everything is translated: interface, log, QC warnings. The current project is kept.

On the command line, `--lang en` or `--lang fr` sets the language of the log.

### Steps

1. **Images**: add one file per round (button, or drag and drop a folder). Channels, image size and pixel size
   are read from the metadata. The round marked ★ is the reference. The order of the list sets the order of the
   channels in the final image. Option: background image (+ multiplier), subtracted channel by channel (same
   channel name) after registration.
2. **Markers**: a rounds × channels table (actual channel names from the file). Type the marker in each cell;
   an empty cell = channel not exported. The right-hand column shows the final image. The legacy tool's
   `channel_name.csv` can be imported/exported (matched **by channel name**, no longer by position).
   To reuse the markers on another slide acquired under the same conditions: "Export as CSV…" here, then
   "Import a CSV…" in the new project. Rounds are matched by name and, if the names differ (other dates in the
   file names), by the row order of the CSV; the matching is then displayed for you to check.
3. **Sections**: automatic detection of tissue sections on the DAPI of the reference round. One final image is
   produced per section, each section being registered independently. Rectangles can be moved, drawn manually,
   renamed, enabled/disabled; or choose "Whole slide".
4. **Options**: output folder and name (`<name>_S01.ome.tif`, …), pyramid, compression, output resolution,
   registration mode, number of processes, temporary folder.
5. **Run & QC**: "Register only" lets you check the QC before writing the images; "Generate images" then reuses
   the registration. The QC table gives, for each section × round, the shift, the rotation, the DAPI correlation
   before/after and the residual; orange rows should be checked. Click a row to see the overlay (magenta =
   reference, green = round, white = aligned). A round not acquired on a section has no preview: a message says
   so. If you reopen a project that has already been registered, the QC saved in `<name>_QC/` is reloaded
   automatically.
- **Batch**: a queue of projects processed one after the other. "Create projects from folders…" clones the
  current project (markers, options) for other slides: one folder = one slide, files being matched to rounds in
  alphabetical order.

File → Save saves the whole project (`*.hifi.json`), registration included.

### Output files (in the output folder)

| File | Content |
|---|---|
| `<name>_S01.ome.tif` … | Final image per section: tiled pyramidal OME-TIFF, losslessly compressed, with marker names and pixel size in the metadata (opens in QuPath). |
| `<name>_S01_channels.txt` | List of channels, in order. |
| `<name>_QC/` | Before/after overlays (PNG) and `registration_qc.csv`. |
| `<name>_QC/<name>_markers.csv` | Markers table, re-importable for another slide (Markers → Import a CSV…). Option "Save the markers table (CSV) with the QC", checked by default. |
| `<name>_project.hifi.json` | Copy of the project with the computed transformations (traceability). |

### How it works

- **Never the whole slide in memory**: every read covers a region only, directly from the CZI.
- **Structure images**: DAPI can change appearance from one round to the next (sharp nuclei, then faded DAPI
  where only autofluorescence remains). Registration therefore compares two representations and keeps the more
  reliable one at each step:
  - *structure*: nuclei removed by morphological opening, then log and 3–40 µm band-pass. What remains are
    vessels, holes, cracks, edges and the grey/white matter contrast.
  - *raw*: nuclei kept; the best option when both rounds have sharp DAPI.
- **Per-section registration, in 3 steps**: (1) coarse localisation at low resolution, (2) rigid refinement
  (translation + rotation) on patches with robust fitting, (3) **local deformation correction**: shift measured
  on a grid (400 µm by default), outlier measurements rejected, field smoothed then applied pixel by pixel.
  *Precise* mode: half resolution, 2 iterations. *Fast* mode: quarter resolution, 1 iteration, 2× coarser grid.
- **A single read**: each section is read once per round. Reference-round data are shared between processes
  via the temporary disk.
- **Parallelism**: registrations and channel warping (in strips) run in several processes; compressed
  OME-TIFF writing is multithreaded.
- **Temporary folder**: each section is assembled in a temporary file (2 bytes × channels × section pixels)
  then written as OME-TIFF. Put it on a fast local disk, not on the network or OneDrive.

### Command line (no interface)

```bash
conda run -n multiplex python -m hifialign run slide1.hifi.json slide2.hifi.json
```

Options: `--register-only` (registration and QC only) and `--write-only` (reuses the saved registration).

### Things to watch out for

- **CZI channel order**: the test files store channels in the order Cy7, Cy5, Cy3, EGFP, DAPI, whereas the
  legacy `channel_name.csv` assumed Cy3, Cy5, Cy7, GFP, DAPI. The legacy tool matched markers **by position**:
  check that your earlier results did not swap markers. The new tool matches by channel name.
- **Max. displacement between rounds** (Options page, 500 µm by default): increase it if a section moved a lot
  between two scans.
- **Reading the QC**: with DAPI that changes appearance, a structure correlation of 0.25 to 0.4 is normal.
  Look mainly at the overlay (Run & QC page) and at the "Max deformation". Several tens of µm indicate tissue
  that slid or folded; it is corrected, but the area deserves a look.
- **Round missing from an area**: if a round was not scanned on a section, its channels are left at 0 in that
  section's image, with a warning. The channel list stays the same for all sections.
- **Channel names**: "DAPI" also matches "DAPI_2", "DAPI-1", etc.

---

<a id="francais"></a>

## HiFi Align — guide d'utilisation

[English version above](#english) · **Français**

Interface graphique et moteur réécrit pour recaler des images multiplex (un fichier CZI ou TIFF par round),
pensés pour des lames entières de très grande taille (> 100 000 px). Les anciens scripts (`main.py`,
`image_registration/`) restent utilisables mais ne sont plus nécessaires.

### Lancer

- **Double-cliquer** sur `Lanch_HiFiAlign.command` dans le Finder (la première fois : clic droit → Ouvrir).
- ou dans un terminal, depuis ce dossier :

```bash
conda run -n multiplex python -m hifialign
```

### Interface

Les étapes sont dans la barre latérale à gauche (raccourcis ⌘1 à ⌘5). En bas de cette barre, ou dans le menu
**Affichage** :

- **Thème** : clair, sombre ou comme le système (suit automatiquement le mode clair/sombre de macOS).
- **Langue** : français ou anglais. Tout est traduit : interface, journal, alertes du QC. Le projet en cours est conservé.

En ligne de commande, `--lang en` ou `--lang fr` choisit la langue du journal.

### Étapes

1. **Images** : ajoutez un fichier par round (bouton ou glisser-déposer d'un dossier). Les canaux, la taille
   et la taille de pixel sont lus dans les métadonnées. Le round marqué ★ est la référence. L'ordre de la liste
   donne l'ordre des canaux dans l'image finale. Option : image de fond (+ multiplicateur), soustraite canal par
   canal (même nom de canal) après recalage.
2. **Marqueurs** : tableau rounds × canaux (noms réels des canaux du fichier). Écrivez le marqueur dans chaque
   case ; case vide = canal non exporté. La colonne de droite montre l'image finale. Import/export du
   `channel_name.csv` de l'ancien outil possible (correspondance **par nom de canal**, plus par position).
   Pour réutiliser les marqueurs sur une autre lame acquise dans les mêmes conditions : « Exporter en CSV… » ici,
   puis « Importer un CSV… » dans le nouveau projet. Les rounds sont associés par nom, et si les noms diffèrent
   (autres dates dans les noms de fichiers), par l'ordre des lignes du CSV ; l'association est alors affichée pour
   vérification.
3. **Coupes** : détection automatique des coupes sur le DAPI du round de référence. Une image finale est
   produite par coupe, chaque coupe étant recalée indépendamment. Rectangles déplaçables, dessin manuel,
   renommage, activation/désactivation ; ou « Lame entière ».
4. **Options** : dossier et nom de sortie (`<nom>_S01.ome.tif`, …), pyramide, compression, résolution de
   sortie, mode de recalage, nombre de processus, dossier temporaire.
5. **Exécution et QC** : « Recaler seulement » permet de vérifier le QC avant d'écrire les images ;
   « Générer les images » réutilise ensuite le recalage. Le tableau QC donne, pour chaque coupe × round, le
   décalage, la rotation, la corrélation DAPI avant/après et le résidu ; les lignes orange sont à vérifier.
   Cliquez une ligne pour voir la superposition (magenta = référence, vert = round, blanc = aligné). Un round
   non acquis sur une coupe n'a pas d'aperçu : un message l'indique. Si vous rouvrez un projet déjà recalé, le QC
   enregistré dans `<nom>_QC/` est rechargé automatiquement.
- **Lots** : file de projets traités l'un après l'autre. « Créer des projets à partir de dossiers » clone le
  projet courant (marqueurs, options) pour d'autres lames : un dossier = une lame, les fichiers étant associés
  aux rounds par ordre alphabétique.

Fichier → Enregistrer sauve tout le projet (`*.hifi.json`), recalage compris.

### Fichiers produits (dans le dossier de sortie)

| Fichier | Contenu |
|---|---|
| `<nom>_S01.ome.tif` … | Image finale par coupe : OME-TIFF pyramidal tuilé, compressé sans perte, noms des marqueurs et taille de pixel dans les métadonnées (s'ouvre dans QuPath). |
| `<nom>_S01_channels.txt` | Liste des canaux dans l'ordre. |
| `<nom>_QC/` | Superpositions avant/après (PNG) et `registration_qc.csv`. |
| `<nom>_QC/<nom>_markers.csv` | Tableau des marqueurs, réimportable pour une autre lame (Marqueurs → Importer un CSV). Option « Enregistrer le tableau des marqueurs (CSV) avec le QC », cochée par défaut. |
| `<nom>_project.hifi.json` | Copie du projet avec les transformations calculées (traçabilité). |

### Comment ça marche

- **Jamais la lame entière en mémoire** : chaque lecture porte sur une région, directement dans le CZI.
- **Images de structure** : le DAPI peut changer d'aspect d'un round à l'autre (noyaux nets, puis DAPI
  délavé où ne reste que l'autofluorescence). Le recalage compare donc deux représentations, et garde à chaque
  étape la plus fiable :
  - *structure* : noyaux effacés par ouverture morphologique, puis log et passe-bande 3–40 µm. Il reste les
    vaisseaux, trous, fissures, bords et le contraste substance grise/blanche.
  - *brute* : noyaux conservés, la meilleure option quand les deux rounds ont un DAPI net.
- **Recalage par coupe, en 3 étapes** : (1) localisation grossière à basse résolution, (2) affinage rigide
  (translation + rotation) sur des patchs avec ajustement robuste, (3) **correction des déformations locales** :
  décalage mesuré sur une grille (400 µm par défaut), mesures aberrantes rejetées, champ lissé puis appliqué
  pixel par pixel. Mode *précis* : demi-résolution, 2 itérations. Mode *rapide* : quart de résolution,
  1 itération, grille 2× plus lâche.
- **Une seule lecture** : chaque coupe est lue une fois par round. Les données du round de référence sont
  partagées entre les processus via le disque temporaire.
- **Parallélisme** : les recalages et la déformation des canaux (par bandes) tournent dans plusieurs processus ;
  l'écriture compressée de l'OME-TIFF est multithread.
- **Dossier temporaire** : chaque coupe est assemblée dans un fichier temporaire (2 octets × canaux × pixels de
  la coupe) puis écrite en OME-TIFF. Mettez-le sur un disque local rapide, pas sur le réseau ni OneDrive.

### Ligne de commande (sans interface)

```bash
conda run -n multiplex python -m hifialign run lame1.hifi.json lame2.hifi.json
```

Options : `--register-only` (recalage et QC seulement) et `--write-only` (réutilise le recalage enregistré).

### Points d'attention

- **Ordre des canaux CZI** : les fichiers de test stockent les canaux dans l'ordre Cy7, Cy5, Cy3, EGFP, DAPI,
  alors que l'ancien `channel_name.csv` supposait Cy3, Cy5, Cy7, GFP, DAPI. L'ancien outil associait les
  marqueurs **par position** : vérifiez que vos anciens résultats n'ont pas inversé des marqueurs. Le nouvel
  outil associe par nom de canal.
- **Déplacement maximal entre rounds** (page Options, 500 µm par défaut) : à augmenter si une coupe a beaucoup
  bougé entre deux scans.
- **Lire le QC** : avec un DAPI qui change d'aspect, une corrélation de structure de 0,25 à 0,4 est normale.
  Regardez surtout la superposition (page Exécution) et la « déformation max ». Plusieurs dizaines de µm
  signalent un tissu qui a glissé ou s'est plissé ; c'est corrigé, mais la zone mérite un coup d'œil.
- **Round absent d'une zone** : si un round n'a pas été scanné sur une coupe, ses canaux sont laissés à 0 dans
  l'image de cette coupe, avec une alerte. La liste des canaux reste la même pour toutes les coupes.
- **Noms de canaux** : « DAPI » reconnaît aussi « DAPI_2 », « DAPI-1 », etc.
