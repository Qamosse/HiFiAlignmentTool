# English translations, keyed by the French source strings used in tr() calls.
# Keep the {placeholders} identical (checked by the translation coverage test).
EN = {
    # ---------------------------------------------------------------- window, sidebar, menus
    'ÉTAPES': 'STEPS',
    'AUTRES': 'OTHER',
    'APPARENCE': 'APPEARANCE',
    'Lots': 'Batch',
    'Fichier': 'File',
    'Importer un channel_name.csv…': 'Import a channel_name.csv…',
    'Exporter en CSV…': 'Export as CSV…',
    'Affichage': 'View',
    'Thème': 'Theme',
    'Langue': 'Language',
    'Aide': 'Help',
    'À propos': 'About',
    'nouveau projet': 'new project',
    'Ouvrir un projet': 'Open a project',
    'Projets (*{ext})': 'Projects (*{ext})',
    'Enregistré : {path}': 'Saved: {path}',
    'Enregistrer le projet': 'Save the project',
    "Recalage d'images multiplex": 'Multiplex image registration',
    'Images': 'Images',
    'Marqueurs': 'Markers',
    'Coupes': 'Sections',
    'Options': 'Options',
    'Exécution et QC': 'Run & QC',
    'Thème : système': 'Theme: system',
    'Thème : clair': 'Theme: light',
    'Thème : sombre': 'Theme: dark',
    'Nouveau projet': 'New project',
    'Ouvrir un projet…': 'Open a project…',
    'Enregistrer': 'Save',
    'Enregistrer sous…': 'Save as…',
    'Comme le système': 'Same as system',
    'Clair': 'Light',
    'Sombre': 'Dark',
    'La langue pourra être changée à la fin du traitement.': 'The language can be changed once processing has '
                                                             'finished.',
    'Fichiers introuvables': 'Files not found',
    "HiFi Align {v}\nRecalage d'images multiplex (rounds CZI/TIFF), traitement par coupe, sortie OME-TIFF "
    "pyramidale.\nBasé sur HiFiAlignmentTool (jhausserlab).":
        'HiFi Align {v}\nMultiplex image registration (CZI/TIFF rounds), per-section processing, pyramidal '
        'OME-TIFF output.\nBased on HiFiAlignmentTool (jhausserlab).',
    'Abandonner le projet courant (non enregistré) ?': 'Discard the current (unsaved) project?',
    'Ouverture impossible': 'Cannot open',
    'Traitement en cours': 'Processing in progress',
    'Un traitement est en cours. Annuler et quitter ?': 'Processing is running. Cancel it and quit?',
    'Images introuvables (partage réseau monté ?) :': 'Images not found (is the network share mounted?):',

    # ---------------------------------------------------------------- run page
    '{m} min {s:02d} s': '{m} min {s:02d} s',
    'Exécution et contrôle qualité': 'Run & quality control',
    "« Recaler seulement » permet de vérifier le QC avant d'écrire les images ; « Générer les images » réutilise "
    "ensuite ce recalage.":
        '“Register only” lets you check the QC before writing the images; “Generate images” then reuses that '
        'registration.',
    'Recaler seulement': 'Register only',
    'Calcule le recalage et le QC sans écrire les images finales.': 'Computes the registration and the QC without '
                                                                    'writing the final images.',
    'Générer les images': 'Generate images',
    'Écrit les images finales en réutilisant le recalage existant.': 'Writes the final images, reusing the existing '
                                                                     'registration.',
    'Ouvrir le dossier de sortie': 'Open output folder',
    'Prêt.': 'Ready.',
    'Contrôle qualité du recalage': 'Registration quality control',
    'Avant': 'Before',
    'Après': 'After',
    'Lancez un recalage pour voir ici la superposition avant/après de chaque round.':
        'Run a registration to see the before/after overlay of each round here.',
    'Journal': 'Log',
    'Démarrage…': 'Starting…',
    '{t} écoulées': '{t} elapsed',
    'Terminé.': 'Done.',
    'lame': 'slide',
    'fond': 'background',
    'Traitement par lots': 'Batch processing',
    "Chaque élément est un fichier projet (*.hifi.json), par exemple une lame. Ils sont traités l'un après l'autre ; "
    "le journal et le QC s'affichent dans la page « Exécution ».":
        'Each item is a project file (*.hifi.json), for instance one slide. They are processed one after the '
        'other; the log and QC are shown on the “Run” page.',
    'Projets': 'Projects',
    '▶  Tout lancer (recalage + images)': '▶  Run all (registration + images)',
    'Annuler': 'Cancel',
    'Cliquez une ligne pour voir la superposition. Lignes orange : à vérifier.':
        'Click a row to see the overlay. Orange rows: to be checked.',
    'Coupe': 'Section',
    'Round': 'Round',
    'Décalage x/y (µm)': 'Shift x/y (µm)',
    'Rotation (°)': 'Rotation (°)',
    'Corr. avant': 'Corr. before',
    'Corr. après': 'Corr. after',
    'Patchs rigides': 'Rigid patches',
    'Déformation max (µm)': 'Max deformation (µm)',
    'Points de grille': 'Grid points',
    'Alertes': 'Warnings',
    'superposé': 'overlap',
    'référence': 'reference',
    'round': 'round',
    'Annulation en cours (fin des tâches en cours)…': 'Cancelling (waiting for running tasks)…',
    "Pas d'aperçu pour cette ligne.": 'No preview for this row.',
    "Pas d'aperçu : {msg}": 'No preview: {msg}',
    'Contrôle qualité du dernier recalage (rechargé depuis {d}).': 'Quality control of the last registration '
                                                                   '(reloaded from {d}).',
    'Ajouter des projets…': 'Add projects…',
    'Ajouter le projet courant': 'Add current project',
    'Retirer': 'Remove',
    'Créer des projets à partir de dossiers…': 'Create projects from folders…',
    '▶  Lancer le lot': '▶  Run batch',
    "Configurez d'abord un projet modèle (images, marqueurs, options).": 'First set up a template project (images, '
                                                                         'markers, options).',
    "Dossier d'une lame ({n} choisi(s) — Annuler pour terminer)": 'Folder of one slide ({n} selected — Cancel to '
                                                                   'finish)',
    "{n} projet(s) créé(s). Les fichiers de chaque dossier sont associés aux rounds dans l'ordre alphabétique : "
    "vérifiez-les en ouvrant les projets si besoin.":
        '{n} project(s) created. The files of each folder are assigned to the rounds in alphabetical order: open '
        'the projects to check them if needed.',
    'Projets invalides': 'Invalid projects',
    'Projet incomplet': 'Incomplete project',
    '{d} : {n} image(s) pour {r} rounds — ignoré.': '{d}: {n} image(s) for {r} rounds — skipped.',
    '⛔ Annulé.': '⛔ Cancelled.',
    'Annulé': 'Cancelled',
    'Recalage': 'Registration',
    'Aucun recalage valide pour la configuration actuelle. Lancer le recalage puis générer les images ?':
        'No valid registration for the current settings. Run the registration, then generate the images?',
    '❌ Erreur : {e}': '❌ Error: {e}',
    'Fichiers créés :': 'Files created:',

    # ---------------------------------------------------------------- sections page
    'Chaque coupe produit sa propre image finale (recalage indépendant par coupe). Détection automatique sur le '
    'canal de référence du round de référence ; vous pouvez déplacer les rectangles, en dessiner, les renommer ou '
    'les désactiver. Molette = zoom, glisser = déplacer la vue, double-clic = vue entière.':
        'Each section produces its own final image (registered independently). Sections are detected '
        'automatically on the reference channel of the reference round; you can move the rectangles, draw new '
        'ones, rename or disable them. Wheel = zoom, drag = pan, double-click = whole view.',
    'Lame entière (une seule image, pas de découpage)': 'Whole slide (a single image, no sections)',
    "Recharger l'aperçu": 'Reload preview',
    "Ajoutez des images (étape 1) pour afficher l'aperçu du round de référence.":
        'Add images (step 1) to display the overview of the reference round.',
    "Aire minimale d'une coupe :": 'Minimum section area:',
    'Marge autour des coupes :': 'Margin around sections:',
    'Fusionner les fragments à moins de :': 'Merge fragments closer than:',
    'Dessiner une coupe': 'Draw a section',
    "Chargement de l'aperçu…": 'Loading preview…',
    'Aperçu : {w} × {h} px (échelle 1/{s:.0f}).': 'Preview: {w} × {h} px (scale 1/{s:.0f}).',
    'Détection en cours…': 'Detecting…',
    '{n} coupe(s) détectée(s).': '{n} section(s) detected.',
    'Canal affiché :': 'Displayed channel:',
    'Actif': 'Active',
    'Nom': 'Name',
    'largeur': 'width',
    'hauteur': 'height',
    'Détecter automatiquement': 'Detect automatically',
    'Supprimer': 'Delete',
    'Tout supprimer': 'Delete all',
    'Renuméroter': 'Renumber',
    'Aperçu impossible : {err}': 'Cannot display preview: {err}',
    'Détection': 'Detection',
    'Remplacer les coupes existantes ?': 'Replace the existing sections?',

    # ---------------------------------------------------------------- images page
    'Images (*.czi *.tif *.tiff);;Tous les fichiers (*)': 'Images (*.czi *.tif *.tiff);;All files (*)',
    "Ajoutez une image par round (CZI ou TIFF). Les canaux et la taille de pixel sont lus dans les métadonnées. "
    "L'ordre de la liste = l'ordre des canaux dans l'image finale. Vous pouvez aussi glisser-déposer des fichiers "
    "ou un dossier dans la fenêtre.":
        'Add one image per round (CZI or TIFF). Channels and pixel size are read from the metadata. The order of '
        'the list is the order of the channels in the final image. You can also drag and drop files or a folder '
        'onto the window.',
    'Référence et fond': 'Reference and background',
    'Canal de référence (recalage) :': 'Reference channel (registration):',
    'Image de fond': 'Background image',
    'Aucun': 'None',
    'Image de fond (optionnel) :': 'Background image (optional):',
    'Multiplicateur du fond :': 'Background multiplier:',
    'auto (métadonnées)': 'auto (metadata)',
    'Taille de pixel (µm) :': 'Pixel size (µm):',
    'Ajouter des images (rounds)': 'Add images (rounds)',
    '＋ Ajouter des images…': '＋ Add images…',
    '▲ Monter': '▲ Move up',
    '▼ Descendre': '▼ Move down',
    '★ Définir comme référence': '★ Set as reference',
    'Nom du round': 'Round name',
    'Canaux (ordre du fichier)': 'Channels (file order)',
    'Taille (px)': 'Size (px)',
    'Pixel (µm)': 'Pixel (µm)',
    'Fichiers non lus': 'Files not read',
    'Fichier introuvable': 'File not found',
    'Fichier introuvable (partage réseau monté ?)': 'File not found (is the network share mounted?)',
    'Round de référence : tous les autres sont recalés sur lui.': 'Reference round: all the others are registered '
                                                                  'onto it.',
    'erreur': 'error',
    'Fond illisible': 'Unreadable background',
    'Fond': 'Background',
    'Canaux du fond : {chans}\nLes canaux absents du fond ne seront pas corrigés.':
        'Background channels: {chans}\nChannels missing from the background will not be corrected.',
    'Nom déjà utilisé': 'Name already used',
    "Un autre round s'appelle déjà « {name} ».": 'Another round is already called “{name}”.',
    'Parcourir…': 'Browse…',

    # ---------------------------------------------------------------- markers page
    "Indiquez le marqueur imagé dans chaque canal de chaque round. Case vide = canal non exporté. Les cases grisées "
    "n'existent pas dans le fichier. Les colonnes sont les noms réels des canaux lus dans les fichiers (pas besoin "
    "de connaître leur ordre).":
        'Enter the marker imaged in each channel of each round. Empty cell = channel not exported. Greyed-out cells '
        'do not exist in the file. Columns are the actual channel names read from the files (no need to know their '
        'order).',
    'Image finale : {n} canaux': 'Final image: {n} channels',
    'Importer channel_name.csv': 'Import channel_name.csv',
    'Exporter le CSV': 'Export the CSV',
    'Importer un CSV…': 'Import a CSV…',
    'Import CSV': 'CSV import',
    'Import effectué avec des avertissements :': 'Import done, with warnings:',
    ' (réf.)': ' (ref.)',
    '{label} — canal {pos} du fichier : {col}': '{label} — file channel {pos}: {col}',
    '   ⚠ doublon': '   ⚠ duplicate',

    # ---------------------------------------------------------------- options page
    'Emplacement et format des images finales, méthode de recalage et ressources de calcul.':
        'Location and format of the final images, registration method and computing resources.',
    'Image(s) finale(s)': 'Final image(s)',
    'Dossier de sortie': 'Output folder',
    'Dossier de sortie :': 'Output folder:',
    'Nom de base :': 'Base name:',
    'Pyramidale (recommandé pour QuPath)': 'Pyramidal (recommended for QuPath)',
    'Compression (sans perte) :': 'Compression (lossless):',
    'zlib (recommandé)': 'zlib (recommended)',
    'aucune': 'none',
    'Résolution de sortie (1 = pleine) :': 'Output resolution (1 = full):',
    'Garder le canal de référence de chaque round': 'Keep the reference channel of every round',
    'Noms complets « marqueur|canal|round »': 'Full names “marker|channel|round”',
    'Enregistrer le contrôle qualité (PNG + CSV)': 'Save the quality control (PNG + CSV)',
    'Performances': 'Performance',
    'auto ({n})': 'auto ({n})',
    'Processus parallèles :': 'Parallel processes:',
    'Dossier temporaire': 'Temporary folder',
    'Dossier temporaire :': 'Temporary folder:',
    'Précis : mesures à 1/2 résolution, 2 itérations (≈ 0,1–0,5 µm)': 'Precise: measured at 1/2 resolution, '
                                                                       '2 iterations (≈ 0.1–0.5 µm)',
    'Rapide : mesures à 1/4 résolution, 1 itération (≈ 1–2 µm)': 'Fast: measured at 1/4 resolution, 1 iteration '
                                                                 '(≈ 1–2 µm)',
    'Corriger aussi la rotation (rigide)': 'Also correct rotation (rigid)',
    'Corriger les déformations locales du tissu (non rigide)': 'Correct local tissue deformation (non-rigid)',
    'Mesure le décalage local sur une grille de points et corrige les étirements, glissements ou plis du tissu '
    'entre les rounds.':
        'Measures the local shift on a grid of points and corrects stretching, sliding or folding of the tissue '
        'between rounds.',
    'Espacement de la grille de déformation :': 'Deformation grid spacing:',
    'Déplacement max. entre rounds :': 'Max. displacement between rounds:',
    "Nombre de patchs d'affinage :": 'Number of refinement patches:',
    'Taille des patchs :': 'Patch size:',
    '{d} — {free:.0f} Go libres.': '{d} — {free:.0f} GB free.',
    '{d} — inaccessible.': '{d} — not accessible.',
    'Utilisez un disque local rapide (pas OneDrive ni le réseau) : il faut ~2 octets × canaux × pixels de la plus '
    'grande coupe.':
        'Use a fast local disk (not OneDrive or the network): it needs ~2 bytes × channels × pixels of the largest '
        'section.',

    # ---------------------------------------------------------------- engine: log messages
    'Recalage : {n} paire(s) section × round à traiter (mode {mode}).': 'Registration: {n} section × round pair(s) '
                                                                         'to process ({mode} mode).',
    'précis': 'precise',
    'rapide': 'fast',
    'lame entière': 'whole slide',
    'Coupe {name} ({i}/{n}) : {C} canaux × {W} × {H} px ({gb:.1f} Go non compressé) → {out}':
        'Section {name} ({i}/{n}): {C} channels × {W} × {H} px ({gb:.1f} GB uncompressed) → {out}',
    'Écriture {name}': 'Writing {name}',
    '{n} processus de calcul, dossier temporaire : {d}': '{n} worker processes, temporary folder: {d}',
    'Terminé en {t}.': 'Finished in {t}.',
    'Aucune image (round) dans le projet.': 'No image (round) in the project.',
    'Deux rounds ont le même nom : les noms doivent être uniques.': 'Two rounds have the same name: names must be '
                                                                    'unique.',
    'Choisissez un dossier de sortie.': 'Choose an output folder.',
    'Aucun canal à exporter (tous les marqueurs sont vides).': 'No channel to export (all markers are empty).',
    'Le facteur de réduction doit être entre 0 et 1.': 'The downscale factor must be between 0 and 1.',
    '  ⚠ {name} / {label} : aucune donnée acquise dans cette zone → canaux laissés vides (0).':
        '  ⚠ {name} / {label}: no data acquired in this area → channels left empty (0).',
    'Préparation de la référence': 'Preparing the reference',
    "  jusqu'à {n} recalage(s) en parallèle (~{gb:.1f} Go chacun).": '  up to {n} registration(s) in parallel '
                                                                      '(~{gb:.1f} GB each).',
    'Recalage non effectué.': 'Registration not done.',
    'Espace insuffisant dans le dossier temporaire {d} : {free:.0f} Go libres, ~{need:.0f} Go nécessaires.':
        'Not enough space in the temporary folder {d}: {free:.0f} GB free, ~{need:.0f} GB needed.',
    'Déformation {name}': 'Warping {name}',
    '  canaux recalés en {s:.1f} s': '  channels warped in {s:.1f} s',
    '  OME-TIFF écrit en {s:.1f} s': '  OME-TIFF written in {s:.1f} s',
    'Fichier introuvable : {path}': 'File not found: {path}',
    '{label} : pas de canal de référence "{ch}" (canaux : {chans})': '{label}: no reference channel "{ch}" '
                                                                     '(channels: {chans})',
    'Fichier de fond introuvable : {path}': 'Background file not found: {path}',
    '  ⚠ {lab} absent de {name} : ses canaux sont vides (0) dans cette image.':
        '  ⚠ {lab} missing from {name}: its channels are empty (0) in this image.',
    '{label} : le canal "{ch}" n\'existe pas dans le fichier.': '{label}: channel "{ch}" does not exist in the file.',
    'Fond : pas de canal de référence "{ch}".': 'Background: no reference channel "{ch}".',
    'Round non acquis dans cette zone : canaux vides.': 'Round not acquired in this area: empty channels.',
    'Dossier de sortie inaccessible : {e}': 'Output folder not accessible: {e}',
    'Transformations absentes ou obsolètes : nouveau recalage.': 'Transforms missing or outdated: registering again.',
    '  {name} / {label} : décalage ({sx:+.1f}, {sy:+.1f}) px, rotation {rot:+.3f}°, corrélation {c0:.2f} → '
    '{c1:.2f}, {ni}/{np} patchs, résidu {res:.2f} px':
        '  {name} / {label}: shift ({sx:+.1f}, {sy:+.1f}) px, rotation {rot:+.3f}°, correlation {c0:.2f} → '
        '{c1:.2f}, {ni}/{np} patches, residual {res:.2f} px',
    'Contrôle qualité enregistré dans {d}': 'Quality control saved in {d}',
    ', déformation locale ≤ {d:.1f} µm ({v}/{n} points)': ', local deformation ≤ {d:.1f} µm ({v}/{n} points)',
    'Aucun round actif dans le projet.': 'No active round in the project.',
    'CSV vide': 'Empty CSV',
    'Noms de rounds différents : association par ordre des lignes, à vérifier :\n  {pairs}':
        'Round names differ: rounds matched by row order, please check:\n  {pairs}',
    'Lignes du CSV sans round correspondant (ignorées) : {labels}': 'CSV rows without a matching round (ignored): '
                                                                    '{labels}',
    'Rounds du projet sans ligne dans le CSV (marqueurs inchangés) : {labels}': 'Project rounds without a CSV row '
                                                                                '(markers unchanged): {labels}',
    '{label} : canal "{col}" (marqueur "{val}") absent du fichier (canaux : {chans})':
        '{label}: channel "{col}" (marker "{val}") not in the file (channels: {chans})',

    # ---------------------------------------------------------------- engine: registration warnings
    'Recalage grossier peu fiable (corrélation {score:.2f}).': 'Unreliable coarse registration (correlation '
                                                               '{score:.2f}).',
    'Corrélation de structure faible après recalage ({v:.2f}) : à vérifier.': 'Low structure correlation after '
                                                                             'registration ({v:.2f}): please check.',
    'Affinage rigide : seulement {k} patch(s) exploitable(s), recalage grossier conservé.':
        'Rigid refinement: only {k} usable patch(es), coarse registration kept.',
    'Déformation locale : seulement {v}/{n} points fiables.': 'Local deformation: only {v}/{n} reliable points.',
    'Affinage rigide : ajustement robuste impossible, recalage grossier conservé.':
        'Rigid refinement: robust fit failed, coarse registration kept.',
    'Affinage rigide : trop peu de patchs concordants.': 'Rigid refinement: too few consistent patches.',
    'pystackreg a échoué : {e}': 'pystackreg failed: {e}',

    'Tableau des marqueurs enregistré : {path}': 'Markers table saved: {path}',
    'Enregistrer le tableau des marqueurs (CSV) avec le QC': 'Save the markers table (CSV) with the QC',
    'Copie du tableau de la page Marqueurs dans le dossier <nom>_QC, réimportable pour une autre lame (Marqueurs → '
    'Importer un CSV).': 'Copy of the Markers table in the <name>_QC folder, re-importable for another slide '
                          '(Markers → Import a CSV).',

    # ---------------------------------------------------------------- command line
    'ERREUR : {e}': 'ERROR: {e}',
}
