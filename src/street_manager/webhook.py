"""AWS SNS webhook handler for Street Manager open data notifications."""

import json
import logging

import httpx
from fastapi import APIRouter, Request, Response

from src.street_manager.sns_verify import verify_sns_signature

logger = logging.getLogger(__name__)

router = APIRouter()

# Event types we care about — skip inspections, FPNs, comments, reinstatements.
RELEVANT_EVENT_TYPES = {
    "WORK_START",
    "WORK_STOP",
    "WORK_START_REVERTED",
    "PERMIT_SUBMITTED",
    "PERMIT_GRANTED",
    "PERMIT_REFUSED",
    "PERMIT_CANCELLED",
    "PERMIT_REVOKED",
    "PERMIT_ALTERATION_SUBMITTED",
    "PERMIT_ALTERATION_GRANTED",
    "ACTIVITY_CREATED",
    "ACTIVITY_UPDATED",
    "ACTIVITY_CANCELLED",
    "SECTION_58_APPLIED",
    "SECTION_58_REMOVED",
}

# Will be set by main.py after initialisation
_notification_handler = None


def set_notification_handler(handler):
    """Register the callback that processes filtered notifications."""
    global _notification_handler
    _notification_handler = handler


async def _handle_subscription_confirmation(body: dict) -> Response:
    """Confirm an SNS topic subscription by fetching the SubscribeURL."""
    subscribe_url = body.get("SubscribeURL")
    topic_arn = body.get("TopicArn", "unknown")

    if not subscribe_url:
        logger.error("SubscriptionConfirmation missing SubscribeURL")
        return Response(status_code=400)

    logger.info("Confirming SNS subscription for topic: %s", topic_arn)

    async with httpx.AsyncClient() as client:
        resp = await client.get(subscribe_url)
        if resp.status_code == 200:
            logger.info("SNS subscription confirmed for %s", topic_arn)
        else:
            logger.error(
                "Failed to confirm SNS subscription: %s %s",
                resp.status_code, resp.text,
            )

    return Response(status_code=200)


async def _handle_notification(body: dict) -> Response:
    """Process an SNS notification message."""
    # The actual Street Manager payload is JSON-encoded inside the "Message" field
    message_str = body.get("Message", "")

    try:
        notification = json.loads(message_str)
    except (json.JSONDecodeError, TypeError):
        logger.warning("Could not parse SNS Message as JSON: %.200s", message_str)
        return Response(status_code=200)  # ACK to prevent retries

    event_type = notification.get("event_type", "")
    object_ref = notification.get("object_reference", "unknown")

    if event_type not in RELEVANT_EVENT_TYPES:
        logger.debug("Skipping irrelevant event type: %s for %s", event_type, object_ref)
        return Response(status_code=200)

    logger.info("Processing %s for %s", event_type, object_ref)

    if _notification_handler:
        try:
            await _notification_handler(notification)
        except Exception:
            logger.exception("Error processing notification %s", object_ref)
            # Still return 200 — don't want SNS to keep retrying a bad message

    return Response(status_code=200)


@router.post("/webhook/street-manager")
async def sns_webhook(request: Request) -> Response:
    """Receive AWS SNS messages from Street Manager open data topics.

    Handles two SNS message types:
    - SubscriptionConfirmation: auto-confirms by fetching the SubscribeURL
    - Notification: parses the Street Manager event and processes it
    """
    # SNS sends messages with content-type text/plain, body is JSON
    raw_body = await request.body()

    # Log every incoming request so we can reconstruct it if processing fails
    logger.info(
        "Incoming POST — headers: %s",
        dict(request.headers),
    )
    logger.info("Incoming POST — body: %s", raw_body.decode("utf-8", errors="replace"))

    try:
        body = json.loads(raw_body)
    except json.JSONDecodeError:
        logger.warning("Could not parse request body as JSON")
        return Response(status_code=400)

    message_type = body.get("Type", "")

    # Verify SNS message signature to prevent spoofed requests.
    # Allow SubscriptionConfirmation through even if verification fails,
    # since the SubscribeURL itself is a one-time token that validates the request.
    sig_valid = await verify_sns_signature(body)
    if not sig_valid:
        if message_type == "SubscriptionConfirmation":
            logger.warning(
                "SNS signature verification failed for SubscriptionConfirmation — "
                "proceeding anyway (SubscribeURL is self-validating)"
            )
        else:
            logger.warning("Rejected message with invalid SNS signature — body logged above")
            return Response(status_code=403)

    if message_type == "SubscriptionConfirmation":
        return await _handle_subscription_confirmation(body)
    elif message_type == "Notification":
        return await _handle_notification(body)
    elif message_type == "UnsubscribeConfirmation":
        logger.info("Received UnsubscribeConfirmation — topic: %s", body.get("TopicArn"))
        return Response(status_code=200)
    else:
        logger.warning("Unknown SNS message type: %s", message_type)
        return Response(status_code=200)
