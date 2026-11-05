"""Map Shelly output components (Switch vs Light) for plugs vs dimmers."""

from __future__ import annotations

from shelly_mcp.client import ShellyClient, ShellyError
from shelly_mcp.components import fetch_components


def output_kind(
    client: ShellyClient, output_id: int = 0, forced: str | None = None
) -> str:
    """Return ``switch`` or ``light`` for the given output id."""
    if forced in ("switch", "light"):
        return forced
    try:
        data = fetch_components(client, dynamic=True)
    except ShellyError:
        data = {}
    for item in data.get("components") or []:
        key = item.get("key") or ""
        if key == f"light:{output_id}":
            return "light"
        if key == f"switch:{output_id}":
            return "switch"
    if _supports(client, "Switch.GetStatus", output_id):
        return "switch"
    if _supports(client, "Light.GetStatus", output_id):
        return "light"
    raise ShellyError(
        f"No switch:{output_id} or light:{output_id} on this device. "
        "Use get_components or list_methods."
    )


def _supports(client: ShellyClient, method: str, output_id: int) -> bool:
    try:
        client.call(method, {"id": output_id})
        return True
    except ShellyError as exc:
        if "404" in str(exc) or "No handler" in str(exc):
            return False
        raise


def get_status(
    client: ShellyClient, output_id: int = 0, forced_kind: str | None = None
) -> dict:
    kind = output_kind(client, output_id, forced_kind)
    method = "Switch.GetStatus" if kind == "switch" else "Light.GetStatus"
    status = client.call(method, {"id": output_id})
    return {"kind": kind, "id": output_id, "status": status}


def set_output(
    client: ShellyClient,
    on: bool,
    output_id: int = 0,
    brightness: int | None = None,
    forced_kind: str | None = None,
) -> dict:
    kind = output_kind(client, output_id, forced_kind)
    if kind == "switch":
        if brightness is not None:
            raise ShellyError("brightness applies to Light (dimmers), not Switch relays")
        client.call("Switch.Set", {"id": output_id, "on": on})
    else:
        params: dict = {"id": output_id, "on": on}
        if brightness is not None:
            if not 0 <= brightness <= 100:
                raise ShellyError("brightness must be 0–100")
            params["brightness"] = brightness
        client.call("Light.Set", params)
    return get_status(client, output_id, forced_kind=kind)


def turn_off(
    client: ShellyClient, output_id: int = 0, forced_kind: str | None = None
) -> dict:
    """Turn off a switch relay or dimmer light (Light.Set on=false)."""
    kind = output_kind(client, output_id, forced_kind)
    if kind == "light":
        client.call("Light.Set", {"id": output_id, "on": False})
    else:
        client.call("Switch.Set", {"id": output_id, "on": False})
    return get_status(client, output_id, forced_kind=kind)


def turn_on(
    client: ShellyClient,
    output_id: int = 0,
    brightness: int | None = None,
    forced_kind: str | None = None,
) -> dict:
    kind = output_kind(client, output_id, forced_kind)
    if kind == "light":
        if brightness is None:
            brightness = 100
        if not 0 <= brightness <= 100:
            raise ShellyError("brightness must be 0–100")
        client.call("Light.Set", {"id": output_id, "on": True, "brightness": brightness})
    else:
        if brightness is not None:
            raise ShellyError("brightness applies to dimmers (Light), not Switch relays")
        client.call("Switch.Set", {"id": output_id, "on": True})
    return get_status(client, output_id, forced_kind=kind)


def toggle_output(
    client: ShellyClient, output_id: int = 0, forced_kind: str | None = None
) -> dict:
    kind = output_kind(client, output_id, forced_kind)
    before = get_status(client, output_id, kind)
    if kind == "light":
        client.call("Light.Toggle", {"id": output_id})
    else:
        output = before["status"].get("output")
        if not isinstance(output, bool):
            raise ShellyError(f"Output {output_id} has no boolean on/off state")
        client.call("Switch.Set", {"id": output_id, "on": not output})
    after = get_status(client, output_id, kind)
    return {"before": before, "after": after, "ok": True}
