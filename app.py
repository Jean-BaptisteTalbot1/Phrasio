"""Phrasio : apprends une langue avec tes propres phrases du quotidien.

Lancement :  python app.py
"""
import os
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

import audio
from local_engine import EngineError, fetch_voices, prepare, translate
from config import Config, app_dir
from store import Phrase, PhraseStore, StoreError

ACCENT = "#0F766E"
ACCENT_HOVER = "#115E59"
MUTED = ("#6B7280", "#9CA3AF")
CARD = ("#FFFFFF", "#1F2428")
BG = ("#F3F4F6", "#16191C")
DANGER = ("#B91C1C", "#F87171")
MAX_ROWS = 150


def open_file(path: Path) -> None:
    if sys.platform.startswith("win"):
        os.startfile(str(path))  # noqa
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


def locale_label(v: dict) -> str:
    return f"{v['locale_name']} · {v['locale']}"


def voice_label(v: dict) -> str:
    return f"{v['display']} ({v['gender']}) · {v['name']}"


def after_dot(label: str) -> str:
    return label.rsplit("·", 1)[-1].strip()


# =====================================================================
#  Paramètres
# =====================================================================
class SettingsDialog(ctk.CTkToplevel):
    def __init__(self, app: "App"):
        super().__init__(app)
        self.app = app
        self.cfg = app.cfg
        self.voices = list(app.voices)
        self.title("Paramètres")
        self.geometry("620x560")
        self.resizable(False, False)
        self.transient(app)
        self.after(100, self.grab_set)

        tabs = ctk.CTkTabview(self, segmented_button_selected_color=ACCENT,
                              segmented_button_selected_hover_color=ACCENT_HOVER)
        tabs.pack(fill="both", expand=True, padx=16, pady=(12, 0))
        self._lang_tab(tabs.add("Langues"))
        self._audio_tab(tabs.add("Audio"))
        self._folder_tab(tabs.add("Dossier"))
        if not self.voices:
            self.after(300, lambda: self.reload_voices(force=False))  # premier lancement : on charge la liste tout de suite

        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.pack(fill="x", padx=16, pady=12)
        ctk.CTkButton(bar, text="Enregistrer", fg_color=ACCENT, hover_color=ACCENT_HOVER,
                      command=self.save).pack(side="right")
        ctk.CTkButton(bar, text="Annuler", fg_color="transparent", border_width=1,
                      text_color=("gray20", "gray85"), command=self.destroy).pack(side="right", padx=8)

    # ---------- onglets ----------
    def _field(self, parent, label, value, show=None, row=0):
        ctk.CTkLabel(parent, text=label, anchor="w").grid(row=row, column=0, sticky="w", pady=6, padx=(4, 12))
        e = ctk.CTkEntry(parent, width=360, show=show)
        e.insert(0, value)
        e.grid(row=row, column=1, sticky="w", pady=6)
        return e

    def _lang_tab(self, t):
        self.lang_frame = t
        ctk.CTkButton(t, text="Mettre à jour la liste des voix", width=220, fg_color=ACCENT,
                      hover_color=ACCENT_HOVER, command=self.reload_voices).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(4, 12), padx=4)

        ctk.CTkLabel(t, text="Ma langue", anchor="w", font=ctk.CTkFont(weight="bold")).grid(
            row=1, column=0, sticky="w", padx=4)
        self.cb_src_loc = ctk.CTkComboBox(t, width=400, command=lambda _: self._fill_voices("src"))
        self.cb_src_loc.grid(row=2, column=0, columnspan=2, sticky="w", pady=4, padx=4)
        self.cb_src_voice = ctk.CTkComboBox(t, width=400)
        self.cb_src_voice.grid(row=3, column=0, columnspan=2, sticky="w", pady=(0, 16), padx=4)

        ctk.CTkLabel(t, text="Langue à apprendre", anchor="w", font=ctk.CTkFont(weight="bold")).grid(
            row=4, column=0, sticky="w", padx=4)
        self.cb_tgt_loc = ctk.CTkComboBox(t, width=400, command=lambda _: self._fill_voices("tgt"))
        self.cb_tgt_loc.grid(row=5, column=0, columnspan=2, sticky="w", pady=4, padx=4)
        self.cb_tgt_voice = ctk.CTkComboBox(t, width=400)
        self.cb_tgt_voice.grid(row=6, column=0, columnspan=2, sticky="w", pady=(0, 8), padx=4)

        ctk.CTkLabel(t, text="Astuce : tape dans une liste pour filtrer, ex. « es- » ou « Spanish ».",
                     text_color=MUTED).grid(row=7, column=0, columnspan=2, sticky="w", padx=4)
        self._fill_locales()

    def _audio_tab(self, t):
        self.e_p1 = self._field(t, "Pause après l'original (s)", str(self.cfg.pause_after_source), row=0)
        self.e_p2 = self._field(t, "Pause entre les répétitions (s)", str(self.cfg.pause_between), row=1)
        self.e_p3 = self._field(t, "Pause avant la phrase suivante (s)", str(self.cfg.pause_after), row=2)
        self.e_size = self._field(t, "Phrases par leçon", str(self.cfg.lesson_size), row=3)

        ctk.CTkLabel(t, text="Vitesse de la langue cible", anchor="w").grid(row=4, column=0, sticky="w", pady=6, padx=(4, 12))
        self.seg_rate = ctk.CTkSegmentedButton(t, values=["-30 %", "-15 %", "Normale"],
                                               selected_color=ACCENT, selected_hover_color=ACCENT_HOVER)
        self.seg_rate.set({-30: "-30 %", -15: "-15 %"}.get(self.cfg.target_rate, "Normale"))
        self.seg_rate.grid(row=4, column=1, sticky="w")

        ctk.CTkLabel(t, text="Ordre", anchor="w").grid(row=5, column=0, sticky="w", pady=6, padx=(4, 12))
        self.seg_order = ctk.CTkSegmentedButton(t, values=["Ma langue d'abord", "Langue cible d'abord"],
                                                selected_color=ACCENT, selected_hover_color=ACCENT_HOVER)
        self.seg_order.set("Langue cible d'abord" if self.cfg.target_first else "Ma langue d'abord")
        self.seg_order.grid(row=5, column=1, sticky="w")

        ctk.CTkLabel(t, text="Apparence", anchor="w").grid(row=6, column=0, sticky="w", pady=6, padx=(4, 12))
        self.seg_theme = ctk.CTkSegmentedButton(t, values=["Clair", "Sombre", "Système"],
                                                selected_color=ACCENT, selected_hover_color=ACCENT_HOVER)
        self.seg_theme.set({"Light": "Clair", "Dark": "Sombre"}.get(self.cfg.appearance, "Système"))
        self.seg_theme.grid(row=6, column=1, sticky="w")

        ctk.CTkLabel(t, text="Changer ces réglages demande de régénérer l'audio (bouton « Synchroniser »).",
                     text_color=MUTED).grid(row=7, column=0, columnspan=2, sticky="w", pady=(14, 0), padx=4)

    def _folder_tab(self, t):
        ctk.CTkLabel(t, text="Dossier de travail", anchor="w", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=4, pady=(4, 6))
        row = ctk.CTkFrame(t, fg_color="transparent")
        row.pack(fill="x", padx=4)
        self.e_folder = ctk.CTkEntry(row, width=420)
        self.e_folder.insert(0, self.cfg.workspace)
        self.e_folder.pack(side="left")
        ctk.CTkButton(row, text="Parcourir…", width=100, fg_color=ACCENT, hover_color=ACCENT_HOVER,
                      command=self._browse).pack(side="left", padx=8)
        ctk.CTkLabel(t, justify="left", text_color=MUTED, text=(
            "Choisis un dossier dans OneDrive, Google Drive, Dropbox ou iCloud :\n"
            "tes phrases et tes MP3 seront synchronisés automatiquement et\n"
            "accessibles depuis ton téléphone.\n\n"
            "Exemple : C:\\Users\\toi\\OneDrive\\Phrasio")).pack(anchor="w", padx=4, pady=14)

    def _browse(self):
        d = filedialog.askdirectory(parent=self, title="Choisir le dossier de travail")
        if d:
            self.e_folder.delete(0, "end")
            self.e_folder.insert(0, d)

    # ---------- voix ----------
    def _fill_locales(self):
        locs = {}
        for v in self.voices:
            locs.setdefault(v["locale"], locale_label(v))
        values = sorted(locs.values())
        if not values:
            values = ["(clique sur « Charger la liste des voix »)"]
        for cb, current in ((self.cb_src_loc, self.cfg.source_locale), (self.cb_tgt_loc, self.cfg.target_locale)):
            cb.configure(values=values)
            cb.set(locs.get(current, values[0]))
        self._fill_voices("src", self.cfg.source_voice)
        self._fill_voices("tgt", self.cfg.target_voice)

    def _fill_voices(self, which, preferred=None):
        loc_cb, voice_cb = ((self.cb_src_loc, self.cb_src_voice) if which == "src"
                            else (self.cb_tgt_loc, self.cb_tgt_voice))
        loc = after_dot(loc_cb.get())
        vs = [voice_label(v) for v in self.voices if v["locale"] == loc]
        voice_cb.configure(values=vs or [""])
        chosen = next((x for x in vs if preferred and x.endswith(preferred)), vs[0] if vs else "")
        voice_cb.set(chosen)

    def reload_voices(self, force=True):
        def done(voices):
            self.voices = voices
            self.app.voices = voices
            self._fill_locales()

        self.app.run_bg(lambda: fetch_voices(use_cache=not force),
                        done, parent=self, busy="Chargement de la liste des voix…")

    # ---------- enregistrer ----------
    def save(self):
        c = self.cfg
        try:
            p1, p2, p3 = float(self.e_p1.get()), float(self.e_p2.get()), float(self.e_p3.get())
            size = int(self.e_size.get())
        except ValueError:
            messagebox.showerror("Phrasio", "Les pauses et le nombre de phrases doivent être des nombres.", parent=self)
            return
        folder = self.e_folder.get().strip()
        if not folder:
            messagebox.showerror("Phrasio", "Choisis un dossier de travail (onglet Dossier).", parent=self)
            return

        c.pause_after_source, c.pause_between, c.pause_after, c.lesson_size = p1, p2, p3, size
        c.target_rate = {"-30 %": -30, "-15 %": -15}.get(self.seg_rate.get(), 0)
        c.target_first = self.seg_order.get() == "Langue cible d'abord"
        c.appearance = {"Clair": "Light", "Sombre": "Dark"}.get(self.seg_theme.get(), "System")
        c.workspace = folder
        if self.voices:
            c.source_locale = after_dot(self.cb_src_loc.get()) or c.source_locale
            c.target_locale = after_dot(self.cb_tgt_loc.get()) or c.target_locale
            c.source_voice = after_dot(self.cb_src_voice.get()) or c.source_voice
            c.target_voice = after_dot(self.cb_tgt_voice.get()) or c.target_voice
        c.save()
        self.destroy()
        self.app.on_settings_changed()


