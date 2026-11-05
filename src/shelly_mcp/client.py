"""Shelly Gen2+ JSON-RPC client (local HTTP)."""

from __future__ import annotations

import hashlib
import json
import random
import re
import urllib.error
import urllib.request

USERNAME = "admin"
RPC_TIMEOUT = 15


class ShellyError(Exception):
    """Device returned an error or could not be reached."""


class AuthRequired(ShellyError):
    """Device rejected a call with a digest challenge."""

    def __init__(self, challenge: dict):
        super().__init__("authentication required")
        self.challenge = challenge


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def parse_digest_header(header: str) -> dict:
    value = header.strip()
    if value.lower().startswith("digest"):
        value = value[6:].strip()
    challenge: dict[str, str] = {}
    for match in re.finditer(r'(\w+)=(?:"([^"]*)"|([^",\s]+))', value):
        key = match.group(1).lower()
        challenge[key] = match.group(2) if match.group(2) is not None else match.group(3)
    return challenge


def challenge_from_body(body: str) -> dict:
    if not body.strip():
        return {}
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, dict):
        return {}
    error = data.get("error")
    if isinstance(error, dict):
        data = error
    message = data.get("message")
    if isinstance(message, str) and message.startswith("{"):
        try:
            inner = json.loads(message)
        except json.JSONDecodeError:
            inner = None
        if isinstance(inner, dict):
            data = {**data, **inner}
    challenge: dict = {}
    for key in ("realm", "nonce", "nc", "algorithm", "auth_type", "stale"):
        if key in data and data[key] is not None:
            challenge[key] = data[key]
    return challenge


def build_auth(challenge: dict, password: str) -> dict:
    realm = challenge["realm"]
    nonce = challenge["nonce"]
    nc = "00000001"
    cnonce = random.randint(1, 2**31 - 1)
    ha1 = sha256_hex(f"{USERNAME}:{realm}:{password}")
    ha2 = sha256_hex("dummy_method:dummy_uri")
    response = sha256_hex(f"{ha1}:{nonce}:{nc}:{cnonce}:auth:{ha2}")
    return {
        "realm": realm,
        "username": USERNAME,
        "nonce": nonce,
        "cnonce": cnonce,
        "nc": nc,
        "response": response,
        "algorithm": "SHA-256",
    }


def normalize_host(host: str) -> str:
    value = host.strip()
    value = re.sub(r"^https?://", "", value)
    return value.rstrip("/")


class ShellyClient:
    def __init__(self, host: str, password: str | None = None):
        self.host = normalize_host(host)
        self.password = password or None

    def call(self, method: str, params: dict | None = None):
        try:
            return self._post(method, params)
        except AuthRequired as err:
            return self._retry_with_auth(method, params, err.challenge)

    def _retry_with_auth(
        self, method: str, params: dict | None, challenge: dict
    ):
        if not self.password:
            raise ShellyError(
                "Device requires a password. Set a password_env on the device "
                "or SHELLY_PASSWORD / default_password_env in config."
            )
        if "realm" not in challenge or "nonce" not in challenge:
            raise ShellyError(
                "Device requires a password, but the 401 response had no digest challenge."
            )
        try:
            return self._post(method, params, auth=build_auth(challenge, self.password))
        except AuthRequired as err:
            stale = err.challenge.get("stale")
            if stale in (True, "true", "TRUE") and "realm" in err.challenge and "nonce" in err.challenge:
                return self._post(
                    method, params, auth=build_auth(err.challenge, self.password)
                )
            raise ShellyError("Authentication failed. Check the device password.") from err

    def _post(self, method: str, params: dict | None = None, auth: dict | None = None):
        body: dict = {"id": 1, "method": method}
        if params is not None:
            body["params"] = params
        if auth is not None:
            body["auth"] = auth
        request = urllib.request.Request(
            f"http://{self.host}/rpc",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=RPC_TIMEOUT) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            if exc.code == 401:
                challenge = challenge_from_body(raw)
                header = exc.headers.get("WWW-Authenticate") if exc.headers else None
                if header:
                    for key, value in parse_digest_header(header).items():
                        challenge.setdefault(key, value)
                raise AuthRequired(challenge) from exc
            raise ShellyError(f"{method} failed: HTTP {exc.code} {raw}".rstrip()) from exc
        except urllib.error.URLError as exc:
            raise ShellyError(f"Could not reach {self.host}: {exc.reason}") from exc
        except TimeoutError as exc:
            raise ShellyError(f"Timed out talking to {self.host}") from exc

        if isinstance(payload, dict) and "error" in payload:
            error = payload["error"]
            code = error.get("code") if isinstance(error, dict) else None
            if code == 401:
                challenge = challenge_from_body(json.dumps(payload))
                raise AuthRequired(challenge)
            raise ShellyError(f"{method} error: {error}")
        if isinstance(payload, dict) and "result" in payload:
            return payload["result"]
        return payload
