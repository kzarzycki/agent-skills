import { mkdir, writeFile } from 'node:fs/promises';
import { join } from 'node:path';
import { ERROR_CODES, makeError } from './schema.js';

const HUMAN_NAME = /^[0-9]{2}-[A-Z0-9-]+\.md$/;
const SAFE_NAME = /^[A-Za-z0-9._-]+$/;

function assertSafeSegment(value, label) {
  if (
    typeof value !== 'string' ||
    value.length === 0 ||
    value === '.' ||
    value === '..' ||
    value.includes('..') ||
    value.includes('/') ||
    value.includes('\\') ||
    !SAFE_NAME.test(value)
  ) {
    throw makeError(ERROR_CODES.INVALID_ARTIFACT_PATH, `${label} is not a safe path segment: ${value}`);
  }
}

function assertHumanName(name) {
  assertSafeSegment(name, 'human artifact name');
  if (!HUMAN_NAME.test(name)) {
    throw makeError(ERROR_CODES.INVALID_ARTIFACT_PATH, `human artifact must be NN-NAME.md: ${name}`);
  }
}

export function createWorkItemPaths({ baseDir = '.workflow', workId }) {
  assertSafeSegment(workId, 'workId');
  const root = join(baseDir, workId);
  return {
    root,
    stateDir: join(root, '_state'),
    phasesDir: join(root, '_phases'),
    reviewsDir: join(root, '_reviews'),
    evidenceDir: join(root, '_evidence'),
    stateFile: join(root, '_state', 'state.json'),
  };
}

export async function ensureWorkItem(paths) {
  await mkdir(paths.stateDir, { recursive: true });
  await mkdir(paths.phasesDir, { recursive: true });
  await mkdir(paths.reviewsDir, { recursive: true });
  await mkdir(paths.evidenceDir, { recursive: true });
}

export async function writeHumanArtifact(paths, { ordinal, slug, content, overwrite = false }) {
  assertSafeSegment(ordinal, 'ordinal');
  assertSafeSegment(slug, 'slug');
  const name = `${ordinal}-${slug}.md`;
  assertHumanName(name);
  const path = join(paths.root, name);
  await mkdir(paths.root, { recursive: true });
  await writeFile(path, content, { encoding: 'utf8', flag: overwrite ? 'w' : 'wx' });
  return path;
}

export async function writePhaseInternal(paths, { phase, filename, content }) {
  assertSafeSegment(phase, 'phase');
  assertSafeSegment(filename, 'filename');
  const dir = join(paths.phasesDir, phase);
  await mkdir(dir, { recursive: true });
  const path = join(dir, filename);
  await writeFile(path, content, 'utf8');
  return path;
}

export async function writeReviewInternal(paths, { phase, reviewer, content }) {
  assertSafeSegment(phase, 'phase');
  assertSafeSegment(reviewer, 'reviewer');
  const dir = join(paths.reviewsDir, phase);
  await mkdir(dir, { recursive: true });
  const path = join(dir, `${reviewer}.md`);
  await writeFile(path, content, 'utf8');
  return path;
}
