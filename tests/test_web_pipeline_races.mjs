// Cancellation/race coverage across actual Response bodies, not stub readers.
import test from 'node:test';
import assert from 'node:assert/strict';
import {createSnapshotReader} from '../web/snapshot-reader.mjs';
import {createDirectoryLoader} from '../web/directory-loader.mjs';
import {createDirectorySession} from '../web/directory-session.mjs';

const now = Date.parse('2026-10-10T12:00:00Z');
function response(id) {
  const time = new Date(now).toISOString();
  return new Response(JSON.stringify({schema_version: 1, generated_at: time, resources: [{
    id, name: 'Synthetic fixture', category: 'meal', address: 'Test address',
    latitude: 0, longitude: 0, source_name: 'Test fixture',
    source_url: 'https://example.com/', verified_at: time,
  }]}), {headers: {'Content-Type': 'application/json'}});
}
function setup() {
  const requests = [];
  const session = createDirectorySession(() => now);
  session.search({latitude: 0, longitude: 0});
  const reader = createSnapshotReader('/directory.json', {origin: 'https://example.com',
    fetchImpl: (_url, {signal}) => new Promise((resolve, reject) => {
      requests.push({signal, resolve, reject});
    })});
  return {session, requests, loader: createDirectoryLoader(session, reader)};
}
function safeEmpty(state, status) {
  assert.equal(state.status, status); assert.equal(state.results.length, 0);
  assert.match(state.notice, /211.*911/);
}

test('superseding a pending real fetch settles old request before fetch responds', async () => {
  const {session, loader, requests} = setup();
  const old = loader.refresh(); const recent = loader.refresh();
  assert.equal(requests[0].signal.aborted, true);
  safeEmpty(await old, 'loading');
  requests[1].resolve(response('new')); await recent;
  requests[0].resolve(response('old')); await Promise.resolve();
  assert.equal(session.getState().results[0].resource.id, 'new');
});

test('cancel during a real body stream cancels it and does not resurrect results', async () => {
  let bodyController, canceled = false;
  const body = new ReadableStream({start(controller) { bodyController = controller; },
    cancel() { canceled = true; }});
  const session = createDirectorySession(() => now);
  const reader = createSnapshotReader('/data', {origin: 'https://example.com',
    fetchImpl: async () => new Response(body, {headers: {'Content-Type': 'application/json'}})});
  const loader = createDirectoryLoader(session, reader);
  const pending = loader.refresh();
  // Let fetch resolve and acquire its stream reader before cancellation.
  await new Promise(resolve => setImmediate(resolve));
  bodyController.enqueue(new TextEncoder().encode('{"schema_version":'));
  loader.cancel(); safeEmpty(await pending, 'unavailable');
  assert.equal(canceled, true); safeEmpty(session.getState(), 'unavailable');
});

test('disposing while fetch ignores abort settles and prevents later read attempts', async () => {
  const {session, loader, requests} = setup(); const pending = loader.refresh();
  loader.dispose(); safeEmpty(await pending, 'unavailable');
  requests[0].resolve(response('late')); await Promise.resolve();
  safeEmpty(await loader.refresh(), 'unavailable');
  assert.equal(requests.length, 1); safeEmpty(session.getState(), 'unavailable');
});

test('late rejected fetch cannot clear data from the replacement request', async () => {
  const {session, loader, requests} = setup();
  const old = loader.refresh(); const recent = loader.refresh(); await old;
  requests[1].resolve(response('current')); await recent;
  requests[0].reject(new Error('late old transport failure'));
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(session.getState().results[0].resource.id, 'current');
});

test('newer HTTP failure stays unavailable after late old valid Response', async () => {
  const {session, loader, requests} = setup();
  const old = loader.refresh(); const recent = loader.refresh(); await old;
  requests[1].resolve(new Response('offline', {status: 503}));
  safeEmpty(await recent, 'unavailable');
  requests[0].resolve(response('old')); await new Promise(resolve => setImmediate(resolve));
  safeEmpty(session.getState(), 'unavailable');
});
