import pytest
from fastapi.testclient import TestClient
from server.config import settings
from server.app import app, locks, rate_windows, hub

@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setattr(settings,'data_dir',tmp_path)
    monkeypatch.setattr(settings,'gemini_api_key','')
    monkeypatch.setattr(settings,'decision_api_key','')
    monkeypatch.setattr(settings,'decision_model','')
    monkeypatch.setattr(settings,'enable_demo',True)
    locks.clear();rate_windows.clear();hub.rooms.clear()
    with TestClient(app) as c:
        yield c
