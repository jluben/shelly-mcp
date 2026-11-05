# shelly-mcp

Local [Model Context Protocol](https://modelcontextprotocol.io/) server for **Shelly Gen2+** devices on your LAN. Talks JSON-RPC over HTTP (`http://<device>/rpc`) — the same API the Shelly app uses.

Works with **Cursor**, **Claude Desktop**, and any MCP client that supports stdio (or streamable HTTP via Docker).

## Supported hardware (high level)

| Device | How this server controls it |
|--------|-----------------------------|
| Plugs / relays | `Switch.*` (auto-detected) |
| Dimmers (e.g. Pro Dimmer) | `Light.*` — use `turn_on` / `turn_off` / `lights_on` |
| **Pro RGBWW PM** | `RGB.Set` + `CCT.Set` (`set_rgb`, `set_cct`, `set_white`, `rgbww_off`) |
| **Pro EM-50** | `EM1.*` / `EM1Data.*` with **labeled channels** (`get_em_readings`, etc.) |
| Anything else Gen2+ | Generic `rpc` + `list_methods` |

Gen1 devices (`/relay/0` only) are **not** supported.

## Requirements

- Python **3.11+**
- Shelly devices on a network reachable from the machine running the MCP server
- Optional: [Docker](https://www.docker.com/) for HTTP transport on a LAN host

## Repository

Hosted on [Cursor Origin](https://origin.cursor.com): **josh-0wx8p/shelly-mcp** (private).  
Web: [cursor.com/codebase/josh-0wx8p/shelly-mcp](https://cursor.com/codebase/josh-0wx8p/shelly-mcp)

## Install

```powershell
git clone https://origin.cursor.com/josh-0wx8p/shelly-mcp.git shelly-mcp
cd shelly-mcp
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
```

On macOS/Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Configuration

Copy the example and edit device IPs (Shelly app → device info, or your router):

```powershell
Copy-Item config.example.json shelly-config.json
```

Example `shelly-config.json`:

```json
{
  "devices": [
    {
      "id": "office-lights",
      "host": "192.168.5.11",
      "output": "light"
    },
    {
      "id": "office-busy-sign",
      "host": "192.168.5.19",
      "output": "switch"
    },
    {
      "id": "office-outdoor-lights",
      "host": "192.168.5.12",
      "profile": "rgbcct"
    },
    {
      "id": "office-power-meter",
      "host": "192.168.5.15",
      "type": "em50",
      "channels": {
        "0": "AC",
        "1": "Office"
      }
    }
  ]
}
```

| Field | Meaning |
|-------|---------|
| `id` | Name you use in MCP tool calls |
| `host` | LAN IP or hostname |
| `output` | `light` or `switch` — hints for on/off helpers (optional) |
| `profile` | Pro RGBWW: `rgbcct`, `light`, `cctx2`, `rgbx2light` |
| `type` | `em50` for Pro EM-50 |
| `channels` | EM-50 labels: `{"0":"AC","1":"Office"}` or `["AC","Office"]` |
| `password_env` | Env var name for device password (optional) |

**Do not commit** `shelly-config.json` (gitignored). Use `password_env`, not inline passwords.

Environment overrides:

- `SHELLY_CONFIG` — path to config file
- `SHELLY_PASSWORD` — default device password
- `SHELLY_HOST` + `SHELLY_DEVICE_ID` — single device without a file

## Claude Desktop (Windows)

`claude_desktop_config.json` (via **Settings → Developer → Edit Config**):

```json
{
  "mcpServers": {
    "shelly": {
      "command": "C:\\Windows\\System32\\cmd.exe",
      "args": ["/c", "C:\\path\\to\\shelly-mcp\\run-shelly-mcp.cmd"]
    }
  }
}
```

Edit `run-shelly-mcp.cmd` so paths match your install. **Fully quit** Claude after changes.

Optional: install **`shelly-mcp.mcpb`** via **Settings → Extensions → Install Extension** (build with `npx @anthropic-ai/mcpb pack .`).

## Cursor

**Settings → MCP**:

```json
{
  "mcpServers": {
    "shelly": {
      "command": "C:\\path\\to\\shelly-mcp\\.venv\\Scripts\\python.exe",
      "args": ["-u", "-m", "shelly_mcp"],
      "env": {
        "SHELLY_CONFIG": "C:\\path\\to\\shelly-mcp\\shelly-config.json"
      }
    }
  }
}
```

After code updates, restart the MCP client. Call **`server_info`** — version should match `pyproject.toml`.

## MCP tools (summary)

### Core

- `server_info`, `list_devices`, `reload_config`, `get_device_info`, `get_components`, `list_methods`, `rpc`

### On / off (auto Switch vs Light)

- `turn_on`, `turn_off`, `lights_on`, `lights_off`, `control_device`
- `get_output_status`, `set_output`, `toggle_output`
- `set_switch`, `get_switch_status`, `toggle_switch` (delegates to Light on dimmers)

### Pro RGBWW

- `get_rgbww_status`, `set_rgb`, `set_cct`, `set_white`, `rgbww_off`, `set_light`, `toggle_light`

### Pro EM-50

- `list_em_channels`, `get_em_status`, `get_em_energy`, `get_em_readings`
- `set_em_channel_label` — writes `EM1.SetConfig` `name` on the device

## Run manually

```powershell
$env:SHELLY_CONFIG = ".\shelly-config.json"
shelly-mcp
```

HTTP (e.g. Docker):

```powershell
shelly-mcp --transport streamable-http --host 0.0.0.0 --port 8765
```

## Docker

```powershell
Copy-Item config.example.json shelly-config.json
# edit shelly-config.json
docker compose up --build -d
```

On Windows Docker Desktop, the container may not reach IoT VLANs; running stdio on the host is usually simpler.

## Authentication

If the device has **Device access** / admin password enabled, set `SHELLY_PASSWORD` or per-device `password_env`. Username is always `admin` (Shelly digest auth).

## Development

```powershell
pip install -e .
python -m shelly_mcp
```

Project layout:

```
src/shelly_mcp/
  server.py      # MCP tools
  client.py      # JSON-RPC + auth
  config.py      # shelly-config.json
  outputs.py     # Switch / Light
  rgbww.py       # Pro RGBWW
  em50.py        # Pro EM-50 + channel labels
```

## License

MIT (add a LICENSE file if you publish publicly.)
