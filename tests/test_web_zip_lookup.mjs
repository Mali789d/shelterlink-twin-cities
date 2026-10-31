import test from 'node:test';
import assert from 'node:assert/strict';
import {CITY_CENTROIDS, NEIGHBORHOOD_CENTROIDS, ZIP_CENTROIDS, lookupPlace} from '../web/zip-lookup.mjs';
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

test('place lookup forgives common texting variants like Python', () => {
  assert.deepEqual(lookupPlace('St. Paul'), CITY_CENTROIDS['saint paul']);
  assert.deepEqual(lookupPlace('ST. PAUL, MN'), CITY_CENTROIDS['saint paul']);
  assert.deepEqual(lookupPlace('Minneapolis, Minnesota'), CITY_CENTROIDS['minneapolis']);
  assert.deepEqual(lookupPlace('st.  louis   park'), CITY_CENTROIDS['st louis park']);
  assert.deepEqual(lookupPlace('west st. paul'), CITY_CENTROIDS['west saint paul']);
  assert.deepEqual(lookupPlace('north st paul'), CITY_CENTROIDS['north saint paul']);
  assert.deepEqual(lookupPlace('55401 mn'), ZIP_CENTROIDS['55401']);
});

test('variant forgiveness never guesses a place', () => {
  for (const input of ['mn', 'minnesota', 'duluth mn', '5540.1', 'st.paul']) {
    assert.equal(lookupPlace(input), null, JSON.stringify(input));
  }
});

test('well-known neighborhoods resolve to their primary ZIP centroid', () => {
  assert.equal(Object.keys(NEIGHBORHOOD_CENTROIDS).length, 50);
  assert.ok(Object.isFrozen(NEIGHBORHOOD_CENTROIDS));
  assert.deepEqual(lookupPlace('frogtown'), ZIP_CENTROIDS['55103']);
  assert.deepEqual(lookupPlace('uptown'), ZIP_CENTROIDS['55408']);
  assert.deepEqual(lookupPlace('cedar riverside'), ZIP_CENTROIDS['55454']);
  assert.deepEqual(lookupPlace('downtown minneapolis'), CITY_CENTROIDS['minneapolis']);
  assert.deepEqual(lookupPlace('downtown st paul'), CITY_CENTROIDS['saint paul']);
  assert.ok(Object.isFrozen(lookupPlace('midway')));
});

test('neighborhood lookup forgives the same texting variants as Python', () => {
  assert.deepEqual(lookupPlace('North-Loop'), lookupPlace('north loop'));
  assert.deepEqual(lookupPlace("Dayton's Bluff"), lookupPlace('daytons bluff'));
  assert.deepEqual(lookupPlace('Dayton\u2019s Bluff'), lookupPlace('daytons bluff'));
  assert.deepEqual(lookupPlace('payne-phalen'), lookupPlace('payne phalen'));
  assert.deepEqual(lookupPlace('MAC-GROVELAND'), lookupPlace('mac groveland'));
  assert.deepEqual(lookupPlace('west 7th'), lookupPlace('west seventh'));
  assert.deepEqual(lookupPlace('Frogtown, MN'), lookupPlace('frogtown'));
  assert.notEqual(lookupPlace('North-Loop'), null);
});

test('ambiguous neighborhood names stay unknown instead of guessing a city', () => {
  // 'Como' is a Minneapolis neighborhood AND Saint Paul's Como Park; bare
  // 'Downtown' is both cities; 'St Anthony' is a suburb and a park district;
  // 'Jordan' and 'Windom' name both metro neighborhoods and other MN cities.
  for (const input of ['como', 'downtown', 'st anthony', 'jordan', 'windom',
    'riverside', 'uptown minneapolis']) {
    assert.equal(lookupPlace(input), null, JSON.stringify(input));
  }
});

test('unknown and ambiguous places return null instead of a guess', () => {
  for (const input of ['10001', '1000', '554150', 'nowhere particular',
    '123 Main St, Minneapolis', '44.9, -93.1', '', null, {}, 55415]) {
    assert.equal(lookupPlace(input), null, JSON.stringify(input));
  }
});

test('inherited Object member names never resolve as places', () => {
  // Plain-object maps expose prototype members to bracket reads; a texted
  // 'constructor' or '__proto__' must stay unknown, matching Python's dict.
  for (const input of ['constructor', '__proto__', 'Constructor', '  constructor  ']) {
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

test('metro city names resolve inside the Twin Cities metro', () => {
  assert.equal(Object.keys(CITY_CENTROIDS).length, 49);
  for (const [name, place] of Object.entries(CITY_CENTROIDS)) {
    assert.match(name, /^[a-z ]+$/);
    assert.ok(Object.isFrozen(place));
    assert.ok(place.latitude > 44.70 && place.latitude < 45.25, name);
    assert.ok(place.longitude > -93.75 && place.longitude < -92.85, name);
    assert.deepEqual(lookupPlace(name), place);
  }
  assert.deepEqual(lookupPlace('Maple Grove'), CITY_CENTROIDS['maple grove']);
  assert.deepEqual(lookupPlace('eden prairie'), CITY_CENTROIDS['eden prairie']);
  assert.equal(lookupPlace('nowhereville'), null);
});

test('a leading preposition falls back only after the literal text fails', () => {
  assert.deepEqual(lookupPlace('in minneapolis'), lookupPlace('minneapolis'));
  assert.deepEqual(lookupPlace('near frogtown'), ZIP_CENTROIDS['55103']);
  assert.deepEqual(lookupPlace('around saint paul'), lookupPlace('saint paul'));
  assert.deepEqual(lookupPlace('at minneapolis'), lookupPlace('minneapolis'));
  assert.deepEqual(lookupPlace('by uptown'), lookupPlace('uptown'));
  // 'Near North' is a real neighborhood: the literal lookup must win over
  // stripping 'near', which would leave the neighborhood unreachable.
  assert.equal(lookupPlace('north'), null);
  assert.ok(lookupPlace('near north') !== null);
  // A lone preposition stays unknown, and forgiving one never un-ambiguates.
  for (const lone of ['in', 'near', 'around', 'at', 'by']) {
    assert.equal(lookupPlace(lone), null, lone);
  }
  assert.equal(lookupPlace('near como'), null);
  assert.equal(lookupPlace('in downtown'), null);
});
