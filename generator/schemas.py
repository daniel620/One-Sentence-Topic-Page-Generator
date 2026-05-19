"""Pydantic data contract for the hot-event topic page generator.

Everything is one of:
  - an enum (event type, status, claim type, etc.)
  - a piece of *evidence* (`Source`, `Claim*`, `Contradiction`, `EvidenceGraph`)
  - a piece of *editorial structure* (`UIComponent`, `UIItem`, `KeyFact`,
    `TimelineEvent`, `Entity`)
  - a *stage I/O wrapper* (`EventHypothesis`, `EvidenceAwareIA`,
    `TopicPageData`, `ResearchResult`)
  - a *QA result* (`QAGateResult`, `QARepairAction`)

The renderer is downstream of `TopicPageData`. Anything that should appear on
the page lives here; anything internal-only (claim IDs, source IDs, QA gate
names) is filtered out by the renderer in public mode.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class EventType(str, Enum):
    TECH_LAUNCH = "tech_launch"
    LIVE_EVENT = "live_event"
    SPORTS_TOURNAMENT = "sports_tournament"
    CULTURAL_EVENT = "cultural_event"
    DISASTER = "disaster"
    ECONOMIC_EVENT = "economic_event"


class EventStatus(str, Enum):
    LIVE = "live"
    UPCOMING = "upcoming"
    CONCLUDED = "concluded"
    DEVELOPING = "developing"
    SCHEDULED = "scheduled"


class ConfidenceLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class LayoutStyle(str, Enum):
    """Coarse hint from Stage 1B about the dominant page shape.

    The renderer maps `(event_type, status)` to a richer `PageRecipe`
    in `generator.page_layout`; `layout_style` is the LLM's preference,
    not the final layout decision.
    """

    HERO_FOCUS = "hero_focus"
    DASHBOARD = "dashboard"
    TIMELINE_FIRST = "timeline_first"


class ComponentType(str, Enum):
    KEY_FACTS = "key_facts"
    STAT_GRID = "stat_grid"
    COMPARISON_TABLE = "comparison_table"
    LIVE_TRACKER = "live_tracker"
    ACTION_LIST = "action_list"
    TIMELINE = "timeline"
    ENTITY_LIST = "entity_list"
    SOURCE_LIST = "source_list"
    UNCERTAINTY_BOX = "uncertainty_box"
    CONFIDENCE_BANNER = "confidence_banner"


class ComponentRegistry(BaseModel):
    """Single source of truth for the known UI component types."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    component_types: tuple[ComponentType, ...] = tuple(ComponentType)

    @property
    def component_values(self) -> tuple[str, ...]:
        return tuple(component.value for component in self.component_types)

    def validate_component_type(self, value: ComponentType | str) -> ComponentType:
        try:
            component_type = value if isinstance(value, ComponentType) else ComponentType(value)
        except ValueError as exc:
            raise ValueError(
                f"Invalid component type: {value}. "
                f"Allowed component types: {', '.join(self.component_values)}"
            ) from exc
        if component_type not in self.component_types:
            raise ValueError(
                f"Invalid component type: {component_type.value}. "
                f"Allowed component types: {', '.join(self.component_values)}"
            )
        return component_type


COMPONENT_REGISTRY = ComponentRegistry()


def validate_component_registry(
    values: list[ComponentType | str] | tuple[ComponentType | str, ...],
) -> list[ComponentType]:
    if not isinstance(values, (list, tuple)):
        raise ValueError("required_components must be a list of known component types")
    return [COMPONENT_REGISTRY.validate_component_type(value) for value in values]


class SourceType(str, Enum):
    OFFICIAL = "official"
    PRIMARY_DATA = "primary_data"
    REPUTABLE_MEDIA = "reputable_media"
    LOCAL_MEDIA = "local_media"
    SOCIAL = "social"
    AGGREGATOR = "aggregator"
    UNKNOWN = "unknown"


class ClaimType(str, Enum):
    METRIC = "metric"
    STATUS = "status"
    SCHEDULE = "schedule"
    DATE = "date"
    QUOTE = "quote"
    LOCATION = "location"
    ENTITY = "entity"
    IMPACT = "impact"
    ACTION = "action"


