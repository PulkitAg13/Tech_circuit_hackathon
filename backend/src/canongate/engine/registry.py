"""Auto-discovery registry using __init_subclass__.

Any class that subclasses a registered base gets recorded automatically
when its module is imported. No central __init__.py list needed — this
eliminates merge conflicts when 4 people are adding checks in parallel.
"""

from __future__ import annotations

from typing import ClassVar, TypeVar

T = TypeVar("T")


class _RegistryMixin:
    """Mixin that auto-registers subclasses in a class-level registry.

    Subclasses MUST define `check_id: ClassVar[str]` to be registered.
    Abstract intermediaries (check_id not set) are silently skipped.
    """

    _registry: ClassVar[dict[str, type]] = {}

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        # Only register concrete classes that define check_id
        check_id = getattr(cls, "check_id", None)
        if check_id and isinstance(check_id, str):
            if check_id in cls._registry:
                existing = cls._registry[check_id]
                raise ValueError(
                    f"Duplicate check_id {check_id!r}: "
                    f"{cls.__qualname__} conflicts with {existing.__qualname__}"
                )
            cls._registry[check_id] = cls

    @classmethod
    def get_all(cls) -> dict[str, type]:
        return dict(cls._registry)

    @classmethod
    def get(cls, check_id: str) -> type | None:
        return cls._registry.get(check_id)
