import time
from datetime import datetime
from traitement import main, DOSSIER_ENTREE, EXTENSIONS_ACCEPTEES

INTERVALLE_SECONDES = 10


def log(message):
    heure = datetime.now().strftime("%H:%M:%S")
    print(f"[{heure}] {message}", flush=True)


def compter_images():
    if not DOSSIER_ENTREE.exists():
        return 0
    return sum(
        1 for f in DOSSIER_ENTREE.iterdir()
        if f.is_file() and f.suffix.lower() in EXTENSIONS_ACCEPTEES
    )


def boucle():
    log(f"Surveillance démarrée — vérification toutes les {INTERVALLE_SECONDES} secondes")
    log(f"Dossier surveillé : {DOSSIER_ENTREE.resolve()}")
    log("─" * 50)

    while True:
        nb = compter_images()
        if nb > 0:
            log(f"{nb} image(s) détectée(s) → lancement du traitement...")
            try:
                main()
            except Exception as e:
                log(f"ERREUR pendant le traitement : {e}")
        else:
            log("Aucune image — en attente...")

        time.sleep(INTERVALLE_SECONDES)


if __name__ == "__main__":
    boucle()
