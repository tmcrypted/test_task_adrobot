import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app, get_keitaro


class FakeKeitaro:
    def __init__(self):
        self.campaign_payloads = []
        self.stream_payloads = []
        self.updated_streams = []
        self.stream_detail_requests = []
        self.remote_streams = {
            701: {"id": 701, "campaign_id": 70, "name": "Offers", "position": 1,
                  "offers": [{"offer_id": 18001, "share": 50, "state": "active"},
                             {"offer_id": 18002, "share": 50, "state": "active"}]},
            702: {"id": 702, "campaign_id": 70, "name": "GEO", "position": 2,
                  "offers": [], "filters": [{"name": "country", "payload": ["AU"]}]},
        }

    def get_catalogs(self):
        return {"offers": [{"id": 18001, "name": "Offer One"}, {"id": 18002, "name": "Offer Two"},
                            {"id": 18003, "name": "Offer Three"}],
                "domains": [{"id": 1813, "name": "test.example"}],
                "groups": [{"id": 10332, "name": "FORTESTS"}],
                "traffic_sources": [{"id": 836, "name": "FORTESTS"}]}

    def request(self, method, path, params=None, json=None):
        if path == "/offers":
            return self.get_catalogs()["offers"]
        if path.startswith("/offers/"):
            offer_id = int(path.rsplit("/", 1)[-1])
            return next((offer for offer in self.get_catalogs()["offers"] if offer["id"] == offer_id), None)
        if method == "GET" and path.startswith("/streams/"):
            return self.remote_streams[int(path.rsplit("/", 1)[-1])]
        raise AssertionError(f"Unexpected API request: {method} {path}")

    def get_campaigns(self, offset=0, limit=100):
        return [{"id": 70, "name": "test_demo", "state": "active"}][offset:offset + limit]

    def create_campaign(self, payload):
        self.campaign_payloads.append(payload)
        return {"id": 80, **payload}

    def create_stream(self, payload):
        self.stream_payloads.append(payload)
        stream_id = 801 + len(self.stream_payloads)
        stream = {"id": stream_id, "position": len(self.stream_payloads), **payload}
        self.remote_streams[stream_id] = stream
        return stream

    def get_streams(self, campaign_id):
        return [stream for stream in self.remote_streams.values() if stream.get("campaign_id") == campaign_id]

    def get_stream(self, stream_id):
        self.stream_detail_requests.append(stream_id)
        return self.remote_streams[stream_id]

    def update_stream(self, stream_id, payload):
        self.updated_streams.append((stream_id, payload))
        self.remote_streams[stream_id]["offers"] = payload["offers"]
        return self.remote_streams[stream_id]

    def enable_campaign(self, campaign_id):
        return {"id": campaign_id, "state": "active"}


@pytest.fixture
def fake_keitaro():
    return FakeKeitaro()


@pytest.fixture
def client(fake_keitaro):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    TestingSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(engine)

    def override_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_keitaro] = lambda: fake_keitaro
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)
    engine.dispose()
