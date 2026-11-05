"""MCP server exposing local Shelly Gen2+ control."""

from __future__ import annotations

# Claude Desktop on Windows uses stdio; unbuffered stdout avoids MCP hangs.
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(line_buffering=True)
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(line_buffering=True)

import argparse
import json
import os
import sys
from pathlib import Path

from mcp.server.mcpserver import MCPServer

from shelly_mcp.client import ShellyClient, ShellyError
from shelly_mcp import outputs as shelly_outputs
from shelly_mcp import em50 as shelly_em50
from shelly_mcp import rgbww as shelly_rgbww
from shelly_mcp import __version__
from shelly_mcp.registry import DeviceRegistry, dumps
from shelly_mcp.rpc_params import parse_params

mcp = MCPServer(
    "shelly",
    title="Shelly Local",
    instructions=(
        "Shelly LAN control v"
        + __version__
        + ". Pro RGBWW: use get_rgbww_status, set_rgb, set_cct, set_white, rgbww_off — "
        "not Switch.*. Pro Dimmer: turn_off/turn_on/lights_off/lights_on. "
        "rgbcct profile = RGB.Set (color) + CCT.Set (white, ct in Kelvin). "
        "EM-50: list_em_channels, get_em_readings, set_em_channel_label (channels 0 and 1)."
    ),
)

_registry: DeviceRegistry | None = None


def registry() -> DeviceRegistry:
    global _registry
    if _registry is None:
        path = os.environ.get("SHELLY_CONFIG")
        _registry = DeviceRegistry.load(Path(path) if path else None)
    return _registry


def _client(device_id: str) -> ShellyClient:
    return registry().get_client(device_id)


def _forced_kind(device_id: str) -> str | None:
    return registry().get_entry(device_id).output


def _profile(device_id: str) -> str | None:
    return registry().get_entry(device_id).profile


def _em_labels(device_id: str) -> dict[int, str] | None:
    return registry().get_entry(device_id).channel_labels


def _ok(result) -> str:
    return dumps(result)


def _err(exc: Exception) -> str:
    return dumps({"error": str(exc), "ok": False})


@mcp.tool(
    description="MCP server version and configured devices. Call after restart to verify updates."
)
def server_info() -> str:
    reg = registry()
    return _ok(
        {
            "version": __version__,
            "config_path": str(reg.config_path) if reg.config_path else None,
            "devices": reg.list_devices(),
        }
    )


@mcp.tool(
    description="List Shelly devices from config (id, host, whether a password is set)."
)
def list_devices() -> str:
    return dumps({"devices": registry().list_devices()})


@mcp.tool(description="Reload shelly-config.json (or SHELLY_CONFIG) without restarting.")
def reload_config() -> str:
    return dumps(registry().reload())


@mcp.tool(description="Shelly.GetDeviceInfo for a configured device.")
def get_device_info(device_id: str) -> str:
    try:
        result = registry().get_client(device_id).call("Shelly.GetDeviceInfo")
    except ShellyError as exc:
        raise ValueError(str(exc)) from exc
    return dumps(result)


@mcp.tool(
    description=(
        "Shelly.GetComponents summary: light/switch/input keys on the device."
    )
)
def get_components(device_id: str) -> str:
    try:
        result = registry().get_client(device_id).call(
            "Shelly.GetComponents", {"dynamic": True}
        )
        keys = [c.get("key") for c in (result.get("components") or []) if c.get("key")]
    except ShellyError as exc:
        raise ValueError(str(exc)) from exc
    return dumps({"keys": keys, "components": result.get("components"), "total": result.get("total")})


@mcp.tool(
    description=(
        "On/off and brightness for plug (Switch) or dimmer (Light). "
        "Auto-detects component type."
    )
)
def get_output_status(device_id: str, output_id: int = 0) -> str:
    try:
        result = shelly_outputs.get_status(
            _client(device_id), output_id, _forced_kind(device_id)
        )
    except (ShellyError, KeyError) as exc:
        return _err(exc)
    return _ok(result)


