from sanjiv.maritime.adapters.aisstream import AISStreamAdapter


def test_aisstream_timestamp_and_record_id_are_deterministic() -> None:
    payload = {
        "MessageType": "PositionReport",
        "Metadata": {"MMSI": 999123456, "time_utc": "2026-07-20T10:00:00Z"},
        "Message": {"PositionReport": {"Latitude": 20.0, "Longitude": 70.0}},
    }
    timestamp = AISStreamAdapter._extract_source_timestamp(payload)
    assert timestamp.isoformat() == "2026-07-20T10:00:00+00:00"
    assert AISStreamAdapter._record_id(payload) == AISStreamAdapter._record_id(payload)
    assert AISStreamAdapter._record_id(payload).startswith("sha256:")


def test_provider_message_id_is_preserved() -> None:
    payload = {"Metadata": {"MessageID": "provider-42"}}
    assert AISStreamAdapter._record_id(payload) == "provider-42"
