"""Generated KYC wire models. Source: Legichain API; do not edit by hand."""

from __future__ import annotations

import datetime as dt

import uuid

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

DocumentTypeAllowed = Literal[
    "tr_id_card", "passport", "driver_license",
    "eu_national_id", "uk_passport",
]

IntentKind = Literal["onboarding", "re_verification", "periodic_review"]

class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

class KYCApplicationCreateRequest(StrictModel):
    external_reference: str | None = Field(default=None, max_length=255)
    subject_external_id: str | None = Field(default=None, max_length=128)
    persona_id: str | None = Field(default=None, max_length=32)
    intent: IntentKind = "onboarding"
    document_type_allowed: list[DocumentTypeAllowed] = Field(
        default_factory=lambda: ["tr_id_card", "passport"],
        min_length=1,
        max_length=3,
    )
    nfc_required: bool = False
    # Which checks to run for this application. The document image is
    # always required; these gate the biometric leg. Default True keeps
    # today's behaviour (liveness + face-match); a tenant that only needs
    # to verify a genuine document sends both False for a document-only
    # flow (optionally with nfc_required=True for a chip-authenticated one).
    liveness_required: bool = True
    face_match_required: bool = True
    callback_url: str | None = Field(default=None, max_length=512)
    claimed_full_name: str | None = Field(default=None, max_length=255)
    # Faz G-7.1: full claimed-fields surface. All optional — tenants
    # send what they have. The decision engine cross-checks these
    # against OCR / NFC output so a typo or identity substitution
    # surfaces as a critical-field inconsistency rather than passing
    # silently.
    claimed_personal_number: str | None = Field(default=None, max_length=32)
    """TR TCKN (11 digits) or generic personal/national ID number
    (DE Idnr, ES DNI). Country code disambiguates the format."""
    claimed_birth_date: dt.date | None = None
    claimed_expiry_date: dt.date | None = None
    claimed_document_number: str | None = Field(default=None, max_length=32)
    claimed_nationality: str | None = Field(
        default=None, min_length=3, max_length=3,
    )
    """ISO 3166-1 alpha-3, e.g. TUR / DEU / FRA / USA."""
    claimed_issuing_country: str | None = Field(
        default=None, min_length=3, max_length=3,
    )
    """Country that issued the document. Often == nationality."""
    claimed_sex: Literal["M", "F"] | None = None
    claimed_document_type: DocumentTypeAllowed | None = None
    """Which exact type the user said they'd scan. Lets the SDK
    pre-configure the camera UI before the upload happens."""
    meta: dict[str, Any] = Field(default_factory=dict)

    @field_validator("document_type_allowed")
    @classmethod
    def unique_doc_types(cls, v: list[str]) -> list[str]:
        if len(set(v)) != len(v):
            raise ValueError("document_type_allowed must not contain duplicates")
        return v

    @field_validator(
        "claimed_nationality", "claimed_issuing_country",
        mode="before",
    )
    @classmethod
    def _uppercase_iso_country(cls, v):  # noqa: ANN206
        if isinstance(v, str):
            v = v.strip().upper()
            return v or None
        return v

class KYCApplicationCreateResponse(StrictModel):
    application_id: str
    persona_id: str
    persona_created: bool
    client_token: str
    client_token_expires_at: dt.datetime
    state: str
    next_steps: list[str]
    expires_at: dt.datetime

class KYCApplicationStatusResponse(StrictModel):
    application_id: str
    persona_id: str
    state: str
    # Faz G-7.4: customer-facing step name derived from `state`. Lets
    # the SDK render the right UI panel without hard-coding every
    # internal state value.
    current_step: str
    # Whether the SDK can call POST /retry to start a fresh attempt.
    # True only when the application is in a non-terminal state that
    # accepts a retry (rejected / manual_review / awaiting_* after a
    # soft fail) AND current_attempt < max_attempts.
    retry_available: bool
    current_attempt: int
    max_attempts: int
    intent: str
    nfc_required: bool
    # Which checks this application was created to run. The document image
    # is always required; these gate the biometric leg. Purely additive —
    # they echo back the flags sent to POST /v1/kyc/applications so an
    # integration can confirm the effective configuration.
    liveness_required: bool = True
    face_match_required: bool = True
    document_type_allowed: list[str]
    risk_score: float | None = None
    decision: dict[str, Any] | None = None
    # Winner-only view: field_name → consolidated value (highest-priority
    # source per field). Backwards-compatible.
    extracted_fields: dict[str, Any] | None = None
    # Per-field provenance: field_name → list of {source, value} entries
    # (oldest source first, then winners by priority). Lets the tester
    # UI show "OCR ön yüz dedi X, MRZ arka yüz dedi Y" comparisons.
    extracted_fields_by_source: dict[str, list[dict[str, str]]] | None = None
    # Per-field full detail (v6 reader engine): field_name → list of
    # {source, value, confidence, validation_status, alternatives?}. Purely
    # additive — an opt-in richer view alongside the existing two keys.
    extracted_fields_detail: dict[str, list[dict[str, Any]]] | None = None
    completed_at: dt.datetime | None = None
    expires_at: dt.datetime
    requested_at: dt.datetime
    #: Set once this application's personal data + files were deleted under
    #: the account's retention rule. The decision + status are kept; the
    #: extracted/claimed fields read back null. Additive, default null.
    pii_purged_at: dt.datetime | None = None

