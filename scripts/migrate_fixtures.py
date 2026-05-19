"""Migrate fixture JSONs from old typed claim format to unified Claim model.

The old format had type-specific fields (value, unit, date_value, etc.)
at the top level of each claim object. The new format stores these in
a claim_attributes dict.
"""
import json
import glob
import sys

METRIC_FIELDS = {'value', 'unit', 'direction', 'base_value_if_delta', 'evidence_snippet'}
STATUS_FIELDS = {'status', 'observed_at', 'source_evidence'}
SCHEDULE_FIELDS = {'event_datetime', 'timezone', 'event_name'}
DATE_FIELDS = {'date_value'}
LOCATION_FIELDS = {'location'}
ENTITY_FIELDS = {'entity_name', 'entity_role'}

ALL_TYPED = METRIC_FIELDS | STATUS_FIELDS | SCHEDULE_FIELDS | DATE_FIELDS | LOCATION_FIELDS | ENTITY_FIELDS

for fp in sorted(glob.glob('tests/fixtures/*.json')):
    fx = json.load(open(fp))
    g = fx.get('evidence_graph', {})
    changed = False
    for c in g.get('claims', []):
        attrs = {}
        for field in ALL_TYPED:
            if field in c:
                attrs[field] = c.pop(field)
        if attrs:
            c['claim_attributes'] = attrs
            changed = True
    if changed:
        with open(fp, 'w') as f:
            json.dump(fx, f, indent=2, ensure_ascii=False, default=str)
        print(f'Migrated: {fp}')
    else:
        print(f'No changes needed: {fp}')
