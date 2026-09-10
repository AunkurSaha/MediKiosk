# PHASE5 — Prototype rules and triage

Current report reconciled during stabilization on 2026-09-10. See [stabilization evidence and remaining gates](stabilization-implementation-status.md). This is a synthetic-data local prototype.

The original report overstated completion. The independent audit reproduced anonymous staff access, forged acknowledgement, missing creation delivery, negation/context errors, misleading rule explanations and acknowledged alerts that never resolved.

Stabilization reuses the existing server-owned demo doctor identity for staff routes and WebSocket admission. It versions alert evidence, preserves acknowledgement history separately from current trigger state, emits committed creation/update/resolution/reactivation events, resynchronizes the dashboard and derives counters from unique records. Browser delivery also required enabling Vite WebSocket proxying, installing the uvicorn WebSocket transport and selecting the admission subprotocol.

Rule thresholds remain prototype content, not clinically validated rules. Explanations describe actual conditions only; no diagnosis is an alert reason. Current symptom evidence preserves field context/polarity. Exact known phrases are supported offline; unrecognized wording requires staff review and does not prove symptom absence.

Patient copy no longer asserts staff notification. A socket write is not human acknowledgement. Delivery is limited to the current single backend process; there is no durable cross-worker messaging guarantee.

Final acceptance is governed by the stabilization matrix, not historical unit-test counts.
