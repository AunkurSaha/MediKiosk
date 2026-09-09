# Canonical SIH Demo Scenario — MediKiosk

Use this scenario to keep implementation coherent.

## Patient journey

1. Patient selects Bengali.
2. Patient accepts consent.
3. Patient has demo identity/token.
4. Patient reports chest pain beginning yesterday/last night.
5. Interview enters chest-pain structured flow.
6. Patient reports worsening on walking/exertion.
7. Patient reports breathlessness.
8. Safety engine fires an urgent, explainable alert.
9. Triage dashboard displays the alert.
10. Patient uploads old prescription.
11. Extraction identifies a medicine with confidence/provenance.
12. Patient uploads lab report.
13. Extraction identifies HbA1c result.
14. Timeline includes dated prior information.
15. Doctor opens the patient token.
16. Doctor sees:
    - current complaint/HPI;
    - past history;
    - medication;
    - lab;
    - timeline;
    - alert;
    - source/verification states.
17. Draft clinical summary is shown.
18. Doctor edits it.
19. Doctor confirms it.
20. System can show FHIR-compatible export.

## Safety language

Alert wording should resemble:

**Potential emergency symptoms detected — immediate clinical assessment recommended.**

Reasons can include the reported structured facts.

Do not display a diagnosis such as myocardial infarction.

## Purpose

This single flow should prove nearly every major product claim without requiring broad disease coverage.
