import test from 'node:test';
import assert from 'node:assert/strict';
import {createDirectorySession} from '../web/directory-session.mjs';
import {createDirectoryLoader} from '../web/directory-loader.mjs';
const now = Date.parse('2026-10-08T18:00:00Z');
function snapshot(id = 'test') {
  const time = new Date(now).toISOString();
  return {schema_version: 1, generated_at: time, resources: [{
    id, name: 'Fixture only', category: 'meal', address: 'Test address',
    latitude: 0, longitude: 0, source_name: 'Test fixture',
    source_url: 'https://example.com/', verified_at: time,
  }]};
}
function setup() {
  const requests = [];
  const session = createDirectorySession(() => now);
  const loader = createDirectoryLoader(session, ({signal}) => new Promise((resolve, reject) => {
    requests.push({signal, resolve, reject});
  }));
  return {session, loader, requests};
}
const origin = {latitude: 0, longitude: 0};

test('refresh immediately clears results and installs a validated replacement', async () => {
  const {session, loader, requests} = setup();
  session.replaceSnapshot(snapshot()); session.search(origin);
  const pending = loader.refresh();
  assert.equal(session.getState().status, 'loading');
  assert.equal(session.getState().results.length, 0);
  requests[0].resolve(snapshot('fresh'));
  const state = await pending;
  assert.equal(state.results[0].resource.id, 'fresh');
});
test('newer refresh wins even when older success resolves last', async () => {
  const {session, loader, requests} = setup(); session.search(origin);
  const old = loader.refresh(); const recent = loader.refresh();
  assert.equal(requests[0].signal.aborted, true);
  requests[1].resolve(snapshot('new')); await recent;
  requests[0].resolve(snapshot('old')); await old;
  assert.equal(session.getState().results[0].resource.id, 'new');
});
test('older failure cannot clear a newer successful replacement', async () => {
  const {session, loader, requests} = setup(); session.search(origin);
  const old = loader.refresh(); const recent = loader.refresh();
  requests[1].resolve(snapshot('new')); await recent;
  requests[0].reject(new Error('old network error')); await old;
  assert.equal(session.getState().results[0].resource.id, 'new');
});
test('older success cannot revive results after newer refresh fails', async () => {
  const {session, loader, requests} = setup();
  const old = loader.refresh(); const recent = loader.refresh();
  requests[1].reject(new Error('offline')); await recent;
  requests[0].resolve(snapshot()); await old;
  assert.equal(session.getState().status, 'unavailable');
});
test('old response during a pending newer request leaves loading state intact', async () => {
  const {session, loader, requests} = setup();
  const old = loader.refresh(); const recent = loader.refresh();
  requests[0].resolve(snapshot()); await old;
  assert.equal(session.getState().status, 'loading');
  requests[1].resolve(snapshot()); await recent;
  assert.equal(session.getState().status, 'ready');
});
test('invalid replacement is unavailable, never successful just because reader resolved', async () => {
  const {loader, requests} = setup(); const pending = loader.refresh();
  requests[0].resolve({});
  const state = await pending; assert.equal(state.status, 'unavailable');
  assert.match(state.notice, /211.*911/);
});
test('cancel aborts pending reader and late success cannot revive data', async () => {
  const {session, loader, requests} = setup(); const pending = loader.refresh();
  loader.cancel(); assert.equal(requests[0].signal.aborted, true);
  requests[0].resolve(snapshot()); await pending;
  assert.equal(session.getState().status, 'unavailable');
  const next = loader.refresh(); requests[1].resolve(snapshot()); await next;
  assert.equal(session.getState().status, 'ready');
});
test('dispose aborts, clears and permanently disables new reads', async () => {
  const {session, loader, requests} = setup(); const pending = loader.refresh();
  loader.dispose(); assert.equal(requests[0].signal.aborted, true);
  requests[0].resolve(snapshot()); await pending;
  assert.equal((await loader.refresh()).status, 'unavailable');
  assert.equal(requests.length, 1);
  assert.equal(session.getState().results.length, 0);
});
test('synchronous reader errors fail closed', async () => {
  const session = createDirectorySession(() => now);
  const loader = createDirectoryLoader(session, () => { throw new Error('reader failed'); });
  assert.equal((await loader.refresh()).status, 'unavailable');
});
test('reader can return a snapshot directly without a promise', async () => {
  const session = createDirectorySession(() => now);
  assert.equal((await createDirectoryLoader(session, () => snapshot()).refresh()).status, 'ready');
});
test('invalid loader dependencies reject early', () => {
  assert.throws(() => createDirectoryLoader({}, () => snapshot()));
  assert.throws(() => createDirectoryLoader(createDirectorySession(), null));
});
