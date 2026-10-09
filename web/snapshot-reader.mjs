// Bounded same-origin snapshot reads for a future static page. No polling/retries.
const DEFAULT_MAX_BYTES = 1024 * 1024;

export function createSnapshotReader(url, {origin, fetchImpl = globalThis.fetch,
  maxBytes = DEFAULT_MAX_BYTES, timeoutMs = 10000} = {}) {
  const base = new URL(origin);
  const target = new URL(url, base);
  if (!['https:', 'http:'].includes(base.protocol) || target.origin !== base.origin
      || target.username || target.password || target.hash) {
    throw new Error('A same-origin HTTP(S) snapshot URL is required');
  }
  if (typeof fetchImpl !== 'function' || !Number.isInteger(maxBytes) || maxBytes < 1
      || maxBytes > DEFAULT_MAX_BYTES || !Number.isInteger(timeoutMs) || timeoutMs < 1
      || timeoutMs > 60000) throw new Error('Invalid reader limits');

  return async function readSnapshot({signal} = {}) {
    const controller = new AbortController();
    let reader = null;
    let timer;
    let abortHandler;
    const stopped = new Promise((_, reject) => {
      abortHandler = () => {
        controller.abort();
        reject(new Error('Snapshot read canceled or timed out'));
      };
      signal?.addEventListener('abort', abortHandler, {once: true});
      timer = setTimeout(abortHandler, timeoutMs);
    });
    const work = async () => {
      if (signal?.aborted) throw new Error('Snapshot read canceled');
      const response = await fetchImpl(target.href, {signal: controller.signal,
        credentials: 'omit', redirect: 'error', cache: 'no-store',
        headers: {Accept: 'application/json'}});
      if (controller.signal.aborted) throw new Error('Snapshot read canceled');
      if (!response.ok || response.redirected) throw new Error('Snapshot request failed');
      const type = response.headers.get('content-type')?.split(';')[0].trim().toLowerCase();
      if (type !== 'application/json') throw new Error('Snapshot must be JSON');
      const length = response.headers.get('content-length');
      if (length !== null && (!/^\d+$/.test(length) || Number(length) > maxBytes)) {
        throw new Error('Snapshot exceeds read limit');
      }
      if (!response.body || typeof response.body.getReader !== 'function') {
        throw new Error('A streaming response body is required');
      }
      reader = response.body.getReader();
      const chunks = [];
      let size = 0;
      while (true) {
        if (controller.signal.aborted) throw new Error('Snapshot read canceled');
        const {done, value} = await reader.read();
        if (done) break;
        if (!(value instanceof Uint8Array)) throw new Error('Invalid snapshot bytes');
        size += value.byteLength;
        if (size > maxBytes) throw new Error('Snapshot exceeds read limit');
        chunks.push(value);
      }
      const bytes = new Uint8Array(size);
      let offset = 0;
      for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.byteLength; }
      return JSON.parse(new TextDecoder('utf-8', {fatal: true}).decode(bytes));
    };
    try {
      return await Promise.race([work(), stopped]);
    } finally {
      clearTimeout(timer);
      signal?.removeEventListener('abort', abortHandler);
      controller.abort();
      // Cancellation is best-effort; never wait forever on a stalled stream.
      if (reader) {
        try { Promise.resolve(reader.cancel()).catch(() => {}); } catch { /* best-effort cleanup */ }
      }
    }
  };
}
