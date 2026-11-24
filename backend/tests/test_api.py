from app.config import settings


def test_campaign_creation_builds_geo_before_fallback(client, fake_keitaro):
    response = client.post("/api/campaigns", json={
        "name": "sample", "country_code": "au", "offer_id": 18001,
        "domain_id": 1813, "group_id": 10332, "traffic_source_id": 836,
    })
    assert response.status_code == 200, response.text
    assert response.json()["name"] == f"{settings.campaign_prefix}sample"
    assert fake_keitaro.campaign_payloads[0]["state"] == "disabled"
    assert fake_keitaro.campaign_payloads[0]["domain_id"] == 1813
    assert fake_keitaro.stream_payloads[0]["filters"] == [
        {"name": "country", "mode": "accept", "payload": ["AU"]}
    ]
    assert fake_keitaro.stream_payloads[0]["action_payload"] == "https://google.com"
    assert fake_keitaro.stream_payloads[1]["offers"] == [
        {"offer_id": 18001, "share": 100, "state": "active"}
    ]
    assert response.json()["state"] == "active"


def test_global_operation_history_supports_campaign_and_action_filters(client):
    created = client.post("/api/campaigns", json={
        "name": "history_sample", "country_code": "au", "offer_id": 18001,
        "domain_id": 1813, "group_id": 10332, "traffic_source_id": 836,
    })
    assert created.status_code == 200, created.text

    response = client.get("/api/history", params={"campaign_id": 80, "action": "campaign.create", "limit": 10})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 1
    assert body["has_more"] is False
    assert body["items"][0]["campaign_id"] == 80
    assert body["items"][0]["action"] == "campaign.create"


def test_fetch_add_push_and_archive_keeps_offer_record(client, fake_keitaro):
    fetched = client.post("/api/campaigns/70/streams/fetch")
    assert fetched.status_code == 200, fetched.text
    stream = next(item for item in fetched.json() if item["stream_id"] == 701)
    assert stream["has_offer_flow"] is True
    assert stream["dirty"] is False

    response = client.post("/api/campaigns/70/streams/701/offers", json={"offer_id": 18003})
    assert response.status_code == 200, response.text
    assert response.json()["dirty"] is True
    assert {offer["share"] for offer in response.json()["offers"] if offer["present"]} == {33, 34}

    pushed = client.post("/api/campaigns/70/streams/701/push")
    assert pushed.status_code == 200, pushed.text
    assert len(fake_keitaro.updated_streams[-1][1]["offers"]) == 3
    assert sum(offer["share"] for offer in fake_keitaro.updated_streams[-1][1]["offers"]) == 100

    # Simulate a user removing one association directly in Keitaro, then fetching again.
    fake_keitaro.remote_streams[701]["offers"] = [
        item for item in fake_keitaro.remote_streams[701]["offers"] if item["offer_id"] != 18001
    ]
    fetched_again = client.post("/api/campaigns/70/streams/fetch")
    assert fetched_again.status_code == 200, fetched_again.text
    stream = next(item for item in fetched_again.json() if item["stream_id"] == 701)
    removed = next(item for item in stream["offers"] if item["offer_id"] == 18001)
    assert removed["state"] == "removed"
    assert removed["share"] == 0
    assert stream["has_offer_flow"] is True


def test_fetch_does_not_parse_offerless_stream_details(client, fake_keitaro):
    response = client.post("/api/campaigns/70/streams/fetch")
    assert response.status_code == 200
    geo = next(item for item in response.json() if item["stream_id"] == 702)
    assert geo["has_offer_flow"] is False
    assert geo["offers"] == []
    assert 702 not in fake_keitaro.stream_detail_requests


def test_cancel_removes_unsynced_association(client):
    client.post("/api/campaigns/70/streams/fetch")
    client.post("/api/campaigns/70/streams/701/offers", json={"offer_id": 18003})
    cancelled = client.post("/api/campaigns/70/streams/701/cancel")
    assert cancelled.status_code == 200
    stream = cancelled.json()
    assert all(offer["offer_id"] != 18003 for offer in stream["offers"])
    assert stream["dirty"] is False


def test_cancel_after_restoring_keeps_previously_synced_offer_archived(client, fake_keitaro):
    # The offer existed in Keitaro, then was removed there and fetched into the local archive.
    initial = client.post("/api/campaigns/70/streams/fetch")
    assert initial.status_code == 200
    fake_keitaro.remote_streams[701]["offers"] = [
        item for item in fake_keitaro.remote_streams[701]["offers"] if item["offer_id"] != 18001
    ]
    fetched = client.post("/api/campaigns/70/streams/fetch")
    assert fetched.status_code == 200
    archived = next(item for item in fetched.json()[0]["offers"] if item["offer_id"] == 18001)
    assert archived["state"] == "removed"
    assert archived["dirty"] is False

    restored = client.post("/api/campaigns/70/streams/701/offers/18001/restore")
    assert restored.status_code == 200, restored.text
    assert next(item for item in restored.json()["offers"] if item["offer_id"] == 18001)["present"]

    cancelled = client.post("/api/campaigns/70/streams/701/cancel")
    assert cancelled.status_code == 200, cancelled.text
    restored_offer = next(item for item in cancelled.json()["offers"] if item["offer_id"] == 18001)
    assert restored_offer["state"] == "removed"
    assert restored_offer["present"] is False
    assert restored_offer["share"] == 0
    assert cancelled.json()["dirty"] is False


def test_remove_new_draft_offer_drops_it_without_leaving_a_dirty_archive(client):
    client.post("/api/campaigns/70/streams/fetch")
    client.post("/api/campaigns/70/streams/701/offers", json={"offer_id": 18003})
    response = client.post("/api/campaigns/70/streams/701/offers/18003/remove")
    assert response.status_code == 200
    assert all(offer["offer_id"] != 18003 for offer in response.json()["offers"])
    assert response.json()["dirty"] is False


def test_last_unpinned_offer_cannot_be_pinned_or_removed(client):
    client.post("/api/campaigns/70/streams/fetch")
    pinned = client.post("/api/campaigns/70/streams/701/offers/18001/pin")
    assert pinned.status_code == 200
    second_pin = client.post("/api/campaigns/70/streams/701/offers/18002/pin")
    assert second_pin.status_code == 400
    removal = client.post("/api/campaigns/70/streams/701/offers/18002/remove")
    assert removal.status_code == 400
