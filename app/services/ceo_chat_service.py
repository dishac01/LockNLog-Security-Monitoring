"""
CEO mitigation assistant: curated dataset + TF-IDF retrieval (trained index)
and live context from the asset archive + high-risk logs.
"""

from __future__ import annotations

import json
import logging
import pickle
import re
from pathlib import Path
from threading import Lock

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "ceo_mitigation_dataset.jsonl"
INDEX_CACHE_PATH = _PROJECT_ROOT / "instance" / "ceo_chat_index.pkl"

_lock = Lock()
_records: list[dict] = []
_vectorizer: TfidfVectorizer | None = None
_doc_matrix = None  # scipy sparse or ndarray


def _record_to_text(rec: dict) -> str:
    parts = [
        rec.get("title") or "",
        rec.get("content") or "",
        rec.get("domain") or "",
        " ".join(rec.get("tags") or []),
        " ".join(rec.get("risk_bands") or []),
    ]
    return " ".join(p for p in parts if p).strip()


def load_dataset() -> list[dict]:
    if not DATA_PATH.is_file():
        logger.warning("CEO mitigation dataset missing at %s", DATA_PATH)
        return []
    rows: list[dict] = []
    with DATA_PATH.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                logger.warning("skip bad jsonl line")
    return rows


def _fit_vectorizer(records: list[dict]) -> tuple[TfidfVectorizer, np.ndarray]:
    corpus = [_record_to_text(r) for r in records]
    vectorizer = TfidfVectorizer(
        max_features=6000,
        ngram_range=(1, 2),
        min_df=1,
        stop_words="english",
    )
    X = vectorizer.fit_transform(corpus)
    return vectorizer, X


def _try_load_cache() -> bool:
    global _records, _vectorizer, _doc_matrix
    if not INDEX_CACHE_PATH.is_file():
        return False
    try:
        if DATA_PATH.stat().st_mtime > INDEX_CACHE_PATH.stat().st_mtime:
            return False
    except OSError:
        return False
    try:
        with INDEX_CACHE_PATH.open("rb") as f:
            payload = pickle.load(f)
        _records = payload["records"]
        _vectorizer = payload["vectorizer"]
        _doc_matrix = payload["matrix"]
        return True
    except Exception:
        logger.exception("failed to load CEO chat index cache")
        return False


def ensure_index_trained() -> None:
    """Load or fit TF-IDF index (thread-safe)."""
    global _records, _vectorizer, _doc_matrix
    with _lock:
        if _vectorizer is not None and _doc_matrix is not None and _records:
            return
        if _try_load_cache():
            return
        _records = load_dataset()
        if not _records:
            _vectorizer = None
            _doc_matrix = None
            return
        _vectorizer, _doc_matrix = _fit_vectorizer(_records)
        try:
            INDEX_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
            with INDEX_CACHE_PATH.open("wb") as f:
                pickle.dump(
                    {"records": _records, "vectorizer": _vectorizer, "matrix": _doc_matrix},
                    f,
                )
        except Exception:
            logger.exception("could not persist CEO chat index cache")


def build_and_save_index() -> dict:
    """Explicit training entrypoint (used by scripts)."""
    global _records, _vectorizer, _doc_matrix
    with _lock:
        _records = load_dataset()
        if not _records:
            return {"ok": False, "error": "no records", "count": 0}
        _vectorizer, _doc_matrix = _fit_vectorizer(_records)
        INDEX_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with INDEX_CACHE_PATH.open("wb") as f:
            pickle.dump(
                {"records": _records, "vectorizer": _vectorizer, "matrix": _doc_matrix},
                f,
            )
        return {"ok": True, "count": len(_records), "cache": str(INDEX_CACHE_PATH)}


def retrieve_top_k(query: str, k: int = 6) -> list[tuple[dict, float]]:
    ensure_index_trained()
    if not _vectorizer or _doc_matrix is None or not _records:
        return []
    q = (query or "").strip()
    if not q:
        return []
    q_vec = _vectorizer.transform([q])
    sims = cosine_similarity(q_vec, _doc_matrix)[0]
    top_idx = np.argsort(sims)[::-1][:k]
    out: list[tuple[dict, float]] = []
    for i in top_idx:
        out.append((_records[int(i)], float(sims[int(i)])))
    return out


