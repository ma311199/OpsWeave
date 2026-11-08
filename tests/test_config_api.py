import os

from opsweave.api.routes import config
from opsweave.config import database


def test_config_masks_secrets_and_does_not_read_them_from_sqlite(client, monkeypatch):
    database.update_configs(
        {
            "llm_api_key": "stale-llm-secret",
            "embedding_api_key": "stale-embedding-secret",
            "milvus_password": "stale-milvus-secret",
        }
    )
    monkeypatch.setenv("LLM_API_KEY", "llm-secret-1234")
    monkeypatch.setenv("EMBEDDING_API_KEY", "embedding-secret-5678")
    monkeypatch.setenv("MILVUS_PASSWORD", "milvus-secret-9012")
    config.get_settings.cache_clear()

    response = client.get("/api/config/")
    assert response.status_code == 200
    result = response.json()
    assert result["llm"]["api_key"] == "...1234"
    assert result["embedding"]["api_key"] == "...5678"
    assert result["milvus"]["password"] == "...9012"
    assert "stale-llm-secret" not in response.text


def test_config_updates_secrets_in_environment_and_nonsecret_values_in_sqlite(
    client, monkeypatch
):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("EMBEDDING_API_KEY", raising=False)
    monkeypatch.delenv("MILVUS_PASSWORD", raising=False)
    config.get_settings.cache_clear()

    response = client.put(
        "/api/config/",
        json={
            "llm_api_key": "new-llm-secret",
            "embedding_api_key": "new-embedding-secret",
            "milvus_password": "new-milvus-secret",
            "llm_model": "test-model",
        },
    )
    assert response.status_code == 200
    assert os.environ["LLM_API_KEY"] == "new-llm-secret"
    assert os.environ["EMBEDDING_API_KEY"] == "new-embedding-secret"
    assert os.environ["MILVUS_PASSWORD"] == "new-milvus-secret"
    stored = database.get_all_configs()
    assert stored["llm_model"] == "test-model"
    assert not {"llm_api_key", "embedding_api_key", "milvus_password"} & stored.keys()


