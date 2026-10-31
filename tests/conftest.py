import pytest

from backend import manifest


@pytest.fixture(autouse=True)
def no_manifest(monkeypatch):
    """Tests start without a sede.yaml, whatever the machine has; manifest tests opt in."""
    monkeypatch.setattr(manifest, "load", lambda *args, **kwargs: None)
