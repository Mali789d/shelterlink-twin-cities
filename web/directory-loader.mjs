// Inject a snapshot reader; this coordinator itself has no endpoint or credentials.
// Prevent out-of-order refreshes from replacing newer data or reviving cleared results.
export function createDirectoryLoader(session, readSnapshot) {
  if (!session || ['beginRefresh', 'replaceSnapshot', 'failRefresh', 'getState']
    .some(method => typeof session[method] !== 'function')) {
    throw new Error('A directory session is required');
  }
  if (typeof readSnapshot !== 'function') throw new Error('A snapshot reader is required');
  let generation = 0;
  let active = null;
  let disposed = false;

  function invalidate() {
    generation += 1;
    active?.abort();
    active = null;
  }

  return Object.freeze({
    async refresh() {
      if (disposed) return session.getState();
      invalidate();
      const request = generation;
      const controller = new AbortController();
      active = controller;
      session.beginRefresh();
      try {
        const snapshot = await readSnapshot({signal: controller.signal});
        if (disposed || generation !== request) return session.getState();
        active = null;
        return session.replaceSnapshot(snapshot);
      } catch {
        if (disposed || generation !== request) return session.getState();
        active = null;
        return session.failRefresh();
      }
    },
    cancel() {
      invalidate();
      return session.failRefresh();
    },
    dispose() {
      disposed = true;
      invalidate();
      return session.failRefresh();
    },
  });
}
