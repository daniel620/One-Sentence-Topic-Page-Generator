import test from 'node:test';
import assert from 'node:assert/strict';
import { getExampleByInput, getExampleBySlug } from '../src/lib/examples.mjs';
import { renderTopicPage } from '../src/lib/render.mjs';

test('bundled examples are retrievable by exact sentence', () => {
  const page = getExampleByInput('Nintendo Switch 2 launches worldwide on June 5, 2025.');
  assert.ok(page);
  assert.equal(page.slug, 'nintendo-switch-2-launch');
});

test('renderer emits recognizable headline, timeline and source sections', () => {
  const page = getExampleBySlug('fifa-world-cup-2026');
  const html = renderTopicPage(page);

  assert.match(html, /2026 FIFA World Cup/);
  assert.match(html, /Live timeline/);
  assert.match(html, /Sources/);
  assert.match(html, /Estadio Azteca/);
});