@mcp.tool(
    description=(
        "Turn OFF office lights, dimmers, or relays. Use this instead of set_switch "
        "when the user says lights off. Calls Light.Set on=false for dimmers."
    )
)
def turn_off(device_id: str, output_id: int = 0) -> str:
    try:
        result = shelly_outputs.turn_off(
            _client(device_id), output_id, _forced_kind(device_id)
        )
    except (ShellyError, KeyError) as exc:
        return _err(exc)
    return _ok({"ok": True, **result})


@mcp.tool(
    description=(
        "Turn ON lights, dimmers, or relays. Dimmers default to brightness 100."
    )
)
def turn_on(
    device_id: str, output_id: int = 0, brightness: int | None = None
) -> str:
    try:
        result = shelly_outputs.turn_on(
            _client(device_id),
            output_id,
            brightness,
            _forced_kind(device_id),
        )
    except (ShellyError, KeyError) as exc:
        return _err(exc)
    return _ok({"ok": True, **result})


@mcp.tool(
    description=(
        "Turn ON the office-lights dimmer (default device_id office-lights, brightness 100)."
    )
)
def lights_on(device_id: str = "office-lights", brightness: int = 100) -> str:
    return turn_on(device_id, 0, brightness)


@mcp.tool(description="Turn OFF the office-lights dimmer (default device_id office-lights).")
def lights_off(device_id: str = "office-lights") -> str:
    return turn_off(device_id)


@mcp.tool(
    description=(
        "Control a configured device: action is on, off, toggle, or status. "
        "Works for dimmers (Light) and plugs (Switch). Prefer this over set_switch."
    )
)
def control_device(
    device_id: str,
    action: str,
    output_id: int = 0,
    brightness: int = 100,
) -> str:
    act = action.strip().lower()
    if act == "status":
        return get_output_status(device_id, output_id)
    if act == "off":
        return turn_off(device_id, output_id)
    if act == "on":
        return turn_on(device_id, output_id, brightness)
    if act == "toggle":
        return toggle_output(device_id, output_id)
    return _err(ValueError('action must be "on", "off", "toggle", or "status"'))


@mcp.tool(
    description=(
        "Turn output on/off. Dimmers: optional brightness 0–100 with Light.Set."
    )
)
def set_output(
    device_id: str, on: bool, output_id: int = 0, brightness: int | None = None
) -> str:
    if not on:
        return turn_off(device_id, output_id)
    try:
        result = shelly_outputs.set_output(
            _client(device_id),
            on,
            output_id,
            brightness,
            _forced_kind(device_id),
        )
    except (ShellyError, KeyError) as exc:
        return _err(exc)
    return _ok({"ok": True, **result})


@mcp.tool(description="Flip on/off state (Switch or Light).")
def toggle_output(device_id: str, output_id: int = 0) -> str:
    try:
        result = shelly_outputs.toggle_output(
            _client(device_id), output_id, _forced_kind(device_id)
        )
    except (ShellyError, KeyError) as exc:
        return _err(exc)
    return _ok(result)


@mcp.tool(description="Light.GetStatus for dimmers (not plugs).")
def get_light_status(device_id: str, light_id: int = 0) -> str:
    try:
        result = registry().get_client(device_id).call(
            "Light.GetStatus", {"id": light_id}
        )
    except ShellyError as exc:
        raise ValueError(str(exc)) from exc
    return dumps(result)


@mcp.tool(description="Light.Set — on/off and optional brightness 0–100.")
def set_light(
    device_id: str, on: bool, light_id: int = 0, brightness: int | None = None
) -> str:
    if not on:
        return turn_off(device_id, light_id)
    try:
        result = shelly_outputs.turn_on(
            _client(device_id), light_id, brightness, "light"
        )
    except (ShellyError, KeyError) as exc:
        return _err(exc)
    return _ok({"ok": True, **result})


@mcp.tool(description="Light.Toggle for dimmers.")
def toggle_light(device_id: str, light_id: int = 0) -> str:
    return toggle_output(device_id, light_id)


@mcp.tool(
    description=(
        "Read output state. Uses Switch on plugs/relays, Light on dimmers (auto-detect)."
    )
)
def get_switch_status(device_id: str, switch_id: int = 0) -> str:
    return get_output_status(device_id, switch_id)


