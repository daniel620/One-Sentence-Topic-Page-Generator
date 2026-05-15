import { validateTopicPage } from './schema.mjs';

function stripHtml(html) {
  return html
    .replace(/<script[\s\S]*?<\/script>/gi, ' ')
    .replace(/<style[\s\S]*?<\/style>/gi, ' ')
    .replace(/<[^>]+>/g, ' ')
    .replace(/&nbsp;/g, ' ')
    .replace(/&amp;/g, '&')
    .replace(/\s+/g, ' ')
    .trim();
}

function absoluteUrl(href) {
  try {
    return new URL(href).toString();
  } catch {
    return null;
  }
}

export async function searchWeb(query, options = {}) {
  const endpoint = process.env.SEARCH_ENDPOINT || 'https://duckduckgo.com/html/';
  const limit = Number(process.env.SEARCH_RESULT_LIMIT || options.limit || 5);
  const response = await fetch(`${endpoint}?q=${encodeURIComponent(query)}`, {
    headers: {
      'user-agent': 'Mozilla/5.0 (compatible; TopicPageGenerator/1.0)'
    }
  });

  if (!response.ok) {
    throw new Error(`Search request failed with ${response.status}`);
  }

  const html = await response.text();
  const matches = [...html.matchAll(/<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>([\s\S]*?)<\/a>/gi)].slice(0, limit);
  return matches
    .map((match) => ({
      url: absoluteUrl(match[1]),
      title: stripHtml(match[2])
    }))
    .filter((item) => item.url);
}

export async function fetchDocument(url) {
  const timeoutMs = Number(process.env.FETCH_TIMEOUT_MS || 15000);
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const response = await fetch(url, {
      headers: {
        'user-agent': 'Mozilla/5.0 (compatible; TopicPageGenerator/1.0)'
      },
      signal: controller.signal
    });

    if (!response.ok) {
      throw new Error(`Fetch failed for ${url} with ${response.status}`);
    }

    const html = await response.text();
    return stripHtml(html).slice(0, 6000);
  } finally {
    clearTimeout(timeout);
  }
}

function topicPageSchema() {
  return {
    name: 'topic_page',
    schema: {
      type: 'object',
      additionalProperties: false,
      required: ['slug', 'inputSentence', 'eventType', 'pageTitle', 'kicker', 'heroSummary', 'whatChanged', 'whyItMatters', 'lastUpdated', 'statusLabel', 'keyFacts', 'timeline', 'watchItems', 'entities', 'coverageAngles', 'faq', 'sources'],
      properties: {
        slug: { type: 'string' },
        inputSentence: { type: 'string' },
        eventType: { type: 'string' },
        pageTitle: { type: 'string' },
        kicker: { type: 'string' },
        heroSummary: { type: 'string' },
        whatChanged: { type: 'string' },
        whyItMatters: { type: 'string' },
        lastUpdated: { type: 'string' },
        statusLabel: { type: 'string' },
        keyFacts: { type: 'array', items: { type: 'object', additionalProperties: false, required: ['label', 'value'], properties: { label: { type: 'string' }, value: { type: 'string' } } } },
        timeline: { type: 'array', items: { type: 'object', additionalProperties: false, required: ['date', 'title', 'description'], properties: { date: { type: 'string' }, title: { type: 'string' }, description: { type: 'string' } } } },
        watchItems: { type: 'array', items: { type: 'object', additionalProperties: false, required: ['title', 'description'], properties: { title: { type: 'string' }, description: { type: 'string' } } } },
        entities: { type: 'array', items: { type: 'object', additionalProperties: false, required: ['name', 'role', 'detail'], properties: { name: { type: 'string' }, role: { type: 'string' }, detail: { type: 'string' } } } },
        coverageAngles: { type: 'array', items: { type: 'object', additionalProperties: false, required: ['title', 'description'], properties: { title: { type: 'string' }, description: { type: 'string' } } } },
        faq: { type: 'array', items: { type: 'object', additionalProperties: false, required: ['question', 'answer'], properties: { question: { type: 'string' }, answer: { type: 'string' } } } },
        sources: { type: 'array', items: { type: 'object', additionalProperties: false, required: ['label', 'url', 'note'], properties: { label: { type: 'string' }, url: { type: 'string' }, note: { type: 'string' } } } }
      }
    }
  };
}

export async function buildTopicPageWithOpenAI(inputSentence) {
  const apiKey = process.env.OPENAI_API_KEY;
  if (!apiKey) {
    throw new Error('OPENAI_API_KEY is required for live generation from a new sentence.');
  }

  const searchResults = await searchWeb(inputSentence);
  const documents = await Promise.all(searchResults.map(async (result) => ({
    ...result,
    text: await fetchDocument(result.url)
  })));

  const prompt = [
    'You are building a newsroom-quality topic page data model.',
    'Infer the event type, keep every claim grounded in the supplied sources, and prefer official sources when sources conflict.',
    'Return only JSON that matches the provided schema.',
    '',
    `INPUT SENTENCE: ${inputSentence}`,
    '',
    'SOURCE DOSSIER:'
  ];

  documents.forEach((document, index) => {
    prompt.push(`${index + 1}. ${document.title}`);
    prompt.push(document.url);
    prompt.push(document.text);
    prompt.push('');
  });

  const response = await fetch('https://api.openai.com/v1/chat/completions', {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      authorization: `Bearer ${apiKey}`
    },
    body: JSON.stringify({
      model: process.env.OPENAI_MODEL || 'gpt-4.1-mini',
      temperature: 0.2,
      messages: [
        { role: 'system', content: 'Produce concise, citation-ready structured data for a topic page.' },
        { role: 'user', content: prompt.join('\n') }
      ],
      response_format: {
        type: 'json_schema',
        json_schema: {
          name: topicPageSchema().name,
          strict: true,
          schema: topicPageSchema().schema
        }
      }
    })
  });

  if (!response.ok) {
    const failure = await response.text();
    throw new Error(`OpenAI request failed with ${response.status}: ${failure}`);
  }

  const payload = await response.json();
  const content = payload.choices?.[0]?.message?.content;
  const parsed = JSON.parse(content);
  return validateTopicPage(parsed);
}
