"""Paginated Shelly.GetComponents helper."""

from __future__ import annotations

from shelly_mcp.client import ShellyClient


def fetch_components(client: ShellyClient, **params: object) -> dict:
    """Return all components, following Shelly.GetComponents pagination."""
    all_items: list[dict] = []
    offset = 0
    total: int | None = None
    cfg_rev = None
    while True:
        page = client.call("Shelly.GetComponents", {**params, "offset": offset})
        batch = page.get("components") or []
        if total is None:
            total = page.get("total")
            cfg_rev = page.get("cfg_rev")
        all_items.extend(batch)
        offset += len(batch)
        if not batch:
            break
        if total is not None and offset >= total:
            break
    count = total if total is not None else len(all_items)
    return {
        "components": all_items,
        "total": count,
        "cfg_rev": cfg_rev,
        "offset": 0,
    }
