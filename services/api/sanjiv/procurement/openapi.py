from typing import Any

from fastapi import FastAPI
from pydantic.json_schema import models_json_schema

from sanjiv.procurement.contracts import PROCUREMENT_OPENAPI_MODELS


def add_procurement_contract_schemas(application: FastAPI) -> None:
    """Add future procurement schemas without registering callable endpoints."""
    schema = application.openapi()
    _, procurement_schema = models_json_schema(
        [(model, "validation") for model in PROCUREMENT_OPENAPI_MODELS],
        ref_template="#/components/schemas/{model}",
    )
    definitions: dict[str, Any] = procurement_schema.get("$defs", {})
    components = schema.setdefault("components", {}).setdefault("schemas", {})
    components.update(definitions)
    application.openapi_schema = schema
