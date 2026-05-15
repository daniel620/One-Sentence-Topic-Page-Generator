from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator


# ============================================================================
# ENUMS: Event & Status
# ============================================================================

class EventType(str, Enum):
    TECH_LAUNCH = "tech_launch"
    LIVE_EVENT = "live_event"
    SPORTS_TOURNAMENT = "sports_tournament"
    CULTURAL_EVENT = "cultural_event"
    DISASTER = "disaster"


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
    HERO_FOCUS = "hero_focus"
    DASHBOARD = "dashboard"
    TIMELINE_FIRST = "timeline_first"


class ComponentType(str, Enum):
    STAT_GRID = "stat_grid"
    COMPARISON_TABLE = "comparison_table"
    LIVE_TRACKER = "live_tracker"
    ACTION_LIST = "action_list"
    TIMELINE = "timeline"
    ENTITY_LIST = "entity_list"
    SOURCE_LIST = "source_list"
    UNCERTAINTY_BOX = "uncertainty_box"
    CONFIDENCE_BANNER = "confidence_banner"


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


# ============================================================================
# SOURCE & SCORING
# ============================================================================

def calculate_source_authority_score(source_type: SourceType) -> float:
    """Calculate authority score based on source type."""
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

    @property
    def overall_score(self) -> float:
        """Calculate weighted overall score."""
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


# ============================================================================
# EVIDENCE: Claims, Contradictions
# ============================================================================

class Claim(BaseModel):
    """Base claim model with common fields."""
    model_config = ConfigDict(extra="forbid")

    claim_id: str = Field(min_length=1, max_length=100)
    text: str = Field(min_length=1, max_length=500)
    claim_type: ClaimType
    source_ids: list[str] = Field(min_length=1, max_length=5)
    confidence: ConfidenceLevel = ConfidenceLevel.MEDIUM
    freshness: str = Field(default="fresh", max_length=20)
    component_targets: list[ComponentType] = Field(default_factory=list)
    validation_status: str = Field(default="pending", max_length=40)


class MetricClaim(Claim):
    """Metric claim with value, unit, direction."""
    claim_type: ClaimType = ClaimType.METRIC
    value: str = Field(min_length=1, max_length=60)
    unit: str = Field(min_length=1, max_length=60)
    direction: str | None = Field(default=None, max_length=40)
    base_value_if_delta: str | None = Field(default=None, max_length=60)
    evidence_snippet: str = Field(min_length=1, max_length=300)


class StatusClaim(Claim):
    """Status claim with timestamp."""
    claim_type: ClaimType = ClaimType.STATUS
    status: str = Field(min_length=1, max_length=120)
    observed_at: datetime | None = None
    source_evidence: str | None = Field(default=None, max_length=300)


class ScheduleClaim(Claim):
    """Schedule claim with timezone."""
    claim_type: ClaimType = ClaimType.SCHEDULE
    event_datetime: datetime
    timezone: str | None = Field(default=None, max_length=40)
    event_name: str = Field(min_length=1, max_length=160)


class DateClaim(Claim):
    """Date claim."""
    claim_type: ClaimType = ClaimType.DATE
    date_value: datetime


class LocationClaim(Claim):
    """Location claim."""
    claim_type: ClaimType = ClaimType.LOCATION
    location: str = Field(min_length=1, max_length=200)


class EntityClaim(Claim):
    """Entity claim with name and role."""
    claim_type: ClaimType = ClaimType.ENTITY
    entity_name: str = Field(min_length=1, max_length=160)
    entity_role: str = Field(min_length=1, max_length=200)


class Contradiction(BaseModel):
    """Represents conflicting claims."""
    model_config = ConfigDict(extra="forbid")

    topic: str = Field(min_length=1, max_length=160)
    claim_a: str = Field(min_length=1, max_length=500)
    sources_a: list[str] = Field(min_length=1, max_length=5)
    claim_b: str = Field(min_length=1, max_length=500)
    sources_b: list[str] = Field(min_length=1, max_length=5)
    resolution: ResolutionPolicy = ResolutionPolicy.UNRESOLVED
    display_policy: DisplayPolicy = DisplayPolicy.SHOW_UNCERTAINTY_BOX


# ============================================================================
# EVIDENCE GRAPH
# ============================================================================