# =====================================================================
#  Fenêtre principale
# =====================================================================
class App(ctk.CTk):
    def __init__(self):
        self.cfg = Config.load()
        ctk.set_appearance_mode(self.cfg.appearance)
        super().__init__()
        self.title("Phrasio")
        self.geometry("1000x760")
        self.minsize(820, 600)
        self.configure(fg_color=BG)

        self.executor = ThreadPoolExecutor(max_workers=1)  # une opération à la fois
        self.store = None
        self.voices = []
        self.editing_id = None

        self._build_header()
        self._build_editor()
        self._build_list()
        self._build_status()

        self.after(200, self.startup)

    # ---------- construction ----------
    def _build_header(self):
        h = ctk.CTkFrame(self, fg_color="transparent")
        h.pack(fill="x", padx=24, pady=(18, 8))
        left = ctk.CTkFrame(h, fg_color="transparent")
        left.pack(side="left")
        ctk.CTkLabel(left, text="Phrasio", font=ctk.CTkFont(size=26, weight="bold"),
                     text_color=ACCENT).pack(anchor="w")
        ctk.CTkLabel(left, text="Tes phrases du quotidien, dans la langue que tu apprends.",
                     text_color=MUTED).pack(anchor="w")
        ctk.CTkButton(h, text="⚙  Paramètres", width=120, fg_color="transparent", border_width=1,
                      text_color=("gray20", "gray85"), command=self.open_settings).pack(side="right")
        self.lbl_pair = ctk.CTkLabel(h, text="", font=ctk.CTkFont(size=14, weight="bold"))
        self.lbl_pair.pack(side="right", padx=16)

    def _build_editor(self):
        card = ctk.CTkFrame(self, fg_color=CARD, corner_radius=14)
        card.pack(fill="x", padx=24, pady=8)
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=18, pady=16)
        inner.grid_columnconfigure(0, weight=1)
        inner.grid_columnconfigure(1, weight=1)

        self.lbl_src = ctk.CTkLabel(inner, text="Je dis", anchor="w", font=ctk.CTkFont(weight="bold"))
        self.lbl_src.grid(row=0, column=0, sticky="w")
        self.lbl_tgt = ctk.CTkLabel(inner, text="Traduction", anchor="w", font=ctk.CTkFont(weight="bold"))
        self.lbl_tgt.grid(row=0, column=1, sticky="w", padx=(12, 0))

        self.txt_src = ctk.CTkTextbox(inner, height=80, wrap="word", font=ctk.CTkFont(size=15), border_width=1)
        self.txt_src.grid(row=1, column=0, sticky="ew")
        self.txt_tgt = ctk.CTkTextbox(inner, height=80, wrap="word", font=ctk.CTkFont(size=15), border_width=1)
        self.txt_tgt.grid(row=1, column=1, sticky="ew", padx=(12, 0))

        ctk.CTkLabel(inner, text="Entrée : traduire  ·  Ctrl+Entrée : ajouter  ·  Windows+H : dicter",
                     text_color=MUTED, font=ctk.CTkFont(size=12)).grid(row=2, column=0, sticky="w", pady=(6, 0))

        btns = ctk.CTkFrame(inner, fg_color="transparent")
        btns.grid(row=2, column=1, sticky="e", pady=(10, 0))
        self.btn_cancel = ctk.CTkButton(btns, text="Annuler", width=90, fg_color="transparent", border_width=1,
                                        text_color=("gray20", "gray85"), command=self.cancel_edit)
        ctk.CTkButton(btns, text="Traduire", width=100, fg_color="transparent", border_width=1,
                      text_color=("gray20", "gray85"), command=self.do_translate).pack(side="left", padx=4)
        ctk.CTkButton(btns, text="▶  Écouter", width=100, fg_color="transparent", border_width=1,
                      text_color=("gray20", "gray85"), command=self.do_preview).pack(side="left", padx=4)
        self.btn_add = ctk.CTkButton(btns, text="＋  Ajouter", width=120, fg_color=ACCENT,
                                     hover_color=ACCENT_HOVER, command=self.do_add)
        self.btn_add.pack(side="left", padx=(4, 0))
        self.btn_row = btns

        self.txt_src.bind("<Return>", self._on_enter)
        self.txt_src.bind("<Control-Return>", self._on_ctrl_enter)
        self.txt_tgt.bind("<Control-Return>", self._on_ctrl_enter)

    def _build_list(self):
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.pack(fill="x", padx=24, pady=(12, 4))
        self.lbl_count = ctk.CTkLabel(bar, text="Mes phrases", font=ctk.CTkFont(size=16, weight="bold"))
        self.lbl_count.pack(side="left")
        self.e_search = ctk.CTkEntry(bar, placeholder_text="Rechercher…", width=200)
        self.e_search.pack(side="left", padx=16)
        self.e_search.bind("<KeyRelease>", lambda _: self.refresh_list())

        ctk.CTkButton(bar, text="📁  Dossier", width=100, fg_color="transparent", border_width=1,
                      text_color=("gray20", "gray85"), command=self.open_folder).pack(side="right")
        ctk.CTkButton(bar, text="🎧  Générer les leçons", width=160, fg_color=ACCENT,
                      hover_color=ACCENT_HOVER, command=self.do_lessons).pack(side="right", padx=8)
        ctk.CTkButton(bar, text="↻  Synchroniser", width=130, fg_color="transparent", border_width=1,
                      text_color=("gray20", "gray85"), command=self.do_sync).pack(side="right")

        self.list_frame = ctk.CTkScrollableFrame(self, fg_color=CARD, corner_radius=14)
        self.list_frame.pack(fill="both", expand=True, padx=24, pady=(4, 8))
        self.list_frame.grid_columnconfigure(1, weight=1)

    def _build_status(self):
        self.status = ctk.CTkLabel(self, text="", anchor="w", text_color=MUTED)
        self.status.pack(fill="x", padx=26, pady=(0, 10))

    # ---------- utilitaires ----------
    def set_status(self, text):
        self.status.configure(text=text)

    def run_bg(self, work, done=None, parent=None, busy="Un instant…"):
        """Exécute une tâche réseau en arrière-plan pour ne pas geler la fenêtre."""
        self.set_status(busy)
        self.configure(cursor="watch")

        def wrapper():
            try:
                result = work()
                self.after(0, lambda: self._bg_done(done, result))
            except (EngineError, StoreError) as e:
                msg = str(e)
                self.after(0, lambda: self._bg_error(msg, parent))
            except Exception as e:  # dernier filet de sécurité
                msg = f"Erreur inattendue : {e}"
                self.after(0, lambda: self._bg_error(msg, parent))

        self.executor.submit(wrapper)

    def _bg_done(self, done, result):
        self.configure(cursor="")
        self.set_status("")
        if done:
            done(result)

    def _bg_error(self, msg, parent):
        self.configure(cursor="")
        self.set_status(msg)
        messagebox.showerror("Phrasio", msg, parent=parent or self)

    def voice_name(self, locale):
        v = next((v for v in self.voices if v["locale"] == locale), None)
        return v["locale_name"] if v else locale

    def src_text(self):
        return self.txt_src.get("1.0", "end-1c").strip()

    def tgt_text(self):
        return self.txt_tgt.get("1.0", "end-1c").strip()

    def clear_editor(self):
        self.txt_src.delete("1.0", "end")
        self.txt_tgt.delete("1.0", "end")
        self.txt_src.focus_set()

    # ---------- démarrage ----------
    def startup(self):
        if not self.cfg.is_ready:
            self.set_status("Bienvenue ! Choisis tes langues, tes voix et ton dossier pour commencer.")
            self.open_settings()
            return
        self.on_settings_changed()

    def on_settings_changed(self):
        ctk.set_appearance_mode(self.cfg.appearance)
        try:
            self.store = PhraseStore(self.cfg.workspace)
        except OSError as e:
            messagebox.showerror("Phrasio", f"Dossier inaccessible : {e}")
            return
        try:
            self.voices = fetch_voices()  # depuis le cache local si possible
        except EngineError as e:
            self.set_status(str(e))
        src, tgt = self.voice_name(self.cfg.source_locale), self.voice_name(self.cfg.target_locale)
        self.lbl_pair.configure(text=f"{src}  →  {tgt}")
        self.lbl_src.configure(text=f"Je dis · {src}")
        self.lbl_tgt.configure(text=f"Traduction · {tgt}")
        self.refresh_list()
        self.txt_src.focus_set()
        self.prepare_models()

    def prepare_models(self):
        """Télécharge au besoin les voix et les modèles de traduction, puis les charge en mémoire."""
        c = self.cfg

        def progress(msg):
            self.after(0, lambda: self.set_status(msg))

        self.run_bg(lambda: prepare(c.source_locale, c.source_voice, c.target_locale, c.target_voice, progress),
                    lambda _: self.set_status("Prêt. Tout fonctionne hors ligne."),
                    busy="Préparation des modèles…")

    def open_settings(self):
        SettingsDialog(self)

    # ---------- liste ----------
    def refresh_list(self):
        for w in self.list_frame.winfo_children():
            w.destroy()
        if not self.store:
            return
        all_p = self.store.for_target(self.cfg.target_locale)
        q = self.e_search.get().strip().lower()
        shown = [p for p in reversed(all_p)
                 if not q or q in p.source_text.lower() or q in p.target_text.lower()]
        self.lbl_count.configure(text=f"Mes phrases ({len(all_p)})")

        if not all_p:
            ctk.CTkLabel(self.list_frame, text="Aucune phrase pour l'instant.\nÉcris ta première phrase ci-dessus !",
                         text_color=MUTED, justify="center").grid(row=0, column=0, columnspan=3, pady=40, padx=20)
            return

        sig = self.cfg.audio_signature()
        for r, p in enumerate(shown[:MAX_ROWS]):
            ctk.CTkLabel(self.list_frame, text=f"{p.id:04d}", text_color=MUTED, width=48,
                         font=ctk.CTkFont(family="Consolas", size=12)).grid(row=r, column=0, sticky="nw", padx=(10, 6), pady=8)
            txt = ctk.CTkFrame(self.list_frame, fg_color="transparent")
            txt.grid(row=r, column=1, sticky="ew", pady=6)
            ctk.CTkLabel(txt, text=p.target_text, anchor="w", justify="left", wraplength=620,
                         font=ctk.CTkFont(size=15, weight="bold")).pack(anchor="w")
            ctk.CTkLabel(txt, text=p.source_text, anchor="w", justify="left", wraplength=620,
                         text_color=MUTED).pack(anchor="w")

            acts = ctk.CTkFrame(self.list_frame, fg_color="transparent")
            acts.grid(row=r, column=2, sticky="e", padx=8)
            pending = self.store.needs_audio(p, sig)
            ctk.CTkButton(acts, text="⏳" if pending else "▶", width=34, height=30,
                          fg_color="transparent", border_width=1, text_color=("gray20", "gray85"),
                          command=lambda p=p: self.play(p)).pack(side="left", padx=2)
            ctk.CTkButton(acts, text="✎", width=34, height=30, fg_color="transparent", border_width=1,
                          text_color=("gray20", "gray85"),
                          command=lambda p=p: self.start_edit(p)).pack(side="left", padx=2)
            ctk.CTkButton(acts, text="✕", width=34, height=30, fg_color="transparent", border_width=1,
                          text_color=DANGER, command=lambda p=p: self.delete(p)).pack(side="left", padx=2)

        if len(shown) > MAX_ROWS:
            ctk.CTkLabel(self.list_frame, text=f"… et {len(shown) - MAX_ROWS} autres (utilise la recherche)",
                         text_color=MUTED).grid(row=MAX_ROWS, column=0, columnspan=3, pady=10)

    # ---------- actions ----------
    def _on_enter(self, _):
        self.do_translate()
        return "break"

    def _on_ctrl_enter(self, _):
        self.do_add()
        return "break"

    def _need_ready(self):
        if not self.cfg.is_ready or not self.store:
            messagebox.showinfo("Phrasio", "Choisis d'abord ton dossier de travail.")
            self.open_settings()
            return False
        return True

    def do_translate(self, then=None):
        if not self._need_ready():
            return
        text = self.src_text()
        if not text:
            return
        c = self.cfg

        def done(result):
            self.txt_tgt.delete("1.0", "end")
            self.txt_tgt.insert("1.0", result)
            if then:
                then()

        self.run_bg(lambda: translate(text, c.source_locale, c.target_locale), done, busy="Traduction…")

    def do_add(self):
        if not self._need_ready():
            return
        src, tgt = self.src_text(), self.tgt_text()
        if not src:
            return
        c, store = self.cfg, self.store

        def translated():
            # Pas de traduction saisie : on traduit dans la même tâche, avec le texte capturé maintenant
            return tgt or translate(src, c.source_locale, c.target_locale)

        if self.editing_id is not None:
            p = store.get(self.editing_id)

            def work():
                p.source_text, p.target_text = src, translated()
                store.save()
                audio.generate_phrase(store, p, c)

            self.cancel_edit()
        else:
            def work():
                p = store.add(c.source_locale, src, c.target_locale, translated(), c.source_voice, c.target_voice)
                self.after(0, self.refresh_list)
                audio.generate_phrase(store, p, c)

            self.clear_editor()

        self.run_bg(work, lambda _: (self.refresh_list(), self.set_status("Phrase ajoutée, audio prêt.")),
                    busy="Génération de l'audio…")

    def do_preview(self):
        if not self._need_ready():
            return
        src, tgt = self.src_text(), self.tgt_text()
        if not (src and tgt):
            messagebox.showinfo("Phrasio", "Écris la phrase et sa traduction d'abord.")
            return
        c = self.cfg
        p = Phrase(0, "", c.source_locale, src, c.target_locale, tgt, c.source_voice, c.target_voice)
        out = app_dir() / "apercu.mp3"

        def work():
            out.write_bytes(audio.build_phrase_audio(p, c))
            return out

        self.run_bg(work, open_file, busy="Préparation de l'aperçu…")

    def play(self, p):
        path = self.store.audio_path(p)
        if path.exists() and not self.store.needs_audio(p, self.cfg.audio_signature()):
            open_file(path)
            return
        self.run_bg(lambda: audio.generate_phrase(self.store, p, self.cfg),
                    lambda _: (self.refresh_list(), open_file(path)), busy="Génération de l'audio…")

    def start_edit(self, p):
        self.editing_id = p.id
        self.txt_src.delete("1.0", "end")
        self.txt_src.insert("1.0", p.source_text)
        self.txt_tgt.delete("1.0", "end")
        self.txt_tgt.insert("1.0", p.target_text)
        self.btn_add.configure(text="✓  Enregistrer")
        self.btn_cancel.pack(side="left", padx=4, before=self.btn_row.winfo_children()[1])
        self.txt_tgt.focus_set()

    def cancel_edit(self):
        self.editing_id = None
        self.btn_add.configure(text="＋  Ajouter")
        self.btn_cancel.pack_forget()
        self.clear_editor()

    def delete(self, p):
        if messagebox.askyesno("Phrasio", f"Supprimer cette phrase ?\n\n{p.source_text}"):
            try:
                self.store.delete(p.id)
            except StoreError as e:
                messagebox.showerror("Phrasio", str(e))
            self.refresh_list()

    def do_sync(self):
        """Relit le CSV (modifié dans Excel ou sur un autre PC) et régénère l'audio manquant."""
        if not self._need_ready():
            return
        store, c = self.store, self.cfg
        store.load()
        sig = c.audio_signature()
        todo = [p for p in store.for_target(c.target_locale) if store.needs_audio(p, sig)]
        self.refresh_list()
        if not todo:
            self.set_status("Tout est à jour.")
            return
        if len(todo) > 20 and not messagebox.askyesno(
                "Phrasio", f"{len(todo)} phrases à (re)générer. Continuer ?"):
            return

        def work():
            for i, p in enumerate(todo, 1):
                self.after(0, lambda i=i: self.set_status(f"Audio {i} / {len(todo)}…"))
                audio.generate_phrase(store, p, c)
            return len(todo)

        self.run_bg(work, lambda n: (self.refresh_list(), self.set_status(f"{n} fichier(s) audio générés.")),
                    busy="Synchronisation…")

    def do_lessons(self):
        if not self._need_ready():
            return
        store, c = self.store, self.cfg
        sig = c.audio_signature()
        missing = [p for p in store.for_target(c.target_locale) if store.needs_audio(p, sig)]
        if missing:
            if not messagebox.askyesno("Phrasio", f"{len(missing)} phrase(s) n'ont pas d'audio à jour. "
                                                  "Les générer d'abord ?"):
                return

        def work():
            for i, p in enumerate(missing, 1):
                self.after(0, lambda i=i: self.set_status(f"Audio {i} / {len(missing)}…"))
                audio.generate_phrase(store, p, c)
            return audio.build_lessons(store, c.target_locale, c.lesson_size)

        def done(files):
            self.refresh_list()
            self.set_status(f"{len(files)} leçon(s) créées dans lecons/{c.target_locale}.")
            if files and messagebox.askyesno("Phrasio", f"{len(files)} leçon(s) prêtes. Ouvrir le dossier ?"):
                open_file(store.lessons_dir(c.target_locale))

        self.run_bg(work, done, busy="Création des leçons…")

    def open_folder(self):
        if self.store:
            open_file(self.store.root)


if __name__ == "__main__":
    App().mainloop()
