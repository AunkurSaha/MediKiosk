# PHASE4B — BHASHINI adapter

Current report reconciled during stabilization on 2026-09-10. See [stabilization evidence and remaining gates](stabilization-implementation-status.md). This is a synthetic-data local prototype.

The existing BHASHINI adapter is implemented and tested using mocked HTTP responses. No live BHASHINI ASR or TTS acceptance is demonstrated; local credentials were absent in the authoritative audit.

Stabilization preserves the provider-neutral interface and offline mocks. It fixes direct-inference-only configuration and per-request cache loss, restricts discovery callbacks, bounds response size and adds an overall speech-service deadline. Live ASR accepts decoded 16-kHz mono PCM WAV only; unchecked browser WebM/MP4 is rejected as unsupported instead of mislabeled. Native browser recording requires evaluated conversion before live acceptance.

Do not describe this as full live multilingual speech capability. Real synthetic EN/BN/HI evaluation, supported-format evidence and provider handling review remain external acceptance work. No new provider was added.

Final acceptance is governed by the stabilization matrix, not historical unit-test counts.
