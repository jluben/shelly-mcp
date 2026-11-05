"""Shelly Pro RGBWW PM — RGB + CCT control by device profile."""

from __future__ import annotations

from shelly_mcp.client import ShellyClient, ShellyError

PROFILES = ("light", "rgbcct", "cctx2", "rgbx2light")


def component_keys(client: ShellyClient) -> set[str]:
    try:
        data = client.call("Shelly.GetComponents", {"dynamic": True})
    except ShellyError:
        return set()
    return {c.get("key") for c in (data.get("components") or []) if c.get("key")}


def detect_profile(client: ShellyClient, configured: str | None = None) -> str:
    if configured and configured in PROFILES:
        return configured
    keys = component_keys(client)
    if "rgb:0" in keys and "cct:0" in keys:
        return "rgbcct"
    if "cct:0" in keys and "cct:1" in keys and "rgb:0" not in keys:
        return "cctx2"
    if "rgb:0" in keys and any(k.startswith("light:") for k in keys):
        return "rgbx2light"
    if any(k.startswith("light:") for k in keys):
        return "light"
    raise ShellyError(
        f"Could not detect Pro RGBWW profile from components: {sorted(keys)}. "
        f"Set profile in shelly-config.json to one of {PROFILES}."
    )


def get_rgbww_status(client: ShellyClient, profile: str | None = None) -> dict:
    prof = detect_profile(client, profile)
    out: dict = {"profile": prof}
    if prof == "rgbcct":
        out["rgb"] = client.call("RGB.GetStatus", {"id": 0})
        out["cct"] = client.call("CCT.GetStatus", {"id": 0})
    elif prof == "cctx2":
        out["cct_0"] = client.call("CCT.GetStatus", {"id": 0})
        out["cct_1"] = client.call("CCT.GetStatus", {"id": 1})
    elif prof == "rgbx2light":
        out["rgb"] = client.call("RGB.GetStatus", {"id": 0})
        out["light_0"] = client.call("Light.GetStatus", {"id": 0})
        out["light_1"] = client.call("Light.GetStatus", {"id": 1})
    else:
        lights = {}
        for lid in range(5):
            key = f"light:{lid}"
            if key in component_keys(client):
                lights[str(lid)] = client.call("Light.GetStatus", {"id": lid})
        out["lights"] = lights
    return out


def set_rgb(
    client: ShellyClient,
    *,
    on: bool | None = None,
    red: int | None = None,
    green: int | None = None,
    blue: int | None = None,
    brightness: int | None = None,
    rgb_id: int = 0,
    transition_duration: float | None = None,
) -> dict:
    params: dict = {"id": rgb_id}
    if on is not None:
        params["on"] = on
    if brightness is not None:
        if not 0 <= brightness <= 100:
            raise ShellyError("brightness must be 0–100")
        params["brightness"] = brightness
    if red is not None or green is not None or blue is not None:
        if red is None or green is None or blue is None:
            raise ShellyError("red, green, and blue must all be set together (0–255)")
        for name, val in (("red", red), ("green", green), ("blue", blue)):
            if not 0 <= val <= 255:
                raise ShellyError(f"{name} must be 0–255")
        params["rgb"] = [red, green, blue]
    if transition_duration is not None:
        params["transition_duration"] = transition_duration
    if len(params) == 1:
        raise ShellyError("set_rgb needs on, brightness, and/or red/green/blue")
    client.call("RGB.Set", params)
    return client.call("RGB.GetStatus", {"id": rgb_id})


def set_cct(
    client: ShellyClient,
    *,
    on: bool | None = None,
    brightness: int | None = None,
    ct: int | None = None,
    cct_id: int = 0,
    transition_duration: float | None = None,
) -> dict:
    params: dict = {"id": cct_id}
    if on is not None:
        params["on"] = on
    if brightness is not None:
        if not 0 <= brightness <= 100:
            raise ShellyError("brightness must be 0–100")
        params["brightness"] = brightness
    if ct is not None:
        if not 1000 <= ct <= 10000:
            raise ShellyError("ct (Kelvin) is usually 2700–6500; allowed 1000–10000")
        params["ct"] = ct
    if transition_duration is not None:
        params["transition_duration"] = transition_duration
    if len(params) == 1:
        raise ShellyError("set_cct needs on, brightness, and/or ct")
    client.call("CCT.Set", params)
    return client.call("CCT.GetStatus", {"id": cct_id})


def rgbww_all_off(client: ShellyClient, profile: str | None = None) -> dict:
    prof = detect_profile(client, profile)
    results: dict = {"profile": prof, "actions": []}
    if prof in ("rgbcct", "rgbx2light"):
        set_rgb(client, on=False)
        results["actions"].append("RGB.Set on=false")
    if prof in ("rgbcct", "cctx2"):
        ids = (0, 1) if prof == "cctx2" else (0,)
        for cid in ids:
            set_cct(client, on=False, cct_id=cid)
            results["actions"].append(f"CCT.Set id={cid} on=false")
    if prof == "rgbx2light":
        for lid in (0, 1):
            client.call("Light.Set", {"id": lid, "on": False})
            results["actions"].append(f"Light.Set id={lid} on=false")
    if prof == "light":
        for lid in range(5):
            key = f"light:{lid}"
            if key in component_keys(client):
                client.call("Light.Set", {"id": lid, "on": False})
                results["actions"].append(f"Light.Set id={lid} on=false")
    results["status"] = get_rgbww_status(client, prof)
    return results


def set_white_channel(
    client: ShellyClient,
    brightness: int = 100,
    ct: int = 4000,
    on: bool = True,
    profile: str | None = None,
) -> dict:
    """Warm/cool white via CCT in rgbcct/cctx2; Light.Set in light profile (channel 0)."""
    prof = detect_profile(client, profile)
    if prof in ("rgbcct", "cctx2"):
        status = set_cct(client, on=on, brightness=brightness, ct=ct, cct_id=0)
        return {"profile": prof, "cct": status}
    if prof == "light":
        client.call(
            "Light.Set", {"id": 0, "on": on, "brightness": brightness}
        )
        return {
            "profile": prof,
            "light_0": client.call("Light.GetStatus", {"id": 0}),
        }
    raise ShellyError(
        f"White channel via CCT not available in profile {prof!r}; use set_rgb or set_light."
    )
