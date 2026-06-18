#!/usr/bin/env python3
"""
interface.py
============
Interface graphique (Tkinter) pour le pipeline OCR du projet.

Fonctionnalités :
  - Bouton "Lancer"  : démarre le Watcher (surveillance du dossier
                        "image_a_traiter") dans un thread en arrière-plan.
  - Bouton "Arrêter" : stoppe le Watcher en cours.
  - Bouton "Tester"  : exécute le pipeline (main.traiter_image) sur UNE
                        image choisie et affiche le résultat JSON.
  - Zones de texte / champs permettant de définir individuellement :
        * le dossier "image à traiter"
        * le dossier "image traitée"
        * le dossier "résultats" (image_traitee_json)
        * le dossier "doublon"
        * le dossier "image non traitable"
    Chaque dossier dispose de son propre champ + bouton "Parcourir...".
  - Une console de logs en direct (sortie du watcher + des actions).

PRÉREQUIS
---------
  Les fichiers main.py, Watcher.py, ocr.py, ocr_easy.py, image_utils.py,
  extraction_text.py doivent être dans le même dossier que ce script.

USAGE
-----
  python interface.py
"""

import json
import queue
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

# Les modules du projet doivent être importables (même dossier)
sys.path.insert(0, str(Path(__file__).resolve().parent))

import main as pipeline_main          # noqa: E402
import Watcher as watcher_module       # noqa: E402


# ---------------------------------------------------------------------------
# Redirection de la sortie console vers une file (thread-safe)
# ---------------------------------------------------------------------------