class ClaimTopic(str, Enum):
    """Controlled topic vocabulary for claim comparison and contradiction detection."""
    EVENT_SCHEDULE = "event_schedule"
    VENUE = "venue"
    PARTICIPANTS = "participants"
    PRICING = "pricing"
    CAPABILITIES = "capabilities"
    ROLLOUT_STATUS = "rollout_status"
    SAFETY = "safety"
    METRICS = "metrics"
    CONTROVERSY = "controversy"
    HISTORY = "history"
    HOW_TO_WATCH = "how_to_watch"
    TICKETING = "ticketing"
    OTHER = "other"


class AISourceRole(str, Enum):
    """AI curator's assessment of a source's role in supporting claims."""
    PUBLIC_CLAIM = "public_claim_source"
    SUPPORTING = "supporting_context"
    BACKGROUND = "background_only"
    DEBUG = "debug_only"
    REJECT = "reject"
    NEEDS_REVIEW = "needs_review"


class AIContradictionResolution(str, Enum):
    """AI reviewer's judgment on whether a candidate contradiction matters."""
    REAL_UNCERTAINTY = "real_uncertainty"
    SCOPE_DIFFERENCE = "scope_difference"
    EXTRACTION_NOISE = "extraction_noise"
    DEBUG_ONLY = "debug_only"


class EvidenceGrade(str, Enum):
    """How strong is the evidence backing a claim? Used to decide which claims
    can anchor public hard facts and which should only support context."""
    FULL_TEXT_VERIFIED = "full_text_verified"
    OFFICIAL_SNIPPET = "official_snippet"
    REPUTABLE_SNIPPET = "reputable_snippet"
    MULTI_SOURCED = "multi_sourced"
    WEAK_SNIPPET = "weak_snippet"



class QARepairAction(str, Enum):
    MISSING_CLAIM_ID = "missing_claim_id"
    WEAK_SOURCE = "weak_source"
    STALE_SOURCE = "stale_source"
    UNSUPPORTED_NUMERIC_CLAIM = "unsupported_numeric_claim"
    MISSING_REQUIRED_COMPONENT = "missing_required_component"
    CONFLICTING_CLAIM = "conflicting_claim"
    UNDEFINED_COMPONENT = "undefined_component"


class ResolutionPolicy(str, Enum):
    PREFER_OFFICIAL = "prefer_official"
    PREFER_NEWER = "prefer_newer"
    UNRESOLVED = "unresolved"
    CONTEXT_DEPENDENT = "context_dependent"


class DisplayPolicy(str, Enum):
    SHOW_UNCERTAINTY_BOX = "show_uncertainty_box"
    OMIT_UNTIL_CONFIRMED = "omit_until_confirmed"
    SHOW_BOTH = "show_both"


class RenderMode(str, Enum):
    """Controls whether the rendered page shows internal trace UI.

    Public is the default and what reviewers/readers see.
    Debug exposes claim IDs, source IDs, QA gate names, and repair actions
    for engineers reviewing the pipeline.
    """

    PUBLIC = "public"
    DEBUG = "debug"


# ---------------------------------------------------------------------------
# Source & scoring
# ---------------------------------------------------------------------------

def calculate_source_authority_score(source_type: SourceType) -> float:
    scores = {
        SourceType.OFFICIAL: 1.0,
        SourceType.PRIMARY_DATA: 0.95,
        SourceType.REPUTABLE_MEDIA: 0.8,
        SourceType.LOCAL_MEDIA: 0.7,
        SourceType.SOCIAL: 0.5,
        SourceType.AGGREGATOR: 0.4,
        SourceType.UNKNOWN: 0.3,
    }
    return scores.get(source_type, 0.3)


