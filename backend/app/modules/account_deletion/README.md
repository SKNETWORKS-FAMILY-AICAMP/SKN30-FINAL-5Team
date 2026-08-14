# Account deletion module

This module owns the authenticated deletion request, the deterministic deletion job state machine,
and ports for provider revocation and backup-expiry verification.

- `service.py` keeps request and job business rules outside API handlers.
- `ports.py` isolates persistence, provider revocation, and backup evidence.
- `codes.py` contains stable machine codes and the policy version.
- `schemas.py` exposes only the approved opaque deletion response.

The module does not implement a scheduler, queue, Firebase deletion adapter, AWS resources, or an
audit purge TTL. User identifiers, provider subjects, tokens, raw failures, and health snapshots may
not enter the post-deletion audit record or application logs.
