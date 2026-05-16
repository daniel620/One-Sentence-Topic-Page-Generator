"""Per-event-type page layout recipes.

A `PageRecipe` is the contract between `TopicPageData` and the renderer.
It controls:

  - which hero variant the page uses (live, delta, schedule, alert);
  - which CSS theme is applied (palette, typography);
  - the preferred order in which `UIComponent`s appear, when the LLM has
    produced them in a different order;
  - which sections are pinned to the top (e.g. a sticky "Now / Next" strip
    on live events) and which are pushed to the bottom (sources, timeline).

The renderer is the only consumer of `PageRecipe`. It is intentionally a
plain dataclass so a future React/Tailwind renderer can read the same
recipe object.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from generator.schemas import ComponentType, EventStatus, EventType


@dataclass(frozen=True)
class PageRecipe:
    """A render-time recipe for an event type + status combination."""

    event_type: EventType
    hero_variant: str
    theme: str
    accent_label: str
    section_order: tuple[ComponentType, ...]
    pinned_top: tuple[ComponentType, ...] = field(default_factory=tuple)
    default_key_facts_labels: tuple[str, ...] = field(default_factory=tuple)

    def order_key(self, component_type: ComponentType) -> int:
        try:
            return self.section_order.index(component_type)
        except ValueError:
            return len(self.section_order)


# Hero variants describe the editorial frame above the fold.
#   - delta:    "what changed" — tech launches
#   - live:     "what's happening right now" — live events in progress
#   - schedule: "what's coming up" — upcoming events / tournaments
#   - alert:    "what to do next" — disasters
HERO_VARIANTS = ("delta", "live", "schedule", "alert")

# Themes correspond to CSS bundles in templates/themes/.
#   - editorial:    light cream, serif headline; for tech launches & cultural
#   - live-dark:    high-contrast dark, sans serif; for in-progress live events
#   - stadium:      cool navy + brand red; for sports tournaments
#   - alert:        amber + cream; for disasters
THEMES = ("editorial", "live-dark", "stadium", "alert")


def _recipe(
    event_type: EventType,
    hero_variant: str,
    theme: str,
    accent_label: str,
    section_order: tuple[ComponentType, ...],
    pinned_top: tuple[ComponentType, ...] = (),
) -> PageRecipe:
    return PageRecipe(
        event_type=event_type,
        hero_variant=hero_variant,
        theme=theme,
        accent_label=accent_label,
        section_order=section_order,
        pinned_top=pinned_top,
    )


# A small, explicit table. Keep it short — every entry should be defensible
# in a code review.
_RECIPES: dict[tuple[EventType, EventStatus], PageRecipe] = {
    # Tech launches read as delta reports. "What changed" comes first;
    # rollout numbers next; then action_list. Concluded vs developing only
    # differs in the urgency label, not the layout.
    (EventType.TECH_LAUNCH, EventStatus.CONCLUDED): _recipe(
        EventType.TECH_LAUNCH, "delta", "editorial", "Rollout",
        section_order=(
            ComponentType.COMPARISON_TABLE,
            ComponentType.STAT_GRID,
            ComponentType.ACTION_LIST,
            ComponentType.TIMELINE,
            ComponentType.ENTITY_LIST,
        ),
    ),
    (EventType.TECH_LAUNCH, EventStatus.DEVELOPING): _recipe(
        EventType.TECH_LAUNCH, "delta", "editorial", "Rolling out",
        section_order=(
            ComponentType.LIVE_TRACKER,
            ComponentType.COMPARISON_TABLE,
            ComponentType.STAT_GRID,
            ComponentType.ACTION_LIST,
            ComponentType.TIMELINE,
        ),
    ),
    # Live cultural events read as now/next guides. LIVE_TRACKER pinned top.
    (EventType.LIVE_EVENT, EventStatus.LIVE): _recipe(
        EventType.LIVE_EVENT, "live", "live-dark", "Live now",
        section_order=(
            ComponentType.LIVE_TRACKER,
            ComponentType.TIMELINE,
            ComponentType.ENTITY_LIST,
            ComponentType.ACTION_LIST,
        ),
        pinned_top=(ComponentType.LIVE_TRACKER,),
    ),
    (EventType.LIVE_EVENT, EventStatus.UPCOMING): _recipe(
        EventType.LIVE_EVENT, "schedule", "editorial", "This week",
        section_order=(
            ComponentType.TIMELINE,
            ComponentType.ENTITY_LIST,
            ComponentType.ACTION_LIST,
        ),
    ),
    (EventType.LIVE_EVENT, EventStatus.DEVELOPING): _recipe(
        EventType.LIVE_EVENT, "live", "live-dark", "In progress",
        section_order=(
            ComponentType.LIVE_TRACKER,
            ComponentType.TIMELINE,
            ComponentType.ENTITY_LIST,
            ComponentType.ACTION_LIST,
        ),
        pinned_top=(ComponentType.LIVE_TRACKER,),
    ),
    (EventType.CULTURAL_EVENT, EventStatus.DEVELOPING): _recipe(
        EventType.CULTURAL_EVENT, "live", "live-dark", "In progress",
        section_order=(
            ComponentType.LIVE_TRACKER,
            ComponentType.TIMELINE,
            ComponentType.ENTITY_LIST,
            ComponentType.ACTION_LIST,
        ),
        pinned_top=(ComponentType.LIVE_TRACKER,),
    ),
    (EventType.LIVE_EVENT, EventStatus.CONCLUDED): _recipe(
        EventType.LIVE_EVENT, "delta", "editorial", "Wrapped",
        section_order=(
            ComponentType.STAT_GRID,
            ComponentType.TIMELINE,
            ComponentType.ENTITY_LIST,
            ComponentType.ACTION_LIST,
        ),
    ),
    # Cultural events behave like live events but lean editorial.
    (EventType.CULTURAL_EVENT, EventStatus.LIVE): _recipe(
        EventType.CULTURAL_EVENT, "live", "live-dark", "Live now",
        section_order=(
            ComponentType.LIVE_TRACKER,
            ComponentType.TIMELINE,
            ComponentType.ENTITY_LIST,
            ComponentType.ACTION_LIST,
        ),
        pinned_top=(ComponentType.LIVE_TRACKER,),
    ),
    (EventType.CULTURAL_EVENT, EventStatus.UPCOMING): _recipe(
        EventType.CULTURAL_EVENT, "schedule", "editorial", "Coming up",
        section_order=(
            ComponentType.TIMELINE,
            ComponentType.ENTITY_LIST,
            ComponentType.ACTION_LIST,
        ),
    ),
    # Sports tournaments read like a match center. Schedule first, teams
    # next, action list (how to watch) last.
    (EventType.SPORTS_TOURNAMENT, EventStatus.UPCOMING): _recipe(
        EventType.SPORTS_TOURNAMENT, "schedule", "stadium", "Kickoff approaching",
        section_order=(
            ComponentType.STAT_GRID,
            ComponentType.TIMELINE,
            ComponentType.ENTITY_LIST,
            ComponentType.ACTION_LIST,
        ),
    ),
    (EventType.SPORTS_TOURNAMENT, EventStatus.SCHEDULED): _recipe(
        EventType.SPORTS_TOURNAMENT, "schedule", "stadium", "Scheduled",
        section_order=(
            ComponentType.STAT_GRID,
            ComponentType.TIMELINE,
            ComponentType.ENTITY_LIST,
            ComponentType.ACTION_LIST,
        ),
    ),
    (EventType.SPORTS_TOURNAMENT, EventStatus.LIVE): _recipe(
        EventType.SPORTS_TOURNAMENT, "live", "live-dark", "Live now",
        section_order=(
            ComponentType.LIVE_TRACKER,
            ComponentType.TIMELINE,
            ComponentType.ENTITY_LIST,
            ComponentType.STAT_GRID,
            ComponentType.ACTION_LIST,
        ),
        pinned_top=(ComponentType.LIVE_TRACKER,),
    ),
    # Disasters lead with the alert and safety actions.
    (EventType.DISASTER, EventStatus.DEVELOPING): _recipe(
        EventType.DISASTER, "alert", "alert", "Developing",
        section_order=(
            ComponentType.LIVE_TRACKER,
            ComponentType.ACTION_LIST,
            ComponentType.STAT_GRID,
            ComponentType.TIMELINE,
        ),
        pinned_top=(ComponentType.LIVE_TRACKER, ComponentType.ACTION_LIST),
    ),
}

# Fallback recipe per event type when status doesn't match exactly.
_FALLBACK: dict[EventType, PageRecipe] = {
    EventType.TECH_LAUNCH: _RECIPES[(EventType.TECH_LAUNCH, EventStatus.CONCLUDED)],
    EventType.LIVE_EVENT: _RECIPES[(EventType.LIVE_EVENT, EventStatus.UPCOMING)],
    EventType.CULTURAL_EVENT: _RECIPES[(EventType.CULTURAL_EVENT, EventStatus.UPCOMING)],
    EventType.SPORTS_TOURNAMENT: _RECIPES[(EventType.SPORTS_TOURNAMENT, EventStatus.UPCOMING)],
    EventType.DISASTER: _RECIPES[(EventType.DISASTER, EventStatus.DEVELOPING)],
}


def get_recipe(event_type: EventType, status: EventStatus) -> PageRecipe:
    """Return the layout recipe for an event type + status combination.

    Falls back to a per-event-type default when the exact pairing isn't
    in the table. The fallback is intentional — we don't want the page to
    refuse to render because the LLM picked an unusual status.
    """
    return _RECIPES.get((event_type, status)) or _FALLBACK[event_type]
