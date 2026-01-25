from __future__ import annotations

import importlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


FallbackPolicy = Literal["keep_original", "mark_unknown", "drop_unknown"]


_WORD_RE = re.compile(r"([A-Za-zА-Яа-яЁё]+|[^A-Za-zА-Яа-яЁё]+)", flags=re.UNICODE)


def _norm_ru(word: str) -> str:
    w = word.lower()
    return w.replace("ё", "е")


def _apply_case_like(template: str, word: str) -> str:
    if not word:
        return word
    if template.isupper():
        return word.upper()
    if template[:1].isupper() and template[1:].islower():
        return word[:1].upper() + word[1:]
    return word


def _cleanup_spacing(text: str) -> str:
    # Collapse whitespace
    t = re.sub(r"\s+", " ", text, flags=re.UNICODE).strip()
    # Remove space before punctuation
    t = re.sub(r"\s+([,.!?;:])", r"\1", t)
    # Remove space after opening brackets/quotes (basic)
    t = re.sub(r"([\(\[\{«])\s+", r"\1", t)
    # Ensure space after punctuation when followed by a letter (basic)
    t = re.sub(r"([,.!?;:])([A-Za-zА-Яа-яЁё])", r"\1 \2", t)
    return t.strip()


@dataclass
class Dictionary:
    path: Path
    ru_to_jg: dict[str, str]
    fallback_policy: FallbackPolicy = "keep_original"
    lemmatize_ru: bool = False

    @classmethod
    def load(cls, path: str | Path) -> "Dictionary":
        p = Path(path)
        if not p.exists():
            return cls(path=p, ru_to_jg={}, fallback_policy="keep_original")
        raw = json.loads(p.read_text(encoding="utf-8"))
        ru_to_jg = raw.get("ru_to_jg", {}) or {}
        fallback = raw.get("fallback_policy", "keep_original")
        lemmatize_ru = bool(raw.get("lemmatize_ru", False))
        return cls(path=p, ru_to_jg=ru_to_jg, fallback_policy=fallback, lemmatize_ru=lemmatize_ru)

    def save(self) -> None:
        payload = {
            "meta": {
                "language_name": "Джангалога",
                "note": "Словарь заполняется пользователем. Ассистент НЕ добавляет слова без запроса.",
            },
            "ru_to_jg": dict(sorted(self.ru_to_jg.items(), key=lambda kv: kv[0])),
            "fallback_policy": self.fallback_policy,
            "lemmatize_ru": self.lemmatize_ru,
        }
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def add(self, ru_word: str, jg_word: str) -> None:
        ru_key = _norm_ru(ru_word.strip())
        if not ru_key:
            raise ValueError("Пустое русское слово")
        jg_val = jg_word.strip()
        if not jg_val:
            raise ValueError("Пустое слово на джангалоге")
        self.ru_to_jg[ru_key] = jg_val
        self.save()

    def _lemma(self, ru_word_norm: str) -> str:
        """
        Lemmatize a normalized RU word (lowercase, 'ё'->'е') using pymorphy3.
        If pymorphy3 isn't installed or fails, returns input.
        """
        if not self.lemmatize_ru:
            return ru_word_norm
        try:
            pymorphy3 = importlib.import_module("pymorphy3")
            MorphAnalyzer = getattr(pymorphy3, "MorphAnalyzer")
        except Exception:
            return ru_word_norm
        # Cache analyzer per instance
        morph = getattr(self, "_morph", None)
        if morph is None:
            morph = MorphAnalyzer()
            setattr(self, "_morph", morph)
        try:
            parses = morph.parse(ru_word_norm)
            if not parses:
                return ru_word_norm
            return getattr(parses[0], "normal_form", ru_word_norm) or ru_word_norm
        except Exception:
            return ru_word_norm

    def translate_text(self, ru_text: str) -> str:
        parts: list[str] = []
        for tok in _WORD_RE.findall(ru_text):
            if re.fullmatch(r"[A-Za-zА-Яа-яЁё]+", tok):
                form = _norm_ru(tok)
                # If dictionary contains a specific form (e.g. plural with special meaning), prefer it.
                mapped = self.ru_to_jg.get(form)
                if mapped is None:
                    key = self._lemma(form)
                    mapped = self.ru_to_jg.get(key)
                if mapped is None:
                    if self.fallback_policy == "drop_unknown":
                        parts.append("")
                    elif self.fallback_policy == "mark_unknown":
                        parts.append(f"⟦{tok}⟧")
                    else:
                        parts.append(tok)
                else:
                    parts.append(_apply_case_like(tok, mapped))
            else:
                parts.append(tok)
        return _cleanup_spacing("".join(parts))


