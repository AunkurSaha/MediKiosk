"""Small declarative flow language; array order is the only traversal order."""

from typing import Literal

from pydantic import Field, model_validator

from .common import APIModel

SectionID = Literal[
    "chief_complaint",
    "hpi",
    "past_medical_history",
    "past_surgical_history",
    "medications",
    "allergies",
    "family_history",
    "personal_history",
    "review_of_systems",
    "ayush_demo",
]


class Localized(APIModel):
    en: str = Field(min_length=1)
    bn: str = Field(min_length=1)
    hi: str = Field(min_length=1)


class Option(APIModel):
    value: str = Field(min_length=1)
    label: Localized
    exclusive: bool = False


class Condition(APIModel):
    question_id: str
    operator: Literal["equals", "contains"] = "equals"
    value: bool | str


class Constraints(APIModel):
    minimum: float | None = None
    maximum: float | None = None
    max_length: int = Field(default=1000, ge=1, le=4000)
    integer: bool = False
    unit: str | None = None

    @model_validator(mode="after")
    def bounds(self):
        if self.minimum is not None and self.maximum is not None:
            if self.minimum > self.maximum:
                raise ValueError("minimum exceeds maximum")
        return self


class Question(APIModel):
    question_id: str = Field(pattern=r"^[a-z][a-z0-9_.]*$")
    field: str = Field(pattern=r"^[a-z][a-z0-9_.]*$")
    type: Literal[
        "boolean",
        "single_choice",
        "multiple_choice",
        "short_text",
        "number",
        "duration",
        "severity",
    ]
    required: bool = True
    allow_unknown: bool = True
    text: Localized
    options: list[Option] = Field(default_factory=list)
    constraints: Constraints = Field(default_factory=Constraints)
    depends_on: list[str] = Field(default_factory=list)
    when: list[Condition] = Field(default_factory=list)
    origin: str | None = None

    @model_validator(mode="after")
    def shape(self):
        choice = self.type in ("single_choice", "multiple_choice")
        if choice != bool(self.options):
            raise ValueError("only choice questions require options")
        if len({o.value for o in self.options}) != len(self.options):
            raise ValueError("duplicate option values")
        if set(self.depends_on) != {c.question_id for c in self.when}:
            raise ValueError("dependencies must exactly match condition references")
        if len(set(self.depends_on)) != len(self.depends_on):
            raise ValueError("duplicate dependencies")
        if self.type == "severity" and (
            self.constraints.minimum != 0
            or self.constraints.maximum != 10
            or not self.constraints.integer
        ):
            raise ValueError("severity requires integer bounds 0..10")
        return self


class Section(APIModel):
    section_id: SectionID
    label: Localized
    questions: list[Question] = Field(min_length=1)


class Flow(APIModel):
    schema_version: Literal[1]
    flow_id: str = Field(pattern=r"^[a-z][a-z0-9_.]*$")
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    namespace: Literal["standard", "ayush_demo", "legacy", "other"]
    label: Localized
    applicable_complaint: str | None = None
    content_status: Literal["prototype_unvalidated"]
    traversal: Literal["ordered_applicable"]
    completion: Literal["all_applicable_addressed"]
    sections: list[Section] = Field(min_length=1)

    @model_validator(mode="after")
    def references(self):
        seen = {}
        fields = set()
        sections = set()
        for section in self.sections:
            if section.section_id in sections:
                raise ValueError("duplicate section ID")
            sections.add(section.section_id)
            if (section.section_id == "ayush_demo") != (self.namespace == "ayush_demo"):
                raise ValueError("AYUSH must be isolated in its own namespace and section")
            if self.namespace == "other" and section.section_id == "ayush_demo":
                raise ValueError("AYUSH section cannot be in other namespace")
            for q in section.questions:
                if q.question_id in seen or q.field in fields:
                    raise ValueError("duplicate question ID or canonical field")
                if self.namespace != "legacy" and not q.field.startswith(section.section_id + "."):
                    raise ValueError("canonical field must belong to its section")
                for condition in q.when:
                    parent = seen.get(condition.question_id)
                    if parent is None:
                        raise ValueError("condition references must name an earlier question")
                    if parent.type == "boolean":
                        valid = condition.operator == "equals" and type(condition.value) is bool
                    elif parent.type in ("single_choice", "multiple_choice"):
                        expected = "contains" if parent.type == "multiple_choice" else "equals"
                        valid = condition.operator == expected and condition.value in {
                            o.value for o in parent.options
                        }
                    else:
                        valid = False
                    if not valid:
                        raise ValueError("condition is incompatible with its parent")
                seen[q.question_id] = q
                fields.add(q.field)
        return self

    def questions(self):
        return [(section, question) for section in self.sections for question in section.questions]
