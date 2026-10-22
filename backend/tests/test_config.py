from config import settings
from pathlib import Path


def test_settings_defaults():
    assert settings.smart_manager_host == "127.0.0.1"
    assert settings.smart_manager_port == 8765
    assert settings.ollama_base_url == "http://127.0.0.1:11434"
    assert settings.agent_max_iterations > 0
    assert settings.agent_default_confirmation_required is True


def test_project_root_and_data_dir():
    assert settings.project_root.exists()
    assert (settings.project_root / "backend").exists()
    assert settings.data_dir.exists()
