const requiredStringFields = [
  'slug',
  'inputSentence',
  'eventType',
  'pageTitle',
  'kicker',
  'heroSummary',
  'whatChanged',
  'whyItMatters',
  'lastUpdated',
  'statusLabel'
];

export function normalizeSentence(value) {
  return value
    .toLowerCase()
    .replace(/[“”]/g, '"')
    .replace(/[^a-z0-9]+/g, ' ')
    .trim();
}

export function validateTopicPage(page) {
  for (const field of requiredStringFields) {
    if (!page[field] || typeof page[field] !== 'string') {
      throw new Error(`Topic page is missing required field: ${field}`);
    }
  }

  for (const field of ['keyFacts', 'timeline', 'watchItems', 'entities', 'coverageAngles', 'faq', 'sources']) {
    if (!Array.isArray(page[field]) || page[field].length === 0) {
      throw new Error(`Topic page must include a non-empty ${field} array`);
    }
  }

  return page;
}
