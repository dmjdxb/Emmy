"""deliver_artifact — hand a produced file to the user via a real download URL.

The failure this kills: on the web, the user cannot reach files the agent writes to its
container disk, and the agent would *fabricate* "Done, it's at /app/x.xlsx (9 KB)" with
nothing actually delivered — real spend, zero output, broken trust.

deliver_artifact uploads the file to the gateway (authenticated with the agent's own
EnergyIR key, the same one used for the LLM), which stores it in R2 and returns a
PRESIGNED download URL. The agent reports THAT url. There is no way to "claim" delivery
without it — a failed upload returns an error, not a path. So "here's your file: <url>"
is always real.
"""

from __future__ import annotations

import base64
import json
import os
import urllib.request
from pathlib import Path

_MAX_BYTES = 25 * 1024 * 1024


def _gateway_artifacts_endpoint() -> tuple[str, str] | None:
    """(url, api_key) for the gateway's /v1/artifacts, reusing the live LLM credentials."""
    try:
        from agent.auxiliary_client import _resolve_nous_runtime_api
    except Exception:
        return None
    runtime = _resolve_nous_runtime_api(force_refresh=False)
    if not runtime:
        return None
    api_key, base_url = runtime
    base = str(base_url or "").rstrip("/")
    if not base or not api_key:
        return None
    # base_url is the inference base (…/v1); the artifact endpoint is …/v1/artifacts.
    if base.endswith("/v1"):
        url = base + "/artifacts"
    elif base.endswith("/v1/"):
        url = base + "artifacts"
    else:
        url = base + "/v1/artifacts"
    return url, api_key


def _guess_mime(name: str) -> str:
    import mimetypes
    return mimetypes.guess_type(name)[0] or "application/octet-stream"


def upload_artifact(path: str) -> dict:
    """Upload one file to the gateway and return {download_url, filename, size} or {error}."""
    p = Path(os.path.expanduser(str(path or "").strip()))
    if not p.is_file():
        return {"error": f"file not found: {p}"}
    data = p.read_bytes()
    if not data:
        return {"error": "file is empty"}
    if len(data) > _MAX_BYTES:
        return {"error": f"file too large (> {_MAX_BYTES // (1024 * 1024)} MB)"}
    endpoint = _gateway_artifacts_endpoint()
    if endpoint is None:
        return {"error": "artifact delivery unavailable (no EnergyIR gateway credentials in this session)"}
    url, key = endpoint
    body = json.dumps({
        "filename": p.name,
        "content_type": _guess_mime(p.name),
        "content_base64": base64.b64encode(data).decode("ascii"),
    }).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, method="POST",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            out = json.loads(r.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        return {"error": f"upload failed: {type(exc).__name__}: {exc}"}
    if "download_url" not in out:
        return {"error": str(out.get("error") or "upload rejected")}
    return out


DELIVER_ARTIFACT_SCHEMA = {
    "name": "deliver_artifact",
    "description": (
        "Deliver a file you produced to the user — returns a real, clickable download URL. "
        "The user CANNOT access files on disk (especially on the web), so ANY deliverable "
        "(xlsx/docx/pptx/pdf/csv/zip/image...) MUST be delivered with this tool. Returns "
        "{download_url, filename, size}. Report the download_url to the user. NEVER claim a "
        "file exists or was 'saved' without delivering it here and quoting the returned URL — "
        "if this tool returns an error, the file was NOT delivered, so say so."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Absolute path of the file to deliver."},
        },
        "required": ["path"],
    },
}


async def _deliver_artifact_handler(args: dict, **_kw) -> str:
    res = upload_artifact(str((args or {}).get("path") or ""))
    return json.dumps(res)


from tools.registry import registry  # noqa: E402 — top-level so discover_builtin_tools finds it

registry.register(
    name="deliver_artifact",
    toolset="office",
    schema=DELIVER_ARTIFACT_SCHEMA,
    handler=_deliver_artifact_handler,
    check_fn=lambda: True,
    emoji="📎",
)
