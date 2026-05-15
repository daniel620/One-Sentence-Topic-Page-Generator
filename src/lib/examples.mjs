import { readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { normalizeSentence, validateTopicPage } from './schema.mjs';

const examplesDirectory = new URL('../../data/examples/', import.meta.url);

function readExamples() {
  return readdirSync(examplesDirectory)
    .filter((file) => file.endsWith('.json'))
    .map((file) => {
      const contents = readFileSync(join(examplesDirectory.pathname, file), 'utf8');
      return validateTopicPage(JSON.parse(contents));
    });
}

let cachedExamples;

export function getExamples() {
  cachedExamples ??= readExamples();
  return cachedExamples;
}

export function getExampleBySlug(slug) {
  return getExamples().find((example) => example.slug === slug) ?? null;
}

export function getExampleByInput(inputSentence) {
  const normalized = normalizeSentence(inputSentence);
  return getExamples().find((example) => normalizeSentence(example.inputSentence) === normalized) ?? null;
}