class KYCSubmitRequest(StrictModel):
    """Final submission — server assembles artifacts + runs decision pipeline.

    The mobile/web client signals that all evidence has been provided
    (documents, optional NFC, selfie, liveness) and the server should now:
      - evaluate hard-fail rules
      - compute weighted risk score
      - apply tenant policy thresholds
      - persist `kyc_risk_scores` + `kyc_decisions` + optional manual review
      - update the persona's identity attestation
      - emit `kyc.completed` (or `kyc.manual_review.assigned`) webhook
    """

    notes: str | None = Field(default=None, max_length=512)

class KYCSubmitResponse(StrictModel):
    """The verdict, or an honest statement that there isn't one yet.

    Biometric evidence is produced by a worker, so at the moment submit
    is called the face match may still be running. The old contract had
    no way to say that: every field was required, so the only way to
    answer was to decide without the evidence — which scored the
    missing-evidence penalty and rejected the applicant.

    When `pending` is true the decision has not run. `outcome`,
    `decision_id` and `risk_score` are null because they do not exist
    yet, not because they failed. Poll `GET /applications/{id}/status`
    or wait for the `kyc.completed` webhook; both already carry the
    outcome once it lands. The response also arrives as HTTP 202 rather
    than 200, so a client can branch on the status line alone.
    """

    application_id: str
    persona_id: str
    state: str
    #: Null only while `pending` is true.
    outcome: Literal["approved", "rejected", "manual_review"] | None = None
    outcome_reason: str | None = None
    decision_id: uuid.UUID | None = None
    risk_score: float | None = None
    risk_components: dict[str, float] = Field(default_factory=dict)
    hard_fail_codes: list[str] = Field(default_factory=list)
    manual_review_id: uuid.UUID | None = None
    manual_review_priority: str | None = None
    #: Null while pending — an application that has not been decided has
    #: no completion time, and inventing one ("now") would make an
    #: unfinished application look finished in any downstream report.
    completed_at: dt.datetime | None = None
    #: True when evidence is still being computed and the decision was
    #: deliberately deferred.
    pending: bool = False
    #: What is still outstanding, e.g. `["face_match"]`. Empty when the
    #: decision has run.
    pending_on: list[str] = Field(default_factory=list)
    #: Suggested poll interval, in milliseconds.
    poll_after_ms: int | None = None

class DocumentSubmitRequest(StrictModel):
    """Mobile/web client upload for one document side.

    All document images are base64-encoded raw bytes (JPEG/PNG/HEIC).
    The server decodes, runs OpenCV IQA pre-check (Laplacian + glare),
    persists the blob to encrypted object storage (managed/BYOC), creates
    `kyc_documents` + `kyc_document_images` rows, and enqueues an
    asynchronous `process_kyc_ocr` task for Tesseract + MRZ extraction.

    `side` semantics:
    - tr_id_card / driver_license: front + back (two calls).
    - passport: single (one call; MRZ is on the data page).
    """

    document_type: DocumentTypeAllowed
    side: Literal["front", "back", "single"]
    mime_type: Literal["image/jpeg", "image/png", "image/heic"]
    image_b64: str = Field(min_length=128, max_length=12_000_000)
    captured_at_client: dt.datetime | None = None
    device_attestation: dict[str, Any] = Field(default_factory=dict)

class SelfieSubmitRequest(StrictModel):
    """Mobile/web client selfie upload.

    Submits one selfie (image or short video frame) as base64. Server:
      1. Runs OpenCV Haar face-quality assessment inline.
      2. Persists the blob + creates `kyc_selfies` row.
      3. Enqueues `process_kyc_face_match` ARQ task that matches against
         the front-side document image.
    """

    mime_type: Literal["image/jpeg", "image/png", "image/heic"]
    image_b64: str = Field(min_length=128, max_length=8_000_000)
    is_video: bool = False
    captured_at_client: dt.datetime | None = None
    device_attestation: dict[str, Any] = Field(default_factory=dict)

