# KYC v2 integration / KYC v2 entegrasyonu

Configure one Legichain API token. The SDK creates the application and keeps
the API-returned client token internally. No backend changes are required.
Mobile requests originate directly from the device; server SDK requests
originate from the customer's server. Choose the tenant's regional API URL.

Tek Legichain API tokeniyle yapılandırın. SDK başvuruyu oluşturur ve API'nin
döndürdüğü dahili bilgileri yönetir. Mobil istekler cihazdan, sunucu SDK
istekleri müşterinin sunucusundan gider. Legichain backend değişikliği gerekmez.

## Evidence and submission

1. Create with document/check options. Document is mandatory. NFC defaults to
   false; liveness and face matching default to true. Explicit false is retained.
2. Capture front/back (single for a passport), NFC if required, and selfie.
3. For active liveness request a fresh challenge. Follow its ordered sequence;
   supply real observed actions and temporal frames, never client PAD scores.
4. Send evidence to `/v2/kyc/applications/{id}/{documents,nfc,selfie,liveness}`.
   Persist each receipt. A 202 receipt is queued work; poll its operation until
   completed. Failed/expired/cancelled operations require recovery.
5. Submit only after evidence processing. `/v1/.../submit` can return 202 with
   a null outcome. Show submitted and return to your app. The final business
   decision arrives at your configured webhook; verify its signature with the
   SDK webhook helper and handle deliveries idempotently.

Belge işleme bittiğinde başvuru gönderilir. `submitted` sonucu kimliğin
onaylandığı anlamına gelmez. Kullanıcıya başvurunun alındığını gösterin;
doğrulama sonucu webhook üzerinden gelir. Bildirimi müşteri uygulaması gönderir.

When face matching is enabled without active liveness, send the selfie plus a
passive liveness record. This is required by the current backend. Native flows
handle it automatically. A receipt being completed does not mean the evidence
passed all identity checks; the backend consolidates those checks at submission.

## Wire contract and migration

See `kyc-contract.json` for request/response fields exported from the unchanged
backend. Low-level APIs remain available for custom capture integrations.

- Liveness uses `mode`, `frame_b64`, `frame_mime_type`, optional
  `challenge_token`, `completed_actions`, `frames` and `device_attestation`.
- An action contains `action`, `started_at_ms`, `ended_at_ms` (1–8 seconds).
  Frame entries contain `image_b64` and `timestamp_ms`, at most 30 entries.
  Action and frame times share the same monotonic capture origin.
- Remove obsolete `actions_performed`, `frames_b64`, `pad_score` fields.
- NFC carries raw TLV bytes of SOD and data groups, including tags/lengths.
  Do not upload only parsed MRZ fields or decoded portrait pixels as DG data.
  AA response bytes go in `active_authentication_b64`, with the 8-byte challenge
  in `device_attestation.aa_challenge_b64`. Validation remains server-side.
- Use a stable unique idempotency key (1–256 bytes) for each evidence capture.
  Keep the same body/key after uncertain transport failures; a deliberate new
  capture uses a new key. Do not blindly retry unkeyed submission: first read
  application status and reconcile `deciding`/terminal states.
- Store receipts and application state in your server's session store when
  using multiple processes. Session helper objects themselves are in-memory.
- Respect retention in your own application; do not log tokens, raw document
  images, chip files or liveness frames. The native flow keeps capture data in
  memory and clears it when closed.

## python integration

```python
from legichain import Legichain

client = Legichain(api_key="YOUR_LEGICHAIN_TOKEN")
flow = client.kyc.start({"subject_external_id": "customer-42"}, idem="customer-42-application")
# body is the current document/selfie/NFC/liveness JSON from your capture client.
receipt = flow.evidence("documents", body, idem="customer-42-front-capture-1")
flow.wait(receipt["operation_id"])
# Add the remaining configured evidence before submitting.
submission = flow.submit()
```
The same API is available with `AsyncLegichain` and `await`.
