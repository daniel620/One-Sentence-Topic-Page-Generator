import { mkdirSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { loadEnvFile } from './lib/env.mjs';
import { getExampleByInput, getExampleBySlug, getExamples } from './lib/examples.mjs';
import { buildTopicPageWithOpenAI } from './lib/live-research.mjs';
import { renderTopicPage } from './lib/render.mjs';

loadEnvFile();

function parseArgs(argv) {
  const args = {};
  for (let index = 0; index < argv.length; index += 1) {
    const token = argv[index];
    if (!token.startsWith('--')) continue;
    const key = token.slice(2);
    const next = argv[index + 1];
    if (!next || next.startsWith('--')) {
      args[key] = true;
      continue;
    }
    args[key] = next;
    index += 1;
  }
  return args;
}

function writePage(page, outputPath) {
  mkdirSync(dirname(outputPath), { recursive: true });
  writeFileSync(outputPath, renderTopicPage(page), 'utf8');
  return outputPath;
}

async function resolveTopicPage(args) {
  if (args['from-example']) {
    const example = getExampleBySlug(args['from-example']);
    if (!example) throw new Error(`Unknown example slug: ${args['from-example']}`);
    return example;
  }

  if (!args.input) {
    throw new Error('Provide --input, --from-example, or --all-examples.');
  }

  const bundledExample = getExampleByInput(args.input);
  if (bundledExample) {
    return bundledExample;
  }

  return buildTopicPageWithOpenAI(args.input);
}

async function main() {
  const args = parseArgs(process.argv.slice(2));

  if (args['all-examples']) {
    const outputs = getExamples().map((example) => {
      const target = resolve('dist', `${example.slug}.html`);
      return writePage(example, target);
    });
    outputs.forEach((output) => console.log(`Generated ${output}`));
    return;
  }

  const page = await resolveTopicPage(args);
  const outputPath = resolve(args.output || `dist/${page.slug}.html`);
  writePage(page, outputPath);
  console.log(`Generated ${outputPath}`);
}

main().catch((error) => {
  console.error(error.message);
  process.exitCode = 1;
});
