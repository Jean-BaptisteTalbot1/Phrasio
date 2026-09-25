"""Traduction (Argos Translate) et synthèse vocale (Piper), 100 % locales.

Aucun compte ni clé. Les modèles se téléchargent une seule fois, puis
tout fonctionne hors ligne.

  - Voix Piper      : %APPDATA%\\Phrasio\\voices\\
  - Modèles Argos   : dossier par défaut d'Argos (dans le profil utilisateur)
"""
import json
import os
import threading
import urllib.request
from pathlib import Path
from typing import Callable, Optional

# Stanza's atomic file-rename fails on Windows (WinError 5) when it tries to
# update resources.json inside the argos packages directory. Patch os.replace so
# that the rename falls back to copy+delete when the destination is locked.
import sys
os.environ["ARGOS_STANZA_AVAILABLE"] = "0"

_real_replace = os.replace

def _safe_replace(src, dst):
    try:
        _real_replace(src, dst)
    except OSError:
        import shutil
        shutil.copy2(src, dst)
        try:
            os.remove(src)
        except OSError:
            pass

os.replace = _safe_replace

import numpy as np

from config import app_dir

SAMPLE_RATE = 22050          # fréquence de sortie commune à toutes les voix
VOICES_DIR = app_dir() / "voices"
CATALOG_CACHE = app_dir() / "piper_catalog.json"
CATALOG_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/main/voices.json?download=true"

Progress = Optional[Callable[[str], None]]

_lock = threading.Lock()
_loaded_voices = {}


class EngineError(Exception):
    pass


def _say(progress: Progress, msg: str) -> None:
    if progress:
        progress(msg)


