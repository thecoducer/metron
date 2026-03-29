"""Semantic entity matching using ONNX Runtime.

Clusters variant entity names (company names, sector labels) into
canonical groups using sentence embeddings and cosine similarity.
Used by the company exposure analysis to deduplicate entities that
appear differently across mutual fund portfolio data sources.

Examples of variants that should cluster together::

    "HDFC Bank Ltd."  /  "HDFC Bank Limited"  /  "HDFC Bank (24/11/2011)"
    "TATA CONSULTANCY SERV LT"  /  "Tata Consultancy Services Limited"
    "Finance - Banks - Private Sector"  /  "Banking"

Uses ``all-MiniLM-L6-v2`` via ONNX Runtime for lightweight CPU
inference — no PyTorch or GPU dependencies required.
"""

import re
import threading
from pathlib import Path

import numpy as np
import onnxruntime as ort
from tokenizers import Tokenizer

from ..constants import MINILM_MODEL_PATH, SEMANTIC_MATCH_THRESHOLD
from ..logging_config import logger

# ---------------------------------------------------------------------------
# Preprocessing — strip noise that doesn't help distinguish entities
# so the model focuses on the semantically meaningful part.
# ---------------------------------------------------------------------------

_DATE_SUFFIX_RE = re.compile(r"\s*\(\d{1,2}/\d{1,2}/\d{4}\)\s*")
_LEGAL_SUFFIX_RE = re.compile(
    r"\b(?:ltd|limited|pvt|private|inc"
    r"|incorporated|corp|corporation)\b\.?",
    re.IGNORECASE,
)
_WHITESPACE_RE = re.compile(r"\s+")


def _preprocess_for_embedding(name: str) -> str:
    """Strip dates and legal suffixes for cleaner embedding.

    >>> _preprocess_for_embedding("HDFC Bank Limited (24/06/2026)")
    'HDFC Bank'
    >>> _preprocess_for_embedding("Tata Consultancy Services Ltd.")
    'Tata Consultancy Services'
    """
    name = _DATE_SUFFIX_RE.sub(" ", name)
    name = _LEGAL_SUFFIX_RE.sub("", name)
    return _WHITESPACE_RE.sub(" ", name).strip()


# ---------------------------------------------------------------------------
# EntityMatcher
# ---------------------------------------------------------------------------


class EntityMatcher:
    """Groups variant entity names using semantic similarity.

    Names are preprocessed (dates / legal suffixes stripped), encoded
    into 384-dim vectors, and compared via cosine similarity.  Similar
    names are clustered using union-find with a configurable threshold.
    The longest member of each cluster is chosen as the canonical
    representative.
    """

    def __init__(
        self,
        threshold: float = SEMANTIC_MATCH_THRESHOLD,
    ) -> None:
        self.threshold = threshold
        # Resolve model path relative to project root (two levels up from
        # this file: app/api/entity_matcher.py → project root).
        project_root = Path(__file__).resolve().parent.parent.parent
        model_dir = project_root / MINILM_MODEL_PATH
        logger.info("Loading ONNX model from %s …", model_dir)
        self._tokenizer = Tokenizer.from_file(str(model_dir / "tokenizer.json"))
        self._tokenizer.enable_padding()
        self._tokenizer.enable_truncation(max_length=512)
        self._session = ort.InferenceSession(
            str(model_dir / "onnx" / "model.onnx"),
        )
        logger.info("MiniLM model loaded (cpu-only)")

    # ---- public API -------------------------------------------------------

    def cluster_names(self, names: list[str]) -> dict[str, str]:
        """Cluster similar names and return mapping to canonical form.

        Each input name is mapped to the longest member of its cluster,
        which serves as the canonical representative.

        Args:
            names: Unique names to cluster.

        Returns:
            Dict mapping each input name to its canonical
            representative.
        """
        if not names:
            return {}
        if len(names) == 1:
            return {names[0]: names[0]}

        processed = [_preprocess_for_embedding(n) for n in names]
        embeddings = self._encode(processed)

        # Pairwise cosine similarity (dot product since normalised).
        sim_matrix: np.ndarray = embeddings @ embeddings.T

        # Union-find clustering.
        parent = list(range(len(names)))

        def find(x: int) -> int:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a: int, b: int) -> None:
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb

        for i in range(len(names)):
            for j in range(i + 1, len(names)):
                if float(sim_matrix[i][j]) >= self.threshold:
                    union(i, j)

        # Group by cluster root.
        clusters: dict[int, list[int]] = {}
        for i in range(len(names)):
            root = find(i)
            clusters.setdefault(root, []).append(i)

        # Pick canonical representative — longest name in the cluster.
        name_map: dict[str, str] = {}
        for indices in clusters.values():
            cluster_members = [names[i] for i in indices]
            canonical = max(cluster_members, key=len)
            for member in cluster_members:
                name_map[member] = canonical

        return name_map

    # ---- private ---------------------------------------------------------

    def _encode(self, texts: list[str]) -> np.ndarray:
        """Tokenize, run ONNX inference, mean-pool, and L2-normalize."""
        encoded = self._tokenizer.encode_batch(texts)
        input_ids = np.array([e.ids for e in encoded], dtype=np.int64)
        attention_mask = np.array([e.attention_mask for e in encoded], dtype=np.int64)
        token_type_ids = np.array([e.type_ids for e in encoded], dtype=np.int64)
        outputs = self._session.run(
            None,
            {
                "input_ids": input_ids,
                "attention_mask": attention_mask,
                "token_type_ids": token_type_ids,
            },
        )
        # Mean pooling over token embeddings.
        token_embeddings: np.ndarray = outputs[0]  # type: ignore[assignment]
        mask = attention_mask[:, :, np.newaxis].astype(np.float32)
        summed = np.sum(token_embeddings * mask, axis=1)
        counts = np.clip(mask.sum(axis=1), a_min=1e-9, a_max=None)
        mean_pooled = summed / counts
        # L2 normalise.
        norms = np.linalg.norm(mean_pooled, axis=1, keepdims=True)
        return mean_pooled / norms


# ---------------------------------------------------------------------------
# Lazy singleton — loads model on first use
# ---------------------------------------------------------------------------

_matcher: EntityMatcher | None = None
_matcher_lock = threading.Lock()


def get_entity_matcher() -> EntityMatcher:
    """Return the singleton EntityMatcher, loading the model on first use."""
    global _matcher
    if _matcher is None:
        with _matcher_lock:
            if _matcher is None:
                _matcher = EntityMatcher()
    return _matcher
