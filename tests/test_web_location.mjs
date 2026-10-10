import test from 'node:test';
import assert from 'node:assert/strict';
import {parseCoordinates} from '../web/location-input.mjs';
import {createDirectorySession} from '../web/directory-session.mjs';

for (const [input, latitude, longitude] of [
  ['44.9778, -93.2650', 44.9778, -93.265], [' +0 , -0 ', 0, -0],
  ['90,180', 90, 180], ['-90,-180', -90, -180], ['.5,-.5', .5, -.5],
  ['\n44.9, -93.1\n', 44.9, -93.1],
]) {
  test(`manual coordinates ${JSON.stringify(input)}`, () => {
    const result = parseCoordinates(input);
    assert.deepEqual(result, {latitude, longitude});
    assert.ok(Object.isFrozen(result));
  });
}
for (const input of [null, {}, 55415, '', '55415', 'Minneapolis', '44.9 -93.1',
  '44.9;-93.1', '44.9,-93.1,0', '91,0', '0,181', '-91,0', '0,-181',
  'NaN,0', 'Infinity,0', '1e2,0', '0x10,0', '44,9,-93,1', '44N,93W',
  'https://example.com', '44.9,', ',0', '1.,0', '1,0 trailing', '1'.repeat(101)]) {
  test(`reject ambiguous or invalid coordinates ${JSON.stringify(input)}`, () => {
    assert.throws(() => parseCoordinates(input));
  });
}

test('manual input feeds local search with no network or location permission', () => {
  const now = Date.parse('2026-10-10T12:00:00Z');
  const time = new Date(now).toISOString();
  const session = createDirectorySession(() => now);
  session.replaceSnapshot({schema_version: 1, generated_at: time, resources: [{
    id: 'fixture', name: 'Synthetic fixture', category: 'meal', address: 'Test address',
    latitude: 44.9, longitude: -93.1, source_name: 'Test fixture',
    source_url: 'https://example.com/', verified_at: time,
  }]});
  const state = session.search(parseCoordinates('44.9, -93.1'));
  assert.equal(state.status, 'results');
  assert.equal(state.results[0].distanceMiles, 0);
  assert.match(state.notice, /211.*911/);
});
