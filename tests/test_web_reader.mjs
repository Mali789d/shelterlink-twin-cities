import test from 'node:test';
import assert from 'node:assert/strict';
import {createSnapshotReader} from '../web/snapshot-reader.mjs';
import {createDirectorySession} from '../web/directory-session.mjs';
import {createDirectoryLoader} from '../web/directory-loader.mjs';
const origin = 'https://example.com';
const encode = text => new TextEncoder().encode(text);
function response(chunks = [encode('{"resources":[]}')], headers = {}, extra = {}) {
  let canceled = false;
  return {ok: true, redirected: false,
    headers: new Headers({'Content-Type': 'application/json', ...headers}),
    body: {getReader: () => ({read: async () => chunks.length
      ? {value: chunks.shift(), done: false} : {done: true},
      cancel: () => { canceled = true; },})},
    wasCanceled: () => canceled, ...extra};
}
function reader(fetchImpl, options = {}) {
  return createSnapshotReader('/directory.json', {origin, fetchImpl, ...options});
}

test('same-origin read uses no credentials, redirect, cache or polling', async () => {
  let calls = 0;
  const read = reader(async (url, options) => {
    calls++; assert.equal(url, 'https://example.com/directory.json');
    assert.equal(options.credentials, 'omit'); assert.equal(options.redirect, 'error');
    assert.equal(options.cache, 'no-store'); assert.equal(options.headers.Accept, 'application/json');
    return response();
  });
  assert.deepEqual(await read(), {resources: []}); assert.equal(calls, 1);
});
for (const url of ['https://other.example/directory.json', 'javascript:alert(1)',
  'https://user:password@example.com/data', '/data#fragment']) {
  test(`reject unsafe snapshot target ${url}`, () => {
    assert.throws(() => createSnapshotReader(url, {origin}));
  });
}
for (const options of [{maxBytes: 0}, {maxBytes: 1048577}, {maxBytes: 1.5},
  {timeoutMs: 0}, {timeoutMs: 60001}, {fetchImpl: null}]) {
  test(`reject reader limits ${JSON.stringify(options)}`, () => {
    assert.throws(() => createSnapshotReader('/data', {origin, ...options}));
  });
}
test('byte cap includes all streamed chunks even without content length', async () => {
  const res = response([encode('{}'), encode(' ')]);
  await assert.rejects(reader(async () => res, {maxBytes: 2})(), /limit/);
  assert.equal(res.wasCanceled(), true);
});
test('exact byte boundary succeeds and split UTF-8 decodes correctly', async () => {
  assert.deepEqual(await reader(async () => response([encode('{}')]), {maxBytes: 2})(), {});
  const bytes = encode('{"name":"é"}');
  const parsed = await reader(async () => response([bytes.slice(0, 10), bytes.slice(10)]))();
  assert.equal(parsed.name, 'é');
});
for (const res of [response([], {'Content-Length': '9999999'}),
  response([], {'Content-Length': 'garbage'}), response([], {'Content-Type': 'text/html'}),
  response([], {}, {ok: false}), response([], {}, {redirected: true}),
  response([], {}, {body: null}), response([new Uint8Array([255])]),
  response([encode('not json')])]) {
  test('reject invalid response without returning a snapshot', async () => {
    await assert.rejects(reader(async () => res)());
  });
}
test('timeout settles even when fetch ignores abort', async () => {
  let signal;
  const read = reader((_url, options) => { signal = options.signal; return new Promise(() => {}); },
    {timeoutMs: 10});
  await assert.rejects(read(), /timed out/); assert.equal(signal.aborted, true);
});
test('timeout also settles while body reader is stalled', async () => {
  const read = reader(async () => response([], {}, {body: {getReader: () => ({
    read: () => new Promise(() => {}), cancel: () => {},
  })}}), {timeoutMs: 10});
  await assert.rejects(read(), /timed out/);
});
test('external cancellation settles even when fetch ignores abort', async () => {
  const controller = new AbortController();
  const pending = reader(() => new Promise(() => {}))({signal: controller.signal});
  controller.abort(); await assert.rejects(pending, /canceled/);
});
test('already canceled signal prevents the fetch', async () => {
  const controller = new AbortController(); controller.abort(); let called = false;
  await assert.rejects(reader(async () => { called = true; return response(); })
    ({signal: controller.signal}), /canceled/);
  assert.equal(called, false);
});
test('loader and session fail closed on reader timeout with safety guidance', async () => {
  const session = createDirectorySession();
  const loader = createDirectoryLoader(session, reader(() => new Promise(() => {}), {timeoutMs: 10}));
  const state = await loader.refresh();
  assert.equal(state.status, 'unavailable'); assert.equal(state.results.length, 0);
  assert.match(state.notice, /211.*911/);
});
