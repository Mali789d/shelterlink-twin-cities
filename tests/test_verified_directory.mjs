// The verified seed must flow through the browser reader exactly like a real
// export: no sample flags, aware timestamps, dialable phones, safe URLs, and
// nearest-first search. Time is derived from the records' own verified_at so
// the suite stays valid after the seed goes stale for real exports.
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {readDirectory, nearbyResources} from '../web/directory.mjs';

const seed = JSON.parse(readFileSync(
  new URL('../data/verified_resources.json', import.meta.url), 'utf8'));

// Mirror app/export_directory.py's field selection so the test exercises the
// same shape the page would receive.
const snapshot = {
  schema_version: 1,
  generated_at: seed.map(item => item.verified_at).sort().at(-1),
  notice: 'Directory information only. Call first; current local help: 211; emergency: 911.',
  resources: seed.map(({id, name, category, address, latitude, longitude,
    phone, website, source_name, source_url, verified_at}) => ({id, name, category,
    address, latitude, longitude, phone, website, source_name, source_url, verified_at})),
};
const now = Date.parse(snapshot.generated_at) + 60 * 60 * 1000;

test('verified seed passes the browser directory gate', () => {
  const directory = readDirectory(snapshot, now);
  assert.equal(directory.resources.length, seed.length);
  for (const item of directory.resources) {
    assert.equal(Object.isFrozen(item), true);
    assert.ok(item.source_url.startsWith('https://'));
  }
});

test('search ranks the nearest verified records first', () => {
  const directory = readDirectory(snapshot, now);
  // US Bank Stadium area, downtown Minneapolis.
  const results = nearbyResources(directory,
    {latitude: 44.9738, longitude: -93.2577, now});
  assert.ok(results.length >= 3);
  const ids = results.map(item => item.resource.id);
  assert.equal(ids[0], 'people-serving-people');
  const distances = results.map(item => item.distanceMiles);
  assert.deepEqual(distances, [...distances].sort((a, b) => a - b));
});

test('category filter finds the verified meal site in Saint Paul', () => {
  const directory = readDirectory(snapshot, now);
  const meals = nearbyResources(directory,
    {latitude: 44.949, longitude: -93.095, category: 'meal', now});
  assert.deepEqual(meals.map(item => item.resource.id), ['saint-paul-opportunity-center']);
});

test('the same seed fails closed once verification ages out', () => {
  const stale = Date.parse(snapshot.generated_at) + 2 * 24 * 60 * 60 * 1000;
  assert.throws(() => readDirectory(snapshot, stale));
});
