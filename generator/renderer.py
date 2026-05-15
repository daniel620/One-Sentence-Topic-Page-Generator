from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from generator.schemas import ComponentType, TopicPageData

TEMPLATE_NAME = "dynamic_topic_page.html.j2"

COMPONENT_TEMPLATE_BY_TYPE = {
    ComponentType.STAT_GRID: "components/stat_grid.html.j2",
    ComponentType.COMPARISON_TABLE: "components/comparison_table.html.j2",
    ComponentType.LIVE_TRACKER: "components/live_tracker.html.j2",
    ComponentType.ACTION_LIST: "components/action_list.html.j2",
    ComponentType.TIMELINE: "components/timeline_component.html.j2",
    ComponentType.ENTITY_LIST: "components/entity_list.html.j2",
    ComponentType.SOURCE_LIST: "components/source_list.html.j2",
}


def render_topic_page(data: TopicPageData, template_dir: Path | None = None) -> str:
    if template_dir is None:
        template_dir = Path(__file__).resolve().parent.parent / "templates"

    env = Environment(
        loader=FileSystemLoader(str(template_dir)),
        autoescape=select_autoescape(["html", "xml"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    template = env.get_template(TEMPLATE_NAME)

    return template.render(
        page=data,
        component_template_by_type=COMPONENT_TEMPLATE_BY_TYPE,
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    )
