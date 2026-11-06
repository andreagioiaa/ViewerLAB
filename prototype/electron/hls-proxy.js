'use strict';

/**
 * HlsProxy
 * --------
 * A loopback-only HTTP helper for HLS playback.
 *
 * Responsibilities:
 *   - expose a random, unguessable local path (so other local processes cannot
 *     piggyback on it);
 *   - fetch manifests and rewrite every URI so segments are fetched back
 *     through the proxy (useful when a CDN requires the same headers/query for
 *     every request);
 *   - pass Range requests through unchanged so seeking works;
 *   - optionally append a rotating query token to matching CDN URLs;
 *   - refuse non-HTTP(S) and (by default) private/loopback targets.
 *
 * It deliberately contains no provider-specific logic. The caller decides the
 * headers, the token and which public stream to play.
 */

const crypto = require('node:crypto');
const http = require('node:http');
const https = require('node:https');
const net = require('node:net');
const { URL } = require('node:url');

const DEFAULT_USER_AGENT =
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 ' +
    '(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36';

const MANIFEST_MAX_BYTES = 8 * 1024 * 1024;
const UPSTREAM_TIMEOUT_MS = 20000;

function isPrivateHost(hostname) {
    const host = hostname.toLowerCase().replace(/^\[|\]$/g, '');
    if (host === 'localhost' || host.endsWith('.localhost')) {
        return true;
    }
    if (host === '::1' || host === '0.0.0.0') {
        return true;
    }
    if (!net.isIPv4(host)) {
        // IPv6 unique-local (fc00::/7) and link-local (fe80::/10)
        return host.startsWith('fc') || host.startsWith('fd') || host.startsWith('fe8') ||
            host.startsWith('fe9') || host.startsWith('fea') || host.startsWith('feb');
    }
    const parts = host.split('.').map(Number);
    const [a, b] = parts;
    return a === 10 || a === 127 || a === 0 ||
        (a === 169 && b === 254) ||
        (a === 172 && b >= 16 && b <= 31) ||
        (a === 192 && b === 168) ||
        (a === 100 && b >= 64 && b <= 127);
}

class HlsProxy {
    constructor(options = {}) {
        this.allowPrivateHosts = Boolean(options.allowPrivateHosts);
        this.insecureTls = Boolean(options.insecureTls);
        this.defaultHeaders = options.headers || {};

        this._server = null;
        this._secret = null;
        this._port = 0;
        this._baseUrl = null;

        this._token = null; // { query: '?t=...', patterns: ['cdn.example'] }

        this._refresh = {
            active: false,
            timer: null,
            url: null,
            headers: {},
            patterns: [],
        };
    }

    get baseUrl() {
        return this._baseUrl;
    }

    get running() {
        return this._server !== null;
    }

    /**
     * Start the loopback server (idempotent).
     * @returns {Promise<string>} base URL, e.g. http://127.0.0.1:53211/p/<secret>/
     */
    start() {
        if (this._server && this._baseUrl) {
            return Promise.resolve(this._baseUrl);
        }

        this._secret = crypto.randomBytes(16).toString('hex');

        return new Promise((resolve, reject) => {
            const server = http.createServer((req, res) => {
                this._handle(req, res).catch((error) => {
                    this._fail(res, 500, 'proxy error');
                    this._log('handler error:', error.message);
                });
            });

            server.on('error', (error) => {
                this._log('server error:', error.message);
                if (!this._baseUrl) {
                    reject(error);
                }
            });

            server.listen(0, '127.0.0.1', () => {
                this._server = server;
                this._port = server.address().port;
                this._baseUrl = `http://127.0.0.1:${this._port}/p/${this._secret}/`;
                this._log(`listening on ${this._baseUrl}`);
                resolve(this._baseUrl);
            });
        });
    }

