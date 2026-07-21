# Phase 9 security review

## Scope and result

The release gate covers authentication and role enforcement, API key/session boundaries, origin
policy, request rate/size/type controls, idempotency abuse, SSRF-safe adapters, log/error redaction,
bounded solver/LLM inputs, injection/content review, immutable records, dependency/container/secret
scans, backup confidentiality and licensing. Portable machine reports live in `reports/security`.
Final Phase 9 completion depends on the last `scripts/security_scan.py --images` run remaining green.

## Implemented controls

- Production API access fails closed when no server-side API key is configured. Governance uses
  server-side key-to-actor/role mapping; caller-supplied actors are ignored.
- Allowed origins are explicit. JSON mutations enforce bounded content length and media type. There
  is no file-upload endpoint; unsupported body types are rejected before parsing.
- Rate limiting is bounded by request count and by stored identity count; identities derived from
  API keys are SHA-256 digests rather than raw secrets.
- The AIS adapter accepts only its documented secure provider host, uses bounded timeout/retry and
  keeps credentials server-side. Optional narrative output is untrusted, figure-checked and
  claim-policy checked before presentation.
- SQL uses static or parameterized statements. No request data reaches a shell command. React's
  normal escaped rendering is retained and external narrative HTML is not injected.
- Solver sizes, time limits and input domains are bounded. Independent checkers and the Evidence
  Auditor block failed plans, approvals and exports.
- Terminal plans, audits, approvals, exports and snapshots are immutable in repositories and via
  database triggers. Backups use restricted temporary permissions and are deleted after restore
  verification.
- Production images omit npm, pip, setuptools and wheel runtime tooling where it is not required.
  Browser-visible configuration contains only the public API origin and no source/solver secret.

## Scanner gate

The portable gate runs npm audit, a frozen uv export plus pip-audit, Bandit medium/high checks,
Gitleaks, Trivy filesystem/misconfiguration/license analysis and Trivy vulnerability scans of both
runtime images. Critical, high and reportable medium findings fail the gate. Scanner suppressions
are limited to reviewed LGPL/MPL license classifications; they are license obligations, not ignored
vulnerabilities, and are documented in `THIRD_PARTY_NOTICES.md`.

## Residual deployment risks

- Demo identities are not an enterprise IdP. Production operators must provision identities,
  rotate keys, terminate TLS and manage session/CSRF controls at the authenticated deployment edge.
- The local stack is single-host and the WebSocket broker is in-process. Redis fan-out is required
  before multiple API replicas.
- Fixtures and replay do not establish real commercial availability, private inventory or model
  accuracy. Licensed recorded validation and operator evidence are required for operational use.
- Malware scanning is not instantiated because Sanjiv exposes no upload surface. Adding uploads
  requires quarantine storage, content inspection and a new threat-model/test gate.
