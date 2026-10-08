import test from 'node:test';
import assert from 'node:assert/strict';
import {readDirectory, filterCategory, nearbyResources} from '../web/directory.mjs';

const now = Date.parse('2026-10-07T12:00:00Z');
const day = 86400000;
function snapshot(verified = now, generated = now) {
  return {schema_version: 1, generated_at: new Date(generated).toISOString(), resources: [{
    id: 'test', name: 'Fixture only', category: 'meal', address: 'Test address',
    latitude: 0, longitude: 0, source_name: 'Test fixture',
    source_url: 'https://example.com/', verified_at: new Date(verified).toISOString(),
  }]};
}
const origin = {latitude: 0, longitude: 0};

for (const [name, search] of [
  ['filter', (directory, at) => filterCategory(directory, 'meal', at)],
  ['nearby', (directory, at) => nearbyResources(directory, {...origin, now: at})],
]) {
  test(`${name} expires a previously validated directory after the exact boundary`, () => {
    const directory = readDirectory(snapshot(), now);
    assert.equal(search(directory, now + day).length, 1);
    assert.throws(() => search(directory, now + day + 1), /refresh/);
  });
  test(`${name} expires an older listing before the snapshot expires`, () => {
    const directory = readDirectory(snapshot(now - day + 1000), now);
    assert.equal(search(directory, now + 1000).length, 1);
    assert.throws(() => search(directory, now + 1001), /refresh/);
  });
  test(`${name} expires an older snapshot even if its listing is current`, () => {
    const directory = readDirectory(snapshot(now, now - day + 1000), now);
    assert.throws(() => search(directory, now + 1001), /refresh/);
  });
  test(`${name} rejects forged and copied validation objects`, () => {
    const directory = readDirectory(snapshot(), now);
    assert.throws(() => search({...directory}, now), /validate/);
    assert.throws(() => search({resources: directory.resources}, now), /validate/);
  });
  test(`${name} rejects clock rollback and invalid clocks`, () => {
    const directory = readDirectory(snapshot(), now);
    for (const at of [now - 1, NaN, Infinity]) assert.throws(() => search(directory, at), /time/);
  });
  test(`${name} can use a fresh replacement after expiry without reviving old data`, () => {
    const old = readDirectory(snapshot(), now);
    const later = now + day + 1;
    const fresh = readDirectory(snapshot(later, later), later);
    assert.equal(search(fresh, later).length, 1);
    assert.throws(() => search(old, later), /refresh/);
  });
}
