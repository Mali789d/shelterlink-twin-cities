import test from 'node:test';
import assert from 'node:assert/strict';
import {readDirectory} from '../web/directory.mjs';

function snapshot(time) {
  return {schema_version: 1, generated_at: time, resources: [{
    id: 'fixture', name: 'Fixture only', address: 'Test address', category: 'meal',
    latitude: 0, longitude: 0, source_name: 'Test fixture',
    source_url: 'https://example.com/', verified_at: time,
  }]};
}

for (const time of ['2026-02-30T12:00:00Z', '2026-02-29T12:00:00Z',
  '2026-04-31T12:00:00Z', '2026-00-01T12:00:00Z', '2026-13-01T12:00:00Z',
  '2026-10-00T12:00:00Z', '2026-10-07T24:00:00Z', '2026-10-07T12:60:00Z',
  '2026-10-07T12:00:60Z', '2026-10-07T12:00:00+24:00',
  '2026-10-07T12:00:00+05:60', 'October 7, 2026 12:00:00Z',
  '2026-10-07 12:00:00Z', '2026-10-07T12:00Z']) {
  for (const field of ['generated_at', 'verified_at']) {
    test(`reject impossible/non-exported ${field}: ${time}`, () => {
      // Evaluate at its Date.parse-normalized value when possible, so rejection
      // cannot accidentally be attributed only to the age check.
      const normalized = Date.parse(time);
      const now = Number.isFinite(normalized) ? normalized : Date.parse('2026-10-07T12:00:00Z');
      const data = snapshot(new Date(now).toISOString());
      if (field === 'generated_at') data[field] = time; else data.resources[0][field] = time;
      assert.throws(() => readDirectory(data, now));
    });
  }
}

for (const time of ['2024-02-29T12:00:00Z', '2000-02-29T12:00:00Z',
  '2026-10-07T12:00:00.123456+05:30', '2026-10-07T12:00:00-05:00',
  '2026-10-07T12:00:00.1Z']) {
  test(`accept valid exporter timestamp ${time}`, () => {
    assert.equal(readDirectory(snapshot(time), Date.parse(time)).resources.length, 1);
  });
}

test('century leap-year rule rejects 1900 February 29 even after normalization', () => {
  const time = '1900-02-29T12:00:00Z';
  assert.throws(() => readDirectory(snapshot(time), Date.parse(time)));
});
