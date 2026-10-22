import test from 'node:test';
import assert from 'node:assert/strict';
import {CITY_CENTROIDS, ZIP_CENTROIDS, lookupPlace} from '../web/zip-lookup.mjs';
import {parseCoordinates, parseLocation} from '../web/location-input.mjs';
import {createDirectorySession} from '../web/directory-session.mjs';

test('every metro ZIP resolves to a frozen centroid inside the Twin Cities', () => {
  assert.equal(Object.keys(ZIP_CENTROIDS).length, 103);
  for (const [zip, place] of Object.entries(ZIP_CENTROIDS)) {
    assert.match(zip, /^55[134]\d{2}$/);
    assert.ok(Object.isFrozen(place));
    assert.ok(place.latitude > 44.70 && place.latitude < 45.25, zip);
    assert.ok(place.longitude > -93.75 && place.longitude < -92.85, zip);
    assert.deepEqual(lookupPlace(zip), place);
  }
});

test('downtown Minneapolis ZIP lands near the core', () => {
  const place = lookupPlace('55401');
  assert.ok(Math.abs(place.latitude - 44.98) < 0.02);
  assert.ok(Math.abs(place.longitude - -93.27) < 0.02);
});

test('city names trim case and whitespace like the Python geocoder', () => {
  assert.deepEqual(lookupPlace(' Minneapolis '), CITY_CENTROIDS['minneapolis']);
  assert.deepEqual(lookupPlace('SAINT PAUL'), CITY_CENTROIDS['st paul']);
  assert.deepEqual(lookupPlace('st paul'), CITY_CENTROIDS['saint paul']);
});

test('unknown and ambiguous places return null instead of a guess', () => {
  for (const input of ['10001', '1000', '554150', 'nowhere particular',
    '123 Main St, Minneapolis', '44.9, -93.1', '', null, {}, 55415]) {
    assert.equal(lookupPlace(input), null, JSON.stringify(input));
  }
});

test('parseLocation keeps accepting explicit coordinates', () => {
  assert.deepEqual(parseLocation('44.9778, -93.2650'), {latitude: 44.9778, longitude: -93.265});
});

test('parseLocation resolves a ZIP or city without network or GPS', () => {
  assert.deepEqual(parseLocation('55415'), ZIP_CENTROIDS['55415']);
  assert.deepEqual(parseLocation(' Minneapolis '), CITY_CENTROIDS['minneapolis']);
  assert.ok(Object.isFrozen(parseLocation('55101')));
});

test('parseLocation still rejects anything ambiguous', () => {
  for (const input of ['123 Main St', 'Duluth', '55415 extra', '44.9 -93.1']) {
    assert.throws(() => parseLocation(input), /Enter latitude, longitude/);
  }
  // '55415  ' trims to a known ZIP, so it resolves rather than throws.
  assert.deepEqual(parseLocation('55415  '), ZIP_CENTROIDS['55415']);
});

test('parseCoordinates itself stays strict - ZIPs are not coordinates', () => {
  assert.throws(() => parseCoordinates('55415'));
});

test('a resolved ZIP feeds local search end to end', () => {
  const now = Date.parse('2026-10-21T12:00:00Z');
  const time = new Date(now).toISOString();
  const session = createDirectorySession(() => now);
  session.replaceSnapshot({schema_version: 1, generated_at: time, resources: [{
    id: 'fixture', name: 'Synthetic fixture', category: 'shelter', address: 'Test address',
    latitude: 44.975, longitude: -93.258, source_name: 'Test fixture',
    source_url: 'https://example.com/', verified_at: time,
  }]});
  const state = session.search(parseLocation('55415'));
  assert.equal(state.status, 'results');
  assert.ok(state.results[0].distanceMiles < 0.5);
  assert.match(state.notice, /211.*911/);
});