class Source(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(min_length=1, max_length=100)
    url: HttpUrl
    title: str = Field(min_length=1, max_length=500)
    publisher: str | None = Field(default=None, max_length=120)
    published_at: datetime | None = None
    source_type: SourceType = SourceType.UNKNOWN
    authority_score: float = Field(default=0.3, ge=0.0, le=1.0)
    freshness_score: float = Field(default=0.5, ge=0.0, le=1.0)
    relevance_score: float = Field(default=0.5, ge=0.0, le=1.0)
    bias_or_limitation: str | None = Field(default=None, max_length=200)
    # AI curation
    ai_source_role: AISourceRole | None = Field(default=None)
    final_source_role: AISourceRole | None = Field(default=None)
    curation_reason: str | None = Field(default=None, max_length=200)

    @property
    def overall_score(self) -> float:
        return (
            self.authority_score * 0.5
            + self.freshness_score * 0.3
            + self.relevance_score * 0.2
        )

    @field_validator("authority_score", mode="before")
    @classmethod
    def validate_authority_from_type(cls, v, info):
        if info.data.get("source_type") and v == 0.3:
            return calculate_source_authority_score(info.data["source_type"])
        return v


# ---------------------------------------------------------------------------
# Claims & evidence
# ---------------------------------------------------------------------------

class Claim(BaseModel):
    """A single unified claim model. No type-specific subclasses.

    All claims share the same core fields. Type-specific data lives in
    claim_attributes — a dict keyed by field name. This replaces the
    old MetricClaim/DateClaim/... discriminator hierarchy, which added
    compile-time complexity for zero runtime benefit (the typed fields
    were only consumed in one place — contradiction detection).
    """

    model_config = ConfigDict(extra="forbid")

    claim_id: str = Field(min_length=1, max_length=100)
    text: str = Field(min_length=1, max_length=500)
    claim_type: ClaimType
    claim_topic: ClaimTopic = ClaimTopic.OTHER
    source_ids: list[str] = Field(min_length=1, max_length=20)
    confidence: ConfidenceLevel = ConfidenceLevel.MEDIUM
    freshness: str = Field(default="fresh", max_length=20)
    component_targets: list[ComponentType] = Field(default_factory=list)
    validation_status: str = Field(default="pending", max_length=40)
    # AI-extracted fields
    evidence_sentence: str = Field(default="", max_length=600)
    public_claim_eligible: bool = False
    evidence_grade: EvidenceGrade = EvidenceGrade.WEAK_SNIPPET
    # Type-specific data. Keys vary by claim_type:
    #   metric: value, unit, direction, base_value_if_delta, evidence_snippet
    #   date: date_value (ISO str)
    #   schedule: event_datetime (ISO str), timezone, event_name
    #   location: location
    #   entity: entity_name, entity_role
    #   status: status, observed_at (ISO str), source_evidence
    claim_attributes: dict[str, Any] = Field(default_factory=dict)


# For backward compatibility — ClaimUnion is now just Claim.
# All code that previously consumed ClaimUnion (list[ClaimUnion]) now uses list[Claim].
ClaimUnion = Claim


class Contradiction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    topic: str = Field(min_length=1, max_length=160)
    claim_a: str = Field(min_length=1, max_length=500)
    sources_a: list[str] = Field(min_length=1, max_length=20)
    claim_b: str = Field(min_length=1, max_length=500)
    sources_b: list[str] = Field(min_length=1, max_length=20)
    resolution: ResolutionPolicy = ResolutionPolicy.UNRESOLVED
    display_policy: DisplayPolicy = DisplayPolicy.SHOW_UNCERTAINTY_BOX
    # AI reviewer fields
    ai_resolution: AIContradictionResolution | None = Field(default=None)
    ai_resolution_reason: str | None = Field(default=None, max_length=200)


class EvidenceGraph(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_hypothesis: str = Field(min_length=1, max_length=300)
    sources: list[Source] = Field(default_factory=list, max_length=30)
    claims: list[Claim] = Field(default_factory=list, max_length=120)
    contradictions: list[Contradiction] = Field(default_factory=list, max_length=10)
    unresolved_questions: list[str] = Field(default_factory=list, max_length=5)
    last_updated: datetime | None = None

    @field_validator("sources")
    @classmethod
    def validate_sources_unique(cls, v):
        ids = [s.source_id for s in v]
        if len(ids) != len(set(ids)):
            raise ValueError("Source IDs must be unique")
        return v

    @field_validator("claims")
    @classmethod
    def validate_claims_unique(cls, v):
        ids = [c.claim_id for c in v]
        if len(ids) != len(set(ids)):
            raise ValueError("Claim IDs must be unique")
        return v

    def get_source_by_id(self, source_id: str) -> Source | None:
        for source in self.sources:
            if source.source_id == source_id:
                return source
        return None

    def validate_claim_sources(self) -> list[str]:
        errors = []
        for claim in self.claims:
            for source_id in claim.source_ids:
                if not self.get_source_by_id(source_id):
                    errors.append(
                        f"Claim {claim.claim_id} references nonexistent source {source_id}"
                    )
        return errors

    @property
    def public_evidence_view(self) -> "EvidenceGraph":
        """Return a filtered EvidenceGraph with only public-eligible content."""
        public_sources = [
            s for s in self.sources
            if s.final_source_role and s.final_source_role.value in (
                "public_claim_source", "supporting_context",
            )
        ]
        public_source_ids = {s.source_id for s in public_sources}
        public_claims = [
            c for c in self.claims
            if c.public_claim_eligible and set(c.source_ids) & public_source_ids
        ]
        public_contradictions = [
            c for c in self.contradictions
            if c.ai_resolution and c.ai_resolution == AIContradictionResolution.REAL_UNCERTAINTY
        ]
        return EvidenceGraph(
            event_hypothesis=self.event_hypothesis,
            sources=public_sources,
            claims=public_claims,
            contradictions=public_contradictions,
            unresolved_questions=self.unresolved_questions,
            last_updated=self.last_updated,
        )


class AISourceAssessment(BaseModel):
    """AI curator's verdict on a single source."""
    model_config = ConfigDict(extra="forbid")
    source_id: str
    role: AISourceRole
    reason: str = Field(default="", max_length=200)


class AIContradictionReview(BaseModel):
    """AI reviewer's verdict on a candidate contradiction."""
    model_config = ConfigDict(extra="forbid")
    contradiction_index: int
    resolution: AIContradictionResolution
    reason: str = Field(default="", max_length=200)


# ---------------------------------------------------------------------------
# Editorial structure (what the renderer reads)
# ---------------------------------------------------------------------------

class Entity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    role: str = Field(min_length=1, max_length=200)


class TimelineEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date_label: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=160)
    detail: str | None = Field(default=None, max_length=500)


class KeyFact(BaseModel):
    """One cell of the at-a-glance strip shown right under the hero.

    Use sparingly — 3 to 5 is the right number. Each `value` should fit
    on one line in the rendered grid.
    """

    model_config = ConfigDict(extra="forbid")

    label: str = Field(min_length=1, max_length=40)
    value: str = Field(min_length=1, max_length=80)
    hint: str | None = Field(default=None, max_length=120)
    claim_id: str | None = Field(default=None, max_length=100)


class UIItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str = Field(min_length=1, max_length=120)
    value: str = Field(min_length=1, max_length=260)
    detail: str | None = Field(default=None, max_length=500)
    link_label: str | None = Field(default=None, max_length=80)
    link_url: HttpUrl | None = None
    claim_id: str | None = Field(default=None, max_length=100)


class UIComponent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    component_type: ComponentType
    title: str = Field(min_length=1, max_length=120)
    summary: str | None = Field(default=None, max_length=260)
    columns: int = Field(default=1, ge=1, le=3)
    items: list[UIItem] = Field(default_factory=list, min_length=1, max_length=24)

    @field_validator("component_type", mode="before")
    @classmethod
    def _validate_component_type(cls, value):
        return COMPONENT_REGISTRY.validate_component_type(value)


# ---------------------------------------------------------------------------
# Stage I/O
# ---------------------------------------------------------------------------

class EventHypothesis(BaseModel):
    """Stage 1A output: classify the event before we have evidence."""

    model_config = ConfigDict(extra="forbid")

    preliminary_event_type: EventType
    freshness_need: str = Field(min_length=1, max_length=100)
    search_intents: list[str] = Field(min_length=2, max_length=6)
    required_source_types: list[SourceType] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list, max_length=5)


