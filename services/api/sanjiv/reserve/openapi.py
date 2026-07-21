from typing import Any

from fastapi import FastAPI
from pydantic.json_schema import models_json_schema

from sanjiv.reserve.contracts import RESERVE_OPENAPI_MODELS


def add_reserve_contract_schemas(application: FastAPI) -> None:
    schema = application.openapi()
    _, reserve_schema = models_json_schema(
        [(model, "validation") for model in RESERVE_OPENAPI_MODELS],
        ref_template="#/components/schemas/{model}",
    )
    definitions: dict[str, Any] = reserve_schema.get("$defs", {})
    schema.setdefault("components", {}).setdefault("schemas", {}).update(definitions)
    application.openapi_schema = schema
