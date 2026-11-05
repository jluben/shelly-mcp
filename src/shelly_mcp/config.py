"""Load Shelly device registry from file or environment."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from shelly_mcp.em50 import parse_channel_labels


@dataclass(frozen=True)
class DeviceEntry:
    id: str
    host: str
    password: str | None
    output: str | None  # "light", "switch", or None for auto-detect
    profile: str | None  # pro rgbww: light, rgbcct, cctx2, rgbx2light
    device_type: str | None  # e.g. em50
    channel_labels: dict[int, str] | None  # EM-50 CT channel names


def _password_for(entry: dict, default_password_env: str | None) -> str | None:
    if "password" in entry and entry["password"]:
        return str(entry["password"])
    env_name = entry.get("password_env") or default_password_env
    if env_name:
        value = os.environ.get(str(env_name))
        if value:
            return value
    return None


def load_config(path: Path | None = None) -> tuple[list[DeviceEntry], Path | None]:
    """Return devices and the config path that was used (if any)."""
    config_path = path or _resolve_config_path()
    if config_path is not None and config_path.is_file():
        raw = json.loads(config_path.read_text(encoding="utf-8"))
        return _parse_config_object(raw), config_path

    inline = os.environ.get("SHELLY_DEVICES")
    if inline:
        raw = json.loads(inline)
        return _parse_config_object(raw), None

    host = os.environ.get("SHELLY_HOST")
    if host:
        device_id = os.environ.get("SHELLY_DEVICE_ID", "default")
        password = os.environ.get("SHELLY_PASSWORD")
        return [
            DeviceEntry(
                id=device_id,
                host=host,
                password=password,
                output=None,
                profile=None,
                device_type=None,
                channel_labels=None,
            )
        ], None

    raise FileNotFoundError(
        "No Shelly config found. Copy config.example.json to shelly-config.json, "
        "set SHELLY_CONFIG, pass SHELLY_DEVICES JSON, or set SHELLY_HOST."
    )


def _resolve_config_path() -> Path | None:
    explicit = os.environ.get("SHELLY_CONFIG")
    if explicit:
        return Path(explicit).expanduser()
    cwd = Path.cwd() / "shelly-config.json"
    if cwd.is_file():
        return cwd
    user = Path.home() / ".config" / "shelly-mcp" / "config.json"
    if user.is_file():
        return user
    return None


def _parse_config_object(raw: dict | list) -> list[DeviceEntry]:
    if isinstance(raw, list):
        devices_raw = raw
        default_password_env = "SHELLY_PASSWORD"
    else:
        devices_raw = raw.get("devices", [])
        default_password_env = raw.get("default_password_env")

    entries: list[DeviceEntry] = []
    seen: set[str] = set()
    for item in devices_raw:
        if not isinstance(item, dict):
            raise ValueError("Each device entry must be an object")
        device_id = str(item.get("id") or "").strip()
        host = str(item.get("host") or "").strip()
        if not device_id or not host:
            raise ValueError("Each device needs non-empty id and host")
        if device_id in seen:
            raise ValueError(f"Duplicate device id: {device_id}")
        seen.add(device_id)
        output = item.get("output")
        if output is not None:
            output = str(output).strip().lower()
            if output not in ("light", "switch"):
                raise ValueError(f"device {device_id}: output must be light, switch, or omitted")
        profile = item.get("profile")
        if profile is not None:
            profile = str(profile).strip().lower()
            allowed = ("light", "rgbcct", "cctx2", "rgbx2light")
            if profile not in allowed:
                raise ValueError(f"device {device_id}: profile must be one of {allowed}")
        device_type = item.get("type") or item.get("device_type")
        if device_type is not None:
            device_type = str(device_type).strip().lower()
        channel_labels = parse_channel_labels(item.get("channels"))
        entries.append(
            DeviceEntry(
                id=device_id,
                host=host,
                password=_password_for(item, default_password_env),
                output=output,
                profile=profile,
                device_type=device_type,
                channel_labels=channel_labels,
            )
        )
    if not entries:
        raise ValueError("No devices configured")
    return entries
