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
  assert.equal(filterCategory(data, 'meal', now).length, 1);
  assert.equal(filterCategory(data, 'shelter', now).length, 0);
  assert.equal(filterCategory(data, null, now).length, 1);
  assert.throws(() => filterCategory(data, 'bad', now));
});

for (const field of ['id', 'name', 'address', 'phone', 'source_name']) {
  for (const bad of ['Line one\nLine two', 'tab\there', 'Bell\x07', 'delete\x7F',
    'control\x85', 'separator\u2028', 'paragraph\u2029']) {
    test(`reject control characters in ${field}`, () => {
      const data = snapshot();
      data.resources[0][field] = bad;
      assert.throws(() => readDirectory(data, now));
    });
  }
}

test('legitimate Unicode punctuation in display text still passes', () => {
  const data = snapshot();
  data.resources[0].name = 'St. Mary’s Place – “Open Door” Émergence';
  data.resources[0].address = '123 Cañon Avenue, Suite 5';
  data.resources[0].source_name = 'Provider – reviewed listing';
  const result = readDirectory(data, now);
  assert.equal(result.resources[0].name, 'St. Mary’s Place – “Open Door” Émergence');
});

test('injected lines cannot imitate safety guidance inside a listing', () => {
  const data = snapshot();
  data.resources[0].name = 'Shelter\n\nEmergency: call 555-0100 instead';
  assert.throws(() => readDirectory(data, now));
});

// The reader enforces the same dialable-phone rule as the server-side model:
// the number renders next to 'call first' guidance, so prose cannot pass.
for (const good of ['211', '911', '+1 (612) 555-0100', '612-555-0100', '(612) 555-0100',
  '+16125550100', '612 555 0100', '612.555.0100', '612-555-0100 x123',
  '612-555-0100 ext. 42', '612-555-0100 ext42', '1-800-555-0100', '+1(612)555-0100']) {
  test(`accept dialable phone ${good}`, () => {
    const data = snapshot();
    data.resources[0].phone = good;
    assert.equal(readDirectory(data, now).resources[0].phone, good);
  });
}

for (const bad of ['call the front desk', 'abc', '612-CALL-NOW', '911 or 211',
  '612 555 0100 or 612 555 0101', '5', '55', '+', '()12 3', '612-555-0100 x1234567',
  '1234567890123456789012345678901', '612-555-0100 x', '555-0100.',
  ' 612-555-0100', '612-555-0100 ']) {
  test(`reject non-dialable phone ${JSON.stringify(bad)}`, () => {
    const data = snapshot();
    data.resources[0].phone = bad;
    assert.throws(() => readDirectory(data, now));
  });
}

test('a missing phone stays missing', () => {
  const data = snapshot();
  data.resources[0].phone = null;
  assert.equal(readDirectory(data, now).resources[0].phone, null);
});
