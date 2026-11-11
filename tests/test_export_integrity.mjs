// Export integrity: known-answer SHA-256 vectors, canonical-form rules, the
// shared cross-language vectors, and readDirectory's closed-on-mismatch gate.
import test from 'node:test';
import assert from 'node:assert/strict';
import {sha256Hex, canonicalJson, resourcesDigest, exportDigest} from '../web/export-integrity.mjs';
import {readDirectory} from '../web/directory.mjs';

const now = Date.parse('2026-11-10T12:30:00Z');

// Shared with tests/test_export_integrity.py: same records, same digests.
const VECTOR = [{address: '123 Cañon Avenue, Suite 5', category: 'shelter',
  id: 'vector-b', latitude: 45.0, longitude: -93.265,
  name: 'St. Mary’s Place – “Open Door”', phone: '211',
  source_name: 'Provider – reviewed', source_url: 'https://example.com/b',
  verified_at: '2026-11-10T12:00:00Z', website: null},
{address: '1 Main St', category: 'meal', id: 'vector-a', latitude: 44.9778,
  longitude: -93.0, name: 'Vector A', phone: null, source_name: 'Provider',
  source_url: 'https://example.com/a', verified_at: '2026-11-10T11:00:00Z',
  website: 'https://example.com'}];
const VECTOR_DIGEST = '9d3377bf26a3ef227379d2b5d97264de592304ce655456bdccceb6a6a718d602';
const ENVELOPE = {generated_at: '2026-11-10T12:00:00Z', resources: VECTOR, schema_version: 1};
const ENVELOPE_DIGEST = '81fed64a29008713571c53acc92e9525380f0fe948afea3bd44e3b1afc75dbb7';

test('sha256 matches published known-answer vectors', () => {
  assert.equal(sha256Hex(''),
    'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855');
  assert.equal(sha256Hex('abc'),
    'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad');
  assert.equal(sha256Hex('abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq'),
    '248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1');
  // Non-ASCII input digests its UTF-8 encoding (matches Python hashlib).
  assert.equal(sha256Hex('résumé-über'),
    'cbf3836cfcb77e1e75b57b396924a53ee1fc3bce206a758834ce910dbfb04836');
});

test('canonical form sorts keys, drops spaces, keeps UTF-8', () => {
  assert.equal(canonicalJson({b: 45.0, a: 'Cañon'}), '{"a":"Cañon","b":45}');
  assert.equal(canonicalJson([true, null, -93.265]), '[true,null,-93.2650000000000005684341886080801486968994140625]');
  assert.throws(() => canonicalJson(Number.NaN), /Non-finite/);
});

test('shared record vector matches the Python exporter', () => {
  assert.equal(resourcesDigest(VECTOR), VECTOR_DIGEST);
});

test('shared envelope vector matches the Python exporter', () => {
  assert.equal(exportDigest(ENVELOPE), ENVELOPE_DIGEST);
});

test('digest ignores injected claims but not reviewed fields', () => {
  const injected = [{...VECTOR[0], availability: 'available', open_now: true, hours: {}}];
  assert.equal(resourcesDigest(injected), resourcesDigest([VECTOR[0]]));
  const edited = [{...VECTOR[0], name: 'Edited after export'}];
  assert.notEqual(resourcesDigest(edited), resourcesDigest([VECTOR[0]]));
  const missing = [{...VECTOR[0]}];
  delete missing[0].phone;
  assert.throws(() => resourcesDigest(missing), /reviewed field/);
});

test('envelope digest covers generated_at, schema_version and every record field', () => {
  // A stale export rolled forward must fail integrity, not just freshness.
  assert.notEqual(exportDigest({...ENVELOPE, generated_at: '2026-11-10T12:30:00Z'}),
    ENVELOPE_DIGEST);
  assert.notEqual(exportDigest({...ENVELOPE, schema_version: 2}), ENVELOPE_DIGEST);
  const edited = JSON.parse(JSON.stringify(ENVELOPE));
  edited.resources[0].name = 'Edited after export';
  assert.notEqual(exportDigest(edited), ENVELOPE_DIGEST);
  // Injected claims and the snapshot's notice change nothing the page may
  // show, so they must not change the digest either.
  const injected = JSON.parse(JSON.stringify(ENVELOPE));
  injected.notice = 'Forged notice';
  injected.resources[0] = {...injected.resources[0], availability: 'available', open_now: true};
  assert.equal(exportDigest(injected), ENVELOPE_DIGEST);
});

test('envelope digest refuses a snapshot missing a reviewed envelope field', () => {
  for (const key of ['generated_at', 'resources', 'schema_version']) {
    const incomplete = {...ENVELOPE};
    delete incomplete[key];
    assert.throws(() => exportDigest(incomplete), /envelope field/);
  }
});

function snapshot() {
  const resources = [{id: 'test', name: 'Test', category: 'meal',
    address: 'Test address', latitude: 44.9, longitude: -93.1, phone: '211',
    website: null, source_name: 'Test source', source_url: 'https://example.com/',
    verified_at: '2026-11-10T12:00:00Z'}];
  const value = {schema_version: 1, generated_at: '2026-11-10T12:00:00Z', resources};
  value.export_sha256 = exportDigest(value);
  return value;
}

test('a digest matching the reviewed envelope passes the gate', () => {
  assert.equal(readDirectory(snapshot(), now).resources.length, 1);
});

test('any envelope edit with a stale digest never renders', () => {
  for (const mutate of [
    data => { data.resources[0].name = 'Edited'; },
    data => { data.resources[0].latitude = 44.8; },
    data => { data.resources.push({...data.resources[0], id: 'second'}); },
    data => { data.generated_at = '2026-11-10T11:59:00Z'; },
    data => { data.schema_version = 2; },
    data => { delete data.export_sha256; },
    data => { data.export_sha256 = data.export_sha256.toUpperCase(); },
    data => { data.export_sha256 = '0'.repeat(64); },
  ]) {
    const data = snapshot();
    mutate(data);
    assert.throws(() => readDirectory(data, now), /integrity|Invalid directory/);
  }
});
