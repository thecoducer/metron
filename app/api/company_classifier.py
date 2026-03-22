"""Zero-shot company sub-industry classification using BART-MNLI.

Classifies company names into granular sub-industry labels (e.g.
"Banking", "Insurance", "Asset Management") using Facebook's
``bart-large-mnli`` model running locally on CPU.

Performance optimisations
-------------------------
1. **Persistent disk cache** — classification results are saved to
   ``data/classification_cache.json`` so they survive process
   restarts.  The cache is global (shared across all users) and
   grows over time.  After a few days/weeks of usage, almost all
   company names will be pre-cached and the model is rarely invoked.
2. **In-memory cache** — a process-local dict avoids redundant disk
   reads within a single run.
"""

import json
import os
import re
import threading

import numpy as np

from ..constants import BART_MNLI_MODEL_PATH
from ..logging_config import logger

# Strip date suffixes like "(24/09/2026)" that add noise for the model.
_DATE_SUFFIX_RE = re.compile(r"\s*\(\d{1,2}/\d{1,2}/\d{4}\)\s*")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_CACHE_PATH = os.path.join(_PROJECT_ROOT, "data", "classification_cache.json")
_SECTOR_LABELS_PATH = os.path.join(_PROJECT_ROOT, "data", "sector_labels.json")


def _load_disk_cache() -> dict[str, tuple[str, float]]:
    """Load the persistent classification cache from disk."""
    if not os.path.exists(_CACHE_PATH):
        return {}
    try:
        with open(_CACHE_PATH) as f:
            raw: dict[str, list] = json.load(f)
        return {k: (v[0], v[1]) for k, v in raw.items()}
    except (json.JSONDecodeError, KeyError, IndexError, OSError) as exc:
        logger.warning("Failed to load classification cache: %s", exc)
        return {}


_save_lock = threading.Lock()


def _save_disk_cache(cache: dict[str, tuple[str, float]]) -> None:
    """Persist the classification cache to disk (non-blocking).

    Takes a snapshot of the cache dict and writes it on a background
    thread.  A lock serialises concurrent writes so snapshots never
    collide on the temp file or silently overwrite each other.
    """
    snapshot = {k: [v[0], v[1]] for k, v in cache.items()}
    threading.Thread(
        target=_write_cache_file,
        args=(snapshot,),
        daemon=True,
    ).start()


def _write_cache_file(serialisable: dict[str, list]) -> None:
    """Write the cache JSON to disk (runs on a background thread)."""
    with _save_lock:
        os.makedirs(os.path.dirname(_CACHE_PATH), exist_ok=True)
        try:
            tmp = _CACHE_PATH + ".tmp"
            with open(tmp, "w") as f:
                json.dump(serialisable, f, indent=1, sort_keys=True)
            os.replace(tmp, _CACHE_PATH)
            logger.debug(
                "Classification cache written: %d entries",
                len(serialisable),
            )
        except OSError as exc:
            logger.warning("Failed to save classification cache: %s", exc)


# ---------------------------------------------------------------------------
# Persistent sector labels — grows from real CDN data
# ---------------------------------------------------------------------------

_sector_labels: list[str] = []
_sector_labels_lock = threading.Lock()


def _load_sector_labels() -> list[str]:
    """Load sector labels from disk."""
    if not os.path.exists(_SECTOR_LABELS_PATH):
        return []
    try:
        with open(_SECTOR_LABELS_PATH) as f:
            labels: list[str] = json.load(f)
        return sorted(set(labels))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to load sector labels: %s", exc)
        return []


def _save_sector_labels(labels: list[str]) -> None:
    """Persist sector labels to disk (non-blocking)."""
    snapshot = sorted(set(labels))
    threading.Thread(
        target=_write_sector_labels_file,
        args=(snapshot,),
        daemon=True,
    ).start()


def _write_sector_labels_file(labels: list[str]) -> None:
    """Write sector labels JSON to disk (background thread)."""
    with _sector_labels_lock:
        os.makedirs(os.path.dirname(_SECTOR_LABELS_PATH), exist_ok=True)
        try:
            tmp = _SECTOR_LABELS_PATH + ".tmp"
            with open(tmp, "w") as f:
                json.dump(labels, f, indent=1)
            os.replace(tmp, _SECTOR_LABELS_PATH)
            logger.debug("Sector labels written: %d entries", len(labels))
        except OSError as exc:
            logger.warning("Failed to save sector labels: %s", exc)


