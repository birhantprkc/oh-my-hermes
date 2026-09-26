"""Project the lexical shortlist index into a sidecar the plugin bundle can read.

The per-turn hook that could use `lexical_shortlist.lexical_ranking` runs
inside Hermes, from the plugin bundle, and the bundle cannot import `omh`
(`tests/test_plugin_bundle_standalone.py`). So the index is written out as
data: every skill's term weights, its anchor words, the stopwords, the
stemmer's exception words, and the BM25 constants. The stemmer's rules are
code, so the bundle repeats them and the parity test holds the two equal. The bundle's reader
(`src/plugin_bundle/omh/skill_shortlist.py`) rebuilds the ranking from this
file alone and holds no vocabulary of its own.

`omh docs skill-shortlist` writes it, `--check` fails when it drifts from the
catalog, and `tests/test_skill_shortlist_sidecar.py` holds the bundle's
ranking equal to this module's source over a fixed message set.
"""

from __future__ import annotations

import json

from . import lexical_shortlist
from .candidate_handoff import _situation
from ..skills.catalog import routable_definitions
from ..skills.catalog_types import omh_skill_display_name

SKILL_SHORTLIST_SCHEMA_VERSION = "omh_skill_shortlist_index/v1"
SKILL_SHORTLIST_SIDECAR_NAME = "skill_shortlist.json"


def _weight_key(weight: float) -> str:
    # Field weights are whole numbers, so their per-term sums are too; the key
    # keeps the sidecar free of float spellings.
    return str(int(weight)) if float(weight).is_integer() else repr(weight)


def skill_shortlist_projection() -> dict[str, object]:
    """The lexical index as plain data, one entry per routable skill in catalog order."""
    index = lexical_shortlist._index()
    definitions = {definition.name: definition for definition in routable_definitions()}
    skills: list[dict[str, object]] = []
    for name, weights, _length in index.documents:
        by_weight: dict[str, list[str]] = {}
        for term, weight in weights.items():
            by_weight.setdefault(_weight_key(weight), []).append(term)
        vocabulary = lexical_shortlist._anchor_vocabulary(name)
        frequency = lexical_shortlist._document_frequency()
        anchors = sorted(
            term
            for term in vocabulary
            if frequency.get(term, 0) <= lexical_shortlist.ANCHOR_MAX_DOCUMENT_FREQUENCY
        )
        skills.append(
            {
                "name": name,
                "label": omh_skill_display_name(name),
                "situation": _situation(definitions[name].description),
                "terms": {key: " ".join(sorted(terms)) for key, terms in by_weight.items()},
                "anchors": " ".join(anchors),
            }
        )
    return {
        "schema_version": SKILL_SHORTLIST_SCHEMA_VERSION,
        "bm25": {"k1": lexical_shortlist._K1, "b": lexical_shortlist._B},
        "score_floor": lexical_shortlist.LEXICAL_SCORE_FLOOR,
        "stopwords": " ".join(sorted(lexical_shortlist.STOPWORDS)),
        "stem_exceptions": " ".join(sorted(lexical_shortlist._STEM_EXCEPTIONS)),
        "skills": skills,
    }


def standalone_skill_shortlist_json() -> str:
    """Serialize the projection for `src/plugin_bundle/omh/tools/skill_shortlist.json`."""
    return json.dumps(skill_shortlist_projection(), ensure_ascii=False, indent=0, sort_keys=True, separators=(",", ":")) + "\n"


__all__ = [
    "SKILL_SHORTLIST_SCHEMA_VERSION",
    "SKILL_SHORTLIST_SIDECAR_NAME",
    "skill_shortlist_projection",
    "standalone_skill_shortlist_json",
]
