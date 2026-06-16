#!/usr/bin/env python3
"""
image_utils.py
==============
Module partagé — chargement et prétraitement des images.
Utilisé par ocr.py et ocr_easy.py pour éviter la duplication de code.

PRÉREQUIS
---------
  pip install Pillow requests

Aucun chemin à configurer ici.
"""

import io
import requests
from PIL import Image, ImageEnhance, ImageFilter


def charger_image(source: str) -> Image.Image:
    """
    Charge une image depuis un fichier local ou une URL HTTP(S).

    Args:
        source: chemin local (ex: "C:/images/facture.png") ou URL (ex: "https://...")

    Returns:
        Objet PIL.Image

    Raises:
        FileNotFoundError: si le fichier local n'existe pas
        requests.RequestException: si l'URL est inaccessible
    """
    if source.startswith("http://") or source.startswith("https://"):
        reponse = requests.get(source, timeout=15)
        reponse.raise_for_status()
        return Image.open(io.BytesIO(reponse.content))
    else:
        return Image.open(source)


def ameliorer_visibilite(image: Image.Image) -> Image.Image:
    """
    Prétraite l'image pour améliorer la qualité OCR :
      - Doublement de la résolution (meilleure lecture des petites polices)
      - Accentuation de la netteté et du contraste
      - Correction de la luminosité
      - Filtre UnsharpMask pour affiner les contours
      - Conversion en niveaux de gris

    Args:
        image: image PIL en entrée (RGB, RGBA ou L)

    Returns:
        Image PIL prétraitée en niveaux de gris
    """
    largeur, hauteur = image.size
    image = image.resize((largeur * 2, hauteur * 2), resample=Image.LANCZOS)
    image = ImageEnhance.Sharpness(image).enhance(2.0)
    image = ImageEnhance.Contrast(image).enhance(1.8)
    image = ImageEnhance.Brightness(image).enhance(1.2)
    image = image.filter(ImageFilter.UnsharpMask(radius=2, percent=150, threshold=3))
    image = image.convert("L")
    return image
