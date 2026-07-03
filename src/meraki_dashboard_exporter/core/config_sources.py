"""Custom pydantic-settings sources for the Meraki Dashboard Exporter.

Provides :class:`FileSecretsSettingsSource`, which implements the widely-used
``<ENV_VAR>_FILE`` convention (Docker / Kubernetes / Vault secret mounts): for
any recognised ``MERAKI_EXPORTER_*_FILE`` environment variable, the referenced
file is read and its (stripped) contents supplied as the value of the
corresponding setting. This lets the Meraki API key be delivered as a mounted
secret file instead of an inline env value (#587).

Wiring
------
This source is opt-in: it only takes effect once ``Settings`` adds it in
``settings_customise_sources``. Place it **below** ``env_settings`` in the
returned tuple so a directly-set env var still wins over the file::

    @classmethod
    def settings_customise_sources(cls, settings_cls, init_settings,
                                   env_settings, dotenv_settings,
                                   file_secret_settings):
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            FileSecretsSettingsSource(settings_cls),
            file_secret_settings,
        )

Rotation semantics
------------------
The file is read **once at process startup** (when ``Settings`` is
constructed). Rotating the secret on disk therefore requires a process restart
to take effect - there is no live re-read. This mirrors the inline env-var
behaviour and is documented for operators.
"""

from __future__ import annotations

import os
import pathlib
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from pydantic_settings import PydanticBaseSettingsSource

from .logging import get_logger

if TYPE_CHECKING:
    from pydantic.fields import FieldInfo
    from pydantic_settings import BaseSettings

logger = get_logger(__name__)

_FILE_SUFFIX = "_FILE"


class FileSecretsSettingsSource(PydanticBaseSettingsSource):
    """Load settings from ``<ENV_VAR>_FILE`` file references.

    Parameters
    ----------
    settings_cls : type[BaseSettings]
        The settings class being populated (used to read ``env_prefix`` and
        ``env_nested_delimiter`` from its ``model_config``).
    environ : Mapping[str, str] | None
        Environment mapping to inspect. Defaults to :data:`os.environ`.

    """

    def __init__(
        self,
        settings_cls: type[BaseSettings],
        environ: Mapping[str, str] | None = None,
    ) -> None:
        """Initialise the source from the settings class and an environ mapping."""
        super().__init__(settings_cls)
        self._environ: Mapping[str, str] = os.environ if environ is None else environ
        config = settings_cls.model_config
        self._prefix: str = config.get("env_prefix", "") or ""
        self._delimiter: str = config.get("env_nested_delimiter") or ""

    def get_field_value(self, field: FieldInfo, field_name: str) -> tuple[Any, str, bool]:
        """Not used - values are assembled in :meth:`__call__`."""
        return None, field_name, False

    def _read_secret_file(self, path: str) -> str | None:
        """Read and strip a secret file, warning (not failing) on error."""
        try:
            with pathlib.Path(path).open(encoding="utf-8") as handle:
                return handle.read().strip()
        except OSError as exc:
            logger.warning(
                "Could not read file-based secret; ignoring",
                path=path,
                error=str(exc),
            )
            return None

    def _assign_nested(self, tree: dict[str, Any], dotted_upper: str, value: str) -> None:
        """Insert ``value`` into ``tree`` under the (lower-cased) nested path."""
        if self._delimiter:
            parts = dotted_upper.split(self._delimiter.upper())
        else:
            parts = [dotted_upper]
        keys = [part.lower() for part in parts]
        node = tree
        for key in keys[:-1]:
            child = node.get(key)
            if not isinstance(child, dict):
                child = {}
                node[key] = child
            node = child
        node[keys[-1]] = value

    def __call__(self) -> dict[str, Any]:
        """Build a (possibly nested) mapping of settings from ``*_FILE`` env vars."""
        result: dict[str, Any] = {}
        prefix_upper = self._prefix.upper()
        for key, path in self._environ.items():
            upper = key.upper()
            if not upper.endswith(_FILE_SUFFIX):
                continue
            if prefix_upper and not upper.startswith(prefix_upper):
                continue
            target = upper[: -len(_FILE_SUFFIX)]
            if prefix_upper:
                target = target[len(prefix_upper) :]
            if not target:
                continue
            content = self._read_secret_file(path)
            if content is None:
                continue
            self._assign_nested(result, target, content)
        return result
