"""Registry of Pydantic models subject to spec-conformance checks."""

from __future__ import annotations


def conformance_models() -> list[type]:
    """Return the model classes to check against the live spec.

    Imported lazily so the rest of the tool (scanner/reducer/oasdiff emit) can run
    in environments where the full runtime package is not importable. Only classes
    *defined in* the model modules are returned — re-exported ``BaseModel`` and
    foreign subclasses are excluded.
    """
    import importlib
    import pkgutil
    import sys

    import structlog
    from pydantic import BaseModel

    import meraki_dashboard_exporter

    excluded = {
        "meraki_dashboard_exporter.app",
        "meraki_dashboard_exporter.core.config",
        "meraki_dashboard_exporter.core.config_models",
        "meraki_dashboard_exporter.models.webhook",
    }
    config = structlog.get_config()
    was_configured = structlog.is_configured()

    def raise_import_error(name: str) -> None:
        error = sys.exception()
        if error is None:
            raise RuntimeError(f"Package walk failed for {name} without an exception")
        raise error

    try:
        structlog.configure(
            logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
            cache_logger_on_first_use=False,
        )
        module_names = sorted(
            info.name
            for info in pkgutil.walk_packages(
                meraki_dashboard_exporter.__path__,
                meraki_dashboard_exporter.__name__ + ".",
                onerror=raise_import_error,
            )
            if info.name not in excluded and info.name.rsplit(".", 1)[-1] != "__main__"
        )
        models: list[type] = []
        for name in module_names:
            module = importlib.import_module(name)
            for obj in vars(module).values():
                if (
                    isinstance(obj, type)
                    and issubclass(obj, BaseModel)
                    and obj is not BaseModel
                    and obj.__module__ == module.__name__
                ):
                    models.append(obj)
        return models
    finally:
        if was_configured:
            structlog.configure(**config)
        else:
            structlog.reset_defaults()