@mcp.tool(
    description=(
        "Turn output on/off. Uses Switch on plugs/relays, Light on dimmers (auto-detect). "
        "For dimmer brightness use set_output or set_light."
    )
)
def set_switch(device_id: str, on: bool, switch_id: int = 0) -> str:
    if not on:
        return turn_off(device_id, switch_id)
    try:
        result = shelly_outputs.set_output(
            _client(device_id), on, switch_id, None, _forced_kind(device_id)
        )
    except (ShellyError, KeyError) as exc:
        return _err(exc)
    return _ok({"ok": True, **result})


@mcp.tool(
    description=(
        "Flip output on/off. Uses Switch on plugs/relays, Light on dimmers (auto-detect)."
    )
)
def toggle_switch(device_id: str, switch_id: int = 0) -> str:
    kind = _forced_kind(device_id)
    if kind == "light" or device_id == "office-lights":
        return toggle_output(device_id, switch_id)
    return toggle_output(device_id, switch_id)


@mcp.tool(
    description=(
        "Call any Shelly RPC method. params_json is optional JSON object, "
        'e.g. {"id": 0} for Switch.GetStatus.'
    )
)
def rpc(device_id: str, method: str, params_json: str | None = None) -> str:
    try:
        params = parse_params(params_json)
        result = _client(device_id).call(method, params)
    except (ShellyError, KeyError, ValueError) as exc:
        return _err(exc)
    return _ok(result)


@mcp.tool(
    description=(
        "Light.Set with plain arguments (no JSON). Use to dim or turn off a dimmer."
    )
)
def light_set(
    device_id: str,
    on: bool,
    light_id: int = 0,
    brightness: int | None = None,
) -> str:
    return set_light(device_id, on, light_id, brightness)


@mcp.tool(
    description=(
        "Shelly Pro RGBWW PM: read profile (rgbcct/light/…) and RGB + CCT/Light status."
    )
)
def get_rgbww_status(device_id: str) -> str:
    try:
        result = shelly_rgbww.get_rgbww_status(_client(device_id), _profile(device_id))
    except (ShellyError, KeyError) as exc:
        return _err(exc)
    return _ok(result)


@mcp.tool(
    description=(
        "Pro RGBWW: set RGB color. red/green/blue 0–255, brightness 0–100, optional on."
    )
)
def set_rgb(
    device_id: str,
    on: bool | None = None,
    red: int | None = None,
    green: int | None = None,
    blue: int | None = None,
    brightness: int | None = None,
    transition_duration: float | None = None,
) -> str:
    try:
        status = shelly_rgbww.set_rgb(
            _client(device_id),
            on=on,
            red=red,
            green=green,
            blue=blue,
            brightness=brightness,
            transition_duration=transition_duration,
        )
    except (ShellyError, KeyError) as exc:
        return _err(exc)
    return _ok({"rgb": status})


@mcp.tool(
    description=(
        "Pro RGBWW tunable white: brightness 0–100, ct color temperature in Kelvin "
        "(e.g. 2700 warm, 6500 cool). Uses CCT.Set in rgbcct profile."
    )
)
def set_cct(
    device_id: str,
    on: bool | None = None,
    brightness: int | None = None,
    ct: int | None = None,
    cct_id: int = 0,
    transition_duration: float | None = None,
) -> str:
    try:
        status = shelly_rgbww.set_cct(
            _client(device_id),
            on=on,
            brightness=brightness,
            ct=ct,
            cct_id=cct_id,
            transition_duration=transition_duration,
        )
    except (ShellyError, KeyError) as exc:
        return _err(exc)
    return _ok({"cct": status})


@mcp.tool(
    description=(
        "Pro RGBWW: turn off all channels (RGB + CCT or all Light channels) for the profile."
    )
)
def rgbww_off(device_id: str) -> str:
    try:
        result = shelly_rgbww.rgbww_all_off(_client(device_id), _profile(device_id))
    except (ShellyError, KeyError) as exc:
        return _err(exc)
    return _ok(result)


