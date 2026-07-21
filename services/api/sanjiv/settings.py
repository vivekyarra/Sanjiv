import json
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    sanjiv_env: str = "development"
    sanjiv_log_level: str = "INFO"
    database_url: str = Field(
        default="postgresql+asyncpg://sanjiv:change-me-local-only@localhost:5432/sanjiv"
    )
    redis_url: str = "redis://localhost:6379/0"
    minio_endpoint: str = "http://localhost:9000"
    sanjiv_allowed_origins: str = "http://localhost:3000"
    sanjiv_ais_enabled: bool = True
    aisstream_api_key: str | None = None
    sanjiv_aisstream_url: str = "wss://stream.aisstream.io/v0/stream"
    sanjiv_ais_bounding_boxes: list[list[list[float]]] = [[[1.0, 40.0], [32.0, 104.0]]]
    sanjiv_ais_connect_timeout_seconds: float = Field(default=10.0, gt=0, le=60)
    sanjiv_ais_subscription_timeout_seconds: float = Field(default=3.0, gt=0, le=3)
    sanjiv_ais_max_retries: int = Field(default=3, ge=0, le=10)
    sanjiv_ais_reconnect_base_seconds: float = Field(default=1.0, gt=0, le=60)
    sanjiv_ais_reconnect_max_seconds: float = Field(default=30.0, gt=0, le=300)
    sanjiv_ais_queue_size: int = Field(default=1000, ge=10, le=10000)
    sanjiv_maritime_storage: str = "postgres"
    sanjiv_maritime_autostart: bool = True
    sanjiv_replay_dataset: Path = Path("data/replay/maritime-watch-v1/manifest.json")
    sanjiv_replay_speed: float = Field(default=20.0, gt=0, le=1000)
    sanjiv_replay_loop: bool = False
    sanjiv_replay_runtime_dir: Path = Path("data/runtime/replay")
    sanjiv_geofence_fixture: Path = Path("data/fixtures/maritime/geofences.geojson")
    sanjiv_stale_after_seconds: int = Field(default=300, ge=60, le=86400)
    sanjiv_websocket_heartbeat_seconds: float = Field(default=10.0, gt=0, le=60)
    sanjiv_scenario_storage: str = "postgres"
    sanjiv_scenario_operator_identity: str = "local-demo-operator"
    sanjiv_scenario_api_key: str | None = None
    sanjiv_procurement_storage: str = "postgres"
    sanjiv_reserve_storage: str = "postgres"
    sanjiv_risk_storage: str = "postgres"
    sanjiv_risk_replay_manifest: Path = Path("data/replay/risk-intelligence-v1/manifest.json")
    sanjiv_audit_storage: str = "postgres"
    sanjiv_phase8_storage: str = "postgres"
    sanjiv_phase8_replay_manifest: Path = Path("data/replay/energy-validation-v1/manifest.json")
    sanjiv_lpg_fixture_manifest: Path = Path("data/fixtures/lpg/manifest.json")
    sanjiv_demo_identity: str = "local-demo-approver"
    sanjiv_demo_identities: str = (
        '{"local-demo-operator":"operator","local-demo-reviewer":"reviewer",'
        '"local-demo-approver":"approver","local-demo-administrator":"administrator"}'
    )
    sanjiv_governance_api_keys: str = "{}"
    sanjiv_api_keys: str = "[]"
    sanjiv_rate_limit_per_minute: int = Field(default=120, ge=10, le=10000)
    sanjiv_max_request_bytes: int = Field(default=1_048_576, ge=1024, le=10_485_760)
    sanjiv_worker_runtime_dir: Path = Path("data/runtime/workers")
    sanjiv_dependency_checks_enabled: bool = False
    sanjiv_llm_provider: str = "disabled"
    sanjiv_llm_model: str | None = None
    sanjiv_llm_timeout_seconds: float = Field(default=10.0, gt=0, le=60)
    openai_api_key: str | None = None

    @field_validator("sanjiv_aisstream_url")
    @classmethod
    def validate_aisstream_destination(cls, value: str) -> str:
        parsed = urlparse(value)
        if (
            parsed.scheme != "wss"
            or parsed.hostname != "stream.aisstream.io"
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("SANJIV_AISSTREAM_URL must use the documented AISStream WSS host")
        return value

    @property
    def allowed_origins(self) -> list[str]:
        return [item.strip() for item in self.sanjiv_allowed_origins.split(",") if item.strip()]

    @property
    def demo_identities(self) -> dict[str, str]:
        value = json.loads(self.sanjiv_demo_identities)
        if not isinstance(value, dict) or not all(
            isinstance(key, str) and isinstance(role, str) for key, role in value.items()
        ):
            raise ValueError("SANJIV_DEMO_IDENTITIES must be a JSON object")
        return value

    @property
    def governance_api_keys(self) -> dict[str, dict[str, str]]:
        value = json.loads(self.sanjiv_governance_api_keys)
        if not isinstance(value, dict):
            raise ValueError("SANJIV_GOVERNANCE_API_KEYS must be a JSON object")
        result: dict[str, dict[str, str]] = {}
        for key, identity in value.items():
            if not isinstance(key, str) or not isinstance(identity, dict):
                raise ValueError("governance API keys must map secrets to identity objects")
            actor = identity.get("actor_id")
            role = identity.get("role")
            if not isinstance(actor, str) or not isinstance(role, str):
                raise ValueError("governance identities require actor_id and role")
            result[key] = {"actor_id": actor, "role": role}
        return result

    @property
    def api_keys(self) -> list[str]:
        value = json.loads(self.sanjiv_api_keys)
        if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
            raise ValueError("SANJIV_API_KEYS must be a JSON array of non-empty strings")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
