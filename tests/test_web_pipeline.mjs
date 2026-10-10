// Full snapshot reader -> refresh loader -> session contract using real Web Responses.
// Synthetic fixtures only; successful reads do not verify provider provenance.
import test from 'node:test';
import assert from 'node:assert/strict';
import {createSnapshotReader} from '../web/snapshot-reader.mjs';
import {createDirectoryLoader} from '../web/directory-loader.mjs';
import {createDirectorySession} from '../web/directory-session.mjs';

const at = Date.parse('2026-10-09T12:00:00Z');
function snapshot(time = at) {
  const date = new Date(time).toISOString();
  return {schema_version: 1, generated_at: date, resources: [{
    id: 'fixture', name: 'Synthetic fixture é', category: 'meal', address: 'Test address',
    latitude: 0, longitude: 0, source_name: 'Test fixture',
    source_url: 'https://example.com/', verified_at: date,
    availability: 'available', open_now: true, hours: {0: [['00:00', '24:00']]},
  }]};
}
function response(data) {
  return new Response(JSON.stringify(data), {headers: {'Content-Type': 'application/json'}});
}
function pipeline(fetchImpl, readerOptions = {}) {
  let now = at;
  const session = createDirectorySession(() => now);
  const reader = createSnapshotReader('/directory.json', {
    origin: 'https://example.com', fetchImpl, ...readerOptions,
  });
  const loader = createDirectoryLoader(session, reader);
  session.search({latitude: 0, longitude: 0});
  return {session, loader, setTime(value) { now = value; }};
}
function unavailable(state) {
  assert.equal(state.status, 'unavailable');
  assert.equal(state.results.length, 0);
  assert.match(state.notice, /211.*911/);
}

test('real JSON response reaches ranked results but injected live claims do not', async () => {
  const {loader} = pipeline(async () => response(snapshot()));
  const state = await loader.refresh();
  assert.equal(state.status, 'results');
  assert.equal(state.results[0].resource.name, 'Synthetic fixture é');
  assert.equal(state.results[0].distanceMiles, 0);
  for (const field of ['availability', 'open_now', 'hours']) {
    assert.equal(field in state.results[0].resource, false);
  }
});

test('real streamed response preserves split UTF-8 and validates complete JSON', async () => {
  const bytes = new TextEncoder().encode(JSON.stringify(snapshot()));
  const stream = new ReadableStream({start(controller) {
    for (let i = 0; i < bytes.length; i++) controller.enqueue(bytes.slice(i, i + 1));
    controller.close();
  }});
  const {loader} = pipeline(async () => new Response(stream,
    {headers: {'Content-Type': 'application/json; charset=utf-8'}}));
  assert.equal((await loader.refresh()).results[0].resource.name, 'Synthetic fixture é');
});

for (const [name, getResponse] of [
  ['stale JSON', () => response(snapshot(at - 86400001))],
  ['HTTP failure', () => new Response('unavailable', {status: 503})],
  ['HTML error with HTTP 200', () => new Response('<html>Error</html>',
    {headers: {'Content-Type': 'text/html'}})],
  ['truncated JSON', () => new Response('{"resources":',
    {headers: {'Content-Type': 'application/json'}})],
  ['invalid schema', () => response({schema_version: 99})],
]) {
  test(`${name} fails closed through the full pipeline after prior success`, async () => {
    let fail = false;
    const {session, loader} = pipeline(async () => fail ? getResponse() : response(snapshot()));
    assert.equal((await loader.refresh()).status, 'results');
    fail = true; unavailable(await loader.refresh()); unavailable(session.getState());
  });
}

test('byte cap clears existing results through real Response streaming', async () => {
  let large = false;
  const data = snapshot();
  const length = new TextEncoder().encode(JSON.stringify(data)).length;
  const {loader} = pipeline(async () => response(large
    ? {...data, padding: 'x'.repeat(100)} : data), {maxBytes: length});
  assert.equal((await loader.refresh()).status, 'results');
  large = true; unavailable(await loader.refresh());
});

test('timeout clears previous results without waiting for an uncooperative fetch', async () => {
  let stalled = false;
  const {loader} = pipeline(() => stalled ? new Promise(() => {}) : response(snapshot()),
    {timeoutMs: 10});
  assert.equal((await loader.refresh()).status, 'results');
  stalled = true; unavailable(await loader.refresh());
});

test('expiry after successful network read clears results without another fetch', async () => {
  let calls = 0;
  const {session, loader, setTime} = pipeline(async () => { calls++; return response(snapshot()); });
  await loader.refresh(); setTime(at + 86400001);
  assert.equal(session.getState().status, 'refresh_required');
  assert.equal(session.getState().results.length, 0); assert.equal(calls, 1);
});
