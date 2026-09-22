"""Legacy profession/specialty labels used by the Nexus mapper.

The source platforms still emit labels from the older taxonomy.  The bundled
CSV is a label catalogue (not candidate data); it lets the Nexus mapper retain
the canonical spelling before resolving the corresponding live master ID.
Deployments may override the bundled file with ``NEXUS_LEGACY_TAXONOMY_PATH``.
Missing or malformed optional files fail open to the live-label mapper.
"""
from __future__ import annotations

import csv
import os
import re
from pathlib import Path


_DEFAULT_PATH = Path(__file__).with_name("data") / "legacy_taxonomy.csv"
_loaded = False
_professions: dict[str, str] = {}
_specialties: dict[str, str] = {}
_specialty_professions: dict[str, set[str]] = {}


def normalize(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").casefold()).strip()


def _load() -> None:
    global _loaded
    if _loaded:
        return
    _loaded = True
    configured = str(os.getenv("NEXUS_LEGACY_TAXONOMY_PATH", "") or "").strip()
    path = Path(configured).expanduser() if configured else _DEFAULT_PATH
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = csv.DictReader(handle)
            for row in rows:
                profession = " ".join(str(row.get("Old Profession") or "").split()).strip()
                specialty = " ".join(str(row.get("Old Specialty") or "").split()).strip()
                profession_key = normalize(profession)
                specialty_key = normalize(specialty)
                if profession and profession_key:
                    _professions.setdefault(profession_key, profession)
                if specialty and specialty_key:
                    _specialties.setdefault(specialty_key, specialty)
                    if profession_key:
                        _specialty_professions.setdefault(specialty_key, set()).add(
                            profession_key,
                        )
    except (OSError, csv.Error, UnicodeError):
        return


def canonical_profession(value: object) -> str:
    _load()
    text = " ".join(str(value or "").split()).strip()
    return _professions.get(normalize(text), "")


def canonical_specialty(value: object) -> str:
    _load()
    text = " ".join(str(value or "").split()).strip()
    return _specialties.get(normalize(text), text)


def is_legacy_profession(value: object) -> bool:
    _load()
    return bool(normalize(value) in _professions)


def is_legacy_specialty(value: object) -> bool:
    _load()
    return bool(normalize(value) in _specialties)


def specialty_profession_labels(value: object) -> tuple[str, ...]:
    """Return old profession labels associated with one old specialty."""
    _load()
    labels = _specialty_professions.get(normalize(value), set())
    return tuple(
        _professions[key] for key in sorted(labels) if key in _professions
    )


__all__ = [
    "canonical_profession",
    "canonical_specialty",
    "is_legacy_profession",
    "is_legacy_specialty",
    "normalize",
    "specialty_profession_labels",
]