class LivenessChallengeRequest(StrictModel):
    """Mobile asks the server for a randomised active-challenge sequence.

    Mobile then prompts the user through the requested actions (blink,
    head_left, smile, etc.) recording frame metadata, and submits the
    completed action log back via `POST /liveness`.
    """

    length: int = Field(default=3, ge=2, le=5)
    ttl_seconds: int = Field(default=60, ge=30, le=300)

class LivenessChallengeResponse(StrictModel):
    application_id: str
    challenge_token: str
    sequence: list[str]
    issued_at: dt.datetime
    valid_until: dt.datetime

class LivenessActionRecord(StrictModel):
    """One completed action in the active challenge sequence."""

    action: Literal["blink", "head_left", "head_right", "smile", "look_up"]
    started_at_ms: int = Field(ge=0)
    ended_at_ms: int = Field(ge=0)

class LivenessVideoFrame(StrictModel):
    """One frame of a multi-frame liveness video.

    The mobile SDK captures ~5-15 frames during the active-challenge
    sequence, base64-encodes each, and submits them alongside the
    representative frame for multi-frame temporal analysis (M19+).
    """

    image_b64: str = Field(min_length=128, max_length=2_000_000)
    timestamp_ms: int = Field(ge=0)

class LivenessSubmitRequest(StrictModel):
    """Mobile submits a representative frame + (optionally) the active
    challenge completion log + (optionally) multi-frame video for
    temporal liveness verification.

    `mode='passive'` runs single-frame PAD only (moire + saturation +
    glare). `mode='active'` additionally validates the action sequence
    against the previously-issued challenge AND, when ``frames`` is
    supplied, runs MediaPipe FaceMesh-based temporal analysis to
    confirm the actions actually occurred.
    """

    mode: Literal["passive", "active"]
    frame_b64: str = Field(min_length=128, max_length=8_000_000)
    frame_mime_type: Literal["image/jpeg", "image/png", "image/heic"] = "image/jpeg"
    challenge_token: str | None = Field(default=None, max_length=255)
    completed_actions: list[LivenessActionRecord] | None = None
    captured_at_client: dt.datetime | None = None
    device_attestation: dict[str, Any] = Field(default_factory=dict)
    # M19+: multi-frame temporal verification. Optional; when provided,
    # the server runs MediaPipe FaceMesh on each frame to verify the
    # action_log timestamps line up with real eye/head/mouth motion.
    frames: list[LivenessVideoFrame] | None = Field(default=None, max_length=30)

class NFCSubmitRequest(StrictModel):
    """Mobile-side NFC chip read submission.

    All DG / SOD payloads are base64-encoded raw bytes (ICAO 9303
    layout: outer 0x6N tag + length + value). The server validates
    them with `kyc/nfc/verifier.verify_nfc()` against the trusted CSCA
    store (kyc_csca_certificates).

    Faz G-7.6: ``access_error`` distinguishes a chip *read* failure
    (user couldn't get the phone close enough, antenna noise, chip
    didn't respond) from a chip *content* failure (read succeeded but
    SOD/DG hashes don't verify → tampered). Access errors keep the
    application at AWAITING_NFC so the user can try the read again;
    content failures push to REJECTED via HARD_NFC_HASH_MISMATCH.
    """

    protocol: Literal["BAC", "PACE"]
    key_derivation: Literal["MRZ", "CAN"] | None = None
    # When True, the mobile SDK is reporting that the chip read itself
    # failed (no SOD obtained). All DG payloads should then be omitted.
    # The server records a soft-fail row + keeps state at AWAITING_NFC
    # so the user can retry. `failure_code` carries the SDK's reason.
    access_error: bool = False
    access_error_code: str | None = Field(default=None, max_length=64)
    """e.g. ``"chip_not_responding"``, ``"can_required"``,
    ``"protocol_negotiation_failed"``. Free-form on the SDK side; we
    just persist + audit it."""
    sod_b64: str | None = Field(default=None, max_length=1_500_000)
    dg1_b64: str | None = Field(default=None, max_length=200_000)
    dg2_b64: str | None = Field(default=None, max_length=400_000)
    dg7_b64: str | None = Field(default=None, max_length=200_000)
    dg11_b64: str | None = Field(default=None, max_length=200_000)
    dg12_b64: str | None = Field(default=None, max_length=200_000)
    dg13_b64: str | None = Field(default=None, max_length=200_000)
    dg14_b64: str | None = Field(default=None, max_length=200_000)
    dg15_b64: str | None = Field(default=None, max_length=200_000)
    active_authentication_b64: str | None = Field(default=None, max_length=200_000)
    read_at_client: dt.datetime | None = None
    device_attestation: dict[str, Any] = Field(default_factory=dict)
