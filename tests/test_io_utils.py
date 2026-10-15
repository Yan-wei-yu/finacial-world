import json
from datetime import datetime, timedelta, timezone

from pipeline.io_utils import num, parse_iso, read_json, to_iso, write_json_atomic


def test_write_then_read_roundtrip_keeps_chinese(tmp_path):
    target = tmp_path / "nested" / "data.json"
    write_json_atomic(target, {"title": "費半重挫", "n": 1})

    assert read_json(target, None) == {"title": "費半重挫", "n": 1}
    assert "費半重挫" in target.read_text(encoding="utf-8")


def test_write_leaves_no_temp_files(tmp_path):
    target = tmp_path / "data.json"
    write_json_atomic(target, [1, 2, 3])
    write_json_atomic(target, [4])

    assert [p.name for p in tmp_path.iterdir()] == ["data.json"]
    assert json.loads(target.read_text(encoding="utf-8")) == [4]


def test_read_json_missing_file_returns_default(tmp_path):
    assert read_json(tmp_path / "nope.json", {"fallback": True}) == {"fallback": True}


def test_read_json_corrupt_file_returns_default(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")

    assert read_json(bad, []) == []


def test_to_iso_normalises_to_utc_with_z_suffix():
    taipei = timezone(timedelta(hours=8))

    assert to_iso(datetime(2026, 10, 15, 21, 0, tzinfo=taipei)) == "2026-10-15T13:00:00Z"
    assert to_iso(datetime(2026, 10, 15, 13, 0)) == "2026-10-15T13:00:00Z"
    assert to_iso(None) is None


def test_parse_iso_accepts_z_and_offsets_and_rejects_garbage():
    assert parse_iso("2026-10-15T13:00:00Z") == datetime(2026, 10, 15, 13, 0, tzinfo=timezone.utc)
    assert parse_iso("2026-10-14T08:30:00-04:00") == datetime(2026, 10, 14, 12, 30, tzinfo=timezone.utc)
    assert parse_iso("2026-10-15T13:00:00").tzinfo is not None
    assert parse_iso("not-a-date") is None
    assert parse_iso(None) is None


def test_num_rejects_non_finite_and_non_numeric_values():
    assert num("1.5") == 1.5
    assert num(3) == 3.0
    assert num(None) is None
    assert num(float("nan")) is None
    assert num(float("inf")) is None
    assert num(True) is None
    assert num("abc") is None