class EvidenceAwareIA(BaseModel):
    """Stage 1B output: information architecture, with evidence in hand."""

    model_config = ConfigDict(extra="forbid")

    final_event_type: EventType
    event_status: EventStatus
    page_thesis: str = Field(min_length=1, max_length=300)
    required_components: list[ComponentType] = Field(min_length=2, max_length=10)
    layout_style: LayoutStyle = LayoutStyle.HERO_FOCUS
    confidence_summary: str = Field(default="", max_length=200)

    @field_validator("required_components")
    @classmethod
    def _validate_required_components(cls, v):
        return validate_component_registry(v)


class EventContext(BaseModel):
    """Thin context object kept for Stage 2's deterministic research code.

    Holds only what Stage 2 actually needs: the event sentence and the
    search queries that Stage 1A produced.
    """

    model_config = ConfigDict(extra="forbid")

    event_type: EventType
    status: EventStatus
    confidence: ConfidenceLevel = ConfidenceLevel.MEDIUM
    primary_entity: str = Field(min_length=1, max_length=160)
    event_sentence: str | None = Field(default=None, max_length=500)
    search_queries: list[str] = Field(min_length=3, max_length=6)

    @field_validator("search_queries")
    @classmethod
    def _validate_queries(cls, values: list[str]) -> list[str]:
        cleaned = [value.strip() for value in values if value.strip()]
        if len(cleaned) < 3:
            raise ValueError("search_queries must include at least 3 non-empty queries")
        if len(set(cleaned)) != len(cleaned):
            raise ValueError("search_queries must not contain duplicates")
        return cleaned


