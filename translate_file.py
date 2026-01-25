from __future__ import annotations

import argparse
import re
from pathlib import Path

from translator import Dictionary

_HAS_WORD_RE = re.compile(r"[A-Za-zА-Яа-яЁё]+", flags=re.UNICODE)


def main() -> None:
    parser = argparse.ArgumentParser(description="Translate RU text file to Jangaloga using a fixed dictionary.")
    parser.add_argument("--in", dest="in_path", required=True, help="Input RU .txt path (utf-8).")
    parser.add_argument("--out", dest="out_path", required=True, help="Output JG .txt path (utf-8).")
    parser.add_argument(
        "--dict",
        dest="dict_path",
        default="dictionary.json",
        help="Dictionary JSON path (default: dictionary.json).",
    )
    args = parser.parse_args()

    in_path = Path(args.in_path)
    out_path = Path(args.out_path)
    dict_path = Path(args.dict_path)

    if not in_path.exists():
        raise SystemExit(f"Input not found: {in_path}")
    if not dict_path.exists():
        raise SystemExit(
            f"Dictionary not found: {dict_path}\n"
            "Build it first:\n"
            "  python build_dictionary.py --n 2500 --out dictionary.json"
        )

    dictionary = Dictionary.load(dict_path)
    ru_text = in_path.read_text(encoding="utf-8")
    jg_text = dictionary.translate_text(ru_text)
    if not _HAS_WORD_RE.search(jg_text):
        raise SystemExit(
            "Не получилось перевести в Джангалогу: в тексте не нашлось слов из словаря.\n"
            "Попробуйте переформулировать или расширить словарь."
        )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(jg_text, encoding="utf-8")
    print(f"Wrote: {out_path}")


if __name__ == "__main__":
    main()


