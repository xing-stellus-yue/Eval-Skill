"""One-global-manager accessors for eval_skill."""

from __future__ import annotations


_eval_manager = None
_extraction_manager = None
_generation_manager = None


def get_eval_manager(*args, **kwargs):
    global _eval_manager
    if _eval_manager is None:
        from .managers.eval_manager import EvalManager

        _eval_manager = EvalManager(*args, **kwargs)
    return _eval_manager


def get_extraction_manager(*args, **kwargs):
    global _extraction_manager
    if _extraction_manager is None:
        from .managers.extraction_manager import ExtractionManager

        _extraction_manager = ExtractionManager(*args, **kwargs)
    return _extraction_manager


def get_generation_manager(*args, **kwargs):
    global _generation_manager
    if _generation_manager is None:
        from .managers.generation_manager import GenerationManager

        _generation_manager = GenerationManager(*args, **kwargs)
    return _generation_manager
