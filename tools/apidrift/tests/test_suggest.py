"""Tests for the mapping suggester."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from apidrift.suggest import suggest_for_model

SPEC: dict[str, Any] = {
    "openapi": "3.0.1",
    "info": {"title": "t", "version": "1"},
    "paths": {
        "/match": {
            "get": {
                "operationId": "getMatch",
                "responses": {
                    "200": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {"a": {}, "b": {}, "c": {}},
                                }
                            }
                        }
                    }
                },
            }
        },
        "/partial": {
            "get": {
                "operationId": "getPartial",
                "responses": {
                    "200": {
                        "content": {
                            "application/json": {
                                "schema": {"type": "object", "properties": {"a": {}}}
                            }
                        }
                    }
                },
            }
        },
    },
}


class Model(BaseModel):
    a: str
    b: str
    c: str


def test_suggester_ranks_best_overlap_first() -> None:
    suggestions = suggest_for_model(Model, SPEC)
    assert suggestions[0].op == "getMatch"
    assert suggestions[0].score == 1.0
    assert suggestions[0].covered == 3
    # getPartial covers only 1/3 and ranks lower.
    assert suggestions[1].op == "getPartial"
    assert suggestions[1].covered == 1