class EvidenceGraph(BaseModel):
    """Central data structure for research findings."""
    model_config = ConfigDict(extra="forbid")

    event_hypothesis: str = Field(min_length=1, max_length=300)
    sources: list[Source] = Field(default_factory=list, max_length=30)
    claims: list[Claim] = Field(default_factory=list, max_length=50)
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
        """Lookup source by ID."""
        for source in self.sources:
            if source.source_id == source_id:
                return source
        return None

    def validate_claim_sources(self) -> list[str]:
        """Validate all claim source_ids exist; return list of errors."""
        errors = []
        for claim in self.claims:
            for source_id in claim.source_ids:
                if not self.get_source_by_id(source_id):
                    errors.append(f"Claim {claim.claim_id} references nonexistent source {source_id}")
        return errors


# ============================================================================
# BASIC MODELS (kept from previous schema)
# ============================================================================

class Entity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    role: str = Field(min_length=1, max_length=200)


class TimelineEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date_label: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=160)
    detail: str | None = Field(default=None, max_length=500)


class UIItem(BaseModel):
    """UI item with optional claim_id for traceability."""
    model_config = ConfigDict(extra="forbid")

    label: str = Field(min_length=1, max_length=120)
    value: str = Field(min_length=1, max_length=260)
    detail: str | None = Field(default=None, max_length=500)
    link_label: str | None = Field(default=None, max_length=80)
    link_url: HttpUrl | None = None
    claim_id: str | None = Field(default=None, max_length=100)

    @field_validator("claim_id")
    @classmethod
    def validate_claim_id_for_facts(cls, v, info):
        """Numeric/date/status facts should have claim_id."""
        # This is a soft warning; hard validation happens at TopicPageData level
        return v


class UIComponent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    component_type: ComponentType
    title: str = Field(min_length=1, max_length=120)
    summary: str | None = Field(default=None, max_length=260)
    columns: int = Field(default=1, ge=1, le=3)
    items: list[UIItem] = Field(default_factory=list, min_length=1, max_length=24)

    @field_validator("items")
    @classmethod
    def validate_items_have_claims_if_facts(cls, v, info):
        """Check that numeric/date items have claim_ids. More lenient during migration."""
        component_type = info.data.get("component_type")
        if component_type in [ComponentType.STAT_GRID, ComponentType.COMPARISON_TABLE]:
            missing_claim_ids = []
            for i, item in enumerate(v):
                # Only flag pure numeric items (e.g. "40%", "100") as requiring claim_id
                # Skip compound text like "United States, Mexico, Canada"
                value_stripped = item.value.strip()
                is_pure_numeric = (
                    value_stripped.replace("%", "").replace(",", "").replace(".", "").isdigit()
                    or value_stripped.replace("-", "").replace(":", "").isdigit()  # times/dates
                )
                if item.claim_id is None and is_pure_numeric:
                    missing_claim_ids.append(i)
            # Silently log but don't fail during migration
            if missing_claim_ids:
                # In M6, this will be upgraded to raise ValueError
                pass
        return v


# Legacy models for backward compatibility
class ResearchEvidence(BaseModel):
    """Legacy: used by stage2_research and existing code."""
    model_config = ConfigDict(extra="forbid")

    label: str = Field(min_length=1, max_length=100)
    signal_type: str = Field(min_length=1, max_length=40)
    snippet: str = Field(min_length=1, max_length=500)
    source_url: HttpUrl
    source_title: str = Field(min_length=1, max_length=500)
    source_publisher: str | None = Field(default=None, max_length=120)
    published_at: str | None = Field(default=None, max_length=60)


class EvidencePoint(BaseModel):
    """Legacy: used by existing TopicPageData."""
    model_config = ConfigDict(extra="forbid")

    claim: str = Field(min_length=1, max_length=220)
    value: str | None = Field(default=None, max_length=120)
    source_url: HttpUrl
    source_title: str | None = Field(default=None, max_length=500)
    snippet: str | None = Field(default=None, max_length=500)


class ComponentEvidenceBucket(BaseModel):
    """Legacy: used by stage2_research for component-evidence mapping."""
    model_config = ConfigDict(extra="forbid")

    component_type: ComponentType
    evidence: list[ResearchEvidence] = Field(default_factory=list, max_length=6)


# ============================================================================
# STAGES: HYPOTHESIS, EVIDENCE-AWARE IA
# ============================================================================

class EventHypothesis(BaseModel):
    """Stage 1A output: initial hypothesis without IA."""
    model_config = ConfigDict(extra="forbid")

    preliminary_event_type: EventType
    freshness_need: str = Field(min_length=1, max_length=100)
    search_intents: list[str] = Field(min_length=2, max_length=6)
    required_source_types: list[SourceType] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list, max_length=5)


