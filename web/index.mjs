// DOM glue for the static directory page. All decisions live in the tested
// headless modules: this file only reads form values, copies view text into
// elements with textContent (never HTML string writes), and forwards events. The page
// keeps no state of its own; the directory session owns status and results.
import {createSnapshotReader} from './snapshot-reader.mjs';
import {createDirectorySession} from './directory-session.mjs';
import {createDirectoryLoader} from './directory-loader.mjs';
import {parseLocation} from './location-input.mjs';
import {PAGE_NOTICE, statusMessage, resultView} from './directory-view.mjs';

const elements = {
  form: document.getElementById('search-form'),
  location: document.getElementById('location'),
  category: document.getElementById('category'),
  radius: document.getElementById('radius'),
  status: document.getElementById('status'),
  results: document.getElementById('results'),
  notice: document.getElementById('notice'),
  refresh: document.getElementById('refresh'),
};

const session = createDirectorySession(() => Date.now());

// The reader needs a same-origin HTTP(S) page; opened from the filesystem the
// constructor throws and the page stays fail-closed at "unavailable".
let loader = null;
try {
  // The reader anchors at the origin root; resolve the snapshot against the
  // page URL so it lives next to the page, still same-origin by its check.
  const snapshotUrl = new URL('./directory.json', globalThis.location.href).href;
  loader = createDirectoryLoader(
    session, createSnapshotReader(snapshotUrl, {origin: globalThis.location.origin}));
} catch {
  loader = null;
}

function setText(element, value) {
  element.textContent = value;
}

function field(tag, className, value) {
  const element = document.createElement(tag);
  if (className) element.setAttribute('class', className);
  setText(element, value);
  return element;
}

function link(className, text, href) {
  const element = field('a', className, text);
  element.setAttribute('href', href);
  // Directory links leave the page; never give the target window control back.
  element.setAttribute('rel', 'noopener noreferrer');
  return element;
}

function renderResult(result) {
  const view = resultView(result);
  const item = document.createElement('li');
  item.append(
    field('strong', 'result-name', view.name),
    field('span', 'result-distance', view.distance),
    field('span', 'result-category', view.category),
    field('span', 'result-address', view.address),
  );
  if (view.phone !== null) item.append(link('result-phone', view.phone, view.phoneHref));
  if (view.websiteText !== null) {
    item.append(link('result-website', view.websiteText, view.websiteHref));
  }
  item.append(field('small', 'result-source', view.source));
  return item;
}

function render(state) {
  let message;
  try {
    message = statusMessage(state.status);
  } catch {
    // An unknown status is a bug; fail closed to the unavailable wording.
    message = statusMessage('unavailable');
  }
  setText(elements.status, `${message.heading}. ${message.detail}`);
  elements.results.replaceChildren();
  if (state.status === 'results') {
    try {
      elements.results.replaceChildren(...state.results.map(renderResult));
    } catch {
      setText(elements.status, statusMessage('unavailable').heading);
    }
  }
}

function submitSearch(event) {
  event.preventDefault();
  let point;
  try {
    point = parseLocation(elements.location.value);
  } catch {
    render(session.search(null));
    return;
  }
  // Forward only a finite, positive radius; a corrupted control falls back
  // to the session default rather than bricking the search.
  const radius = Number(elements.radius.value);
  render(session.search({
    latitude: point.latitude,
    longitude: point.longitude,
    category: elements.category.value || null,
    radiusMiles: Number.isFinite(radius) && radius > 0 ? radius : undefined,
  }));
}

setText(elements.notice, PAGE_NOTICE);
elements.form.addEventListener('submit', submitSearch);
elements.refresh.addEventListener('click', () => {
  if (loader) loader.refresh().then(render);
});
render(session.getState());
if (loader) loader.refresh().then(render);
