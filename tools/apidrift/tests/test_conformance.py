"""Tests for Pydantic model conformance against the live spec."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from apidrift.conformance import check_models


def _op(op_id: str, props: dict[str, dict[str, str]]) -> dict[str, Any]:
    return {
        f"/{op_id}": {
            "get": {
                "operationId": op_id,
                "responses": {
                    "200": {
                        "content": {
                            "application/json": {"schema": {"type": "object", "properties": props}}
                        }
                    }
                },
            }
        }
    }


SPEC: dict[str, Any] = {
    "openapi": "3.0.1",
    "info": {"title": "t", "version": "1"},
    "paths": {
        **_op("getDevice", {"serial": {"type": "string"}, "count": {"type": "integer"}}),
        **_op("getOther", {"extraField": {"type": "string"}}),
        **_op("getNested", {"network": {"type": "object"}}),
        **_op("getTyped", {"count": {"type": "integer"}}),
    },
}


class _NetworkRef(BaseModel):
    id: str | None = None


class NarrowerSubmodel(BaseModel):
    # Spec says bare `object`; model narrows it to a structured submodel.
    # Strictly-narrower typing must be INFO, not a gating WARNING.
    __meraki_op__ = "getNested"
    network: _NetworkRef | None = None


class RealMismatch(BaseModel):
    # Spec says integer; model says str -> genuine drift, must stay WARNING.
    __meraki_op__ = "getTyped"
    count: str


class GoodModel(BaseModel):
    __meraki_op__ = "getDevice"
    serial: str
    count: int


class OptionalFieldModel(BaseModel):
    __meraki_op__ = "getDevice"
    serial: str | None = None
    count: int


class ModelExtra(BaseModel):
    __meraki_op__ = "getDevice"
    serial: str
    derived: str  # not in spec — enrichment field


class UnionModel(BaseModel):
    # Aggregate: serial+count from getDevice, extraField from getOther.
    __meraki_op__ = ["getDevice", "getOther"]
    serial: str
    count: int
    extraField: str


class AnyFieldModel(BaseModel):
    __meraki_op__ = "getDevice"
    serial: str
    count: Any  # untyped — must never be a type-mismatch even if spec says integer


class DerivedModel(BaseModel):
    __meraki_derived__ = True
    whatever: str


class ChildModel(GoodModel):
    # No own __meraki_op__; must NOT inherit GoodModel's op.
    pass


class Unmapped(BaseModel):
    serial: str


def test_conformant_model_yields_no_findings() -> None:
    findings = check_models([GoodModel], SPEC)
    assert findings == []


def test_optional_field_type_check_unwraps_none() -> None:
    # str | None must still be recognised as compatible with spec 'string'.
    findings = check_models([OptionalFieldModel], SPEC)
    assert findings == []


def test_model_extra_field_is_info_not_gating() -> None:
    findings = check_models([ModelExtra], SPEC)
    extras = [f for f in findings if f.kind == "model-extra"]
    assert extras and all(f.severity == "INFO" for f in extras)
    assert any("derived" in f.detail for f in extras)


def test_union_mapping_accepts_fields_from_any_mapped_op() -> None:
    # extraField only exists in getOther; the union must accept it.
    findings = check_models([UnionModel], SPEC)
    assert findings == []


def test_any_typed_field_is_never_a_mismatch() -> None:
    findings = check_models([AnyFieldModel], SPEC)
    assert not [f for f in findings if f.kind == "type-mismatch"]


def test_derived_model_reported_info_and_not_checked() -> None:
    findings = check_models([DerivedModel], SPEC)
    assert [f for f in findings if f.kind == "derived" and f.severity == "INFO"]
    assert not [f for f in findings if f.kind in {"model-extra", "type-mismatch"}]


def test_child_does_not_inherit_meraki_op() -> None:
    findings = check_models([ChildModel], SPEC)
    assert any(f.kind == "unmapped" for f in findings)


def test_unmapped_model_reported_info() -> None:
    findings = check_models([Unmapped], SPEC)
    assert any(f.kind == "unmapped" and f.severity == "INFO" for f in findings)


def test_structured_submodel_vs_bare_object_is_info_not_gating() -> None:
    # Model narrows a spec `object` field to a Pydantic submodel: strictly narrower,
    # reported INFO (model-narrower), never a gating WARNING.
    findings = check_models([NarrowerSubmodel], SPEC)
    assert not [f for f in findings if f.severity == "WARNING"]
    narrower = [f for f in findings if f.kind == "model-narrower"]
    assert narrower and all(f.severity == "INFO" for f in narrower)


def test_real_type_mismatch_still_warns() -> None:
    findings = check_models([RealMismatch], SPEC)
    assert [f for f in findings if f.kind == "type-mismatch" and f.severity == "WARNING"]