class EvidenceAwareIA(BaseModel):
    """Stage 1B output: evidence-aware IA planning."""
    model_config = ConfigDict(extra="forbid")

    final_event_type: EventType
    event_status: EventStatus
    page_thesis: str = Field(min_length=1, max_length=300)
    required_components: list[ComponentType] = Field(min_length=2, max_length=8)
    layout_style: LayoutStyle = LayoutStyle.HERO_FOCUS
    confidence_summary: str = Field(default="", max_length=200)

    @field_validator("required_components")
    @classmethod
    def validate_required_components_from_registry(cls, v):
        """Validate all components are in registry."""
        valid_types = set(ComponentType)
        invalid = [c for c in v if c not in valid_types]
        if invalid:
            raise ValueError(f"Invalid component types: {invalid}")
        return v


# ============================================================================
# EVENT-TYPE REQUIREMENTS
# ============================================================================

class EventTypeRequirement(BaseModel):
    """Required components per event type."""
    model_config = ConfigDict(extra="forbid")

    event_type: EventType
    required_components: list[ComponentType]
    required_claim_types: list[ClaimType] = Field(default_factory=list)
    description: str = Field(default="", max_length=300)


# Define standard requirements
EVENT_TYPE_REQUIREMENTS = {
    EventType.TECH_LAUNCH: EventTypeRequirement(
        event_type=EventType.TECH_LAUNCH,
        required_components=[
            ComponentType.STAT_GRID,
            ComponentType.COMPARISON_TABLE,
            ComponentType.ACTION_LIST,
        ],
        required_claim_types=[
            ClaimType.METRIC,
            ClaimType.STATUS,
            ClaimType.IMPACT,
        ],
        description="Tech launches must show deltas, benchmarks, rollout status, affected users, caveats, next steps.",
    ),
    EventType.LIVE_EVENT: EventTypeRequirement(
        event_type=EventType.LIVE_EVENT,
        required_components=[
            ComponentType.TIMELINE,
            ComponentType.ACTION_LIST,
            ComponentType.LIVE_TRACKER,
        ],
        required_claim_types=[
            ClaimType.SCHEDULE,
            ClaimType.LOCATION,
            ClaimType.STATUS,
        ],
        description="Live events must show timeline, venue, schedule, watch/attend info, live status.",
    ),
    EventType.SPORTS_TOURNAMENT: EventTypeRequirement(
        event_type=EventType.SPORTS_TOURNAMENT,
        required_components=[
            ComponentType.STAT_GRID,
            ComponentType.TIMELINE,
            ComponentType.ACTION_LIST,
        ],
        required_claim_types=[
            ClaimType.SCHEDULE,
            ClaimType.LOCATION,
            ClaimType.ENTITY,
        ],
        description="Sports tournaments must show schedule, venue, teams/participants, standings, how to watch.",
    ),
    EventType.CULTURAL_EVENT: EventTypeRequirement(
        event_type=EventType.CULTURAL_EVENT,
        required_components=[
            ComponentType.STAT_GRID,
            ComponentType.ACTION_LIST,
            ComponentType.TIMELINE,
        ],
        required_claim_types=[
            ClaimType.SCHEDULE,
            ClaimType.LOCATION,
            ClaimType.ENTITY,
        ],
        description="Cultural events must show schedule, venue, participants/lineup, watch/attend info, key context.",
    ),
    EventType.DISASTER: EventTypeRequirement(
        event_type=EventType.DISASTER,
        required_components=[
            ComponentType.STAT_GRID,
            ComponentType.LIVE_TRACKER,
            ComponentType.ACTION_LIST,
        ],
        required_claim_types=[
            ClaimType.LOCATION,
            ClaimType.IMPACT,
            ClaimType.STATUS,
        ],
        description="Disasters must show impact zones, casualties, affected services, relief resources, live status.",
    ),
}


# ============================================================================
# QA: GATES & RESULTS
# ============================================================================

class QAGateResult(BaseModel):
    """Result of a QA gate check."""
    model_config = ConfigDict(extra="forbid")

    gate_name: str = Field(min_length=1, max_length=60)
    status: str = Field(default="pass", max_length=20)  # "pass" or "fail"
    failed_items: list[str] = Field(default_factory=list, max_length=20)
    repair_actions: list[QARepairAction] = Field(default_factory=list, max_length=20)
    confidence_score: float = Field(default=1.0, ge=0.0, le=1.0)
    remediation_suggestions: list[str] = Field(default_factory=list, max_length=10)


