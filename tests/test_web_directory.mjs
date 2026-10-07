import test from 'node:test';
import assert from 'node:assert/strict';
import {readDirectory, filterCategory} from '../web/directory.mjs';

const now = Date.parse('2026-10-06T12:00:00Z');
function snapshot() {
  return {schema_version: 1, generated_at: '2026-10-06T12:00:00Z', resources: [{
    id: 'test', name: 'Test', category: 'meal', address: 'Test address',
    latitude: 44.9, longitude: -93.1, phone: '211', website: null,
    source_name: 'Test source', source_url: 'https://example.com/',
    verified_at: '2026-10-06T12:00:00Z',
  }]};
}

test('directory fields and safety notice survive, live claims do not', () => {
  const data = snapshot();
  Object.assign(data.resources[0], {availability: 'available', hours: {}, open_now: true});
  const result = readDirectory(data, now);
  assert.match(result.notice, /211.*911/);
  for (const field of ['availability', 'hours', 'open_now']) assert.equal(field in result.resources[0], false);
  assert.ok(Object.isFrozen(result.resources[0]));
});

for (const field of ['generated_at', 'verified_at']) {
  for (const value of ['2026-10-05T11:59:59Z', '2026-10-06T12:00:01Z', '2026-10-06T12:00:00', 'garbage']) {
    test(`reject ${field} ${value}`, () => {
      const data = snapshot();
      if (field === 'generated_at') data[field] = value; else data.resources[0][field] = value;
      assert.throws(() => readDirectory(data, now));
    });
  }
}

test('24-hour boundary passes, then fails at view time', () => {
  assert.equal(readDirectory(snapshot(), now + 86400000).resources.length, 1);
  assert.throws(() => readDirectory(snapshot(), now + 86400001));
});

for (const mutate of [
  data => data.resources.push({...data.resources[0]}),
  data => data.resources[0].is_sample = true,
  data => data.resources[0].source_url = 'javascript:alert(1)',
  data => data.resources[0].website = 'https://user:secret@example.com/',
  data => data.resources[0].latitude = 91,
  data => data.resources[0].category = 'unknown',
  data => data.resources[0].name = '',
  data => data.schema_version = 2,
  data => data.resources = [],
]) {
  test(`reject malformed snapshot ${mutate.toString()}`, () => {
    const data = snapshot(); mutate(data); assert.throws(() => readDirectory(data, now));
  });
}

test('category filter returns only requested service', () => {
  const data = readDirectory(snapshot(), now);
  assert.equal(filterCategory(data, 'meal').length, 1);
  assert.equal(filterCategory(data, 'shelter').length, 0);
  assert.equal(filterCategory(data).length, 1);
  assert.throws(() => filterCategory(data, 'bad'));
});
