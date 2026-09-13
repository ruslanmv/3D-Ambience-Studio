"""Configuring where images come from — the SYSTEM CONFIGURATION panel's backing.

Mirrors 3D-Avatar-Chatbot's settings model, so someone who has configured that app recognises
every control. Three things are worth testing rather than eyeballing: secrets never travel back
over HTTP, a partial save does not wipe fields the form did not render, and switching provider
cannot leave the panel with no way to enter a credential.

That last one is the defect this suite exists for. It was caught by looking at a screenshot, not
by reading the code.
"""

from __future__ import annotations

import importlib
import json

import pytest
from ambience.providers.backplate import MockBackplateProvider
from ambience.providers.openai_images import OpenAICompatibleImageProvider
from ambience.providers.registry import provider_from_settings


@pytest.fixture
def store(tmp_path, monkeypatch):
    """A settings module pointed at a scratch directory, with the deployment layer neutral.

    The environment variables matter as much as the directory does: settings now read the
    deployment (a Space Secret, a locked panel), so a developer who happens to export HF_TOKEN
    would otherwise get different results from these tests than CI does. Cleared here, and set
    deliberately by the tests that are about them.
    """
    monkeypatch.setenv("AMBIENCE_DATA_DIR", str(tmp_path))
    for name in (
        "SPACE_ID",
        "HF_TOKEN",
        "HUGGING_FACE_HUB_TOKEN",
        "AMBIENCE_SETTINGS_LOCKED",
        "AMBIENCE_IMAGE_PROVIDER",
        "AMBIENCE_IMAGE_MODEL",
        "AMBIENCE_HF_ROUTING",
        "AMBIENCE_HF_USE_GUIDE",
        "OPENAI_API_KEY",
        "GEMINI_API_KEY",
        "OLLABRIDGE_TOKEN",
        "OLLABRIDGE_LOCAL_TOKEN",
        "HOMEPILOT_TOKEN",
    ):
        monkeypatch.delenv(name, raising=False)
    from ambience import config

    importlib.reload(config)
    from ambience.services import generation_settings

    importlib.reload(generation_settings)
    return generation_settings


class TestProviderCatalogue:
    def test_it_covers_what_the_panel_offers(self, store):
        assert store.PROVIDER_IDS == [
            "huggingface",
            "openai",
            "gemini",
            "ollabridge",
            "ollabridge-local",
            "homepilot",
            "mock-backplate",
        ]

    def test_auth_lists_are_ordered_by_preference_not_alphabetically(self, store):
        # save() takes auth[0] as the provider's default, so the order is load-bearing.
        assert store.provider_spec("ollabridge")["auth"][0] == "pairing"
        assert store.provider_spec("ollabridge-local")["auth"][0] == "local-trust"
        assert store.provider_spec("openai")["auth"] == ["apikey"]

    def test_the_routes_that_cannot_take_a_guide_say_so(self, store):
        # The honest caveat the panel surfaces. OllaBridge's ImageGenerationRequest has no
        # reference-image field, so on that route the camera guide is text only.
        assert store.provider_spec("ollabridge")["supportsGuideImage"] is False
        assert store.provider_spec("ollabridge-local")["supportsGuideImage"] is False
        assert store.provider_spec("homepilot")["supportsGuideImage"] is True


class TestSecrets:
    def test_keys_and_tokens_never_come_back(self, store):
        store.save({"api_key": "sk-secret", "pair_token": "tok-secret"})
        out = store.redact(store.load())
        assert "api_key" not in out
        assert "pair_token" not in out
        assert out["has_api_key"] is True
        assert out["has_pair_token"] is True

    def test_but_the_panel_can_still_tell_one_is_stored(self, store):
        assert store.redact(store.load())["has_api_key"] is False
        store.save({"api_key": "sk-x"})
        assert store.redact(store.load())["has_api_key"] is True

    def test_an_empty_string_clears_a_secret(self, store):
        # Unpairing writes "", and it has to actually clear rather than be treated as "omitted".
        store.save({"pair_token": "tok"})
        store.save({"pair_token": ""})
        assert store.load()["pair_token"] == ""


class TestPartialSave:
    def test_omitted_fields_survive(self, store):
        # The failure this prevents: a form that does not render the key field wiping the key on
        # every save.
        store.save({"api_key": "sk-keep", "model": "m1"})
        store.save({"model": "m2"})
        assert store.load()["api_key"] == "sk-keep"
        assert store.load()["model"] == "m2"

    def test_unknown_fields_are_ignored(self, store):
        store.save({"nonsense": "x"})
        assert "nonsense" not in store.load()

    def test_a_corrupt_file_falls_back_to_defaults(self, store):
        # A bad settings file must not stop the Studio starting; the mock provider needs nothing.
        (store._path()).write_text("{not json", encoding="utf-8")
        assert store.load()["provider"] == store.DEFAULTS["provider"]