class ResearchResult(BaseModel):
    """One Tavily search result, normalized."""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=240)
    title: str = Field(min_length=1, max_length=500)
    url: HttpUrl
    content: str = Field(min_length=1, max_length=3000)
    source_name: str | None = Field(default=None, max_length=120)
    published_date: str | None = Field(default=None, max_length=60)
    score: float | None = Field(default=None, ge=0, le=1)


# ---------------------------------------------------------------------------
# Event-type → required components
# ---------------------------------------------------------------------------

class EventTypeRequirement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_type: EventType
    required_components: list[ComponentType]
    required_claim_types: list[ClaimType] = Field(default_factory=list)
    description: str = Field(default="", max_length=300)


EVENT_TYPE_REQUIREMENTS = {
    EventType.TECH_LAUNCH: EventTypeRequirement(
        event_type=EventType.TECH_LAUNCH,
        required_components=[
            ComponentType.STAT_GRID,
            ComponentType.COMPARISON_TABLE,
            ComponentType.ACTION_LIST,
        ],
        required_claim_types=[ClaimType.METRIC, ClaimType.STATUS, ClaimType.IMPACT],
        description=(
            "Tech launches must show deltas, benchmarks, rollout status, "
            "affected users, caveats, and next steps."
        ),
    ),
    EventType.LIVE_EVENT: EventTypeRequirement(
        event_type=EventType.LIVE_EVENT,
        required_components=[
            ComponentType.TIMELINE,
            ComponentType.ACTION_LIST,
            ComponentType.LIVE_TRACKER,
        ],
        required_claim_types=[ClaimType.SCHEDULE, ClaimType.LOCATION, ClaimType.STATUS],
        description=(
            "Live events must show timeline, venue, schedule, watch/attend "
            "info, and live status."
        ),
    ),
    EventType.SPORTS_TOURNAMENT: EventTypeRequirement(
        event_type=EventType.SPORTS_TOURNAMENT,
        required_components=[
            ComponentType.STAT_GRID,
            ComponentType.TIMELINE,
            ComponentType.ENTITY_LIST,
            ComponentType.ACTION_LIST,
        ],
        required_claim_types=[ClaimType.SCHEDULE, ClaimType.LOCATION, ClaimType.ENTITY],
        description=(
            "Sports tournaments must show schedule, venue, "
            "teams/participants, and how to watch."
        ),
    ),
    EventType.CULTURAL_EVENT: EventTypeRequirement(
        event_type=EventType.CULTURAL_EVENT,
        required_components=[
            ComponentType.TIMELINE,
            ComponentType.ENTITY_LIST,
            ComponentType.ACTION_LIST,
        ],
        required_claim_types=[ClaimType.SCHEDULE, ClaimType.LOCATION, ClaimType.ENTITY],
        description=(
            "Cultural events must show schedule, venue, participants/lineup, "
            "watch/attend info, and key context."
        ),
    ),
    EventType.DISASTER: EventTypeRequirement(
        event_type=EventType.DISASTER,
        required_components=[
            ComponentType.STAT_GRID,
            ComponentType.LIVE_TRACKER,
            ComponentType.ACTION_LIST,
        ],
        required_claim_types=[ClaimType.LOCATION, ClaimType.IMPACT, ClaimType.STATUS],
        description=(
            "Disasters must show impact zones, casualties, affected services, "
            "relief resources, and live status."
        ),
    ),
    EventType.ECONOMIC_EVENT: EventTypeRequirement(
        event_type=EventType.ECONOMIC_EVENT,
        required_components=[
            ComponentType.STAT_GRID,
            ComponentType.COMPARISON_TABLE,
            ComponentType.TIMELINE,
            ComponentType.ACTION_LIST,
        ],
        required_claim_types=[ClaimType.METRIC, ClaimType.STATUS, ClaimType.IMPACT, ClaimType.DATE],
        description=(
            "Economic/political events must show key metrics, affected entities, timeline, and analysis."
        ),
    ),
}


