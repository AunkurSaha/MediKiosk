"""Pure deterministic applicability/traversal, separated from persistence and transport."""

import math

from app.core.errors import WorkflowError
from app.schemas.adaptive import ClinicalHistory, Fact, HistorySection, InterviewState, Progress


def invalid():
    raise WorkflowError("INVALID_ANSWER", "Answer does not match this question.", 422)


def validate_answer(question, payload):
    value = payload.value
    if payload.status != "answered":
        if value is not None or not payload.raw_value.strip():
            invalid()
        if payload.status == "skipped" and question.required:
            invalid()
        if payload.status in ("unknown", "not_reported") and not question.allow_unknown:
            invalid()
        return
    kind = question.type
    bounds = question.constraints
    if kind == "short_text":
        if not isinstance(value, str) or not value.strip() or len(value) > bounds.max_length:
            invalid()
        if payload.raw_value != value:
            invalid()
    elif kind == "boolean":
        if type(value) is not bool:
            invalid()
    elif kind in ("number", "severity"):
        if type(value) not in (int, float) or not math.isfinite(value):
            invalid()
        if bounds.integer and int(value) != value:
            invalid()
        if bounds.minimum is not None and value < bounds.minimum:
            invalid()
        if bounds.maximum is not None and value > bounds.maximum:
            invalid()
    elif kind == "duration":
        from app.schemas.adaptive import Duration

        if not isinstance(value, Duration):
            invalid()
        if bounds.minimum is not None and value.amount < bounds.minimum:
            invalid()
        if bounds.maximum is not None and value.amount > bounds.maximum:
            invalid()
    elif kind in ("single_choice", "multiple_choice"):
        values = value if kind == "multiple_choice" else [value]
        if not isinstance(values, list) or not values or any(type(v) is not str for v in values):
            invalid()
        if len(set(values)) != len(values) or not set(values) <= {
            o.value for o in question.options
        }:
            invalid()
        if len(values) > 1 and any(o.exclusive and o.value in values for o in question.options):
            invalid()


class InterviewEngine:
    def __init__(self, flow, answers: dict[str, Fact]):
        self.flow = flow
        self.answers = answers
        self.applicable = []
        self.active = {}
        for section, question in flow.questions():
            applies = True
            for condition in question.when:
                parent = self.active.get(condition.question_id)
                if parent is None or parent.status != "answered":
                    applies = False
                    break
                if condition.operator == "equals":
                    applies = type(parent.value) is type(condition.value) and (
                        parent.value == condition.value
                    )
                else:
                    applies = isinstance(parent.value, list) and condition.value in parent.value
                if not applies:
                    break
            if applies:
                self.applicable.append((section, question))
                if question.question_id in answers:
                    self.active[question.question_id] = answers[question.question_id]
        self.pending = [
            q.question_id for _, q in self.applicable if q.question_id not in self.active
        ]

    def history(self):
        return ClinicalHistory(
            flow_id=self.flow.flow_id,
            flow_version=self.flow.version,
            namespace=self.flow.namespace,
            selected_complaint=self.flow.label,
            selection_source="legacy_intake"
            if self.flow.namespace == "legacy"
            else "patient_selected",
            sections=[
                HistorySection(
                    section_id=s.section_id,
                    label=s.label,
                    facts=[
                        self.active[q.question_id]
                        for q in s.questions
                        if q.question_id in self.active
                    ],
                )
                for s in self.flow.sections
            ],
        )

    def state(self, cursor=None, revision=0):
        ids = [q.question_id for _, q in self.applicable]
        if cursor not in ids:
            cursor = self.pending[0] if self.pending else None
        index = ids.index(cursor) if cursor else len(ids)
        section, question = self.applicable[index] if cursor else (None, None)
        return InterviewState(
            flow_id=self.flow.flow_id,
            flow_version=self.flow.version,
            namespace=self.flow.namespace,
            revision=revision,
            section=section.label if section else None,
            question=question,
            current_answer=self.active.get(cursor),
            previous_question_id=ids[index - 1] if index > 0 else None,
            active_answers=list(self.active.values()),
            inactive_question_ids=[
                q.question_id
                for _, q in self.flow.questions()
                if q.question_id in self.answers and q.question_id not in self.active
            ],
            missing_required=[
                q.question_id
                for _, q in self.applicable
                if q.required and q.question_id not in self.active
            ],
            progress=Progress(
                addressed=len(self.active),
                applicable=len(ids),
                position=index + 1 if cursor else len(ids),
            ),
            is_complete=not self.pending,
            history=self.history(),
        )

    def after(self, question_id):
        ids = [q.question_id for _, q in self.applicable]
        index = ids.index(question_id)
        # Walk in configuration order, including restored answers for patient review.
        if index + 1 < len(ids):
            return ids[index + 1]
        return self.pending[0] if self.pending else None


def draft_from_history(history):
    lines = [f"Patient selected: {history.selected_complaint.en}"]
    if history.namespace == "ayush_demo":
        lines.append("AYUSH demonstration only; no interpretation.")
    for section in history.sections:
        if section.facts:
            lines.append(f"\n{section.label.en}")
        for fact in section.facts:
            lines.append(
                f"{fact.label.en} — Patient reported ({fact.status}; {fact.source}; "
                f"{fact.language}): {fact.raw_value}"
            )
    return "\n".join(lines)
