#!/usr/bin/env python3
"""
Train (fit) the CEO mitigation TF-IDF index from app/data/ceo_mitigation_dataset.jsonl
and write instance/ceo_chat_index.pkl.

Run from project root:
    python scripts/train_ceo_mitigation_index.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import create_app  # noqa: E402
from app.services import ceo_chat_service  # noqa: E402


def main() -> None:
    app = create_app(testing=True)
    with app.app_context():
        out = ceo_chat_service.build_and_save_index()
    print(out)


if __name__ == "__main__":
    main()
