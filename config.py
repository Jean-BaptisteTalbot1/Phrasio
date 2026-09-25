"""Configuration de l'application.

La configuration est stockée dans le dossier de l'utilisateur
(%APPDATA%\\Phrasio sur Windows), à part du dossier synchronisé.
"""
import json
import os
from dataclasses import dataclass, asdict, field
from pathlib import Path


def app_dir() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home() / ".config")
    d = Path(base) / "Phrasio"
    d.mkdir(parents=True, exist_ok=True)
    return d


CONFIG_FILE = app_dir() / "config.json"


@dataclass
class Config:
    # Dossier de travail (synchronisé par OneDrive, Google Drive, Dropbox...)
    workspace: str = ""

    # Langues et voix
    source_locale: str = "fr-FR"
    source_voice: str = "fr_FR-siwis-medium"
    target_locale: str = "es-MX"
    target_voice: str = "es_MX-claude-high"

    # Audio
    pause_after_source: float = 2.0   # après la phrase originale
    pause_between: float = 2.5        # entre les deux répétitions
    pause_after: float = 4.0          # avant la phrase suivante
    target_rate: int = 0              # vitesse de la langue cible, en % (-30 = plus lent)
    target_first: bool = False        # True : langue cible d'abord, puis l'original
    lesson_size: int = 20             # nombre de phrases par leçon

    # Interface
    appearance: str = "System"        # "Light", "Dark" ou "System"

    @classmethod
    def load(cls) -> "Config":
        if CONFIG_FILE.exists():
            try:
                data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
                known = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
                return cls(**known)
            except (json.JSONDecodeError, TypeError):
                pass
        return cls()

    def save(self) -> None:
        CONFIG_FILE.write_text(json.dumps(asdict(self), indent=2, ensure_ascii=False), encoding="utf-8")

    @property
    def is_ready(self) -> bool:
        return bool(self.workspace)

    def audio_signature(self) -> str:
        """Réglages qui influencent l'audio : s'ils changent, l'audio doit être régénéré."""
        return f"{self.pause_after_source}|{self.pause_between}|{self.pause_after}|{self.target_rate}|{int(self.target_first)}"
