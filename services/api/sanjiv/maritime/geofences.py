import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid5

from shapely.geometry import Point, Polygon, shape

from sanjiv.contracts import TruthClass
from sanjiv.maritime.contracts import Geofence, GeofenceEvent, GeofenceEventType, VesselPosition

GEOFENCE_ENGINE_VERSION = "geofence-engine-1.0.0"


def load_geofences(path: Path) -> list[Geofence]:
    collection = json.loads(path.read_text(encoding="utf-8"))
    if collection.get("type") != "FeatureCollection":
        raise ValueError("geofence fixture must be a GeoJSON FeatureCollection")
    geofences: list[Geofence] = []
    for feature in collection.get("features", []):
        geometry = shape(feature["geometry"])
        if not isinstance(geometry, Polygon) or not geometry.is_valid:
            raise ValueError("each geofence must be a valid Polygon")
        properties = feature["properties"]
        truth_class = TruthClass(properties["truth_class"])
        if properties.get("authoritative", False) and truth_class is TruthClass.ASSUMPTION:
            raise ValueError("assumption geofence cannot be authoritative")
        slug = str(properties["slug"])
        geofences.append(
            Geofence(
                id=uuid5(NAMESPACE_URL, f"urn:sanjiv:geofence:{slug}"),
                slug=slug,
                name=properties["name"],
                kind=properties["kind"],
                coordinates=[
                    [tuple(pair) for pair in ring] for ring in feature["geometry"]["coordinates"]
                ],
                source_ref=properties["source_ref"],
                effective_at=datetime.fromisoformat(
                    properties["effective_at"].replace("Z", "+00:00")
                ).astimezone(UTC),
                truth_class=truth_class,
                confidence=float(properties["confidence"]),
                evidence_id=uuid5(
                    NAMESPACE_URL, f"urn:sanjiv:evidence:geofence:{slug}:{properties['version']}"
                ),
                transformation=properties["transformation"],
                version=properties["version"],
                authoritative=bool(properties.get("authoritative", False)),
            )
        )
    return geofences


class GeofenceEngine:
    def __init__(self, geofences: list[Geofence]) -> None:
        self._geofences = geofences
        self._polygons = {item.id: Polygon(item.coordinates[0]) for item in geofences}
        self._state: dict[tuple[UUID, UUID], bool] = {}
        self._events: set[UUID] = set()

    def evaluate(self, position: VesselPosition) -> list[GeofenceEvent]:
        point = Point(position.longitude, position.latitude)
        events: list[GeofenceEvent] = []
        for geofence in self._geofences:
            inside = self._polygons[geofence.id].covers(point)
            key = (position.vessel_id, geofence.id)
            previous = self._state.get(key)
            self._state[key] = inside
            if previous is None or previous == inside:
                continue
            event_type = GeofenceEventType.ENTRY if inside else GeofenceEventType.EXIT
            event_id = uuid5(
                NAMESPACE_URL,
                f"urn:sanjiv:geofence-event:{position.id}:{geofence.id}:{event_type.value}",
            )
            if event_id in self._events:
                continue
            self._events.add(event_id)
            events.append(
                GeofenceEvent(
                    id=event_id,
                    vessel_id=position.vessel_id,
                    geofence_id=geofence.id,
                    position_id=position.id,
                    event_type=event_type,
                    occurred_at=position.source_timestamp,
                    confidence=min(position.confidence, geofence.confidence),
                    evidence_ids=[*position.evidence_ids, geofence.evidence_id],
                    transformation=GEOFENCE_ENGINE_VERSION,
                )
            )
        return events
