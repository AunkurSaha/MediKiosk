"""The sole authoring source is ai/complaint_flows; persisted snapshots pin each run."""

import json
from functools import lru_cache
from pathlib import Path

from app.schemas.flow import Flow

FLOW_ROOT = Path(__file__).resolve().parents[3] / "ai" / "complaint_flows"


def load_flows(root: Path = FLOW_ROOT) -> dict[str, Flow]:
    flows = {}
    for path in sorted(root.rglob("*.json")):
        try:
            flow = Flow.model_validate(json.loads(path.read_text(encoding="utf-8")))
            if flow.flow_id in flows:
                raise ValueError(f"duplicate flow ID: {flow.flow_id}")
            flows[flow.flow_id] = flow
        except (ValueError, OSError) as exc:
            raise ValueError(f"Invalid complaint flow {path.name}: {exc}") from exc
    if not flows:
        raise ValueError("No complaint flow configuration found")
    return flows


@lru_cache
def registry():
    return load_flows()
