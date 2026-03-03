/* Metron - Server-Sent Events (SSE) Connection Manager
 *
 * Production-ready:
 *  - Exponential backoff with jitter on reconnect
 *  - Max reconnect attempts before giving up (auto-resets on success)
 *  - Handles 401 / auth errors gracefully (redirects to login)
 *  - Reconnects when browser tab becomes visible again
 *  - Handles server-sent `reconnect: true` signal (connection age limit)
 *  - Connection state exposed for UI status indicators
 *  - Supports direct Cloud Run SSE (bypasses Firebase Hosting CDN buffering)
 *    via short-lived signed tokens
 */

class SSEConnectionManager {
  constructor(eventUrl = '/api/events', {
    baseReconnectDelay = 1000,   // initial reconnect delay (ms)
    maxReconnectDelay  = 30000,  // cap on backoff (ms)
    maxRetries         = 50,     // give up after this many consecutive failures
  } = {}) {
    this.eventUrl = eventUrl;
    this.baseReconnectDelay = baseReconnectDelay;
    this.maxReconnectDelay = maxReconnectDelay;
    this.maxRetries = maxRetries;

    // Direct Cloud Run SSE config (set via window.__SSE_CONFIG__)
    const sseConfig = window.__SSE_CONFIG__;
    this._directBaseUrl = sseConfig?.baseUrl || '';
    this._sseToken = '';  // fetched on demand via /api/sse-token

    this.eventSource = null;
    this.messageHandlers = [];
    this.errorHandlers = [];
    this._retryCount = 0;
    this._reconnectTimer = null;
    this._destroyed = false;
    this._boundVisibilityHandler = this._onVisibilityChange.bind(this);
  }

  /* ---- Public API ---- */

  /** Register a callback for incoming SSE data objects. */
  onMessage(handler) {
    this.messageHandlers.push(handler);
  }

  /** Register a callback for fatal / auth errors (receives {type, message}). */
  onError(handler) {
    this.errorHandlers.push(handler);
  }

  /** Open the SSE connection (idempotent). */
  async connect() {
    if (this._destroyed) return;
    this._clearReconnectTimer();

    // Close any existing connection
    if (this.eventSource) {
      this.eventSource.close();
      this.eventSource = null;
    }

    // Build the SSE URL — use direct Cloud Run URL + token if available,
    // otherwise fall back to relative URL (for direct Cloud Run access or local dev)
    let url = this.eventUrl;
    if (this._directBaseUrl) {
      // Refresh the token before each connection (tokens are short-lived)
      await this._refreshToken();
      if (this._sseToken) {
        url = `${this._directBaseUrl}${this.eventUrl}?token=${encodeURIComponent(this._sseToken)}`;
      }
      // If token refresh failed, fall back to relative URL (might work if
      // accessed directly on Cloud Run, won't work through Firebase CDN)
    }

    console.log('[SSE] Connecting to', url === this.eventUrl ? this.eventUrl : 'direct Cloud Run');
    this.eventSource = new EventSource(url);

    this.eventSource.onopen = () => {
      console.log('[SSE] Connection established');
      this._retryCount = 0; // reset backoff on successful connect
    };

    this.eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);

        // Server asks us to reconnect (connection age limit reached)
        if (data.reconnect) {
          console.log('[SSE] Server requested reconnect');
          this.eventSource.close();
          this._scheduleReconnect();
          return;
        }

        // Server-side client limit exceeded
        if (data.error === 'too_many_connections') {
          console.warn('[SSE] Too many connections — will retry later');
          this.eventSource.close();
          this._scheduleReconnect();
          return;
        }

