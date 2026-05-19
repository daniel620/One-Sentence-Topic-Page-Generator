"""Hot event topic page generator package."""

from generator.orchestrator import run_pipeline
from generator.render import render_topic_page

__all__ = ["run_pipeline", "render_topic_page"]
