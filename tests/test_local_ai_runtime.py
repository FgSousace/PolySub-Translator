import sys

from polysub.local_ai_runtime import MANAGED_AI_RUNTIME_ENV, local_ai_dependency_error


def test_source_install_error_contains_the_scoped_pip_command(monkeypatch) -> None:
    monkeypatch.delenv(MANAGED_AI_RUNTIME_ENV, raising=False)
    monkeypatch.delattr(sys, "frozen", raising=False)

    message = local_ai_dependency_error(
        "bibliotek Transformers",
        ModuleNotFoundError("No module named 'transformers'"),
    )

    assert "No module named 'transformers'" in message
    assert 'python -m pip install -e ".[local]"' in message


def test_frozen_install_does_not_recommend_system_pip(monkeypatch) -> None:
    monkeypatch.delenv(MANAGED_AI_RUNTIME_ENV, raising=False)
    monkeypatch.setattr(sys, "frozen", True, raising=False)

    message = local_ai_dependency_error("PyTorch", ImportError("torch missing"))

    assert "zainstaluj ponownie najnowsze wydanie" in message.casefold()
    assert "zwykły pip systemowy nie naprawia" in message
    assert "pip install -e" not in message


def test_managed_amd_runtime_recommends_automatic_repair(monkeypatch) -> None:
    monkeypatch.setenv(MANAGED_AI_RUNTIME_ENV, "amd-rocm")
    monkeypatch.setattr(sys, "frozen", True, raising=False)

    message = local_ai_dependency_error("PyTorch", ImportError("torch missing"))

    assert "środowisko AMD ROCm jest niekompletne" in message
    assert "automatycznie naprawi" in message
