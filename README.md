# Phrasio

Apprends une langue avec **tes propres phrases du quotidien**. Tu écris (ou dictes) une phrase dans ta langue, Phrasio la traduit et crée un fichier audio :

> phrase originale · pause · traduction · pause · traduction · pause plus longue

Les phrases sont regroupées en leçons MP3 à écouter sur ton téléphone, en auto ou en marchant.

**100 % local et gratuit** : pas de compte, pas de clé, pas de carte de crédit. La traduction (Argos Translate) et les voix (Piper) tournent sur ton ordinateur. Internet sert seulement à télécharger les modèles la première fois.

## 1. Installer (Windows)

1. Installe [Python 3.12](https://www.python.org/downloads/) (recommandé pour la compatibilité des librairies). À l'installation, **coche « Add python.exe to PATH »**.
2. Décompresse le dossier `phrasio` où tu veux (ailleurs que dans le dossier synchronisé).
3. Double-clique sur **`installer.bat`**. Compte 5 à 10 minutes : environ 1 Go de librairies à télécharger (surtout pour la traduction).
4. Double-clique sur **`lancer.bat`**.

## 2. Premier lancement

La fenêtre des paramètres s'ouvre :

- **Langues** : choisis ta langue, la langue à apprendre et une voix pour chacune (une quarantaine de langues).
- **Dossier** : choisis ton dossier de travail, par exemple `C:\Users\toi\OneDrive\Phrasio`.

Clique sur **Enregistrer**. Phrasio télécharge alors, une seule fois :

- les deux voix (environ 60 à 120 Mo chacune) ;
- les modèles de traduction (environ 100 Mo par paire de langues).

La barre du bas indique la progression. Quand elle affiche « Prêt », tout fonctionne hors ligne.

**Bon à savoir** : si aucun modèle direct n'existe (ex. français vers espagnol), Phrasio passe par l'anglais (français → anglais → espagnol). C'est automatique. La traduction est correcte mais pas parfaite : relis-la et corrige-la au besoin avant d'ajouter la phrase.

## 3. Utilisation

| Action | Comment |
|---|---|
| Écrire une phrase | Tape dans « Je dis » |
| Dicter | Clique dans le champ, puis **Windows + H** |
| Traduire | **Entrée** ou le bouton « Traduire » |
| Corriger la traduction | Modifie directement le champ de droite |
| Écouter avant d'ajouter | « Écouter » |
| Ajouter | **Ctrl + Entrée** ou « Ajouter » (traduit automatiquement si besoin) |
| Réécouter, modifier, supprimer | Boutons ▶ ✎ ✕ de chaque phrase |
| Créer les leçons | « Générer les leçons » |

**Astuce** : tu peux aussi modifier `phrases.csv` dans Excel (ferme-le ensuite), puis cliquer sur **Synchroniser**. Seules les phrases modifiées sont régénérées.

## 4. Écouter sur ton téléphone

Les leçons sont dans `lecons/<langue>/` de ton dossier :

- `00 - nouvelles phrases (7 derniers jours).mp3`
- `00 - toutes les phrases.mp3`
- `lecon-01 (1-20).mp3`, `lecon-02 (21-40).mp3`, etc.

Ouvre l'application OneDrive (ou Google Drive) sur ton téléphone et touche un fichier pour l'écouter. Tu peux aussi le rendre disponible hors ligne.

## 5. Réglages audio

Dans **Paramètres > Audio** :

- **Pauses** : ajuste le temps pour répéter à voix haute.
- **Vitesse** : ralentis la langue cible au début (-15 % ou -30 %).
- **Ordre** : « Langue cible d'abord » pour t'exercer à comprendre avant d'entendre la traduction.

Après un changement de réglage, clique sur **Synchroniser** pour régénérer l'audio.

## Structure du dossier

```
<ton dossier>/
  phrases.csv                 toutes tes phrases (s'ouvre dans Excel)
  audio/es-MX/0001.mp3        une phrase par fichier
  lecons/es-MX/*.mp3          les leçons assemblées
```

Tu peux apprendre plusieurs langues dans le même dossier : chaque langue cible a ses propres sous-dossiers.

## Où sont les modèles

| Quoi | Où |
|---|---|
| Paramètres | `%APPDATA%\Phrasio\config.json` |
| Voix Piper | `%APPDATA%\Phrasio\voices\` |
| Modèles de traduction | `%USERPROFILE%\.local\share\argos-translate\` |

Tu peux supprimer une voix ou un modèle : il sera retéléchargé au besoin.

## Pour aller plus loin (publication)

- **Exécutable Windows** : PyInstaller peut produire un `.exe`, mais avec Argos Translate (et PyTorch) le paquet sera volumineux. Un installateur (Inno Setup, par exemple) qui installe Python et les librairies est souvent plus simple.
- **Licences** : Piper est sous licence GPL, et chaque voix a sa propre licence (voir le fichier `MODEL_CARD` de la voix). Argos Translate est sous licence MIT. Vérifie-les avant de publier.
- **Idées** : bouton micro intégré (Whisper en local), interface multilingue, révision espacée, export vers Anki.

## Fichiers du code

| Fichier | Rôle |
|---|---|
| `app.py` | Interface (CustomTkinter) |
| `local_engine.py` | Traduction (Argos) et voix (Piper), téléchargement des modèles |
| `audio.py` | Pauses, encodage MP3 et assemblage des leçons |
| `store.py` | Lecture et écriture de `phrases.csv` |
| `config.py` | Paramètres de l'utilisateur |
