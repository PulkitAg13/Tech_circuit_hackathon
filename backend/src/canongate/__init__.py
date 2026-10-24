"""CanonGate: Pre-publication brand & claim governance."""

from __future__ import annotations

import json
import typing
from typing import Any

import pydantic


def _install_pydantic_v1_bridge_if_needed() -> None:
    """Provide transparent Pydantic v2 API methods when running on Pydantic 1.x system Python."""
    if hasattr(pydantic, "computed_field"):
        return

    def computed_field(func: Any = None, **_kwargs: Any) -> Any:
        if func is None:
            return lambda f: f
        return func

    pydantic.computed_field = computed_field  # type: ignore[attr-defined]

    orig_base = pydantic.BaseModel

    class _V2CompatBaseModel(orig_base):
        def __init_subclass__(cls, frozen: bool = False, **kwargs: Any) -> None:
            # Strip Annotated[..., Field(discriminator=...)] before Pydantic v1 metaclass
            anns = getattr(cls, "__annotations__", None)
            if isinstance(anns, dict):
                for k, v in list(anns.items()):
                    if typing.get_origin(v) is typing.Annotated:
                        args = typing.get_args(v)
                        if args:
                            anns[k] = args[0]
            super().__init_subclass__(**kwargs)
            if frozen:
                cls.__config__.allow_mutation = False

        def model_dump(
            self,
            *,
            mode: str = "python",
            exclude: set[str] | None = None,
            **kw: Any,
        ) -> dict[str, Any]:
            d = self.dict(exclude=exclude, **kw)
            if mode == "json":
                return json.loads(self.json(exclude=exclude))
            return d

        def model_dump_json(self, *, exclude: set[str] | None = None, **kw: Any) -> str:
            return self.json(exclude=exclude, **kw)

        def model_copy(self, *, update: dict[str, Any] | None = None, deep: bool = False) -> Any:
            return self.copy(update=update, deep=deep)

        @classmethod
        def model_validate(cls, obj: Any) -> Any:
            return cls.parse_obj(obj)

    pydantic.BaseModel = _V2CompatBaseModel  # type: ignore[misc,assignment]


_install_pydantic_v1_bridge_if_needed()