# =====================================================================
#  Catalogue des voix Piper
# =====================================================================
def fetch_voices(use_cache: bool = True) -> list:
    """Liste des voix Piper disponibles, au même format que l'ancienne version Azure."""
    raw = None
    if use_cache and CATALOG_CACHE.exists():
        try:
            raw = json.loads(CATALOG_CACHE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            raw = None
    if raw is None:
        try:
            with urllib.request.urlopen(CATALOG_URL, timeout=30) as r:
                raw = json.load(r)
        except OSError as e:
            if CATALOG_CACHE.exists():  # hors ligne : on garde l'ancienne liste
                return fetch_voices(use_cache=True)
            raise EngineError(f"Impossible de télécharger la liste des voix ({e.__class__.__name__}). "
                              "Vérifie ta connexion Internet.")
        CATALOG_CACHE.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")

    voices = []
    for key, v in raw.items():
        lang = v.get("language", {})
        code = lang.get("code", key.split("-")[0])            # ex. es_MX
        country = lang.get("country_english", "")
        name_en = lang.get("name_english", code)
        voices.append({
            "name": key,                                        # ex. es_MX-claude-high
            "display": f"{v.get('name', key).replace('_', ' ').title()}",
            "gender": f"qualité {v.get('quality', '?')}",
            "locale": code.replace("_", "-"),                   # ex. es-MX
            "locale_name": f"{name_en} ({country})" if country else name_en,
        })
    return sorted(voices, key=lambda x: (x["locale"], x["name"]))


# =====================================================================
#  Voix : téléchargement et synthèse
# =====================================================================
def voice_installed(voice_key: str) -> bool:
    return (VOICES_DIR / f"{voice_key}.onnx").exists() and (VOICES_DIR / f"{voice_key}.onnx.json").exists()


def ensure_voice(voice_key: str, progress: Progress = None) -> None:
    if voice_installed(voice_key):
        return
    from piper.download_voices import download_voice
    VOICES_DIR.mkdir(parents=True, exist_ok=True)
    _say(progress, f"Téléchargement de la voix {voice_key} (une seule fois)…")
    try:
        download_voice(voice_key, VOICES_DIR)
    except Exception as e:
        for ext in (".onnx", ".onnx.json"):          # pas de fichier à moitié téléchargé
            (VOICES_DIR / f"{voice_key}{ext}").unlink(missing_ok=True)
        raise EngineError(f"Téléchargement de la voix {voice_key} impossible : {e}")


def _load_voice(voice_key: str):
    if voice_key not in _loaded_voices:
        from piper import PiperVoice
        ensure_voice(voice_key)
        _loaded_voices[voice_key] = PiperVoice.load(str(VOICES_DIR / f"{voice_key}.onnx"))
    return _loaded_voices[voice_key]


def _resample(samples: np.ndarray, src_rate: int) -> np.ndarray:
    if src_rate == SAMPLE_RATE or len(samples) == 0:
        return samples
    n_out = int(round(len(samples) * SAMPLE_RATE / src_rate))
    x_old = np.linspace(0.0, 1.0, num=len(samples), endpoint=False)
    x_new = np.linspace(0.0, 1.0, num=n_out, endpoint=False)
    return np.interp(x_new, x_old, samples.astype(np.float32)).astype(np.int16)


def synthesize_pcm(text: str, voice_key: str, rate: int = 0) -> bytes:
    """Audio PCM 16 bits mono à SAMPLE_RATE. rate en % : -15 = 15 % plus lent."""
    from piper import SynthesisConfig
    with _lock:
        voice = _load_voice(voice_key)
        length_scale = None if not rate else 1.0 / (1.0 + rate / 100.0)
        cfg = SynthesisConfig(length_scale=length_scale)
        pause = np.zeros(int(voice.config.sample_rate * 0.25), dtype=np.int16)  # entre les phrases
        parts = []
        for chunk in voice.synthesize(text, cfg):
            parts.append(chunk.audio_int16_array)
            parts.append(pause)
        if not parts:
            raise EngineError("La voix n'a rien produit pour ce texte.")
        audio = np.concatenate(parts[:-1])
        return _resample(audio, voice.config.sample_rate).tobytes()


# =====================================================================
#  Traduction : Argos Translate
# =====================================================================
def argos_code(locale: str) -> str:
    """fr-CA -> fr, es-MX -> es, zh-CN -> zh."""
    return locale.split("-")[0].lower()


def _installed_pairs() -> set:
    import argostranslate.package as pk
    return {(p.from_code, p.to_code) for p in pk.get_installed_packages()}


def translation_installed(src_locale: str, tgt_locale: str) -> bool:
    s, t = argos_code(src_locale), argos_code(tgt_locale)
    pairs = _installed_pairs()
    return (s, t) in pairs or ((s, "en") in pairs and ("en", t) in pairs) or s == t


def ensure_translation(src_locale: str, tgt_locale: str, progress: Progress = None) -> None:
    """Installe le modèle direct si disponible, sinon passe par l'anglais (ex. fr → en → es)."""
    if translation_installed(src_locale, tgt_locale):
        return
    import argostranslate.package as pk
    import argostranslate.translate as tr

    s, t = argos_code(src_locale), argos_code(tgt_locale)
    _say(progress, "Recherche des modèles de traduction…")
    try:
        pk.update_package_index()
        available = {(p.from_code, p.to_code): p for p in pk.get_available_packages()}
    except Exception as e:
        raise EngineError(f"Impossible de joindre le catalogue de traduction ({e.__class__.__name__}). "
                          "Vérifie ta connexion Internet.")

    if (s, t) in available:
        needed = [(s, t)]
    elif (s, "en") in available and ("en", t) in available:
        needed = [(s, "en"), ("en", t)]
    else:
        raise EngineError(f"Aucun modèle de traduction {s} → {t} disponible dans Argos Translate.")

    installed = _installed_pairs()
    for pair in needed:
        if pair in installed:
            continue
        pkg = available[pair]
        _say(progress, f"Téléchargement du modèle {pkg.from_name} → {pkg.to_name} (une seule fois)…")
        try:
            pk.install_from_path(pkg.download())
        except Exception as e:
            raise EngineError(f"Téléchargement du modèle {pair[0]} → {pair[1]} impossible : {e}")
    tr.get_installed_languages.cache_clear()   # Argos garde la liste en cache


def translate(text: str, src_locale: str, tgt_locale: str) -> str:
    import argostranslate.translate as tr
    s, t = argos_code(src_locale), argos_code(tgt_locale)
    if s == t:
        return text
    ensure_translation(src_locale, tgt_locale)
    with _lock:
        try:
            return tr.translate(text, s, t)
        except Exception as e:
            raise EngineError(f"Traduction impossible : {e}")


# =====================================================================
#  Préparation complète (au premier lancement ou après un changement)
# =====================================================================
def prepare(src_locale, src_voice, tgt_locale, tgt_voice, progress: Progress = None) -> None:
    ensure_voice(src_voice, progress)
    ensure_voice(tgt_voice, progress)
    ensure_translation(src_locale, tgt_locale, progress)
    _say(progress, "Chargement des modèles…")
    _load_voice(src_voice)
    _load_voice(tgt_voice)
