"""Tests for the SNS webhook handler."""

import asyncio
import json
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from src.main import app


@pytest.fixture
def client():
    return TestClient(app, raise_server_exceptions=False)


async def _mock_verify_true(body):
    return True


def _patch_signature_verification():
    """Patch SNS signature verification to always pass in tests."""
    return patch(
        "src.street_manager.webhook.verify_sns_signature",
        side_effect=_mock_verify_true,
    )


class TestSnsWebhook:
    def test_health_endpoint(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] in ("ok", "starting", "degraded")

    def test_notification_returns_200(self, client):
        """Valid notification should be accepted (200) even without database configured."""
        notification = {
            "event_type": "WORK_START",
            "object_data": {
                "highway_authority_swa_code": "5660",
                "permit_reference_number": "TEST-001",
                "street_name": "TEST ROAD",
                "traffic_management_type_ref": "road_closure",
            },
            "object_reference": "TEST-001",
        }
        sns_message = {
            "Type": "Notification",
            "Message": json.dumps(notification),
            "MessageId": "test-123",
            "TopicArn": "arn:aws:sns:eu-west-2:287813576808:prod-permit-topic",
        }
        with _patch_signature_verification():
            resp = client.post("/webhook/street-manager", json=sns_message)
        assert resp.status_code == 200

    def test_irrelevant_event_skipped(self, client):
        """Events we don't care about should still return 200 (ACK)."""
        notification = {
            "event_type": "COMMENT_ADDED",
            "object_data": {},
            "object_reference": "TEST-002",
        }
        sns_message = {
            "Type": "Notification",
            "Message": json.dumps(notification),
        }
        with _patch_signature_verification():
            resp = client.post("/webhook/street-manager", json=sns_message)
        assert resp.status_code == 200

    def test_malformed_body_returns_400(self, client):
        resp = client.post(
            "/webhook/street-manager",
            content=b"not json",
            headers={"content-type": "text/plain"},
        )
        assert resp.status_code == 400

    def test_unsigned_message_rejected(self, client):
        """Messages without valid SNS signatures should be rejected."""
        sns_message = {"Type": "Notification", "Message": "{}"}
        resp = client.post("/webhook/street-manager", json=sns_message)
        assert resp.status_code == 403

    def test_unknown_sns_type_returns_200(self, client):
        """Unknown message types with valid signatures should be accepted."""
        sns_message = {"Type": "SomethingNew"}
        with _patch_signature_verification():
            resp = client.post("/webhook/street-manager", json=sns_message)
        assert resp.status_code == 200

    def test_subscription_confirmation_bypasses_signature_check(self, client):
        """SubscriptionConfirmation should proceed even without valid signature."""
        sns_message = {
            "Type": "SubscriptionConfirmation",
            "SubscribeURL": "https://example.com/confirm",
            "TopicArn": "arn:aws:sns:eu-west-2:287813576808:prod-permit-topic",
        }
        mock_response = AsyncMock()
        mock_response.status_code = 200
        with patch("src.street_manager.webhook.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__ = AsyncMock(return_value=mock_client.return_value)
            mock_client.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_client.return_value.get = AsyncMock(return_value=mock_response)
            resp = client.post("/webhook/street-manager", json=sns_message)
        assert resp.status_code == 200
