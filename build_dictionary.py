from __future__ import annotations

import argparse
import importlib
import json
from pathlib import Path

from jg_generator import generate_jg, is_ru_word


def load_seed(seed_path: Path) -> dict:
    return json.loads(seed_path.read_text(encoding="utf-8"))


def _norm_ru(word: str) -> str:
    return word.lower().replace("ё", "е").strip()


def _get_morph():
    try:
        pymorphy3 = importlib.import_module("pymorphy3")
        MorphAnalyzer = getattr(pymorphy3, "MorphAnalyzer")
        return MorphAnalyzer()
    except Exception:
        return None


def _lemma_and_kind(morph, word_norm: str) -> tuple[str, str | None]:
    """
    Returns (lemma, kind) where kind is one of: 'verb'|'adj'|'noun'|None
    """
    if morph is None:
        return word_norm, None
    try:
        parses = morph.parse(word_norm)
        if not parses:
            return word_norm, None
        p0 = parses[0]
        lemma = getattr(p0, "normal_form", word_norm) or word_norm
        tag = getattr(p0, "tag", None)
        pos = getattr(tag, "POS", None) if tag is not None else None
        if pos in {"VERB", "INFN"}:
            return lemma, "verb"
        if pos in {"ADJF", "ADJS", "COMP"}:
            return lemma, "adj"
        if pos in {"NOUN"}:
            return lemma, "noun"
        return lemma, None
    except Exception:
        return word_norm, None


def main() -> None:
    print("Building dictionary...")
    parser = argparse.ArgumentParser(description="Build Jangaloga dictionary from seed + RU frequency list.")
    parser.add_argument("--seed", default="dictionary_seed.json", help="Path to seed JSON.")
    parser.add_argument("--out", default="dictionary.json", help="Output dictionary path.")
    parser.add_argument("--n", type=int, default=3000, help="Target TOTAL dictionary size (approx).")
    args = parser.parse_args()

    seed_path = Path(args.seed)
    out_path = Path(args.out)

    seed = load_seed(seed_path)
    ru_to_jg: dict[str, str] = seed.get("ru_to_jg", {}) or {}
    fallback_policy = seed.get("fallback_policy", "keep_original")
    if fallback_policy == "keep_original":
        # Safety: by default we want output to contain only Jangaloga words
        fallback_policy = "drop_unknown"

    # Reserve already-used JG forms (so generator won't collide with fixed words)
    reserved = set(ru_to_jg.values())

    # Lemmatize frequency list to avoid storing lots of inflected forms.
    try:
        wordfreq = importlib.import_module("wordfreq")
        top_n_list = getattr(wordfreq, "top_n_list")
    except Exception as e:
        raise RuntimeError(
            "Не найден пакет 'wordfreq'. Установите зависимости проекта:\n"
            "  pip install -r requirements.txt\n"
            "или:\n"
            "  pip install wordfreq\n"
        ) from e

    morph = _get_morph()

    # Ensure some common lemmas that might be missing in top-N but are useful.
    ensure_lemmas = [
        "красивый",
        "красота",
        "важный",
        "интересный",
        "удобный",
        "попробовать",
        "помочь",
        "понять",
        "сделать",
        "сказать",
        "думать",
        "читать",
        "писать",
        "говорить",
        "слышать",
        "видеть",
    ]

    candidates: list[tuple[str, str | None]] = []
    seen: set[str] = set()

    # Add ensured first
    for w in ensure_lemmas:
        w2 = _norm_ru(w)
        if not is_ru_word(w2):
            continue
        lemma, kind = _lemma_and_kind(morph, w2)
        if lemma in seen or lemma in ru_to_jg:
            continue
        seen.add(lemma)
        candidates.append((lemma, kind))

    # Then fill from frequency list
    # Oversample to compensate filtering + duplicates after lemmatization
    for w in top_n_list("ru", args.n * 5):
        w2 = _norm_ru(w)
        if not is_ru_word(w2):
            continue
        lemma, kind = _lemma_and_kind(morph, w2)
        if lemma in seen or lemma in ru_to_jg:
            continue
        seen.add(lemma)
        candidates.append((lemma, kind))
        if len(ru_to_jg) + len(candidates) >= args.n:
            break

    # Add generated mappings for anything not in seed, up to target total size
    for lemma, kind in candidates:
        if len(ru_to_jg) >= args.n:
            break
        ru_to_jg[lemma] = generate_jg(lemma, reserved=reserved, kind=kind)
        reserved.add(ru_to_jg[lemma])

    payload = {
        "meta": {
            "language_name": "Джангалога",
            "note": "Сгенерировано из seed + wordfreq(top_n_list). Seed-пары имеют приоритет.",
            "source_seed": str(seed_path.as_posix()),
            "target_size": args.n,
            "actual_size": len(ru_to_jg),
        },
        "ru_to_jg": dict(sorted(ru_to_jg.items(), key=lambda kv: kv[0])),
        "fallback_policy": fallback_policy,
        "lemmatize_ru": bool(seed.get("lemmatize_ru", True)),
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {len(ru_to_jg)} entries to {out_path}")


if __name__ == "__main__":
    main()


