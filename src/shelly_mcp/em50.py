"""Shelly Pro EM-50 — dual EM1 channels with labels."""

from __future__ import annotations

from shelly_mcp.client import ShellyClient, ShellyError

EM50_CHANNELS = (0, 1)


def parse_channel_labels(raw: object) -> dict[int, str] | None:
    if raw is None:
        return None
    if isinstance(raw, list):
        out: dict[int, str] = {}
        for i, label in enumerate(raw):
            if label is None or str(label).strip() == "":
                continue
            out[i] = str(label).strip()
        return out or None
    if isinstance(raw, dict):
        out = {}
        for key, label in raw.items():
            if label is None or str(label).strip() == "":
                continue
            out[int(key)] = str(label).strip()
        return out or None
    raise ValueError("channels must be a JSON object {\"0\": \"name\"} or [\"name0\", \"name1\"]")


def device_channel_name(client: ShellyClient, channel_id: int) -> str | None:
    try:
        cfg = client.call("EM1.GetConfig", {"id": channel_id})
    except ShellyError:
        return None
    name = cfg.get("name") if isinstance(cfg, dict) else None
    if name and str(name).strip():
        return str(name).strip()
    return None


def resolve_label(
    channel_id: int,
    config_labels: dict[int, str] | None,
    client: ShellyClient,
) -> str:
    if config_labels and channel_id in config_labels:
        return config_labels[channel_id]
    device_name = device_channel_name(client, channel_id)
    if device_name:
        return device_name
    return f"channel {channel_id}"


def list_channels(
    client: ShellyClient, config_labels: dict[int, str] | None
) -> list[dict]:
    keys = _em_keys(client)
    channels: list[dict] = []
    for cid in EM50_CHANNELS:
        key = f"em1:{cid}"
        if keys and key not in keys:
            continue
        entry: dict = {
            "id": cid,
            "label": resolve_label(cid, config_labels, client),
            "config_label": (config_labels or {}).get(cid),
            "device_name": device_channel_name(client, cid),
        }
        channels.append(entry)
    if not channels:
        for cid in EM50_CHANNELS:
            channels.append(
                {
                    "id": cid,
                    "label": resolve_label(cid, config_labels, client),
                    "config_label": (config_labels or {}).get(cid),
                    "device_name": device_channel_name(client, cid),
                }
            )
    return channels


def _em_keys(client: ShellyClient) -> set[str]:
    try:
        data = client.call("Shelly.GetComponents", {"dynamic": True})
    except ShellyError:
        return set()
    return {c.get("key") for c in (data.get("components") or []) if c.get("key")}


def get_em_status(
    client: ShellyClient,
    channel_id: int,
    config_labels: dict[int, str] | None,
) -> dict:
    if channel_id not in EM50_CHANNELS:
        raise ShellyError(f"EM-50 channel must be 0 or 1, got {channel_id}")
    status = client.call("EM1.GetStatus", {"id": channel_id})
    return {
        "channel_id": channel_id,
        "label": resolve_label(channel_id, config_labels, client),
        "status": status,
    }


def get_em_energy(
    client: ShellyClient,
    channel_id: int,
    config_labels: dict[int, str] | None,
) -> dict:
    if channel_id not in EM50_CHANNELS:
        raise ShellyError(f"EM-50 channel must be 0 or 1, got {channel_id}")
    data = client.call("EM1Data.GetStatus", {"id": channel_id})
    return {
        "channel_id": channel_id,
        "label": resolve_label(channel_id, config_labels, client),
        "energy_wh": data,
    }


def get_em_snapshot(
    client: ShellyClient,
    channel_id: int | None,
    config_labels: dict[int, str] | None,
) -> dict:
    ids = (channel_id,) if channel_id is not None else EM50_CHANNELS
    channels = []
    for cid in ids:
        if cid not in EM50_CHANNELS:
            raise ShellyError(f"EM-50 channel must be 0 or 1, got {cid}")
        channels.append(
            {
                **get_em_status(client, cid, config_labels),
                "energy_wh": client.call("EM1Data.GetStatus", {"id": cid}),
            }
        )
    return {"channels": channels}


def set_channel_label(
    client: ShellyClient,
    channel_id: int,
    label: str,
    *,
    sync_to_device: bool = True,
) -> dict:
    if channel_id not in EM50_CHANNELS:
        raise ShellyError(f"EM-50 channel must be 0 or 1, got {channel_id}")
    label = label.strip()
    if not label:
        raise ShellyError("label must be non-empty")
    result: dict = {"channel_id": channel_id, "label": label, "synced_to_device": False}
    if sync_to_device:
        resp = client.call(
            "EM1.SetConfig",
            {"id": channel_id, "config": {"name": label}},
        )
        result["synced_to_device"] = True
        result["set_config_result"] = resp
        result["device_name"] = device_channel_name(client, channel_id)
    return result
