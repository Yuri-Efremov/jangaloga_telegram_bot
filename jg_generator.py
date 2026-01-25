from __future__ import annotations

import hashlib
import re


_RU_LETTERS_RE = re.compile(r"^[А-Яа-яЁё]+$", flags=re.UNICODE)


def is_ru_word(token: str) -> bool:
    return bool(_RU_LETTERS_RE.fullmatch(token))


def _h(word: str) -> bytes:
    return hashlib.sha256(word.encode("utf-8")).digest()


def generate_jg(word_ru: str, *, reserved: set[str] | None = None, kind: str | None = None) -> str:
    """
    Deterministically generates a "Jangaloga-looking" Cyrillic token.

    - reserved: set of forms we must not output (to avoid collisions with fixed words)
    - kind: optional hint: "verb"|"noun"|"adj" (influences ending)
    """
    w = word_ru.strip().lower().replace("ё", "е")
    if not w:
        raise ValueError("empty word")

    reserved = reserved or set()
    d = _h(w)

    # phoneme-ish pools inspired by your seed examples
    consonants = ["г", "к", "п", "б", "д", "м", "н", "л", "ж", "ч", "т", "з", "р", "с"]
    vowels = ["а", "о", "у", "я", "ё", "и", "э", "ю", "е"]
    mid = ["гл", "лю", "но", "па", "гу", "жо", "ни", "ля", "мо", "бо", "до", "ти", "по", "чо", "ма"]

    # length 2..4 syllable-ish
    syl_n = 2 + (d[0] % 3)
    parts: list[str] = []
    for i in range(syl_n):
        c = consonants[d[1 + i] % len(consonants)]
        v = vowels[d[8 + i] % len(vowels)]
        chunk = c + v
        if d[16 + i] % 4 == 0:
            chunk = mid[d[24 + i] % len(mid)]
        parts.append(chunk)

    stem = "".join(parts)

    if kind == "verb":
        ending = ["ить", "нить", "ожить", "атъ"][d[31] % 4]
        if ending == "атъ":
            ending = "ать"
    elif kind == "adj":
        ending = ["ати", "ий", "ино", "ый"][d[30] % 4]
    else:
        ending = ["а", "я", "они", "ка", "ти", "ня"][d[29] % 6]

    candidate = stem + ending

    # ensure not reserved (very unlikely, but make it safe)
    if candidate in reserved:
        candidate = candidate + "я"
        if candidate in reserved:
            candidate = candidate + "ни"
    return candidate