class RedirecteurConsole:
    """Redirige write()/flush() vers une queue.Queue lue par l'UI."""

    def __init__(self, file_queue: queue.Queue):
        self.file_queue = file_queue

    def write(self, texte: str) -> None:
        if texte:
            self.file_queue.put(texte)

    def flush(self) -> None:
        pass


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Pipeline OCR — FAMASSER")
        self.geometry("900x700")
        self.minsize(800, 600)

        # État du watcher
        self.watcher_thread: threading.Thread | None = None
        self.watcher_observateur = None
        self.watcher_gestionnaire = None
        self.watcher_actif = False
        self.moteurs_charges = None

        # File de messages pour la console (thread -> UI)
        self.log_queue: queue.Queue = queue.Queue()

        # Dossiers par défaut = sous-dossiers du dossier du script
        racine_defaut = Path(__file__).resolve().parent
        self.dossiers_vars: dict[str, tk.StringVar] = {
            "a_traiter":     tk.StringVar(value=str(racine_defaut / "image_a_traiter")),
            "traitee":       tk.StringVar(value=str(racine_defaut / "image_traitee")),
            "traitee_json":  tk.StringVar(value=str(racine_defaut / "image_traitee_json")),
            "doublon":       tk.StringVar(value=str(racine_defaut / "doublon")),
            "non_traitable": tk.StringVar(value=str(racine_defaut / "image_non_traitable")),
        }
        self.chemin_image_test = tk.StringVar(value="")

        self._construire_interface()

        # Boucle de lecture de la queue de logs
        self.after(150, self._purger_log_queue)

        # Fermeture propre
        self.protocol("WM_DELETE_WINDOW", self._fermer_application)

    # ------------------------------------------------------------------
    # Construction de l'interface
    # ------------------------------------------------------------------

    def _construire_interface(self) -> None:
        padding = {"padx": 8, "pady": 6}

        # --- Cadre des dossiers (chemins éditables) ---------------------
        cadre_dossiers = ttk.LabelFrame(self, text="Dossiers du pipeline")
        cadre_dossiers.pack(fill="x", **padding)

        noms_affiches = {
            "a_traiter":     "Images à traiter",
            "traitee":       "Images traitées",
            "traitee_json":  "Résultats JSON",
            "doublon":       "Doublons",
            "non_traitable": "Images non traitables",
        }
        for cle, libelle in noms_affiches.items():
            ligne = ttk.Frame(cadre_dossiers)
            ligne.pack(fill="x", padx=8, pady=3)
            ttk.Label(ligne, text=f"{libelle} :", width=18, anchor="w").pack(side="left")
            entree = ttk.Entry(ligne, textvariable=self.dossiers_vars[cle])
            entree.pack(side="left", fill="x", expand=True, padx=(0, 6))
            ttk.Button(
                ligne, text="Parcourir...",
                command=lambda c=cle: self._choisir_dossier(c)
            ).pack(side="left")

        ttk.Button(
            cadre_dossiers, text="Créer les dossiers manquants",
            command=self._creer_dossiers_manquants
        ).pack(anchor="e", padx=8, pady=(2, 8))

        # --- Cadre actions (Lancer / Arrêter / Tester) ------------------
        cadre_actions = ttk.LabelFrame(self, text="Actions")
        cadre_actions.pack(fill="x", **padding)

        ligne_watcher = ttk.Frame(cadre_actions)
        ligne_watcher.pack(fill="x", padx=8, pady=(8, 4))

        self.bouton_lancer = ttk.Button(
            ligne_watcher, text="▶ Lancer la surveillance", command=self._lancer_watcher
        )
        self.bouton_lancer.pack(side="left", padx=(0, 6))

        self.bouton_arreter = ttk.Button(
            ligne_watcher, text="■ Arrêter", command=self._arreter_watcher, state="disabled"
        )
        self.bouton_arreter.pack(side="left", padx=(0, 6))

        self.statut_watcher = ttk.Label(ligne_watcher, text="● Inactif", foreground="#b00020")
        self.statut_watcher.pack(side="left", padx=(12, 0))

        ligne_test = ttk.Frame(cadre_actions)
        ligne_test.pack(fill="x", padx=8, pady=(4, 8))

        ttk.Button(
            ligne_test, text="Choisir une image...", command=self._choisir_image_test
        ).pack(side="left")

        entree_image = ttk.Entry(ligne_test, textvariable=self.chemin_image_test)
        entree_image.pack(side="left", fill="x", expand=True, padx=6)

        self.bouton_tester = ttk.Button(
            ligne_test, text="🔍 Tester", command=self._tester_image
        )
        self.bouton_tester.pack(side="left")

        # --- Cadre résultat du test -------------------------------------
        cadre_resultat = ttk.LabelFrame(self, text="Résultat du test (JSON)")
        cadre_resultat.pack(fill="both", expand=True, **padding)

        self.zone_resultat = scrolledtext.ScrolledText(
            cadre_resultat, height=10, wrap="word", font=("Consolas", 9)
        )
        self.zone_resultat.pack(fill="both", expand=True, padx=8, pady=8)

        # --- Cadre logs ---------------------------------------------------
        cadre_logs = ttk.LabelFrame(self, text="Journal / Console")
        cadre_logs.pack(fill="both", expand=True, **padding)

        self.zone_logs = scrolledtext.ScrolledText(
            cadre_logs, height=10, wrap="word", font=("Consolas", 9),
            background="#1e1e1e", foreground="#d4d4d4"
        )
        self.zone_logs.pack(fill="both", expand=True, padx=8, pady=8)

    # ------------------------------------------------------------------
    # Gestion des dossiers
    # ------------------------------------------------------------------

    def _choisir_dossier(self, cle: str) -> None:
        actuel = self.dossiers_vars[cle].get() or "."
        dossier = filedialog.askdirectory(
            title="Choisir un dossier",
            initialdir=actuel if Path(actuel).exists() else ".",
        )
        if dossier:
            self.dossiers_vars[cle].set(dossier)

    def _recuperer_dossiers(self) -> dict[str, Path]:
        """Construit le dict de chemins à partir des champs de l'interface."""
        return {cle: Path(var.get().strip()) for cle, var in self.dossiers_vars.items()}

    def _creer_dossiers_manquants(self) -> None:
        dossiers = self._recuperer_dossiers()
        try:
            for chemin in dossiers.values():
                chemin.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            messagebox.showerror("Erreur", f"Impossible de créer un dossier :\n{exc}")
            return
        self._log("[INFO] Dossiers créés/vérifiés avec succès.\n")
        messagebox.showinfo("OK", "Tous les dossiers existent désormais.")

    # ------------------------------------------------------------------
    # Logs
    # ------------------------------------------------------------------

    def _log(self, texte: str) -> None:
        self.zone_logs.insert("end", texte)
        self.zone_logs.see("end")

    def _purger_log_queue(self) -> None:
        try:
            while True:
                texte = self.log_queue.get_nowait()
                self._log(texte)
        except queue.Empty:
            pass
        self.after(150, self._purger_log_queue)

    # ------------------------------------------------------------------
    # Watcher : Lancer / Arrêter
    # ------------------------------------------------------------------

    def _lancer_watcher(self) -> None:
        if self.watcher_actif:
            return

        dossiers = self._recuperer_dossiers()

        # Validation : tous les champs doivent être remplis
        manquants = [cle for cle, chemin in dossiers.items() if not str(chemin).strip()]
        if manquants:
            messagebox.showerror("Erreur", "Tous les champs de dossiers doivent être remplis.")
            return

        try:
            for chemin in dossiers.values():
                chemin.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            messagebox.showerror("Erreur", f"Impossible de préparer les dossiers :\n{exc}")
            return

        self.bouton_lancer.config(state="disabled")
        self.statut_watcher.config(text="● Démarrage...", foreground="#b06a00")
        self._log("\n[LANCEMENT] Dossiers configurés :\n")
        for cle, chemin in dossiers.items():
            self._log(f"    {cle:15s} -> {chemin}\n")

        self.watcher_thread = threading.Thread(
            target=self._executer_watcher, args=(dossiers,), daemon=True
        )
        self.watcher_thread.start()

    def _executer_watcher(self, dossiers: dict) -> None:
        ancien_stdout = sys.stdout
        sys.stdout = RedirecteurConsole(self.log_queue)
        try:
            self.log_queue.put("[INFO] Chargement des moteurs OCR...\n")
            moteurs = watcher_module.charger_moteurs(verbose=True)
            if moteurs["extraire_texte"] is None and moteurs["extraire_texte_easyocr"] is None:
                self.log_queue.put("[ERREUR] Aucun moteur OCR disponible.\n")
                self.after(0, self._watcher_termine, False)
                return
            self.moteurs_charges = moteurs

            watcher_module.traiter_fichiers_existants(dossiers, moteurs, verbose=True)

            self.watcher_gestionnaire = watcher_module.GestionnaireImages(
                dossiers, moteurs, verbose=True
            )
            self.watcher_observateur = watcher_module.Observer()
            self.watcher_observateur.schedule(
                self.watcher_gestionnaire, str(dossiers["a_traiter"]), recursive=False
            )
            self.watcher_observateur.start()

            self.watcher_actif = True
            self.after(0, self._watcher_demarre)

            while self.watcher_actif:
                time.sleep(watcher_module.INTERVALLE_VERIFICATION)
                if self.watcher_gestionnaire is not None:
                    self.watcher_gestionnaire.traiter_fichiers_stables()

        except Exception as exc:
            self.log_queue.put(f"[ERREUR] {exc}\n")
            self.after(0, self._watcher_termine, False)
        finally:
            if self.watcher_observateur is not None:
                try:
                    self.watcher_observateur.stop()
                    self.watcher_observateur.join()
                except Exception:
                    pass
            sys.stdout = ancien_stdout

    def _watcher_demarre(self) -> None:
        self.statut_watcher.config(text="● Actif", foreground="#1a7a1a")
        self.bouton_arreter.config(state="normal")
        self.bouton_lancer.config(state="disabled")

    def _watcher_termine(self, succes: bool = True) -> None:
        self.watcher_actif = False
        self.statut_watcher.config(text="● Inactif", foreground="#b00020")
        self.bouton_arreter.config(state="disabled")
        self.bouton_lancer.config(state="normal")

    def _arreter_watcher(self) -> None:
        if not self.watcher_actif:
            return
        self._log("\n[ARRET] Arrêt de la surveillance demandé...\n")
        self.watcher_actif = False
        # Le thread va sortir de sa boucle et stopper l'observateur dans finally.
        self.after(500, self._watcher_termine)

    # ------------------------------------------------------------------
    # Test sur une image unique
    # ------------------------------------------------------------------

    def _choisir_image_test(self) -> None:
        chemin = filedialog.askopenfilename(
            title="Choisir une image à tester",
            filetypes=[
                ("Images", "*.png *.jpg *.jpeg *.bmp *.tif *.tiff *.webp"),
                ("Tous les fichiers", "*.*"),
            ],
        )
        if chemin:
            self.chemin_image_test.set(chemin)

    def _tester_image(self) -> None:
        source = self.chemin_image_test.get().strip()
        if not source:
            messagebox.showwarning("Attention", "Veuillez choisir une image à tester.")
            return

        self.bouton_tester.config(state="disabled")
        self.zone_resultat.delete("1.0", "end")
        self.zone_resultat.insert("end", "Traitement en cours...\n")
        self._log(f"\n[TEST] Traitement de : {source}\n")

        thread = threading.Thread(target=self._executer_test, args=(source,), daemon=True)
        thread.start()

    def _executer_test(self, source: str) -> None:
        ancien_stdout = sys.stdout
        sys.stdout = RedirecteurConsole(self.log_queue)
        try:
            resultat = pipeline_main.traiter_image(source, verbose=True)
            texte_json = json.dumps(resultat, ensure_ascii=False, indent=2)
            self.after(0, self._afficher_resultat_test, texte_json, None)
        except Exception as exc:
            self.after(0, self._afficher_resultat_test, None, str(exc))
        finally:
            sys.stdout = ancien_stdout

    def _afficher_resultat_test(self, texte_json: str | None, erreur: str | None) -> None:
        self.zone_resultat.delete("1.0", "end")
        if erreur:
            self.zone_resultat.insert("end", f"[ERREUR] {erreur}\n")
            self._log(f"[ERREUR TEST] {erreur}\n")
        else:
            self.zone_resultat.insert("end", texte_json)
            self._log("[TEST] Terminé avec succès.\n")
        self.bouton_tester.config(state="normal")

    # ------------------------------------------------------------------
    # Fermeture
    # ------------------------------------------------------------------

    def _fermer_application(self) -> None:
        if self.watcher_actif:
            self.watcher_actif = False
            if self.watcher_observateur is not None:
                try:
                    self.watcher_observateur.stop()
                except Exception:
                    pass
        self.destroy()


def main() -> None:
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()