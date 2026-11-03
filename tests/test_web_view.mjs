import test from 'node:test';
import assert from 'node:assert/strict';
import {PAGE_NOTICE, PROTOTYPE_BANNER, phoneHref, resultView, statusMessage}
  from '../web/directory-view.mjs';

function result(overrides = {}) {
  const resource = {
    id: 'r1', name: 'Fixture Shelter', category: 'shelter',
    address: '123 Test Ave, Minneapolis, MN', latitude: 44.98, longitude: -93.27,
    phone: '(612) 555-0100', website: 'https://example.org/shelter?page=1',
    source_name: 'Fixture source', source_url: 'https://example.org/',
    verified_at: '2026-11-03T14:00:00+00:00', ...overrides.resource,
  };
  return Object.freeze({resource, distanceMiles: overrides.distanceMiles ?? 1.26});
}

test('page notice and banner keep 211/911 and the not-live framing', () => {
  assert.match(PAGE_NOTICE, /211/);
  assert.match(PAGE_NOTICE, /911/);
  assert.match(PROTOTYPE_BANNER, /prototype/i);
  assert.match(PROTOTYPE_BANNER, /not a live referral service/);
  assert.doesNotMatch(PAGE_NOTICE + PROTOTYPE_BANNER, /available now|open now/i);
});

test('every session status has a message with heading and detail', () => {
  const statuses = ['unavailable', 'loading', 'refresh_required', 'ready',
    'results', 'no_matches', 'invalid_search'];
  const seen = new Set();
  for (const status of statuses) {
    const message = statusMessage(status);
    assert.ok(message.heading.length > 0, status);
    assert.ok(message.detail.length > 0, status);
    assert.ok(!seen.has(message.heading), `duplicate heading for ${status}`);
    seen.add(message.heading);
  }
});

test('unavailable, refresh_required and no_matches point to 211/911', () => {
  for (const status of ['unavailable', 'refresh_required', 'no_matches']) {
    const message = statusMessage(status);
    assert.match(message.detail, /211/, status);
    assert.match(message.detail, /911/, status);
  }
});

test('unknown statuses throw instead of improvising text', () => {
  assert.throws(() => statusMessage('open_now'), /Unknown directory status/);
  assert.throws(() => statusMessage(''), /Unknown directory status/);
  assert.throws(() => statusMessage(undefined), /Unknown directory status/);
  assert.throws(() => statusMessage('__proto__'), /Unknown directory status/);
});

test('result view formats distance, category label and source line', () => {
  const view = resultView(result());
  assert.equal(view.distance, '1.3 mi');
  assert.equal(view.category, 'Shelter');
  assert.equal(view.name, 'Fixture Shelter');
  assert.equal(view.address, '123 Test Ave, Minneapolis, MN');
  assert.equal(view.source, 'Source: Fixture source - verified 2026-11-03');
});

test('distance rounds to one decimal like the SMS replies', () => {
  assert.equal(resultView(result({distanceMiles: 0.04})).distance, '0.0 mi');
  assert.equal(resultView(result({distanceMiles: 12.25})).distance, '12.3 mi');
});

test('all four categories label distinctly', () => {
  const labels = new Set();
  for (const category of ['shelter', 'meal', 'warming', 'shower']) {
    const view = resultView(result({resource: {category}}));
    labels.add(view.category);
  }
  assert.equal(labels.size, 4);
});

test('unsupported category throws instead of mislabeling a service', () => {
  assert.throws(() => resultView(result({resource: {category: 'housing'}})),
    /Invalid category/);
});

test('phone renders as text plus a digits-only tel link', () => {
  const view = resultView(result());
  assert.equal(view.phone, '(612) 555-0100');
  assert.equal(view.phoneHref, 'tel:6125550100');
});

test('extension survives the tel link', () => {
  const view = resultView(result({resource: {phone: '211 x123'}}));
  assert.equal(view.phoneHref, 'tel:211x123');
});

test('website shows the host and links the validated URL', () => {
  const view = resultView(result());
  assert.equal(view.websiteText, 'example.org');
  assert.equal(view.websiteHref, 'https://example.org/shelter?page=1');
});

test('missing phone or website stay absent, never guessed', () => {
  const view = resultView(result({resource: {phone: null, website: null}}));
  assert.equal(view.phone, null);
  assert.equal(view.phoneHref, null);
  assert.equal(view.websiteText, null);
  assert.equal(view.websiteHref, null);
});

test('malformed results throw instead of rendering a blank listing', () => {
  assert.throws(() => resultView(null), /Invalid result/);
  assert.throws(() => resultView({}), /Invalid result/);
  assert.throws(() => resultView(result({distanceMiles: Number.NaN})), /Invalid distance/);
  assert.throws(() => resultView(result({distanceMiles: -1})), /Invalid distance/);
  assert.throws(() => resultView(result({resource: {name: ''}})), /Invalid name/);
  assert.throws(() => resultView(result({resource: {address: '  '}})), /Invalid address/);
});

test('view objects are frozen against later mutation', () => {
  const view = resultView(result());
  assert.ok(Object.isFrozen(view));
});

test('phoneHref rejects non-dialable text', () => {
  assert.throws(() => phoneHref('call us'), /Invalid phone/);
  assert.throws(() => phoneHref(''), /Invalid phone/);
  assert.throws(() => phoneHref('javascript:alert(1)'), /Invalid phone/);
  assert.equal(phoneHref('+1 (612) 555-0100'), 'tel:+16125550100');
});
