import test from 'node:test';
import assert from 'node:assert/strict';
import {readDirectory, nearbyResources} from '../web/directory.mjs';

const now = Date.now();
const time = new Date(now).toISOString();
function directory(points = [['origin', 0, 0, 'meal'], ['east', 0, 1, 'shelter'],
  ['far', 0, 2, 'meal']]) {
  return readDirectory({schema_version: 1, generated_at: time,
    resources: points.map(([id, latitude, longitude, category]) => ({
      id, latitude, longitude, category, name: id, address: 'Test fixture only',
      source_name: 'Test fixture', source_url: 'https://example.com/',
      verified_at: time,
    }))}, now);
}
const origin = {latitude: 0, longitude: 0};

test('ranks by great-circle distance without changing the directory', () => {
  const data = directory([['far', 0, 2, 'meal'], ['origin', 0, 0, 'meal'], ['east', 0, 1, 'shelter']]);
  const result = nearbyResources(data, {...origin, radiusMiles: 200});
  assert.deepEqual(result.map(item => item.resource.id), ['origin', 'east', 'far']);
  assert.deepEqual(data.resources.map(item => item.id), ['far', 'origin', 'east']);
  assert.equal(result[0].distanceMiles, 0);
  assert.ok(Math.abs(result[1].distanceMiles - 69.0934) < 0.001);
  assert.ok(Object.isFrozen(result));
  assert.ok(Object.isFrozen(result[0]));
  assert.equal('open_now' in result[0].resource, false);
  assert.equal('availability' in result[0].resource, false);
});

test('radius and limit apply after category filtering', () => {
  assert.deepEqual(nearbyResources(directory(), {...origin, radiusMiles: 100})
    .map(item => item.resource.id), ['origin', 'east']);
  assert.deepEqual(nearbyResources(directory(), {...origin, category: 'meal', radiusMiles: 200, limit: 1})
    .map(item => item.resource.id), ['origin']);
  assert.equal(nearbyResources(directory(), {...origin, category: 'shower'}).length, 0);
});

test('radius includes its exact boundary and zero radius allows a co-located site', () => {
  const data = directory([['east', 0, 1, 'meal']]);
  const distance = nearbyResources(data, {...origin, radiusMiles: 100})[0].distanceMiles;
  assert.equal(nearbyResources(data, {...origin, radiusMiles: distance}).length, 1);
  assert.equal(nearbyResources(data, {...origin, radiusMiles: distance - 0.000001}).length, 0);
  assert.equal(nearbyResources(directory(), {...origin, radiusMiles: 0}).length, 1);
});

test('equal distances use stable ID ordering and limits, not source order', () => {
  const data = directory([['z', 0, 0, 'meal'], ['a', 0, 0, 'meal']]);
  assert.equal(nearbyResources(data, {...origin, limit: 1})[0].resource.id, 'a');
});

test('antimeridian uses the short route and antipodal distance remains finite', () => {
  const data = directory([['across', 0, -179.9, 'meal'], ['opposite', 0, -0.1, 'meal']]);
  const result = nearbyResources(data, {latitude: 0, longitude: 179.9, radiusMiles: 13000});
  assert.ok(result[0].distanceMiles < 14);
  assert.ok(Number.isFinite(result[1].distanceMiles));
  assert.ok(result[1].distanceMiles > 12000);
});

for (const options of [{}, {latitude: NaN, longitude: 0}, {latitude: 91, longitude: 0},
  {latitude: 0, longitude: -181}, {latitude: '0', longitude: 0},
  {...origin, radiusMiles: -1}, {...origin, radiusMiles: Infinity},
  {...origin, limit: 0}, {...origin, limit: 101}, {...origin, limit: 1.5},
  {...origin, category: 'beds'}]) {
  test(`reject invalid search options ${JSON.stringify(options)}`, () => {
    assert.throws(() => nearbyResources(directory(), options));
  });
}

test('default radius excludes distant sites and polar coordinates remain finite', () => {
  assert.deepEqual(nearbyResources(directory(), origin).map(item => item.resource.id), ['origin']);
  const polar = nearbyResources(directory([['pole', 90, 180, 'meal']]),
    {latitude: 90, longitude: -180});
  assert.ok(Number.isFinite(polar[0].distanceMiles));
  assert.ok(polar[0].distanceMiles < 0.000001);
});