        this.messageHandlers.forEach(handler => {
          try {
            handler(data);
          } catch (err) {
            console.error('[SSE] Handler error:', err);
          }
        });
      } catch (err) {
        console.error('[SSE] Parse error:', err);
      }
    };

    this.eventSource.onerror = (_event) => {
      // EventSource fires onerror for both transient and fatal failures.
      // readyState === CLOSED means the browser gave up (e.g. 401, CORS).
      const isClosed = this.eventSource.readyState === EventSource.CLOSED;

      if (isClosed) {
        console.warn('[SSE] Connection closed');
        this._handleAuthCheck();
      } else {
        // CONNECTING — browser is auto-retrying, but we layer our own
        // backoff on top in case the browser's retry is too aggressive.
        console.warn('[SSE] Connection error — scheduling reconnect');
        this.eventSource.close();
        this._scheduleReconnect();
      }
    };

    // Listen for tab visibility changes
    document.removeEventListener('visibilitychange', this._boundVisibilityHandler);
    document.addEventListener('visibilitychange', this._boundVisibilityHandler);
  }

  /** Cleanly shut down the connection (no further reconnects). */
  disconnect() {
    this._destroyed = true;
    this._clearReconnectTimer();
    document.removeEventListener('visibilitychange', this._boundVisibilityHandler);
    if (this.eventSource) {
      this.eventSource.close();
      this.eventSource = null;
      console.log('[SSE] Disconnected');
    }
  }

  /* ---- Internal ---- */

  /** Fetch a fresh SSE token from the backend (goes through Firebase Hosting). */
  async _refreshToken() {
    try {
      const fetchFn = window.metronFetch || fetch;
      const resp = await fetchFn('/api/sse-token', { credentials: 'same-origin' });
      if (resp.ok) {
        const data = await resp.json();
        this._sseToken = data.token || '';
      } else if (resp.status === 401) {
        console.warn('[SSE] Token refresh failed — not authenticated');
        this._sseToken = '';
      } else {
        console.warn('[SSE] Token refresh failed — status', resp.status);
      }
    } catch (err) {
      console.warn('[SSE] Token refresh network error:', err.message);
      // Keep existing token (may still be valid)
    }
  }

  _scheduleReconnect() {
    if (this._destroyed) return;
    this._retryCount++;

    if (this._retryCount > this.maxRetries) {
      console.error(`[SSE] Max retries (${this.maxRetries}) exceeded — giving up`);
      this._emitError('max_retries', 'Unable to establish real-time connection. Please reload the page.');
      return;
    }

    // Exponential backoff with jitter: delay = min(base * 2^n + jitter, max)
    const exp = Math.min(this.baseReconnectDelay * Math.pow(2, this._retryCount - 1), this.maxReconnectDelay);
    const jitter = Math.random() * 1000;
    const delay = Math.round(exp + jitter);

    console.log(`[SSE] Reconnecting in ${delay}ms (attempt ${this._retryCount}/${this.maxRetries})`);
    this._clearReconnectTimer();
    this._reconnectTimer = setTimeout(() => this.connect(), delay);
  }

  _clearReconnectTimer() {
    if (this._reconnectTimer) {
      clearTimeout(this._reconnectTimer);
      this._reconnectTimer = null;
    }
  }

  /** If the connection was rejected, check whether the user is still authenticated. */
  async _handleAuthCheck() {
    try {
      const resp = await fetch('/api/auth/me', {
        headers: { 'X-Requested-With': 'MetronApp' },
        credentials: 'same-origin',
      });
      if (resp.status === 401) {
        console.warn('[SSE] Session expired — redirecting to login');
        this._emitError('auth', 'Session expired. Redirecting to login...');
        // Give UI a moment to show toast before redirect
        setTimeout(() => { window.location.href = '/'; }, 1500);
        return;
      }
    } catch (_) {
      // Network error — fall through to reconnect
    }
    this._scheduleReconnect();
  }

  _onVisibilityChange() {
    if (document.visibilityState === 'visible' && !this._destroyed) {
      // Tab became visible — ensure connection is alive
      if (!this.eventSource || this.eventSource.readyState === EventSource.CLOSED) {
        console.log('[SSE] Tab visible — reconnecting');
        this._retryCount = 0;
        this.connect();
      }
    }
  }

  _emitError(type, message) {
    this.errorHandlers.forEach(handler => {
      try {
        handler({ type, message });
      } catch (err) {
        console.error('[SSE] Error handler threw:', err);
      }
    });
  }
}

export default SSEConnectionManager;