def _fetch_live_context() -> str:
    from app.extensions import db
    from app.models.asset import Asset
    from app.models.log import Log

    lines: list[str] = []

    assets = Asset.query.order_by(Asset.business_value.desc()).all()
    lines.append("ASSET ARCHIVE (registered):")
    for a in assets:
        lines.append(
            f"- {a.name} id={a.id} dept={a.department} business_value={a.business_value} "
            f"criticality={a.criticality} sensitivity={a.sensitivity} exposure={a.exposure}"
        )

    lines.append("\nRECENT HIGH-RISK LOG SNAPSHOT (up to 15):")
    risky = (
        Log.query.filter(Log.risk_band.in_(["HIGH", "CRITICAL"]))
        .order_by(Log.timestamp.desc())
        .limit(15)
        .all()
    )
    if not risky:
        risky = Log.query.order_by(Log.timestamp.desc()).limit(10).all()
    for log in risky:
        lines.append(
            f"- ts={log.timestamp.isoformat()} type={log.log_type} sev={log.severity} "
            f"risk_band={log.risk_band} risk_score={log.risk_score} anomaly={log.anomaly_score} "
            f"asset={log.asset_id} event={log.event_type}"
        )

    return "\n".join(lines)


def _sanitize_user_message(msg: str) -> str:
    msg = (msg or "").strip()
    msg = re.sub(r"\s+", " ", msg)
    return msg[:4000]


def compose_reply(user_message: str, history: list[dict]) -> tuple[str, list[dict]]:
    """
    Build assistant reply from retrieval + live asset/log context.
    history: [{"role":"user"|"assistant","content": str}, ...]
    """
    live = _fetch_live_context()
    hist_text = " ".join(
        (h.get("content") or "") for h in history[-8:] if isinstance(h, dict) and h.get("content")
    )
    query = f"{user_message}\n{hist_text}\n{live}"
    hits = retrieve_top_k(query, k=6)

    lines: list[str] = []
    lines.append(
        "Here is a concise mitigation-oriented response based on LockNLog’s **curated playbook** "
        "(trained TF-IDF retrieval over the dataset), your **registered asset archive**, and **recent high-risk logs**.\n"
    )

    if not hits:
        lines.append(
            "The mitigation index is empty or not yet trained. Run `python scripts/train_ceo_mitigation_index.py` "
            "from the project root, then try again.\n"
        )
        lines.append("---\n**Live context (still applies):**\n" + live)
        return "\n".join(lines), []

    lines.append("**Top playbook matches (retrieve & reason):**\n")
    sources: list[dict] = []
    for i, (rec, score) in enumerate(hits, 1):
        rid = rec.get("id", "?")
        title = rec.get("title", "Untitled")
        content = rec.get("content", "").strip()
        lines.append(f"{i}. **{title}** _(playbook id: {rid}, relevance {score:.3f})_\n{content}\n")
        sources.append({"id": rid, "title": title, "score": round(score, 4)})

    lines.append("---\n**How this ties to your environment:**\n")
    lines.append(
        "Use the asset lines above to decide which controls (exposure, sensitivity, business value) "
        "amplify severity. Cross-check high-risk log lines with owning teams within 24h when CRITICAL appears.\n"
    )
    lines.append(
        "\n*Disclaimer: This assistant does not replace legal, fraud, or incident-response counsel; "
        "it retrieves local guidance and live inventory context only.*"
    )

    return "\n".join(lines), sources


def chat(user_message: str, history: list[dict] | None) -> dict:
    msg = _sanitize_user_message(user_message)
    hist = history if isinstance(history, list) else []
    hist = [h for h in hist if isinstance(h, dict) and h.get("role") in ("user", "assistant") and h.get("content")]
    hist = hist[-12:]
    reply, sources = compose_reply(msg, hist)
    return {"reply": reply, "sources": sources, "index_ready": bool(_vectorizer)}