    stop() {
        this.stopRefresh();
        if (this._server) {
            try {
                this._server.close();
                if (typeof this._server.closeAllConnections === 'function') {
                    this._server.closeAllConnections();
                }
            } catch {
                // ignore
            }
        }
        this._server = null;
        this._port = 0;
        this._baseUrl = null;
        this._secret = null;
        this._log('stopped');
    }

    /**
     * Update the optional request headers used for upstream fetches.
     */
    setHeaders(headers) {
        this.defaultHeaders = headers || {};
    }

    /**
     * Set (or clear) a query token appended to matching upstream URLs.
     * @param {{query: string, patterns: string[]}|null} token
     */
    setToken(token) {
        if (!token || !token.query) {
            this._token = null;
            return;
        }
        this._token = {
            query: token.query.startsWith('?') ? token.query : `?${token.query}`,
            patterns: Array.isArray(token.patterns) ? token.patterns.filter(Boolean) : [],
        };
    }

    /**
     * Start a generic token refresh loop.
     *
     * The endpoint must be supplied by the caller and return JSON containing
     * `url` or `hls` (plus an optional `expire`, in seconds or milliseconds).
     * Only the query string is reused; this method knows nothing about any
     * provider.
     *
     * @param {string} tokenUrl
     * @param {Record<string,string>} [headers]
     * @param {string[]} [patterns]
     */
    startRefresh(tokenUrl, headers = {}, patterns = []) {
        this.stopRefresh();

        let target;
        try {
            target = new URL(tokenUrl);
        } catch {
            throw new Error('startRefresh() requires a valid URL');
        }
        if (target.protocol !== 'http:' && target.protocol !== 'https:') {
            throw new Error('startRefresh() only supports http and https');
        }
        if (!this.allowPrivateHosts && isPrivateHost(target.hostname)) {
            throw new Error('startRefresh() refuses private endpoints');
        }

        this._refresh = {
            active: true,
            timer: null,
            url: tokenUrl,
            headers,
            patterns,
        };
        this._scheduleRefresh(0);
    }

    stopRefresh() {
        this._refresh.active = false;
        if (this._refresh.timer) {
            clearTimeout(this._refresh.timer);
            this._refresh.timer = null;
        }
    }

    _scheduleRefresh(delayMs) {
        if (!this._refresh.active) {
            return;
        }
        this._refresh.timer = setTimeout(() => this._refreshOnce(), delayMs);
        if (typeof this._refresh.timer.unref === 'function') {
            this._refresh.timer.unref();
        }
    }

    async _refreshOnce() {
        if (!this._refresh.active) {
            return;
        }

        let nextDelay = 120000;
        try {
            const body = await this._fetchText(this._refresh.url, this._refresh.headers);
            const data = JSON.parse(body);
            const nextUrl = data.url || data.hls || data.stream || '';
            const queryIndex = nextUrl.indexOf('?');

            if (queryIndex >= 0) {
                const query = nextUrl.slice(queryIndex);
                this.setToken({ query, patterns: this._refresh.patterns });
                const match = query.match(/[?&](?:e|exp|expire)=(\d+)/);
                if (match) {
                    nextDelay = this._delayFromExpire(match[1]);
                }
            }

            if (data.expire || data.expires || data.exp) {
                nextDelay = this._delayFromExpire(data.expire || data.expires || data.exp);
            }
        } catch (error) {
            this._log('token refresh failed:', error.message);
            nextDelay = 60000;
        }

        if (this._refresh.active) {
            this._scheduleRefresh(nextDelay);
        }
    }

    _delayFromExpire(rawValue) {
        let value = Number(rawValue);
        if (!Number.isFinite(value)) {
            return 120000;
        }
        if (value < 1e12) {
            value *= 1000; // seconds -> milliseconds
        }
        const remaining = value - Date.now() - 30000;
        return Math.min(600000, Math.max(5000, remaining));
    }

