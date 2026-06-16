# analyse-image

Automatisation OCR Python qui lit des images, extrait deux informations clés (type de document et numéro), et classe les images dans les bons dossiers.

## Fonctionnement

1. Déposer les images dans `image_a_traiter/`
2. Lancer `python traitement.py`
3. Les images sont classées automatiquement :
   - `image_traiter/` — traitées avec succès
   - `image_non_traitable/` — texte illisible ou infos introuvables
   - `doublon/` — image déjà traitée (détection par hash MD5)

## Informations extraites

- **type** : type de document (facture, devis, contrat, etc.)
- **numero** : numéro du document

## Exemple de sortie JSON

```json
[
  {
    "fichier": "facture_001.jpg",
    "statut": "traite",
    "informations": {
      "type": "Facture",
      "numero": "2068564"
    }
  }
]
```

## Stack technique

- Python 3.11
- pytesseract + Tesseract OCR (support français + anglais)
- Pillow (lecture d'images)
- Détection de doublons par hash MD5

## Formats d'images supportés

PNG, JPG, JPEG, TIFF, BMP, GIF, WEBP

## User preferences

- Language: French
