// UI-independent fail-closed state for a future directory page. No network/storage.
import {readDirectory, nearbyResources} from './directory.mjs';

const NOTICE = 'Directory information only. Call first; current local help: 211; emergency: 911.';

export function createDirectorySession(clock = Date.now) {
  if (typeof clock !== 'function') throw new Error('A clock function is required');
  let directory = null;
  let options = null;
  let status = 'unavailable';
  const empty = Object.freeze([]);
  const state = (value, results = empty) => Object.freeze({status: value, results, notice: NOTICE});

  function clear(value) {
    directory = null;
    status = value;
    return state(status);
  }

  function getState() {
    if (!directory) return state(status);
    try {
      const now = clock();
      // A zero-distance search also exercises the full directory freshness gate.
      const results = nearbyResources(directory, options
        ? {...options, now} : {latitude: 0, longitude: 0, now});
      if (!options) return state('ready');
      return state(results.length ? 'results' : 'no_matches', results);
    } catch {
      return clear('refresh_required');
    }
  }

  return Object.freeze({
    // Call before fetching a replacement. Previous results disappear immediately.
    beginRefresh() { return clear('loading'); },
    // A failed refresh never resurrects the last successful directory.
    failRefresh() { return clear('unavailable'); },
    replaceSnapshot(snapshot) {
      try {
        directory = readDirectory(snapshot, clock());
        status = 'ready';
      } catch {
        return clear('unavailable');
      }
      return getState();
    },
    search(input) {
      // Copy only supported scalar options; later caller mutation cannot change state.
      options = input && {latitude: input.latitude, longitude: input.longitude,
        category: input.category, radiusMiles: input.radiusMiles, limit: input.limit};
      if (!options) return state('invalid_search');
      if (!directory) return state(status);
      try {
        nearbyResources(directory, {...options, now: clock()});
      } catch {
        // Distinguish invalid input from an expired directory without preserving results.
        try {
          nearbyResources(directory, {latitude: 0, longitude: 0, now: clock()});
        } catch {
          return clear('refresh_required');
        }
        options = null;
        return state('invalid_search');
      }
      return getState();
    },
    getState,
  });
}