    /**
     * Wrap a remote stream URL so it is fetched through this proxy.
     */
    quote(targetUrl) {
        if (!this._baseUrl) {
            throw new Error('HLS proxy is not running');
        }
        return `${this._baseUrl}playlist?url=${encodeURIComponent(targetUrl)}`;
    }

    // ---------------------------------------------------------------------
    // Request handling
    // ---------------------------------------------------------------------

    async _handle(req, res) {
        const requestUrl = new URL(req.url, `http://127.0.0.1:${this._port}`);

        if (!requestUrl.pathname.startsWith(`/p/${this._secret}/`)) {
            this._fail(res, 404, 'not found');
            return;
        }

        if (req.method !== 'GET' && req.method !== 'HEAD') {
            this._fail(res, 405, 'method not allowed');
            return;
        }

        const rawTarget = requestUrl.searchParams.get('url');
        if (!rawTarget) {
            this._fail(res, 400, 'missing url parameter');
            return;
        }

        let target;
        try {
            target = new URL(rawTarget);
        } catch {
            this._fail(res, 400, 'invalid url parameter');
            return;
        }

        if (target.protocol !== 'http:' && target.protocol !== 'https:') {
            this._fail(res, 400, 'only http and https are supported');
            return;
        }
        if (!this.allowPrivateHosts && isPrivateHost(target.hostname)) {
            this._fail(res, 403, 'private targets are disabled');
            return;
        }

        const upstreamUrl = this._injectToken(target.toString());
        const headers = this._requestHeaders(req);

        const upstream = await this._request(upstreamUrl, headers, req.headers.range);
        const status = upstream.statusCode || 502;
        const upstreamType = String(upstream.headers['content-type'] || '').toLowerCase();

        const manifest = this._looksLikeManifest(target, upstreamType);

        if (manifest && status < 400) {
            const body = await this._readBody(upstream, MANIFEST_MAX_BYTES);
            if (body === null) {
                this._fail(res, 502, 'manifest too large');
                return;
            }
            const text = body.toString('utf8');
            const rewritten = text.includes('#EXTM3U')
                ? this._rewriteManifest(text, target.toString())
                : text;
            const payload = Buffer.from(rewritten, 'utf8');
            res.writeHead(200, {
                'Content-Type': 'application/vnd.apple.mpegurl; charset=utf-8',
                'Content-Length': payload.length,
                'Cache-Control': 'no-store',
                'Access-Control-Allow-Origin': '*',
            });
            res.end(req.method === 'HEAD' ? undefined : payload);
            return;
        }

        // Segment / media response: stream it back with Range semantics intact.
        const responseHeaders = { 'Access-Control-Allow-Origin': '*' };
        for (const name of [
            'content-type',
            'content-length',
            'content-range',
            'accept-ranges',
            'cache-control',
            'last-modified',
            'etag',
        ]) {
            if (upstream.headers[name]) {
                responseHeaders[name] = upstream.headers[name];
            }
        }

        res.writeHead(status, responseHeaders);

        if (req.method === 'HEAD') {
            upstream.resume();
            res.end();
            return;
        }

        upstream.pipe(res);
        upstream.on('error', () => {
            try {
                res.destroy();
            } catch {
                // ignore
            }
        });
        res.on('close', () => {
            upstream.destroy();
        });
    }

    _requestHeaders(req) {
        const headers = {
            'User-Agent': DEFAULT_USER_AGENT,
            Accept: '*/*',
            ...this.defaultHeaders,
        };
        if (req.headers.range) {
            headers.Range = req.headers.range;
        }
        return headers;
    }

    _looksLikeManifest(target, contentType) {
        const path = target.pathname.toLowerCase();
        return path.endsWith('.m3u8') ||
            path.endsWith('.m3u') ||
            contentType.includes('mpegurl') ||
            contentType.includes('vnd.apple.mpegurl');
    }

