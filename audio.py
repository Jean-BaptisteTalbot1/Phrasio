"""Assemblage audio : pauses exactes et encodage MP3, sans FFmpeg."""
from datetime import datetime, timedelta
from pathlib import Path
from typing import List

import lameenc

from local_engine import SAMPLE_RATE, synthesize_pcm
from config import Config
from store import Phrase, PhraseStore

BITRATE = 64  # kb/s, amplement suffisant pour de la voix


def silence(seconds: float) -> bytes:
    return b"\x00\x00" * int(SAMPLE_RATE * max(0.0, seconds))


def encode_mp3(pcm: bytes) -> bytes:
    enc = lameenc.Encoder()
    enc.set_bit_rate(BITRATE)
    enc.set_in_sample_rate(SAMPLE_RATE)
    enc.set_channels(1)
    enc.set_quality(2)
    return bytes(enc.encode(pcm) + enc.flush())


def build_phrase_audio(p: Phrase, cfg: Config) -> bytes:
    """Original, pause, cible, pause, cible, pause longue."""
    src = synthesize_pcm(p.source_text, p.source_voice)
    tgt = synthesize_pcm(p.target_text, p.target_voice, rate=cfg.target_rate)
    if cfg.target_first:
        # Cible d'abord : on essaie de comprendre avant d'entendre l'original
        parts = [tgt, silence(cfg.pause_between), tgt, silence(cfg.pause_after_source),
                 src, silence(cfg.pause_after)]
    else:
        parts = [src, silence(cfg.pause_after_source), tgt, silence(cfg.pause_between),
                 tgt, silence(cfg.pause_after)]
    return encode_mp3(b"".join(parts))


def generate_phrase(store: PhraseStore, p: Phrase, cfg: Config) -> None:
    mp3 = build_phrase_audio(p, cfg)
    path = store.audio_path(p)
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(mp3)
    tmp.replace(path)
    p.audio_sig = p.content_sig(cfg.audio_signature())
    store.save()


def _concat(files: List[Path], out: Path) -> None:
    # Les MP3 ont tous le même format (même encodeur, mêmes réglages) :
    # on peut simplement mettre les trames bout à bout.
    tmp = out.with_suffix(".tmp")
    with open(tmp, "wb") as f:
        for fp in files:
            f.write(fp.read_bytes())
    tmp.replace(out)


def build_lessons(store: PhraseStore, locale: str, size: int) -> List[Path]:
    phrases = [p for p in store.for_target(locale) if store.audio_path(p).exists()]
    out_dir = store.lessons_dir(locale)
    for old in out_dir.glob("*.mp3"):
        old.unlink()
    created = []
    size = max(1, size)
    for i in range(0, len(phrases), size):
        chunk = phrases[i:i + size]
        n = i // size + 1
        out = out_dir / f"lecon-{n:02d} ({chunk[0].id}-{chunk[-1].id}).mp3"
        _concat([store.audio_path(p) for p in chunk], out)
        created.append(out)

    week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    recent = [p for p in phrases if p.date >= week_ago]
    if recent:
        out = out_dir / "00 - nouvelles phrases (7 derniers jours).mp3"
        _concat([store.audio_path(p) for p in recent], out)
        created.append(out)

    if phrases:
        out = out_dir / "00 - toutes les phrases.mp3"
        _concat([store.audio_path(p) for p in phrases], out)
        created.append(out)
    return created
