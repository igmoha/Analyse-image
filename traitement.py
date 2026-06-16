import os
import re
import json
import shutil
import hashlib
from pathlib import Path
import pytesseract
from PIL import Image, ImageEnhance

DOSSIER_ENTREE = Path("image_a_traiter")
DOSSIER_TRAITE = Path("image_traiter")
DOSSIER_NON_TRAITABLE = Path("image_non_traitable")
DOSSIER_DOUBLON = Path("doublon")
FICHIER_HASH = Path("hashes_traites.json")

EXTENSIONS_ACCEPTEES = {".png", ".jpg", ".jpeg", ".tiff", ".bmp", ".gif", ".webp"}

LARGEUR_MAX_OCR = 1200

TYPES_DOCUMENTS = [
    "facture d'avoir",
    "bon de livraison",
    "facture",
]


def charger_hashes():
    if FICHIER_HASH.exists():
        with open(FICHIER_HASH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def sauvegarder_hashes(hashes):
    with open(FICHIER_HASH, "w", encoding="utf-8") as f:
        json.dump(hashes, f, ensure_ascii=False, indent=2)


def calculer_hash(chemin_image):
    hasher = hashlib.md5()
    with open(chemin_image, "rb") as f:
        hasher.update(f.read())
    return hasher.hexdigest()


def preprocesser_image(chemin_image):
    image = Image.open(chemin_image)
    largeur, hauteur = image.size
    if largeur > LARGEUR_MAX_OCR:
        ratio = LARGEUR_MAX_OCR / largeur
        nouvelle_hauteur = int(hauteur * ratio)
        image = image.resize((LARGEUR_MAX_OCR, nouvelle_hauteur), Image.LANCZOS)
    image = image.convert("L")
    image = ImageEnhance.Contrast(image).enhance(2.0)
    return image


def extraire_texte_ocr(chemin_image):
    try:
        image = preprocesser_image(chemin_image)
        texte = pytesseract.image_to_string(image, lang="fra+eng")
        return texte
    except Exception as e:
        print(f"  [OCR] Erreur lors de la lecture de l'image : {e}")
        return None


def detecter_type_document(texte):
    texte_lower = texte.lower()
    for type_doc in TYPES_DOCUMENTS:
        if type_doc in texte_lower:
            mots = type_doc.split()
            type_formate = " ".join(m.capitalize() for m in mots)
            return type_formate
    return None


def extraire_numero_document(texte):
    patterns = [
        # Numéro dans la ligne qui suit l'en-tête de tableau "Numéro | Date ..."
        r"Num[eé]ro\s*[\|].*?\n\s*([A-Z0-9][-A-Z0-9/]{1,15})",
        # Code alphanumérique avec préfixe lettres + chiffres (ex: FAC2400258, AV2600018)
        r"\b([A-Z]{2,5}\d{5,12})\b",
        # Numéro pur précédé du mot-clé numéro/n°
        r"(?:num[eé]ro|n[°o])\s*[:\-]?\s*(\d{4,12})",
        # Suite de chiffres seuls (5 à 10 chiffres) = numéro de facture simple
        r"\b(\d{5,10})\b",
    ]
    for pattern in patterns:
        matches = re.findall(pattern, texte, re.IGNORECASE | re.MULTILINE)
        if matches:
            for m in matches:
                candidat = m.strip()
                if len(candidat) >= 5:
                    return candidat
    return None


def extraire_informations(texte):
    type_doc = detecter_type_document(texte)
    numero = extraire_numero_document(texte)
    return {
        "type": type_doc if type_doc else "inconnu",
        "numero": numero if numero else "non trouvé",
    }


def traiter_image(chemin_image, hashes_connus):
    nom_fichier = chemin_image.name
    print(f"\n{'='*50}")
    print(f"Traitement : {nom_fichier}")

    hash_image = calculer_hash(chemin_image)
    if hash_image in hashes_connus:
        print(f"  [INFO] Doublon détecté (déjà traité : {hashes_connus[hash_image]})")
        shutil.move(str(chemin_image), str(DOSSIER_DOUBLON / nom_fichier))
        return {"fichier": nom_fichier, "statut": "doublon", "original": hashes_connus[hash_image]}

    texte = extraire_texte_ocr(chemin_image)
    if texte is None or len(texte.strip()) < 10:
        print(f"  [INFO] Texte insuffisant ou illisible → image_non_traitable")
        shutil.move(str(chemin_image), str(DOSSIER_NON_TRAITABLE / nom_fichier))
        return {"fichier": nom_fichier, "statut": "non_traitable", "raison": "texte OCR insuffisant"}

    infos = extraire_informations(texte)
    print(f"  [OCR] Texte extrait ({len(texte)} caractères)")
    print(f"  [RÉSULTAT] {json.dumps(infos, ensure_ascii=False)}")

    if infos["type"] == "inconnu" and infos["numero"] == "non trouvé":
        print(f"  [INFO] Informations non trouvées → image_non_traitable")
        shutil.move(str(chemin_image), str(DOSSIER_NON_TRAITABLE / nom_fichier))
        return {"fichier": nom_fichier, "statut": "non_traitable", "raison": "informations introuvables", "details": infos}

    hashes_connus[hash_image] = nom_fichier
    shutil.move(str(chemin_image), str(DOSSIER_TRAITE / nom_fichier))
    print(f"  [OK] Image déplacée vers image_traiter/")
    return {"fichier": nom_fichier, "statut": "traite", "informations": infos}


def main():
    for dossier in [DOSSIER_ENTREE, DOSSIER_TRAITE, DOSSIER_NON_TRAITABLE, DOSSIER_DOUBLON]:
        dossier.mkdir(exist_ok=True)

    hashes_connus = charger_hashes()

    images = [
        f for f in DOSSIER_ENTREE.iterdir()
        if f.is_file() and f.suffix.lower() in EXTENSIONS_ACCEPTEES
    ]

    if not images:
        print("Aucune image trouvée dans le dossier image_a_traiter/")
        return []

    print(f"{'='*50}")
    print(f"{len(images)} image(s) à traiter")

    resultats = []
    for chemin_image in sorted(images):
        resultat = traiter_image(chemin_image, hashes_connus)
        resultats.append(resultat)

    sauvegarder_hashes(hashes_connus)

    print(f"\n{'='*50}")
    print("RÉSUMÉ FINAL")
    print(f"{'='*50}")
    traites = [r for r in resultats if r["statut"] == "traite"]
    doublons = [r for r in resultats if r["statut"] == "doublon"]
    non_traitables = [r for r in resultats if r["statut"] == "non_traitable"]
    print(f"  Traitées avec succès : {len(traites)}")
    print(f"  Doublons             : {len(doublons)}")
    print(f"  Non traitables       : {len(non_traitables)}")

    print(f"\nJSON RÉSULTAT :")
    print(json.dumps(resultats, ensure_ascii=False, indent=2))

    return resultats


if __name__ == "__main__":
    main()
