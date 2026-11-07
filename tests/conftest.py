import pytest

from backend import fonte, manifest


@pytest.fixture(autouse=True)
def no_manifest(monkeypatch):
    """Tests start without a sede.yaml, whatever the machine has; manifest tests opt in."""
    manifest.load_real = getattr(manifest, "load_real", manifest.load)  # os testes da INT-07 religam a leitura de verdade
    monkeypatch.setattr(manifest, "load", lambda *args, **kwargs: None)


@pytest.fixture(autouse=True)
def sem_classica(monkeypatch):
    """Testes não falam com a InToca Sala (Clássica) desta máquina; os testes da INT-07 ligam a fonte de propósito."""
    monkeypatch.setattr(fonte, "classica_porta", lambda: None)
    fonte._cache.clear()
