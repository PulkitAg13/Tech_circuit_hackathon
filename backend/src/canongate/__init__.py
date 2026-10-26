"""CanonGate: Pre-publication brand & claim governance."""

from __future__ import annotations

import importlib.abc
import importlib.machinery
import importlib.util
import json
import os
import pathlib
import sys

os.environ.setdefault("OMP_THREAD_LIMIT", "1")
import typing
from typing import Any

import pydantic

_PKG_ROOT = pathlib.Path(__file__).resolve().parent


class _DirectStatFinder(importlib.abc.MetaPathFinder):
    """Fallback MetaPathFinder using direct `stat()` (`is_file`/`is_dir`) for 9p dcache mounts."""

    def find_spec(
        self,
        fullname: str,
        path: Any = None,
        target: Any = None,
    ) -> importlib.machinery.ModuleSpec | None:
        if not fullname.startswith("canongate."):
            return None
        rel_parts = fullname.split(".")[1:]
        cand_dir = _PKG_ROOT.joinpath(*rel_parts)
        init_py = cand_dir / "__init__.py"
        if init_py.is_file():
            return importlib.util.spec_from_file_location(
                fullname,
                init_py,
                submodule_search_locations=[str(cand_dir)],
            )
        cand_file = _PKG_ROOT.joinpath(*rel_parts[:-1], f"{rel_parts[-1]}.py")
        if cand_file.is_file():
            return importlib.util.spec_from_file_location(fullname, cand_file)
        return None


if not any(type(f).__name__ == "_DirectStatFinder" for f in sys.meta_path):
    sys.meta_path.append(_DirectStatFinder())


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
