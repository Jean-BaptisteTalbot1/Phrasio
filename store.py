"""Stockage des phrases dans un fichier CSV lisible dans Excel.

Structure du dossier de travail :

    <dossier>/
      phrases.csv
      audio/<langue-cible>/0001.mp3
      lecons/<langue-cible>/lecon-01 (1-20).mp3
"""
import csv
import hashlib
import os
from dataclasses import dataclass, asdict, fields
from datetime import datetime
from pathlib import Path
from typing import List, Optional

CSV_NAME = "phrases.csv"


@dataclass
class Phrase:
    id: int
    date: str
    source_locale: str
    source_text: str
    target_locale: str
    target_text: str
    source_voice: str
    target_voice: str
    audio_sig: str = ""   # empreinte du dernier audio généré

    def content_sig(self, settings_sig: str) -> str:
        raw = "|".join([self.source_text, self.target_text, self.source_voice,
                        self.target_voice, settings_sig])
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


FIELDS = [f.name for f in fields(Phrase)]


class StoreError(Exception):
    pass


class PhraseStore:
    def __init__(self, workspace: str):
        self.root = Path(workspace)
        self.root.mkdir(parents=True, exist_ok=True)
        self.csv_path = self.root / CSV_NAME
        self.phrases: List[Phrase] = []
        self.load()

    # ---------- fichiers ----------
    def load(self) -> None:
        self.phrases = []
        if not self.csv_path.exists():
            return
        with open(self.csv_path, newline="", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                try:
                    row = {k: (row.get(k) or "") for k in FIELDS}
                    row["id"] = int(row["id"])
                    self.phrases.append(Phrase(**row))
                except (ValueError, TypeError):
                    continue  # ligne abîmée : on l'ignore plutôt que de planter

    def save(self) -> None:
        tmp = self.csv_path.with_suffix(".tmp")
        try:
            # utf-8-sig : Excel reconnaît les accents correctement
            with open(tmp, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.DictWriter(f, fieldnames=FIELDS)
                w.writeheader()
                for p in self.phrases:
                    w.writerow(asdict(p))
            os.replace(tmp, self.csv_path)
        except PermissionError:
            raise StoreError("Impossible d'écrire phrases.csv. Est-il ouvert dans Excel ? Ferme-le et réessaie.")

    # ---------- chemins ----------
    def audio_dir(self, locale: str) -> Path:
        d = self.root / "audio" / locale
        d.mkdir(parents=True, exist_ok=True)
        return d

    def lessons_dir(self, locale: str) -> Path:
        d = self.root / "lecons" / locale
        d.mkdir(parents=True, exist_ok=True)
        return d

    def audio_path(self, p: Phrase) -> Path:
        return self.audio_dir(p.target_locale) / f"{p.id:04d}.mp3"

    # ---------- opérations ----------
    def next_id(self) -> int:
        return max((p.id for p in self.phrases), default=0) + 1

    def add(self, source_locale, source_text, target_locale, target_text,
            source_voice, target_voice) -> Phrase:
        p = Phrase(
            id=self.next_id(),
            date=datetime.now().strftime("%Y-%m-%d"),
            source_locale=source_locale, source_text=source_text.strip(),
            target_locale=target_locale, target_text=target_text.strip(),
            source_voice=source_voice, target_voice=target_voice,
        )
        self.phrases.append(p)
        self.save()
        return p

    def get(self, pid: int) -> Optional[Phrase]:
        return next((p for p in self.phrases if p.id == pid), None)

    def delete(self, pid: int) -> None:
        p = self.get(pid)
        if not p:
            return
        path = self.audio_path(p)
        self.phrases.remove(p)
        self.save()
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass

    def for_target(self, locale: str) -> List[Phrase]:
        return sorted((p for p in self.phrases if p.target_locale == locale), key=lambda p: p.id)

    def needs_audio(self, p: Phrase, settings_sig: str) -> bool:
        return p.audio_sig != p.content_sig(settings_sig) or not self.audio_path(p).exists()