# ============================================================================
# MAIN: EVENT CONTEXT, RESEARCH, TOPIC PAGE DATA
# ============================================================================

class EventContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_type: EventType
    status: EventStatus
    confidence: ConfidenceLevel = ConfidenceLevel.MEDIUM
    primary_entity: str = Field(min_length=1, max_length=160)
    event_sentence: str | None = Field(default=None, max_length=500)
    search_queries: list[str] = Field(min_length=3, max_length=5)
    # Legacy fields for backward compatibility with existing fixtures
    layout_style: LayoutStyle | None = Field(default=None)
    planned_components: list[ComponentType] | None = Field(default=None)

    @field_validator("search_queries")
    @classmethod
    def validate_queries(cls, values: list[str]) -> list[str]:
        cleaned = [value.strip() for value in values if value.strip()]
        if len(cleaned) < 3:
            raise ValueError("search_queries must include at least 3 non-empty queries")
        if len(set(cleaned)) != len(cleaned):
            raise ValueError("search_queries must not contain duplicates")
        return cleaned


class ResearchResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=240)
    title: str = Field(min_length=1, max_length=500)
    url: HttpUrl
    content: str = Field(min_length=1, max_length=3000)
    source_name: str | None = Field(default=None, max_length=120)
    published_date: str | None = Field(default=None, max_length=60)
    score: float | None = Field(default=None, ge=0, le=1)


class RawResearch(BaseModel):
    """Legacy model; kept for backward compatibility."""
    model_config = ConfigDict(extra="forbid")

    event_type: EventType
    status: EventStatus
    collected_at: str | None = Field(default=None, max_length=60)
    results: list[ResearchResult] = Field(default_factory=list)
    evidence_pack: list[ResearchEvidence] | list[dict] = Field(default_factory=list, max_length=12)
    component_evidence: list[ComponentEvidenceBucket] | list[dict] = Field(default_factory=list, max_length=7)


class TopicPageData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_type: EventType
    status: EventStatus
    confidence: ConfidenceLevel
    headline: str = Field(min_length=1, max_length=120)
    summary: str = Field(min_length=1, max_length=1000)
    urgency_label: str | None = Field(default=None, max_length=80)
    key_entities: list[Entity] = Field(default_factory=list, min_length=1)
    timeline: list[TimelineEvent] = Field(default_factory=list, min_length=1)
    layout_style: LayoutStyle = LayoutStyle.HERO_FOCUS
    sections: list[UIComponent] = Field(default_factory=list, min_length=2, max_length=10)
    # Legacy fields for backward compatibility
    sources: list[Source] | list[dict] = Field(default_factory=list)
    evidence_points: list[EvidencePoint] | list[dict] = Field(default_factory=list)
    # New fields
    evidence_graph_ref: EvidenceGraph | None = None
    qa_results: list[QAGateResult] = Field(default_factory=list, max_length=5)
    last_updated: datetime | None = None

    @field_validator("headline")
    @classmethod
    def validate_headline_length(cls, value: str) -> str:
        words = [word for word in value.split() if word]
        if len(words) > 12:
            raise ValueError("headline must be 12 words or fewer")
        return value

    @field_validator("sections")
    @classmethod
    def validate_all_components_in_registry(cls, v):
        """Validate all component types are in registry."""
        valid_types = set(ComponentType)
        for section in v:
            if section.component_type not in valid_types:
                raise ValueError(f"Invalid component type: {section.component_type}")
        return v

    def validate_numeric_claims_have_sources(self, evidence_graph: EvidenceGraph) -> list[str]:
        """Check that numeric/date claims in sections reference evidence_graph claims."""
        errors = []
        for section_idx, section in enumerate(self.sections):
            for item_idx, item in enumerate(section.items):
                if item.claim_id:
                    # Verify claim exists in evidence graph
                    claim_found = any(c.claim_id == item.claim_id for c in evidence_graph.claims)
                    if not claim_found:
                        errors.append(
                            f"Section {section_idx}, item {item_idx}: claim_id {item.claim_id} not in EvidenceGraph"
                        )
                elif any(char.isdigit() for char in item.value):
                    # Numeric item without claim_id
                    errors.append(
                        f"Section {section_idx}, item {item_idx}: numeric value '{item.value}' has no claim_id"
                    )
        return errors