class TestProviderSwitch:
    """The defect a screenshot caught, and the two shapes it takes."""

    def test_switching_provider_cannot_strand_the_panel(self, store):
        # OllaBridge/pairing → OpenAI, which offers only apikey. Leaving auth_mode on "pairing"
        # renders neither the pairing box nor the key field: no way to enter a credential.
        store.save({"provider": "ollabridge"})
        store.save({"auth_mode": "pairing"})
        after = store.save({"provider": "openai"})
        assert after["auth_mode"] == "apikey"
        assert after["auth_mode"] in store.provider_spec("openai")["auth"]

    def test_every_provider_lands_on_its_own_preferred_mode(self, store):
        # Not merely a valid one. A carried-over mode that happens to be legal is coincidence:
        # nobody chose local-trust *for OllaBridge*.
        for provider in store.PROVIDER_IDS:
            result = store.save({"provider": provider})
            assert result["auth_mode"] == store.provider_spec(provider)["auth"][0], provider

    def test_and_its_own_base_url(self, store):
        store.save({"provider": "ollabridge"})
        assert store.load()["base_url"] == "https://app.ollabridge.com"
        store.save({"provider": "openai"})
        assert store.load()["base_url"] == "https://api.openai.com"

    def test_an_explicit_choice_still_wins(self, store):
        result = store.save({"provider": "ollabridge", "auth_mode": "local-trust", "base_url": "http://x"})
        assert result["auth_mode"] == "local-trust"
        assert result["base_url"] == "http://x"


class TestAdapterSelection:
    def test_the_three_openai_compatible_providers_share_one_adapter(self, store):
        # OpenAI, the cloud bridge and the local bridge differ in base URL and credential and in
        # nothing else that matters, which is the whole reason for one adapter.
        for provider in ("openai", "ollabridge", "ollabridge-local"):
            built = provider_from_settings(store.save({"provider": provider}))
            assert isinstance(built, OpenAICompatibleImageProvider)

    def test_mock_needs_no_network(self, store):
        assert isinstance(provider_from_settings(store.save({"provider": "mock-backplate"})), MockBackplateProvider)

    def test_pairing_mode_sends_the_pair_token_as_the_bearer(self, store):
        # Which field holds the credential is the only difference between the two modes, and the
        # adapter should not have to know that.
        config = store.save({"provider": "ollabridge", "auth_mode": "pairing", "pair_token": "tok-123"})
        built = provider_from_settings(config)
        assert built.api_key == "tok-123"
        assert built._headers()["Authorization"] == "Bearer tok-123"

    def test_apikey_mode_sends_the_api_key(self, store):
        config = store.save({"provider": "openai", "auth_mode": "apikey", "api_key": "sk-abc"})
        assert provider_from_settings(config)._headers()["Authorization"] == "Bearer sk-abc"

    def test_local_trust_sends_no_header_at_all(self, store):
        # Not an empty Bearer: some stacks reject the malformed header rather than ignoring it,
        # which surfaces as a confusing 401 against a bridge configured not to need one.
        config = store.save({"provider": "ollabridge-local", "auth_mode": "local-trust", "api_key": "ignored"})
        assert "Authorization" not in provider_from_settings(config)._headers()


class TestHuggingFaceProvider:
    """The cloud default when the Studio is hosted, and the one route that can use the guide."""

    def test_it_is_offered_first(self, store):
        # Position is the recommendation: it is the open-model route that needs no GPU and no
        # account with any individual inference company.
        assert store.PROVIDER_IDS[0] == "huggingface"

    def test_it_ships_an_apache_licensed_default_model(self, store):
        # Deliberate. A default is a licence decision made on the operator's behalf, and the
        # better-looking FLUX "dev" weights are non-commercial, so they are reachable but never
        # the default.
        spec = store.provider_spec("huggingface")
        assert spec["defaultModel"] == "black-forest-labs/FLUX.1-schnell"

    def test_a_fresh_install_reads_that_model_with_nothing_stored(self, store, monkeypatch):
        # Derived at read time, from no settings file at all: a Space that has never been
        # configured still has a model to generate with. Once anything is saved the value is
        # written like any other, which is why this checks the untouched case specifically.
        monkeypatch.setenv("AMBIENCE_IMAGE_PROVIDER", "huggingface")
        assert not store._path().exists()
        assert store.load()["model"] == "black-forest-labs/FLUX.1-schnell"

    def test_switching_away_does_not_carry_the_model(self, store):
        # A Hub repo id means nothing to OpenAI. Carrying it across guarantees a failing generate.
        store.save({"provider": "huggingface", "model": "Qwen/Qwen-Image"})
        after = store.save({"provider": "openai"})
        assert after["model"] == ""

    def test_the_guide_is_off_until_asked_for(self, store):
        # Only some provider/model pairs implement image-to-image, and the adapter raises rather
        # than falling back — so defaulting it on would break generation for most models.
        assert store.load()["hf_use_guide"] is False
        assert store.load()["hf_routing"] == "auto"


