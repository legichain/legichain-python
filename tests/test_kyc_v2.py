import json
import httpx
import pytest
from pydantic import ValidationError

from legichain import Legichain, AsyncLegichain
from legichain.kyc import OperationFailed

FRAME = "A" * 128

def backend():
    requests = []
    status = {"value": "queued"}
    def handle(request):
        requests.append(request)
        path = request.url.path
        if path == "/v1/kyc/applications":
            return httpx.Response(201, json={"application_id": "tr_app", "client_token": "internal-token"})
        if path.startswith("/v2/kyc/"):
            return httpx.Response(202, json={"operation_id": "tr_operation", "status": "queued"})
        if path == "/v2/operations/tr_operation":
            return httpx.Response(200, json={"id": "tr_operation", "status": status["value"]})
        if path.endswith("/submit"):
            return httpx.Response(202, json={"pending": True, "state": "deciding", "outcome": None})
        return httpx.Response(201, json={"sequence": ["blink", "smile"]})
    return handle, requests, status


def test_complete_wire_contract_token_management_and_submit_order():
    handle, seen, state = backend()
    client = Legichain("tenant.secret", base_url="https://example.test")
    with httpx.Client(transport=httpx.MockTransport(handle)) as transport:
        client._client = transport
        flow = client.kyc.start({"liveness_required": False, "face_match_required": False}, idem="create-1")
        assert json.loads(seen[0].content)["liveness_required"] is False
        assert seen[0].headers["Idempotency-Key"] == "create-1"
        flow.evidence("liveness", {"mode": "active", "frame_b64": FRAME, "challenge_token": "challenge",
            "completed_actions": [{"action": "blink", "started_at_ms": 100, "ended_at_ms": 1500}],
            "frames": [{"image_b64": FRAME, "timestamp_ms": 120}]}, idem="capture-1")
        req = seen[-1]
        assert req.headers["Authorization"] == "Bearer tenant.secret"
        assert req.headers["X-KYC-Client-Token"] == "internal-token"
        assert "completed_actions" in json.loads(req.content)
        with pytest.raises(RuntimeError, match="still processing"): flow.submit()
        assert not any(r.url.path.endswith("/submit") for r in seen)
        with pytest.raises(ValueError, match="does not belong"): flow.wait("other")
        state["value"] = "completed"
        assert flow.wait("tr_operation")["status"] == "completed"
        assert flow.submit()["pending"] is True


def test_invalid_legacy_liveness_and_oversized_frame_list_never_sent():
    client = Legichain("tenant.secret")
    with pytest.raises(ValidationError):
        client.kyc.evidence("app", "ct", "liveness", {"actions_performed": ["blink"]}, idem="key")
    with pytest.raises(ValidationError):
        client.kyc.evidence("app", "ct", "liveness", {"mode": "passive", "frame_b64": FRAME,
            "frames": [{"image_b64": FRAME, "timestamp_ms": n} for n in range(31)]}, idem="key")


@pytest.mark.asyncio
async def test_async_failed_evidence_is_not_submission():
    handle, seen, state = backend()
    client = AsyncLegichain("tenant.secret", base_url="https://example.test")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as transport:
        client._client = transport
        flow = await client.kyc.start({}, idem="create")
        await flow.evidence("nfc", {"protocol": "PACE", "access_error": True}, idem="nfc")
        state["value"] = "failed"
        with pytest.raises(OperationFailed): await flow.wait("tr_operation")
        with pytest.raises(OperationFailed): await flow.submit()
        assert not any(r.url.path.endswith("/submit") for r in seen)
