"""Tests for the spec reducer."""

from __future__ import annotations

from apidrift.reducer import index_operations, reduce_spec

SPEC = {
    "openapi": "3.0.1",
    "info": {"title": "t", "version": "1"},
    "paths": {
        "/orgs": {
            "get": {
                "operationId": "getOrgs",
                "responses": {
                    "200": {
                        "content": {
                            "application/json": {"schema": {"$ref": "#/components/schemas/Org"}}
                        }
                    }
                },
            }
        },
        "/unused": {"get": {"operationId": "getUnused", "responses": {}}},
    },
    "components": {
        "schemas": {
            "Org": {
                "type": "object",
                "properties": {"id": {"$ref": "#/components/schemas/Id"}},
            },
            "Id": {"type": "string"},
            "Orphan": {"type": "object"},
        }
    },
}


def test_index_operations() -> None:
    idx = index_operations(SPEC)
    assert idx["getOrgs"] == ("/orgs", "get")
    assert idx["getUnused"] == ("/unused", "get")


def test_reduce_keeps_only_consumed_ops_and_transitive_refs() -> None:
    reduced = reduce_spec(SPEC, {"getOrgs"})
    assert set(reduced["paths"]) == {"/orgs"}
    schemas = reduced["components"]["schemas"]
    assert set(schemas) == {"Org", "Id"}  # Orphan dropped, Id pulled transitively


def test_reduce_ignores_unknown_op() -> None:
    reduced = reduce_spec(SPEC, {"doesNotExist"})
    assert reduced["paths"] == {}
