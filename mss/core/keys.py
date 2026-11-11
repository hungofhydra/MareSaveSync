"""API keys kept in the cloud, so a new PC doesn't need them typed in again.

Only moved by hand: Settings → Sync up puts this PC's keys in the cloud, Sync down takes the cloud's. The cloud file
is shared-settings.json, {"keys": {"sgdb_key": "...", "igdb_key": "..."}}. Neither direction ever removes a key: Sync up
leaves the cloud's other keys alone, Sync down leaves this PC's other keys alone.
"""
from __future__ import annotations

KEYS = {"sgdb_key": "SteamGridDB", "igdb_key": "IGDB"}       # settings name -> shown name


def set_keys(values: dict) -> dict:
    """The keys this PC has: {name: value} without the empty ones."""
    return {k: str(values.get(k) or "").strip() for k in KEYS if str(values.get(k) or "").strip()}


def merged_doc(cloud_doc: dict, values: dict) -> dict:
    """The cloud file after Sync up: what was there, with this PC's keys put over it."""
    old = cloud_doc.get("keys") if isinstance(cloud_doc.get("keys"), dict) else {}
    return {**cloud_doc, "keys": {**old, **set_keys(values)}}


def from_cloud(cloud_doc: dict) -> dict:
    """The keys in the cloud file that Sync down can take: {name: value}."""
    return set_keys(cloud_doc.get("keys") if isinstance(cloud_doc.get("keys"), dict) else {})


def names(found) -> str:
    return " and ".join(KEYS[k] for k in KEYS if k in found)
