"""Test generalization: classify and generate queries for diverse event types."""
import os, sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv; load_dotenv(ROOT / ".env")

from generator.classify import Stage1A

tests = [
    ("tech", "Apple announced the iPhone 18 Pro at WWDC 2026 on June 8."),
    ("disaster", "A 7.2 magnitude earthquake struck near Tokyo on May 14, 2026."),
    ("sports", "Wimbledon 2026 begins at the All England Club on June 29."),
    ("cultural", "Glastonbury Festival 2026 lineup drops with headliners announced June 25-29."),
    ("corporate", "Tesla reports record Q2 2026 earnings with 45% margin improvement."),
]

stage1a = Stage1A()
today = date(2026, 5, 17)

for category, sentence in tests:
    try:
        h = stage1a.run(sentence, today)
        print(f"[{category}] {sentence}")
        print(f"  Type: {h.preliminary_event_type.value}")
        print(f"  Freshness: {h.freshness_need}")
        print(f"  Queries: {h.search_intents}")
        print()
    except Exception as e:
        print(f"[{category}] {sentence}")
        print(f"  ERROR: {e}")
        print()
