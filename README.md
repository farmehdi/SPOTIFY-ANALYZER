# Analyseur de Données RGPD Spotify

Un outil Python pour analyser votre historique d'écoute Spotify à partir des exports de données RGPD.

## Fonctionnalités

- Import d'exports multiples - Gère les anciens et nouveaux formats d'export Spotify
- Déduplication - Ignore automatiquement les fichiers déjà importés
- Analyses riches - Génère des visualisations et statistiques sur vos habitudes d'écoute
- Stockage SQLite - Toutes les données sont stockées localement dans une base de données simple

## Installation
# Cloner le dépôt
git clone https://github.com/votreusername/spotify-gdpr-analyzer.git
cd spotify-gdpr-analyzer

# Installer les dépendances
pip install pandas matplotlib typer python-dateutil
## Obtenir vos données Spotify

1. Rendez-vous sur vos [Paramètres de confidentialité Spotify](https://www.spotify.com/account/privacy/)
2. Faites défiler et demandez "Données du compte" ou "Historique d'écoute étendu"
3. Attendez que Spotify vous envoie un email (peut prendre jusqu'à 30 jours)
4. Téléchargez et extrayez le fichier ZIP

## Utilisation

### Initialiser la base de données
python spotify_analyzer.py init
### Importer vos données
python spotify_analyzer.py import-export /chemin/vers/votre/export/spotify
Vous pouvez exécuter cette commande plusieurs fois avec différents exports - les doublons sont automatiquement détectés et ignorés.

### Voir les statistiques
python spotify_analyzer.py stats
### Générer un rapport
python spotify_analyzer.py report
Cela crée un dossier report/ contenant :
- report.md - Résumé Markdown avec les statistiques clés
- listening_by_hour.png - Vos habitudes d'écoute par heure de la journée
- listening_by_weekday.png - Vos habitudes d'écoute par jour de la semaine
- top_artists.png - Vos 15 artistes les plus écoutés

## Formats de fichiers supportés

L'outil détecte et importe automatiquement :
- StreamingHistory*.json (ancien format)
- endsong*.json (format historique étendu)

Les morceaux de musique et les épisodes de podcast sont tous deux supportés.

## Schéma de la base de données

L'outil utilise SQLite avec deux tables principales :

- imports - Suit les fichiers qui ont été importés
- events - Événements d'écoute individuels avec horodatages, infos de piste et durée

## Gestion des fuseaux horaires

Tous les horodatages sont stockés en UTC et en heure locale (Europe/Paris). Vous pouvez modifier la constante PARIS dans le code pour utiliser votre fuseau horaire.

## Prérequis

- Python 3.7+
- pandas
- matplotlib
- typer
- python-dateutil

## Licence

MIT

## Contribution

Les pull requests sont les bienvenues ! N'hésitez pas à ouvrir des issues pour signaler des bugs ou demander de nouvelles fonctionnalités.
