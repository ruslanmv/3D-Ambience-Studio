"""The settings endpoints, and the one rule that only matters once the Studio is hosted.

A desk install and a Hugging Face Space run the same code with opposite assumptions about who is
on the other end of the HTTP request. On a desk it is the operator; on a public Space it is
anyone. These tests are about that difference, because it is invisible in the code path — the
same PUT either configures your own tool or reconfigures a stranger's billing.
"""

from __future__ import annotations

import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def api(tmp_path, monkeypatch):
    """The real app, with its data directory and deployment environment under control."""
    monkeypatch.setenv("AMBIENCE_DATA_DIR", str(tmp_path))
    for name in ("SPACE_ID", "HF_TOKEN", "HUGGING_FACE_HUB_TOKEN", "AMBIENCE_SETTINGS_LOCKED"):
        monkeypatch.delenv(name, raising=False)

    def build():
        from ambience import config

        importlib.reload(config)
        from ambience.services import generation_settings

        importlib.reload(generation_settings)
        from ambience import main

        importlib.reload(main)
        return TestClient(main.app)

    return build


class TestOpenInstall:
    def test_settings_are_readable_and_writable(self, api):
        client = api()
        assert client.get("/api/settings/generation").status_code == 200
        response = client.put("/api/settings/generation", json={"provider": "openai"})
        assert response.status_code == 200
        assert response.json()["provider"] == "openai"

    def test_the_read_says_it_is_unlocked(self, api):
        body = api().get("/api/settings/generation").json()
        assert body["locked"] is False
        assert body["lock_reason"] == ""

    def test_an_unknown_provider_is_rejected(self, api):
        assert api().put("/api/settings/generation", json={"provider": "nope"}).status_code == 400


class TestHostedSpace:
    """Everyone shares one configuration and one billing account, so nobody may change it."""

    @pytest.fixture
    def client(self, api, monkeypatch):
        monkeypatch.setenv("SPACE_ID", "ruslanmv/3D-Ambience-Studio")
        monkeypatch.setenv("HF_TOKEN", "env-token")
        return api()

    def test_writing_settings_is_refused(self, client):
        response = client.put("/api/settings/generation", json={"provider": "openai"})
        assert response.status_code == 403

    def test_the_refusal_explains_itself(self, client):
        # A panel that just fails is indistinguishable from a broken one, and the person reading
        # it is usually not the person who deployed it.
        detail = client.put("/api/settings/generation", json={"model": "x"}).json()["detail"]
        assert "Space" in detail or "operator" in detail

    def test_a_refused_write_changes_nothing(self, client):
        before = client.get("/api/settings/generation").json()["provider"]
        client.put("/api/settings/generation", json={"provider": "openai"})
        assert client.get("/api/settings/generation").json()["provider"] == before

    def test_pairing_and_unpairing_are_refused_too(self, client):
        # Both write a credential to the settings file; the PUT guard alone would be a gap.
        assert client.post("/api/settings/generation/pair", json={"code": "1234"}).status_code == 403
        assert client.post("/api/settings/generation/unpair").status_code == 403

    def test_reading_still_works_and_reports_the_lock(self, client):
        body = client.get("/api/settings/generation").json()
        assert body["locked"] is True
        assert body["lock_reason"]

    def test_it_defaults_to_hugging_face_with_the_space_secret(self, client):
        body = client.get("/api/settings/generation").json()
        assert body["provider"] == "huggingface"
        assert body["credential_source"] == "environment"
        assert body["env_var"] == "HF_TOKEN"

    def test_the_space_secret_never_crosses_the_wire(self, client):
        assert "env-token" not in client.get("/api/settings/generation").text

    def test_a_private_space_can_be_unlocked_by_its_operator(self, api, monkeypatch):
        monkeypatch.setenv("SPACE_ID", "ruslanmv/private")
        monkeypatch.setenv("AMBIENCE_SETTINGS_LOCKED", "0")
        assert api().put("/api/settings/generation", json={"provider": "openai"}).status_code == 200


class TestProviderCatalogueEndpoint:
    def test_it_offers_hugging_face_with_its_routing_and_models(self, api):
        providers = api().get("/api/image-providers").json()
        hf = next(p for p in providers if p["id"] == "huggingface")
        assert "auto" in hf["routing"]
        assert any(m["id"] == "black-forest-labs/FLUX.1-schnell" for m in hf["suggestedModels"])
        # Every shortlisted model carries the licence it was chosen for, so the panel can show it.
        assert all(m["licence"] for m in hf["suggestedModels"])