class TestCredentialSource:
    """A Space Secret is the deployment's credential and never passes through the browser."""

    def test_the_environment_wins_over_the_stored_key(self, store, monkeypatch):
        store.save({"provider": "huggingface", "auth_mode": "apikey", "api_key": "stored-key"})
        monkeypatch.setenv("HF_TOKEN", "env-token")
        credential, source = store.credential_for(store.load())
        assert credential == "env-token"
        assert source == "environment"

    def test_the_stored_key_is_used_when_the_environment_is_empty(self, store):
        store.save({"provider": "openai", "auth_mode": "apikey", "api_key": "sk-desk"})
        assert store.credential_for(store.load()) == ("sk-desk", "stored")

    def test_pairing_mode_resolves_the_pair_token(self, store):
        store.save({"provider": "ollabridge", "auth_mode": "pairing", "pair_token": "tok"})
        assert store.credential_for(store.load()) == ("tok", "stored")

    def test_no_credential_anywhere_says_so(self, store):
        assert store.credential_for(store.load())[1] == "none"

    def test_the_panel_is_told_the_source_but_never_the_value(self, store, monkeypatch):
        monkeypatch.setenv("HF_TOKEN", "env-token")
        out = store.redact(store.load())
        assert out["credential_source"] == "environment"
        assert out["env_var"] == "HF_TOKEN"
        assert out["has_credential"] is True
        assert "env-token" not in json.dumps(out)


class TestDeploymentLock:
    """A shared Space must not let a visitor spend the operator's credits."""

    def test_a_desk_install_is_writable(self, store):
        assert store.deployment()["locked"] is False

    def test_a_hosted_space_is_locked(self, store, monkeypatch):
        monkeypatch.setenv("SPACE_ID", "ruslanmv/3D-Ambience-Studio")
        state = store.deployment()
        assert state["locked"] is True
        assert state["space"] is True
        assert state["reason"], "A locked panel has to say why, or it reads as broken."

    def test_a_private_space_can_be_unlocked_deliberately(self, store, monkeypatch):
        monkeypatch.setenv("SPACE_ID", "ruslanmv/private")
        monkeypatch.setenv("AMBIENCE_SETTINGS_LOCKED", "0")
        assert store.deployment()["locked"] is False

    def test_a_desk_install_can_be_locked_deliberately(self, store, monkeypatch):
        monkeypatch.setenv("AMBIENCE_SETTINGS_LOCKED", "1")
        assert store.deployment()["locked"] is True

    def test_a_space_defaults_to_hugging_face(self, store, monkeypatch):
        # Nothing stored, a token present: the working configuration out of the box is the one
        # whose credential the deployment already has.
        monkeypatch.setenv("SPACE_ID", "ruslanmv/3D-Ambience-Studio")
        monkeypatch.setenv("HF_TOKEN", "env-token")
        assert store.load()["provider"] == "huggingface"

    def test_but_a_stored_choice_still_wins(self, store, monkeypatch):
        store.save({"provider": "mock-backplate"})
        monkeypatch.setenv("SPACE_ID", "ruslanmv/3D-Ambience-Studio")
        assert store.load()["provider"] == "mock-backplate"

    def test_an_operator_override_wins_over_everything(self, store, monkeypatch):
        # How a locked deployment is configured at all: the panel cannot be used to set it.
        store.save({"provider": "mock-backplate", "model": "stored-model"})
        monkeypatch.setenv("AMBIENCE_IMAGE_PROVIDER", "huggingface")
        monkeypatch.setenv("AMBIENCE_IMAGE_MODEL", "Qwen/Qwen-Image")
        config = store.load()
        assert config["provider"] == "huggingface"
        assert config["model"] == "Qwen/Qwen-Image"

    def test_an_unknown_override_provider_is_ignored_rather_than_stored(self, store, monkeypatch):
        monkeypatch.setenv("AMBIENCE_IMAGE_PROVIDER", "not-a-provider")
        assert store.load()["provider"] in store.PROVIDER_IDS
