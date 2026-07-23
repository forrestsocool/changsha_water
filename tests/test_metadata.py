"""Repository metadata and privacy regression tests."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_manifest_and_hacs_metadata() -> None:
    manifest = json.loads(
        (ROOT / "custom_components/changsha_water/manifest.json").read_text(
            encoding="utf-8"
        )
    )
    hacs = json.loads((ROOT / "hacs.json").read_text(encoding="utf-8"))
    assert manifest["domain"] == "changsha_water"
    assert manifest["config_flow"] is True
    assert manifest["version"] == "0.1.0"
    assert hacs["country"] == "CN"


def test_private_fields_are_never_defaulted() -> None:
    flow = (ROOT / "custom_components/changsha_water/config_flow.py").read_text(
        encoding="utf-8"
    )
    for field in ("CONF_METER_NUMBER", "CONF_USER_ID", "CONF_TOKEN"):
        assert f"vol.Required({field}, default=" not in flow


def test_no_captured_example_secrets_are_committed() -> None:
    content = "\n".join(
        path.read_text(encoding="utf-8", errors="ignore")
        for base in (
            ROOT / "custom_components",
            ROOT / "README.md",
            ROOT / "hacs.json",
        )
        for path in ([base] if base.is_file() else base.rglob("*"))
        if path.is_file() and "__pycache__" not in path.parts
    )
    assert "801376329" not in content
    assert "466727" not in content
    assert "4AE717FF" not in content
