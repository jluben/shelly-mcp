"""Resolve configured devices to live RPC clients."""

from __future__ import annotations

import json
from pathlib import Path

from shelly_mcp.client import ShellyClient
from shelly_mcp.config import DeviceEntry, load_config


class DeviceRegistry:
    def __init__(self, devices: list[DeviceEntry], config_path: Path | None):
        self._devices = {d.id: d for d in devices}
        self.config_path = config_path

    @classmethod
    def load(cls, config_path: Path | None = None) -> DeviceRegistry:
        devices, path = load_config(config_path)
        return cls(devices, path)

    def list_devices(self) -> list[dict]:
        out: list[dict] = []
        for entry in self._devices.values():
            out.append(
                {
                    "id": entry.id,
                    "host": entry.host,
                    "has_password": entry.password is not None,
                    "output": entry.output or "auto",
                    "profile": entry.profile or "auto",
                    "type": entry.device_type or "auto",
                    "channels": (
                        {str(k): v for k, v in entry.channel_labels.items()}
                        if entry.channel_labels
                        else None
                    ),
                }
            )
        return out

    def get_entry(self, device_id: str) -> DeviceEntry:
        entry = self._devices.get(device_id)
        if entry is None:
            ids = ", ".join(sorted(self._devices))
            raise KeyError(f"Unknown device_id {device_id!r}. Configured: {ids}")
        return entry

    def get_client(self, device_id: str) -> ShellyClient:
        entry = self._devices.get(device_id)
        if entry is None:
            ids = ", ".join(sorted(self._devices))
            raise KeyError(f"Unknown device_id {device_id!r}. Configured: {ids}")
        return ShellyClient(entry.host, entry.password)

    def reload(self, config_path: Path | None = None) -> dict:
        fresh = self.load(config_path)
        self._devices = fresh._devices
        self.config_path = fresh.config_path
        return {
            "reloaded": True,
            "config_path": str(self.config_path) if self.config_path else None,
            "devices": self.list_devices(),
        }


def dumps(data) -> str:
    return json.dumps(data, indent=2, sort_keys=True)
