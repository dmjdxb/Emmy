"""deliver_artifact — uploads a produced file to the gateway and returns a REAL download URL."""

from __future__ import annotations

import json
import urllib.request

import pytest

from tools import artifact_delivery as ad


def test_upload_artifact_returns_real_url(tmp_path, monkeypatch):
    f = tmp_path / "model.xlsx"
    f.write_bytes(b"PK\x03\x04 spreadsheet bytes")
    monkeypatch.setattr(ad, "_gateway_artifacts_endpoint",
                        lambda: ("https://api.energyir.io/v1/artifacts", "eir-key"))

    sent = {}

    class _Resp:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self):
            return json.dumps({
                "id": "abc", "filename": "model.xlsx", "size": 22,
                "download_url": "https://r2.example/artifacts/acct/abc/model.xlsx?sig=x",
            }).encode()

    def _fake_urlopen(req, timeout=None):
        sent["url"] = req.full_url
        sent["auth"] = req.headers.get("Authorization")
        sent["body"] = json.loads(req.data.decode())
        return _Resp()

    monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)
    res = ad.upload_artifact(str(f))
    assert res["download_url"].startswith("https://r2.example/")
    assert sent["url"] == "https://api.energyir.io/v1/artifacts"
    assert sent["auth"] == "Bearer eir-key"
    assert sent["body"]["filename"] == "model.xlsx" and "content_base64" in sent["body"]


def test_missing_file_errors():
    assert "error" in ad.upload_artifact("/no/such/file.xlsx")


def test_no_gateway_credentials_errors(tmp_path, monkeypatch):
    f = tmp_path / "x.txt"; f.write_bytes(b"hi")
    monkeypatch.setattr(ad, "_gateway_artifacts_endpoint", lambda: None)
    res = ad.upload_artifact(str(f))
    assert "error" in res and "unavailable" in res["error"]


def test_upload_failure_is_not_silently_success(tmp_path, monkeypatch):
    f = tmp_path / "x.txt"; f.write_bytes(b"hi")
    monkeypatch.setattr(ad, "_gateway_artifacts_endpoint",
                        lambda: ("https://api.energyir.io/v1/artifacts", "k"))
    def _boom(req, timeout=None):
        raise OSError("connection refused")
    monkeypatch.setattr(urllib.request, "urlopen", _boom)
    res = ad.upload_artifact(str(f))
    assert "error" in res and "download_url" not in res  # NEVER a fake success


def test_endpoint_derivation(monkeypatch):
    import agent.auxiliary_client as aux
    monkeypatch.setattr(aux, "_resolve_nous_runtime_api",
                        lambda force_refresh=False: ("eir-k", "https://api.energyir.io/v1"))
    url, key = ad._gateway_artifacts_endpoint()
    assert url == "https://api.energyir.io/v1/artifacts" and key == "eir-k"


def test_registered_and_never_deferred():
    from tools.registry import discover_builtin_tools, registry
    discover_builtin_tools()
    names = {getattr(e, "name", None) for e in registry._snapshot_entries()}
    assert "deliver_artifact" in names
    from toolsets import _TOOL_SEARCH_NEVER_DEFER
    assert "deliver_artifact" in _TOOL_SEARCH_NEVER_DEFER