    _injectToken(targetUrl) {
        if (!this._token) {
            return targetUrl;
        }
        const matchesAll = this._token.patterns.includes('*');
        if (!matchesAll && this._token.patterns.length === 0) {
            return targetUrl;
        }
        if (!matchesAll && !this._token.patterns.every((pattern) => targetUrl.includes(pattern))) {
            return targetUrl;
        }
        const withoutQuery = targetUrl.split('?')[0];
        return withoutQuery + this._token.query;
    }

    _rewriteManifest(body, manifestUrl) {
        const lines = body.split(/\r?\n/);
        const output = [];

        for (const line of lines) {
            const trimmed = line.trim();

            if (trimmed === '') {
                output.push('');
                continue;
            }

            if (trimmed.startsWith('#')) {
                output.push(this._rewriteAttributes(line, manifestUrl));
                continue;
            }

            // URI line: a variant playlist, a media segment or a key file.
            output.push(this.quote(new URL(trimmed, manifestUrl).toString()));
        }

        return output.join('\n');
    }

    _rewriteAttributes(line, manifestUrl) {
        return line.replace(/URI="([^"]+)"/g, (_match, uri) => {
            const absolute = new URL(uri, manifestUrl).toString();
            return `URI="${this.quote(absolute)}"`;
        });
    }

    _request(url, headers, rangeHeader, redirectsLeft = 5) {
        return new Promise((resolve, reject) => {
            let target;
            try {
                target = new URL(url);
            } catch (error) {
                reject(error);
                return;
            }

            const requestHeaders = { ...headers };
            if (rangeHeader) {
                requestHeaders.Range = rangeHeader;
            }

            const transport = target.protocol === 'http:' ? http : https;
            const request = transport.request({
                protocol: target.protocol,
                hostname: target.hostname,
                port: target.port || (target.protocol === 'http:' ? 80 : 443),
                path: target.pathname + target.search,
                method: 'GET',
                headers: requestHeaders,
                rejectUnauthorized: !this.insecureTls,
            }, (response) => {
                const status = response.statusCode || 0;
                const location = response.headers.location;
                if (status >= 300 && status < 400 && location && redirectsLeft > 0) {
                    response.resume();
                    const next = new URL(location, url).toString();
                    this._request(next, headers, rangeHeader, redirectsLeft - 1)
                        .then(resolve, reject);
                    return;
                }
                resolve(response);
            });

            request.on('error', reject);
            request.setTimeout(UPSTREAM_TIMEOUT_MS, () => {
                request.destroy(new Error('upstream timeout'));
            });
            request.end();
        });
    }

    async _fetchText(url, headers) {
        const response = await this._request(url, headers || {});
        if ((response.statusCode || 0) >= 400) {
            response.resume();
            throw new Error(`upstream returned HTTP ${response.statusCode}`);
        }
        const body = await this._readBody(response, MANIFEST_MAX_BYTES);
        if (body === null) {
            throw new Error('upstream response is too large');
        }
        return body.toString('utf8');
    }

    _readBody(stream, limit) {
        return new Promise((resolve) => {
            const chunks = [];
            let size = 0;
            let settled = false;

            const finish = (value) => {
                if (settled) return;
                settled = true;
                resolve(value);
            };

            stream.on('data', (chunk) => {
                size += chunk.length;
                if (size > limit) {
                    stream.destroy();
                    finish(null);
                    return;
                }
                chunks.push(chunk);
            });
            stream.on('end', () => finish(Buffer.concat(chunks)));
            stream.on('error', () => finish(Buffer.concat(chunks)));
        });
    }

    _fail(res, status, message) {
        if (res.headersSent) {
            try {
                res.destroy();
            } catch {
                // ignore
            }
            return;
        }
        res.writeHead(status, {
            'Content-Type': 'text/plain; charset=utf-8',
            'Cache-Control': 'no-store',
        });
        res.end(message);
    }

    _log(...args) {
        if (process.env.VIEWERLAB_DEBUG) {
            console.log('[hls-proxy]', ...args);
        }
    }
}

module.exports = { HlsProxy };