@mcp.tool(
    description=(
        "Pro RGBWW: white light via CCT (default ct=4000K, brightness=100). "
        "Shortcut for warm/cool white without RGB."
    )
)
def set_white(
    device_id: str,
    on: bool = True,
    brightness: int = 100,
    ct: int = 4000,
) -> str:
    try:
        result = shelly_rgbww.set_white_channel(
            _client(device_id),
            brightness=brightness,
            ct=ct,
            on=on,
            profile=_profile(device_id),
        )
    except (ShellyError, KeyError) as exc:
        return _err(exc)
    return _ok(result)


@mcp.tool(
    description=(
        "Shelly Pro EM-50: list CT channels 0 and 1 with labels from config and device."
    )
)
def list_em_channels(device_id: str) -> str:
    try:
        result = shelly_em50.list_channels(_client(device_id), _em_labels(device_id))
    except (ShellyError, KeyError) as exc:
        return _err(exc)
    return _ok({"channels": result})


@mcp.tool(
    description=(
        "EM-50 live power: voltage, current, act_power (W). channel_id 0 or 1; "
        "includes human label."
    )
)
def get_em_status(device_id: str, channel_id: int = 0) -> str:
    try:
        result = shelly_em50.get_em_status(
            _client(device_id), channel_id, _em_labels(device_id)
        )
    except (ShellyError, KeyError) as exc:
        return _err(exc)
    return _ok(result)


@mcp.tool(
    description=(
        "EM-50 total energy counters (Wh): total_act_energy, total_act_ret_energy."
    )
)
def get_em_energy(device_id: str, channel_id: int = 0) -> str:
    try:
        result = shelly_em50.get_em_energy(
            _client(device_id), channel_id, _em_labels(device_id)
        )
    except (ShellyError, KeyError) as exc:
        return _err(exc)
    return _ok(result)


@mcp.tool(
    description=(
        "EM-50 both channels: labels, live EM1 status, and EM1Data energy totals. "
        "Omit channel_id for all channels."
    )
)
def get_em_readings(device_id: str, channel_id: int | None = None) -> str:
    try:
        result = shelly_em50.get_em_snapshot(
            _client(device_id), channel_id, _em_labels(device_id)
        )
    except (ShellyError, KeyError) as exc:
        return _err(exc)
    return _ok(result)


@mcp.tool(
    description=(
        "Set EM-50 channel label in shelly-config (channels) and optionally on the "
        "device via EM1.SetConfig name. channel_id 0 or 1."
    )
)
def set_em_channel_label(
    device_id: str,
    channel_id: int,
    label: str,
    sync_to_device: bool = True,
) -> str:
    try:
        result = shelly_em50.set_channel_label(
            _client(device_id),
            channel_id,
            label,
            sync_to_device=sync_to_device,
        )
    except (ShellyError, KeyError) as exc:
        return _err(exc)
    note = (
        "Config file labels are loaded at startup; edit shelly-config.json "
        "channels and reload_config to persist locally."
    )
    return _ok({**result, "note": note})


@mcp.tool(description="Shelly.ListMethods — discover components supported by the device.")
def list_methods(device_id: str) -> str:
    try:
        result = registry().get_client(device_id).call("Shelly.ListMethods")
    except ShellyError as exc:
        raise ValueError(str(exc)) from exc
    return dumps(result)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Shelly local MCP server")
    parser.add_argument(
        "--transport",
        choices=("stdio", "sse", "streamable-http"),
        default=os.environ.get("SHELLY_MCP_TRANSPORT", "stdio"),
        help="MCP transport (default: stdio for Cursor)",
    )
    parser.add_argument(
        "--host",
        default=os.environ.get("SHELLY_MCP_HOST", "127.0.0.1"),
        help="Bind host for sse / streamable-http",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("SHELLY_MCP_PORT", "8765")),
        help="Bind port for sse / streamable-http",
    )
    args = parser.parse_args(argv)

    try:
        registry()
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc

    print(f"shelly-mcp {__version__} starting (stdio)", file=sys.stderr, flush=True)

    if args.transport == "stdio":
        mcp.run(transport="stdio")
    elif args.transport == "sse":
        mcp.run(transport="sse", host=args.host, port=args.port)
    else:
        mcp.run(
            transport="streamable-http",
            host=args.host,
            port=args.port,
            json_response=True,
            stateless_http=True,
        )


if __name__ == "__main__":
    main()
