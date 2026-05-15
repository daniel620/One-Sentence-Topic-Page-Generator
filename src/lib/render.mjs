function escapeHtml(value) {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function eventTypeLabel(eventType) {
  return {
    sports: 'Tournament snapshot',
    culture: 'Culture desk brief',
    tech: 'Launch tracker'
  }[eventType] || 'Live topic file';
}

function watchHeading(eventType) {
  return {
    sports: 'What to watch before kickoff',
    culture: 'What to watch through the week',
    tech: 'What to watch in the rollout'
  }[eventType] || 'What to watch next';
}

export function renderTopicPage(page) {
  const facts = page.keyFacts
    .map((fact) => `<div class="fact"><dt>${escapeHtml(fact.label)}</dt><dd>${escapeHtml(fact.value)}</dd></div>`)
    .join('');

  const timeline = page.timeline
    .map((item) => `<li><span>${escapeHtml(item.date)}</span><div><strong>${escapeHtml(item.title)}</strong><p>${escapeHtml(item.description)}</p></div></li>`)
    .join('');

  const watchItems = page.watchItems
    .map((item) => `<article class="mini-card"><h3>${escapeHtml(item.title)}</h3><p>${escapeHtml(item.description)}</p></article>`)
    .join('');

  const entities = page.entities
    .map((entity) => `<li><strong>${escapeHtml(entity.name)}</strong><span>${escapeHtml(entity.role)}</span><p>${escapeHtml(entity.detail)}</p></li>`)
    .join('');

  const angles = page.coverageAngles
    .map((angle) => `<article class="mini-card"><h3>${escapeHtml(angle.title)}</h3><p>${escapeHtml(angle.description)}</p></article>`)
    .join('');

  const faq = page.faq
    .map((item) => `<details><summary>${escapeHtml(item.question)}</summary><p>${escapeHtml(item.answer)}</p></details>`)
    .join('');

  const sources = page.sources
    .map((source) => `<li><a href="${escapeHtml(source.url)}">${escapeHtml(source.label)}</a><span>${escapeHtml(source.note)}</span></li>`)
    .join('');

  return `<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>${escapeHtml(page.pageTitle)} · Topic page</title>
    <style>
      :root {
        --bg: #f5f2eb;
        --paper: rgba(255,255,255,0.72);
        --ink: #14213d;
        --muted: #5c6474;
        --accent: #d97706;
        --line: rgba(20,33,61,0.12);
        --shadow: 0 24px 80px rgba(20,33,61,0.12);
      }
      * { box-sizing: border-box; }
      body {
        margin: 0;
        font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        background: radial-gradient(circle at top, #fff8e8 0, #f5f2eb 52%, #efeae0 100%);
        color: var(--ink);
      }
      a { color: inherit; }
      .shell {
        width: min(1200px, calc(100% - 32px));
        margin: 0 auto;
        padding: 32px 0 56px;
      }
      .hero {
        display: grid;
        grid-template-columns: 2fr 1fr;
        gap: 24px;
        padding: 28px;
        border: 1px solid var(--line);
        border-radius: 28px;
        background: linear-gradient(140deg, rgba(255,255,255,0.88), rgba(255,248,232,0.8));
        box-shadow: var(--shadow);
      }
      .eyebrow, .status-pill {
        display: inline-flex;
        align-items: center;
        gap: 8px;
        font-size: 0.82rem;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        color: var(--muted);
      }
      .status-pill {
        margin-top: 16px;
        padding: 10px 14px;
        border-radius: 999px;
        background: rgba(217,119,6,0.12);
        color: #9a3412;
      }
      h1 {
        margin: 14px 0 12px;
        font-size: clamp(2.4rem, 4vw, 4.8rem);
        line-height: 0.96;
        max-width: 14ch;
      }
      .summary, .prose p, details p, .mini-card p, .entity-list p, .timeline p, .source-list span {
        color: var(--muted);
        line-height: 1.6;
      }
      .hero-side {
        display: grid;
        gap: 16px;
        align-content: start;
      }
      .card {
        padding: 20px;
        border-radius: 22px;
        background: var(--paper);
        border: 1px solid rgba(20,33,61,0.08);
        backdrop-filter: blur(14px);
      }
      dl { margin: 0; display: grid; gap: 14px; }
      .fact dt {
        font-size: 0.76rem;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: var(--muted);
        margin-bottom: 4px;
      }
      .fact dd {
        margin: 0;
        font-size: 1.08rem;
        font-weight: 700;
      }
      .grid {
        display: grid;
        grid-template-columns: 1.15fr 0.85fr;
        gap: 24px;
        margin-top: 24px;
      }
      .stack { display: grid; gap: 24px; }
      .section-title {
        margin: 0 0 18px;
        font-size: 1.3rem;
      }
      .timeline {
        list-style: none;
        margin: 0;
        padding: 0;
        display: grid;
        gap: 18px;
      }
      .timeline li {
        display: grid;
        grid-template-columns: 120px 1fr;
        gap: 14px;
        padding-top: 18px;
        border-top: 1px solid var(--line);
      }
      .timeline li:first-child { padding-top: 0; border-top: 0; }
      .timeline span, .entity-list span {
        display: block;
        color: var(--accent);
        font-size: 0.85rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.06em;
      }
      .mini-grid {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 16px;
      }
      .mini-card {
        padding: 18px;
        border-radius: 18px;
        background: rgba(255,255,255,0.74);
        border: 1px solid var(--line);
      }
      .mini-card h3 { margin: 0 0 10px; font-size: 1rem; }
      .entity-list, .source-list {
        list-style: none;
        padding: 0;
        margin: 0;
        display: grid;
        gap: 14px;
      }
      .entity-list li, .source-list li {
        padding-top: 14px;
        border-top: 1px solid var(--line);
      }
      .entity-list li:first-child, .source-list li:first-child { border-top: 0; padding-top: 0; }
      details {
        border-top: 1px solid var(--line);
        padding: 16px 0;
      }
      details:first-of-type { padding-top: 0; border-top: 0; }
      summary {
        cursor: pointer;
        font-weight: 700;
      }
      .footer-note {
        margin-top: 24px;
        font-size: 0.92rem;
        color: var(--muted);
      }
      @media (max-width: 900px) {
        .hero, .grid, .timeline li { grid-template-columns: 1fr; }
        .mini-grid { grid-template-columns: 1fr; }
      }
    </style>
  </head>
  <body>
    <main class="shell">
      <section class="hero">
        <div>
          <div class="eyebrow">${escapeHtml(eventTypeLabel(page.eventType))} · ${escapeHtml(page.kicker)}</div>
          <h1>${escapeHtml(page.pageTitle)}</h1>
          <p class="summary">${escapeHtml(page.heroSummary)}</p>
          <div class="status-pill">${escapeHtml(page.statusLabel)}</div>
        </div>
        <aside class="hero-side">
          <section class="card">
            <h2 class="section-title">Key facts</h2>
            <dl>${facts}</dl>
          </section>
          <section class="card prose">
            <h2 class="section-title">Why this page exists</h2>
            <p>${escapeHtml(page.whatChanged)}</p>
            <p>${escapeHtml(page.whyItMatters)}</p>
          </section>
        </aside>
      </section>

      <section class="grid">
        <div class="stack">
          <section class="card">
            <h2 class="section-title">Live timeline</h2>
            <ol class="timeline">${timeline}</ol>
          </section>
          <section class="card">
            <h2 class="section-title">Coverage angles</h2>
            <div class="mini-grid">${angles}</div>
          </section>
        </div>
        <div class="stack">
          <section class="card">
            <h2 class="section-title">${escapeHtml(watchHeading(page.eventType))}</h2>
            <div class="mini-grid">${watchItems}</div>
          </section>
          <section class="card">
            <h2 class="section-title">Key players</h2>
            <ul class="entity-list">${entities}</ul>
          </section>
          <section class="card">
            <h2 class="section-title">FAQ</h2>
            ${faq}
          </section>
          <section class="card">
            <h2 class="section-title">Sources</h2>
            <ul class="source-list">${sources}</ul>
            <p class="footer-note">Research snapshot updated ${escapeHtml(page.lastUpdated)}. The renderer is deterministic; source gathering and structured synthesis happen before this HTML is produced.</p>
          </section>
        </div>
      </section>
    </main>
  </body>
</html>`;
}
