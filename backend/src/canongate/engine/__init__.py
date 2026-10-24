"""Engine: auto-registering check execution, streaming runner, and shared NLP/NLI stack."""

from __future__ import annotations

import importlib.util as _ilu
import pathlib as _pl
import sys as _sys

if "canongate.engine.nlp" not in _sys.modules:
    _nlp_path = _pl.Path(__file__).with_name("nlp.py")
    if _nlp_path.is_file():
        _spec = _ilu.spec_from_file_location("canongate.engine.nlp", _nlp_path)
        if _spec is not None and _spec.loader is not None:
            _mod = _ilu.module_from_spec(_spec)
            _sys.modules["canongate.engine.nlp"] = _mod
            _spec.loader.exec_module(_mod)

from canongate.engine.check import Check
from canongate.engine.nlp import (
    HybridFactRetriever,
    MiniCheckNliScorer,
    ParsedToken,
    QASemSlotAligner,
    RetrievedFact,
    SlotAlignment,
    SpacyLinguisticAnalyzer,
    default_fact_retriever,
    default_linguistic_analyzer,
    default_nli_scorer,
    default_slot_aligner,
    extract_restrictive_qualifiers,
    extract_value_anchors,
    temperature_scale_prob,
)
from canongate.engine.runner import run_checks, run_checks_collect

__all__ = [
    "Check",
    "HybridFactRetriever",
    "MiniCheckNliScorer",
    "ParsedToken",
    "QASemSlotAligner",
    "RetrievedFact",
    "SlotAlignment",
    "SpacyLinguisticAnalyzer",
    "default_fact_retriever",
    "default_linguistic_analyzer",
    "default_nli_scorer",
    "default_slot_aligner",
    "extract_restrictive_qualifiers",
    "extract_value_anchors",
    "run_checks",
    "run_checks_collect",
    "temperature_scale_prob",
]