# ---------------------------------------------------------------------------
# QA
# ---------------------------------------------------------------------------

class QAGateResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gate_name: str = Field(min_length=1, max_length=60)
    status: str = Field(default="pass", max_length=20)
    failed_items: list[str] = Field(default_factory=list, max_length=20)
    repair_actions: list[QARepairAction] = Field(default_factory=list, max_length=20)
    confidence_score: float = Field(default=1.0, ge=0.0, le=1.0)
    remediation_suggestions: list[str] = Field(default_factory=list, max_length=10)


# ---------------------------------------------------------------------------
# Top-level page data
# ---------------------------------------------------------------------------

class TopicPageData(BaseModel):
    """The structured page object the renderer reads.

    Editorial fields:
      - `headline`: 12-word max, the page's H1.
      - `deck`: one-sentence subhead under the headline, editorial voice.
      - `summary`: 2-3 sentence lead paragraph.
      - `urgency_label`: optional short chip e.g. "Live now", "Rolled out".
      - `key_facts`: 3-5 at-a-glance facts under the hero.
      - `sections`: ordered list of `UIComponent` blocks.
      - `timeline`, `key_entities`: kept for components that read them.

    Trace fields (stripped in public render):
      - `evidence_graph_ref`: full evidence graph for debug + citations.
      - `qa_results`: gate results from the QA loop.
    """

    model_config = ConfigDict(extra="forbid")

    event_type: EventType
    status: EventStatus
    confidence: ConfidenceLevel
    headline: str = Field(min_length=1, max_length=120)
    deck: str | None = Field(default=None, max_length=240)
    summary: str = Field(min_length=1, max_length=1000)
    urgency_label: str | None = Field(default=None, max_length=80)
    as_of_label: str | None = Field(default=None, max_length=80)
    key_facts: list[KeyFact] = Field(default_factory=list, max_length=6)
    key_entities: list[Entity] = Field(default_factory=list, min_length=1)
    timeline: list[TimelineEvent] = Field(default_factory=list, min_length=1)
    layout_style: LayoutStyle = LayoutStyle.HERO_FOCUS
    sections: list[UIComponent] = Field(default_factory=list, min_length=1, max_length=10)
    evidence_graph_ref: EvidenceGraph | None = None
    qa_results: list[QAGateResult] = Field(default_factory=list, max_length=5)
    last_updated: datetime | None = None

    @field_validator("headline")
    @classmethod
    def _validate_headline_length(cls, value: str) -> str:
        if len([word for word in value.split() if word]) > 12:
            raise ValueError("headline must be 12 words or fewer")
        return value

    @field_validator("sections")
    @classmethod
    def _validate_section_components(cls, v):
        for section in v:
            COMPONENT_REGISTRY.validate_component_type(section.component_type)
        return v

    def validate_numeric_claims_have_sources(self, evidence_graph: EvidenceGraph) -> list[str]:
        errors: list[str] = []
        for section_idx, section in enumerate(self.sections):
            for item_idx, item in enumerate(section.items):
                if item.claim_id:
                    if not any(c.claim_id == item.claim_id for c in evidence_graph.claims):
                        errors.append(
                            f"Section {section_idx}, item {item_idx}: claim_id "
                            f"{item.claim_id} not in EvidenceGraph"
                        )
                elif any(char.isdigit() for char in item.value):
                    errors.append(
                        f"Section {section_idx}, item {item_idx}: numeric value "
                        f"'{item.value}' has no claim_id"
                    )
        return errors
