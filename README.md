# Analyseur RGPD Spotify

Outil qui analyse un export RGPD Spotify (StreamingHistory_music / StreamingHistory_podcast).
- Importer les écoutes dans une base SQLite locale
- Analyser (minutes totales, par heure, par jour, top artistes)
- Génération d'un rapport Markdown + graphiques
- Mise à jour incrémentale : relancer l'import n'ajoute pas de doublons

## Confidentialité (RGPD)
Les fichiers d'export Spotify (JSON/ZIP) sont des données personnelles : ils ne doivent jamais être commit sur GitHub.
La base `spotify.sqlite` et le dossier `report/` restent en local.

## Installation (Windows)
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install pandas matplotlib typer python-dateutil
python .\spotify_tool.py initialisation
python .\spotify_tool.py import-export "CHEMIN_VERS_LE_DOSSIER_D'EXPORTATION_SPOTIFY"
python .\spotify_tool.py rapport
python .\spotify_tool.py stats
Mise à jour : relancer la commande import-export sur le même dossier doit afficher rows_inserted : 0 et files_skipped : 2.
