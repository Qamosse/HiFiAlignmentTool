# HiFi Align — guide d'utilisation

Interface graphique et moteur réécrit pour recaler des images multiplex (un fichier CZI ou TIFF par round),
pensés pour des lames entières de très grande taille (> 100 000 px). Les anciens scripts (`main.py`,
`image_registration/`) restent utilisables mais ne sont plus nécessaires.

## Lancer

- **Double-cliquer** sur `Lancer HiFiAlign.command` dans le Finder (la première fois : clic droit → Ouvrir).
- ou dans un terminal, depuis ce dossier :

```bash
conda run -n multiplex python -m hifialign
```

## Interface

Les étapes sont dans la barre latérale à gauche (raccourcis ⌘1 à ⌘5). En bas de cette barre, ou dans le menu
**Affichage** :

- **Thème** : clair, sombre ou comme le système (suit automatiquement le mode clair/sombre de macOS).
- **Langue** : français ou anglais. Tout est traduit : interface, journal, alertes du QC. Le projet en cours est conservé.

En ligne de commande, `--lang en` ou `--lang fr` choisit la langue du journal.

## Étapes

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

## Fichiers produits (dans le dossier de sortie)

| Fichier | Contenu |
|---|---|
| `<nom>_S01.ome.tif` … | Image finale par coupe : OME-TIFF pyramidal tuilé, compressé sans perte, noms des marqueurs et taille de pixel dans les métadonnées (s'ouvre dans QuPath). |
| `<nom>_S01_channels.txt` | Liste des canaux dans l'ordre. |
| `<nom>_QC/` | Superpositions avant/après (PNG) et `registration_qc.csv`. |
| `<nom>_QC/<nom>_markers.csv` | Tableau des marqueurs, réimportable pour une autre lame (Marqueurs → Importer un CSV). Option « Enregistrer le tableau des marqueurs (CSV) avec le QC », cochée par défaut. |
| `<nom>_project.hifi.json` | Copie du projet avec les transformations calculées (traçabilité). |

## Comment ça marche

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

## Ligne de commande (sans interface)

```bash
conda run -n multiplex python -m hifialign run lame1.hifi.json lame2.hifi.json
```

Options : `--register-only` (recalage et QC seulement) et `--write-only` (réutilise le recalage enregistré).

## Points d'attention

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
