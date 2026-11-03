// Pure view text for the static directory page (web/index.html). No DOM,
// network or storage: every user-facing string is decided here so the DOM
// glue in web/index.mjs only copies text into elements and never formats
// data or invents statuses. English only: the reviewed Spanish/Somali wording
// covers SMS templates, and new unreviewed translation stays out of scope.

// The same safety notice the session state and the exported snapshot carry.
// It must stay identical: the page, the exporter and the SMS replies all point
// to 211/911, and one wording is easier to keep reviewed.
export const PAGE_NOTICE =
  'Directory information only. Call first; current local help: 211; emergency: 911.';

// Always visible, above any listing: the page is local-test groundwork, not a
// launched referral service, and it only ever shows a fresh verified export.
export const PROTOTYPE_BANNER =
  'Local-test prototype. Listings appear only from a fresh, verified directory '
  + 'export. This page is not a live referral service.';

// One message per session status (web/directory-session.mjs). Unknown statuses
// throw instead of rendering a guess: a page that cannot describe its state
// must fail closed to "unavailable" at the glue layer, never improvise text.
const STATUS_MESSAGES = Object.freeze({
  unavailable: Object.freeze({
    heading: 'Directory unavailable',
    detail: 'No current verified directory is loaded. '
      + 'For current local help call 211; emergency 911.',
  }),
  loading: Object.freeze({
    heading: 'Loading the directory',
    detail: 'Fetching the current verified export. Previous results are cleared first.',
  }),
  refresh_required: Object.freeze({
    heading: 'Directory needs a refresh',
    detail: 'The loaded export is no longer current, so its listings are hidden. '
      + 'Refresh to load a fresh one. For current local help call 211; emergency 911.',
  }),
  ready: Object.freeze({
    heading: 'Directory loaded',
    detail: 'Enter a Twin Cities ZIP, city, neighborhood or "latitude, longitude" to search.',
  }),
  results: Object.freeze({
    heading: 'Nearest resources',
    detail: 'Call first when possible; hours and space can change.',
  }),
  no_matches: Object.freeze({
    heading: 'No matching resources',
    detail: 'Nothing in the current directory matches within the search area. '
      + 'For current local help call 211; emergency 911.',
  }),
  invalid_search: Object.freeze({
    heading: 'Search not understood',
    detail: 'Enter latitude, longitude, or a Twin Cities metro ZIP or city. '
      + 'The page never guesses a location.',
  }),
});

export function statusMessage(status) {
  // Own-property read: a '__proto__' status must throw, not resolve to an
  // inherited Object member as if it were a known state (same guard as
  // web/zip-lookup.mjs lookupNormalized).
  if (typeof status !== 'string' || !Object.hasOwn(STATUS_MESSAGES, status)) {
    throw new Error(`Unknown directory status: ${String(status)}`);
  }
  return STATUS_MESSAGES[status];
}

// Category values come from the validated directory; labels are display-only.
const CATEGORY_LABELS = Object.freeze({
  shelter: 'Shelter',
  meal: 'Meal',
  warming: 'Warming center',
  shower: 'Shower',
});

function requireText(value, label) {
  if (typeof value !== 'string' || !value.trim()) throw new Error(`Invalid ${label}`);
  return value;
}

// A tel: link target is only ever the dialable number the directory validated.
// Re-check the same dialable shape as the server model and web/directory.mjs
// before stripping: arbitrary text must never shrink into a dialable fragment.
const DIALABLE_PHONE = /^\+?\(?[0-9][0-9().\- ]{1,27}[0-9](?: ?(?:x|ext\.?) ?[0-9]{1,6})?$/;
export function phoneHref(phone) {
  requireText(phone, 'phone');
  if (!DIALABLE_PHONE.test(phone)) throw new Error('Invalid phone');
  return `tel:${phone.replace(/[^0-9+x]/gi, '')}`;
}

// One result row as plain view data. The resource passed the fail-closed
// checks in web/directory.mjs readDirectory; the defensive re-checks here keep
// a malformed caller from crashing the page into a blank listing.
export function resultView(result) {
  if (!result || typeof result !== 'object' || !result.resource) {
    throw new Error('Invalid result');
  }
  const {resource} = result;
  if (!Number.isFinite(result.distanceMiles) || result.distanceMiles < 0) {
    throw new Error('Invalid distance');
  }
  const label = CATEGORY_LABELS[resource.category];
  if (!label) throw new Error('Invalid category');
  // verified_at passed the exporter's strict ISO check; show its date portion.
  const verified = requireText(resource.verified_at, 'verification date').slice(0, 10);
  const view = {
    name: requireText(resource.name, 'name'),
    distance: `${result.distanceMiles.toFixed(1)} mi`,
    category: label,
    address: requireText(resource.address, 'address'),
    phone: resource.phone === null ? null : requireText(resource.phone, 'phone'),
    phoneHref: resource.phone === null ? null : phoneHref(resource.phone),
    // Show the host, not the full URL: recognizable, and the validated href
    // still carries the exact link.
    websiteText: resource.website === null ? null : new URL(resource.website).host,
    websiteHref: resource.website === null ? null : resource.website,
    source: `Source: ${requireText(resource.source_name, 'source name')} - verified ${verified}`,
  };
  return Object.freeze(view);
}
