"""Minimal translation layer (French source strings, English dictionary).

    from .i18n import tr
    tr('Fichier introuvable : {path}', path=p)

The language is a process-wide setting, also exported as the HIFIALIGN_LANG environment variable so that
worker processes (spawned afterwards) produce their messages in the same language.
"""
from __future__ import annotations

import os

LANGUAGES = {'fr': 'Français', 'en': 'English'}
_ENV = 'HIFIALIGN_LANG'
_lang = os.environ.get(_ENV, 'fr') if os.environ.get(_ENV, 'fr') in LANGUAGES else 'fr'


def set_language(lang: str) -> None:
    global _lang
    _lang = lang if lang in LANGUAGES else 'fr'
    os.environ[_ENV] = _lang


def language() -> str:
    return _lang


def tr(text: str, **kw) -> str:
    if _lang == 'en':
        from .i18n_en import EN
        text = EN.get(text, text)
    return text.format(**kw) if kw else text
