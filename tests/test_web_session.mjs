import test from 'node:test';
import assert from 'node:assert/strict';
import {createDirectorySession} from '../web/directory-session.mjs';

const initial = Date.parse('2026-10-08T12:00:00Z');
const origin = {latitude: 0, longitude: 0};
function snapshot(now = initial) {
  const time = new Date(now).toISOString();
  return {schema_version: 1, generated_at: time, resources: [{
    id: 'test', name: 'Fixture only', category: 'meal', address: 'Test address',
    latitude: 0, longitude: 0, source_name: 'Test fixture',
    source_url: 'https://example.com/', verified_at: time,
  }]};
}
function setup() {
  let now = initial;
  return {session: createDirectorySession(() => now), setTime(value) { now = value; }};
}
function noResults(state, status) {
  assert.equal(state.status, status);
  assert.equal(state.results.length, 0);
  assert.match(state.notice, /211.*911/);
}

test('starts unavailable, without claiming a directory exists', () => {
  noResults(setup().session.getState(), 'unavailable');
});
test('validated snapshot is ready, search returns safe immutable results', () => {
  const {session} = setup();
  noResults(session.replaceSnapshot(snapshot()), 'ready');
  const state = session.search(origin);
  assert.equal(state.status, 'results');
  assert.equal(state.results.length, 1);
  assert.ok(Object.isFrozen(state));
  assert.ok(Object.isFrozen(state.results));
  assert.equal('availability' in state.results[0].resource, false);
});
test('no matches is distinct from unavailable', () => {
  const {session} = setup(); session.replaceSnapshot(snapshot());
  noResults(session.search({...origin, category: 'shower'}), 'no_matches');
});
test('starting refresh removes previously displayed results', () => {
  const {session} = setup(); session.replaceSnapshot(snapshot()); session.search(origin);
  noResults(session.beginRefresh(), 'loading');
  noResults(session.getState(), 'loading');
  noResults(session.search(origin), 'loading');
});
test('failed refresh cannot fall back to previous results', () => {
  const {session} = setup(); session.replaceSnapshot(snapshot()); session.search(origin);
  noResults(session.failRefresh(), 'unavailable');
  noResults(session.getState(), 'unavailable');
});
test('invalid replacement clears a previously valid directory', () => {
  const {session} = setup(); session.replaceSnapshot(snapshot()); session.search(origin);
  noResults(session.replaceSnapshot({}), 'unavailable');
  noResults(session.getState(), 'unavailable');
});
test('long-open state reads revalidate without a new search', () => {
  const {session, setTime} = setup(); session.replaceSnapshot(snapshot()); session.search(origin);
  setTime(initial + 86400000); assert.equal(session.getState().status, 'results');
  setTime(initial + 86400001); noResults(session.getState(), 'refresh_required');
  setTime(initial); noResults(session.getState(), 'refresh_required');
});
test('fresh replacement reapplies search preferences but never old results', () => {
  const {session, setTime} = setup(); session.replaceSnapshot(snapshot()); session.search(origin);
  session.beginRefresh(); setTime(initial + 86400001);
  assert.equal(session.replaceSnapshot(snapshot(initial + 86400001)).status, 'results');
});
test('invalid searches clear results and a corrected search works', () => {
  const {session} = setup(); session.replaceSnapshot(snapshot()); session.search(origin);
  noResults(session.search({...origin, latitude: 91}), 'invalid_search');
  noResults(session.getState(), 'ready');
  assert.equal(session.search(origin).status, 'results');
});
test('caller mutation of search preferences does not affect future state', () => {
  const {session} = setup(); session.replaceSnapshot(snapshot());
  const options = {...origin}; session.search(options); options.latitude = 91;
  assert.equal(session.getState().status, 'results');
});
test('clock rollback clears rather than revives a validated directory', () => {
  const {session, setTime} = setup(); session.replaceSnapshot(snapshot());
  setTime(initial - 1); noResults(session.getState(), 'refresh_required');
});
test('safety guidance remains in every unavailable/invalid state', () => {
  const {session} = setup();
  for (const state of [session.getState(), session.beginRefresh(), session.failRefresh(),
    session.replaceSnapshot(null), session.search(null)]) assert.match(state.notice, /211.*911/);
});

test('clearing search input removes prior results', () => {
  const {session} = setup(); session.replaceSnapshot(snapshot()); session.search(origin);
  noResults(session.search(null), 'invalid_search');
  noResults(session.getState(), 'ready');
});
test('clock failure produces refresh-required with safety guidance', () => {
  let broken = false;
  const session = createDirectorySession(() => { if (broken) throw new Error('clock'); return initial; });
  session.replaceSnapshot(snapshot()); broken = true;
  noResults(session.getState(), 'refresh_required');
});
