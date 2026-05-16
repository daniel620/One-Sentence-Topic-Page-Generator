from __future__ import annotations

import pytest
from pydantic import ValidationError

from generator.schemas import (
    COMPONENT_REGISTRY,
    ComponentType,
    EvidenceAwareIA,
    EventStatus,
    EventType,
    EventTypeRequirement,
    EVENT_TYPE_REQUIREMENTS,
    ConfidenceLevel,
    Entity,
    LayoutStyle,
    TopicPageData,
    UIComponent,
    UIItem,
)


def test_ui_component_rejects_unknown_component_type() -> None:
    with pytest.raises(ValidationError) as exc:
        UIComponent.model_validate(
            {
                "component_type": "invented_component",
                "title": "Invalid",
                "items": [{"label": "One", "value": "Two"}],
            }
        )

    assert "invented_component" in str(exc.value).lower()


def test_evidence_aware_ia_rejects_unknown_required_component() -> None:
    with pytest.raises(ValidationError) as exc:
        EvidenceAwareIA.model_validate(
            {
                "final_event_type": EventType.TECH_LAUNCH,
                "event_status": EventStatus.DEVELOPING,
                "page_thesis": "Explain the launch.",
                "required_components": ["invented_component", ComponentType.ACTION_LIST],
                "layout_style": LayoutStyle.HERO_FOCUS,
                "confidence_summary": "Low confidence.",
            }
        )

    assert "invented_component" in str(exc.value).lower()


@pytest.mark.parametrize(
    ("event_type", "expected_components"),
    [
        (
            EventType.TECH_LAUNCH,
            {
                ComponentType.STAT_GRID,
                ComponentType.COMPARISON_TABLE,
                ComponentType.ACTION_LIST,
            },
        ),
        (
            EventType.LIVE_EVENT,
            {
                ComponentType.TIMELINE,
                ComponentType.ACTION_LIST,
                ComponentType.LIVE_TRACKER,
            },
        ),
        (
            EventType.SPORTS_TOURNAMENT,
            {
                ComponentType.STAT_GRID,
                ComponentType.TIMELINE,
                ComponentType.ENTITY_LIST,
                ComponentType.ACTION_LIST,
            },
        ),
        (
            EventType.CULTURAL_EVENT,
            {
                ComponentType.TIMELINE,
                ComponentType.ENTITY_LIST,
                ComponentType.ACTION_LIST,
            },
        ),
        (
            EventType.DISASTER,
            {
                ComponentType.STAT_GRID,
                ComponentType.LIVE_TRACKER,
                ComponentType.ACTION_LIST,
            },
        ),
    ],
)
def test_event_type_requirement_includes_expected_components(
    event_type: EventType,
    expected_components: set[ComponentType],
) -> None:
    requirement: EventTypeRequirement = EVENT_TYPE_REQUIREMENTS[event_type]
    assert set(requirement.required_components) == expected_components


def test_topic_page_sections_reject_unknown_component_type() -> None:
    with pytest.raises(ValidationError) as exc:
        TopicPageData.model_validate(
            {
                "event_type": EventType.TECH_LAUNCH,
                "status": EventStatus.CONCLUDED,
                "confidence": ConfidenceLevel.HIGH,
                "headline": "Valid headline",
                "summary": "Valid summary",
                "key_entities": [Entity(name="OpenAI", role="Company")],
                "timeline": [{"date_label": "May 2026", "title": "Launch"}],
                "sections": [
                    {
                        "component_type": "stat_grid",
                        "title": "Stats",
                        "items": [UIItem(label="Speed", value="40% faster").model_dump(mode="json")],
                    },
                    {
                        "component_type": "invented_component",
                        "title": "Invalid",
                        "items": [{"label": "One", "value": "Two"}],
                    },
                ],
            }
        )

    assert "invented_component" in str(exc.value).lower()
    assert "allowed component types" in str(exc.value).lower()


def test_component_registry_matches_component_enum() -> None:
    assert set(COMPONENT_REGISTRY.component_types) == set(ComponentType)
