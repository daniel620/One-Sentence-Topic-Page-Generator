"""Hot event topic page generator package."""

from generator.pipeline import run_pipeline
from generator.renderer import render_topic_page

__all__ = ["run_pipeline", "render_topic_page"]
