from fastapi.testclient import TestClient

from app import main


class FakeRecognizer:
    model_version = "test-model"

    def recognize(self, content: bytes):
        assert content == b"safe-image"
        return "synthetic text", 12.5


def test_health_not_ready(monkeypatch):
    monkeypatch.setattr(main, "recognizer", None)
    response = TestClient(main.app).get("/health")
    assert response.json()["recognizer_loaded"] is False


def test_line_recognition_contract(monkeypatch):
    monkeypatch.setattr(main, "recognizer", FakeRecognizer())
    with TestClient(main.app) as client:
        monkeypatch.setattr(main, "recognizer", FakeRecognizer())
        response = client.post(
            "/recognize-line", files={"image": ("line.png", b"safe-image", "image/png")}
        )
    assert response.status_code == 200
    assert response.json() == {
        "text": "synthetic text",
        "processing_ms": 12.5,
        "model_version": "test-model",
        "uncertain": True,
    }
