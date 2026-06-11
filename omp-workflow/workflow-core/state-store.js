import { mkdir, open, readFile, rename, unlink, writeFile } from 'node:fs/promises';
import { dirname } from 'node:path';
import { validateState, ERROR_CODES, makeError } from './schema.js';

async function readJsonIfExists(path) {
  try {
    const text = await readFile(path, 'utf8');
    return JSON.parse(text);
  } catch (error) {
    if (error?.code === 'ENOENT') return null;
    throw error;
  }
}

async function acquireLock(lockPath) {
  try {
    const handle = await open(lockPath, 'wx');
    await handle.close();
    return async () => {
      await unlink(lockPath).catch(() => {});
    };
  } catch (error) {
    if (error?.code === 'EEXIST') {
      throw makeError(ERROR_CODES.STALE_STATE_REVISION, 'state write already in progress');
    }
    throw error;
  }
}

export async function loadState(statePath) {
  const state = await readJsonIfExists(statePath);
  if (state === null) {
    throw makeError(ERROR_CODES.INVALID_STATE_SCHEMA, `state file not found: ${statePath}`);
  }
  return validateState(state);
}

export async function saveState(statePath, nextState, { expectedRevision }) {
  await mkdir(dirname(statePath), { recursive: true });
  const release = await acquireLock(`${statePath}.lock`);
  try {
    const current = await readJsonIfExists(statePath);
    if (current === null) {
      if (expectedRevision !== null) {
        throw makeError(ERROR_CODES.STALE_STATE_REVISION, 'state file does not exist');
      }
    } else {
      validateState(current);
      if (current.revision !== expectedRevision) {
        throw makeError(
          ERROR_CODES.STALE_STATE_REVISION,
          `expected revision ${expectedRevision}, found ${current.revision}`,
        );
      }
    }

    const stateToWrite = validateState({
      ...nextState,
      revision: current === null ? 0 : current.revision + 1,
    });

    const tmpPath = `${statePath}.tmp-${process.pid}-${Date.now()}`;
    await writeFile(tmpPath, `${JSON.stringify(stateToWrite, null, 2)}\n`, 'utf8');
    await rename(tmpPath, statePath);
    return stateToWrite;
  } finally {
    await release();
  }
}