def get_sector_labels() -> list[str]:
    """Return the current sector labels list."""
    global _sector_labels
    if not _sector_labels:
        _sector_labels = _load_sector_labels()
    return _sector_labels


def update_sector_labels(new_sectors: set[str]) -> None:
    """Merge *new_sectors* into the persisted sector labels.

    Call this after fetching CDN data with the set of unique
    sector strings from the response.  Only non-empty, non-blank
    sectors are added.
    """
    global _sector_labels
    clean = {s.strip() for s in new_sectors if s and s.strip()}
    if not clean:
        return

    existing = set(get_sector_labels())
    merged = existing | clean
    if merged == existing:
        return  # nothing new

    _sector_labels = sorted(merged)
    _save_sector_labels(_sector_labels)
    logger.info(
        "Sector labels updated: %d → %d (%d new)",
        len(existing),
        len(merged),
        len(merged - existing),
    )


# ---------------------------------------------------------------------------
# Label narrowing — pick top-K relevant labels per company name
# ---------------------------------------------------------------------------

# Max candidate labels per company for BART-MNLI.  Fewer labels →
# higher confidence and faster inference.
_NARROWED_LABEL_COUNT = 10


def _narrow_labels(
    company_names: list[str],
    all_labels: list[str],
    label_embeddings: np.ndarray,
    model: object,
    top_k: int = _NARROWED_LABEL_COUNT,
) -> dict[str, list[str]]:
    """Pick the top-K most relevant labels for each company name.

    Uses SentenceTransformer cosine similarity between the company
    name and all sector labels.  Returns a dict mapping each name
    to its narrowed candidate list.
    """
    if len(all_labels) <= top_k:
        return {name: all_labels for name in company_names}

    name_embeddings = model.encode(
        company_names,
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    # cosine similarity (dot product since normalised)
    sim_matrix: np.ndarray = name_embeddings @ label_embeddings.T

    result: dict[str, list[str]] = {}
    for i, name in enumerate(company_names):
        top_indices = np.argsort(sim_matrix[i])[::-1][:top_k]
        result[name] = [all_labels[j] for j in top_indices]
    return result


# ---------------------------------------------------------------------------
# CompanyClassifier
# ---------------------------------------------------------------------------


class CompanyClassifier:
    """Zero-shot company sub-industry classifier.

    Uses a two-tier lookup:
    1. Persistent disk cache (instant, grows over time).
    2. BART-MNLI zero-shot inference (slow, last resort).

    When the model is invoked, candidate labels are first narrowed
    to the top-K most relevant (by SentenceTransformer similarity)
    to avoid diluting confidence across 100+ labels.

    Results from tier 2 are written back to the disk cache so
    subsequent runs benefit.
    """

    def __init__(self, *, load_model: bool = True) -> None:
        from transformers import pipeline

        self._cache: dict[str, tuple[str, float]] = _load_disk_cache()
        logger.info(
            "Classification cache loaded: %d entries from disk",
            len(self._cache),
        )
        labels = get_sector_labels()
        logger.info(
            "Sector labels loaded: %d entries from disk",
            len(labels),
        )
        model_path = os.path.join(_PROJECT_ROOT, BART_MNLI_MODEL_PATH)
        if load_model:
            logger.info("Loading BART-MNLI model from %s …", model_path)
            self._pipeline = pipeline(
                "zero-shot-classification",
                model=model_path,
                device="cpu",
            )
            logger.info("BART-MNLI model loaded (local, cpu-only)")
        else:
            self._pipeline = None

        # SentenceTransformer for label narrowing (loaded lazily).
        self._st_model: object | None = None
        self._label_embeddings: np.ndarray | None = None
        self._label_list: list[str] = []

    def _get_label_embeddings(self, all_labels: list[str]) -> tuple[object, np.ndarray]:
        """Return (st_model, label_embeddings), loading lazily.

        Reuses the EntityMatcher's SentenceTransformer model.
        Recomputes embeddings if the label list has changed.
        """
        if self._st_model is not None and self._label_list == all_labels and self._label_embeddings is not None:
            return self._st_model, self._label_embeddings

        from .entity_matcher import get_entity_matcher

        matcher = get_entity_matcher()
        self._st_model = matcher.model
        self._label_embeddings = matcher.model.encode(
            all_labels,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        self._label_list = all_labels
        logger.debug("Label embeddings computed: %d labels", len(all_labels))
        return self._st_model, self._label_embeddings

    def classify(
        self,
        company_name: str,
        labels: list[str] | None = None,
    ) -> tuple[str, float]:
        """Classify a company name into a sub-industry label.

        Args:
            company_name: The company name to classify.
            labels: Candidate labels.  Defaults to the dynamic
                sector labels collected from CDN data.

        Returns:
            Tuple of (best_label, confidence_score).
        """
        if company_name in self._cache:
            return self._cache[company_name]

        # BART-MNLI inference.
        if self._pipeline is None:
            return ("Unknown", 0.0)

        all_labels = labels or get_sector_labels()
        if not all_labels:
            return ("Unknown", 0.0)

        # Strip date suffixes for cleaner model input.
        clean = _DATE_SUFFIX_RE.sub("", company_name).strip()

        # Narrow labels to top-K relevant for this company.
        st_model, label_embs = self._get_label_embeddings(all_labels)
        narrowed = _narrow_labels([clean], all_labels, label_embs, st_model)[clean]

        result = self._pipeline(clean, narrowed)
        best_label: str = result["labels"][0]
        best_score: float = result["scores"][0]

        self._cache[company_name] = (best_label, best_score)
        return best_label, best_score

    def classify_batch(
        self,
        company_names: list[str],
        labels: list[str] | None = None,
    ) -> dict[str, tuple[str, float]]:
        """Classify multiple company names.

        Uses two tiers: disk cache → BART-MNLI model.  Only truly
        unknown names reach the model.  New results are persisted
        to the disk cache.

        Args:
            company_names: Company names to classify.
            labels: Candidate labels.  Defaults to the dynamic
                sector labels collected from CDN data.

        Returns:
            Dict mapping each company name to (label, confidence).
        """
        results: dict[str, tuple[str, float]] = {}
        need_model: list[str] = []
        cached_count = 0

        for name in company_names:
            if name in self._cache:
                results[name] = self._cache[name]
                cached_count += 1
                continue
            need_model.append(name)

        model_classified = 0
        if need_model:
            if self._pipeline is not None:
                all_labels = labels or get_sector_labels()
                if not all_labels:
                    for name in need_model:
                        results[name] = ("Unknown", 0.0)
                else:
                    # Strip date suffixes for cleaner model input.
                    clean_names = [_DATE_SUFFIX_RE.sub("", n).strip() for n in need_model]

                    # Narrow to top-K labels per company, then
                    # group by label set to batch efficiently.
                    st_model, label_embs = self._get_label_embeddings(all_labels)
                    per_name_labels = _narrow_labels(
                        clean_names,
                        all_labels,
                        label_embs,
                        st_model,
                    )

                    # Classify each company with its narrowed
                    # label set.  Per-name classification is needed
                    # since each company gets different candidates.
                    for orig, clean in zip(need_model, clean_names):
                        narrowed = per_name_labels[clean]
                        res = self._pipeline(clean, narrowed)
                        best_label: str = res["labels"][0]
                        best_score: float = res["scores"][0]
                        self._cache[orig] = (
                            best_label,
                            best_score,
                        )
                        results[orig] = (best_label, best_score)
                        model_classified += 1
            else:
                for name in need_model:
                    results[name] = ("Unknown", 0.0)

        logger.info(
            "Classification: %d total, %d cached, %d model",
            len(company_names),
            cached_count,
            model_classified,
        )

        if model_classified > 0:
            _save_disk_cache(self._cache)

        return results


# ---------------------------------------------------------------------------
# Lazy singleton — loads model on first use
# ---------------------------------------------------------------------------

_classifier: CompanyClassifier | None = None
_classifier_lock = threading.Lock()


def get_company_classifier() -> CompanyClassifier:
    """Return the singleton CompanyClassifier, loading the model on first use."""
    global _classifier
    if _classifier is None:
        with _classifier_lock:
            if _classifier is None:
                _classifier = CompanyClassifier()
    return _classifier
