// View-time checks for static exports. No network, tracking, DOM or paid backend.
const MAX_AGE_MS = 24 * 60 * 60 * 1000;
const CATEGORIES = new Set(['shelter', 'meal', 'warming', 'shower']);

function timestamp(value) {
  if (typeof value !== 'string' || !/(Z|[+-]\d{2}:\d{2})$/.test(value)) {
    throw new Error('A timezone is required');
  }
  const parsed = Date.parse(value);
  if (!Number.isFinite(parsed)) throw new Error('Invalid timestamp');
  return parsed;
}

function current(value, now) {
  const age = now - timestamp(value);
  return age >= 0 && age <= MAX_AGE_MS;
}

function text(value) {
  if (typeof value !== 'string' || !value.trim()) throw new Error('Missing directory text');
  return value;
}

function safeUrl(value) {
  const url = new URL(text(value));
  if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password) {
    throw new Error('Unsafe source URL');
  }
  return url.href;
}

export function readDirectory(snapshot, now = Date.now()) {
  if (!Number.isFinite(now)) throw new Error('Invalid current time');
  if (!snapshot || snapshot.schema_version !== 1 || !Array.isArray(snapshot.resources)
      || !snapshot.resources.length) throw new Error('Invalid directory snapshot');
  if (!current(snapshot.generated_at, now)) throw new Error('Directory needs a refresh');
  const ids = new Set();
  const resources = snapshot.resources.map(item => {
    if (!item || typeof item !== 'object') throw new Error('Invalid resource');
    const id = text(item.id).trim();
    if (ids.has(id)) throw new Error('Duplicate resource ID');
    ids.add(id);
    if (item.is_sample === true || !CATEGORIES.has(item.category)) throw new Error('Invalid resource');
    if (!current(item.verified_at, now)) throw new Error('Resource needs a refresh');
    if (!Number.isFinite(item.latitude) || Math.abs(item.latitude) > 90
        || !Number.isFinite(item.longitude) || Math.abs(item.longitude) > 180) {
      throw new Error('Invalid resource coordinates');
    }
    // Allowlist directory fields. Ignore any injected availability/hours/open claims.
    return Object.freeze({
      id, name: text(item.name), category: item.category, address: text(item.address),
      latitude: item.latitude, longitude: item.longitude,
      phone: item.phone == null ? null : text(item.phone),
      website: item.website == null ? null : safeUrl(item.website),
      source_name: text(item.source_name), source_url: safeUrl(item.source_url),
      verified_at: item.verified_at,
    });
  });
  return Object.freeze({
    resources: Object.freeze(resources),
    notice: 'Directory information only. Call first; current local help: 211; emergency: 911.',
  });
}

export function filterCategory(directory, category = null) {
  if (category !== null && !CATEGORIES.has(category)) throw new Error('Unsupported category');
  return directory.resources.filter(item => category === null || item.category === category);
}
