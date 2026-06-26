"""Registry of Pydantic models subject to spec-conformance checks."""

from __future__ import annotations


def conformance_models() -> list[type]:
    """Return the model classes to check against the live spec.

    Imported lazily so the rest of the tool (scanner/reducer/oasdiff emit) can run
    in environments where the full runtime package is not importable. Only classes
    *defined in* the model modules are returned — re-exported ``BaseModel`` and
    foreign subclasses are excluded.
    """
    from pydantic import BaseModel

    from meraki_dashboard_exporter.core import api_models, domain_models

    models: list[type] = []
    for module in (api_models, domain_models):
        for obj in vars(module).values():
            if (
                isinstance(obj, type)
                and issubclass(obj, BaseModel)
                and obj is not BaseModel
                and obj.__module__ == module.__name__
            ):
                models.append(obj)
    return models
