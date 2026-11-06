'use strict';

/**
 * MpvManager
 * ----------
 * Owns one mpv child process and talks to it over mpv's JSON IPC protocol
 * (newline-delimited JSON on a Windows named pipe, or a Unix socket).
 *
 * This is a clean-room implementation: it only uses the public mpv IPC
 * documented in DOCS/man/ipc.rst. No code from the analyzed application is
 * reproduced here.
 */

const { spawn } = require('node:child_process');
const { EventEmitter } = require('node:events');
const crypto = require('node:crypto');
const fs = require('node:fs');
const net = require('node:net');
const os = require('node:os');
const path = require('node:path');

const OBSERVED_PROPERTIES = [
    'time-pos',
    'duration',
    'pause',
    'idle-active',
    'eof-reached',
    'video-params/w',
    'video-params/h',
    'video-bitrate',
    'paused-for-cache',
    'media-title',
];

function defaultBinaryPath() {
    if (process.env.MPV_PATH) {
        return path.resolve(process.env.MPV_PATH);
    }
    const exe = process.platform === 'win32' ? 'mpv.exe' : 'mpv';
    const bundled = path.join(__dirname, 'bin', exe);
    if (fs.existsSync(bundled)) {
        return bundled;
    }
    return exe; // resolved through PATH by spawn()
}

function defaultPipeName() {
    const suffix = crypto.randomBytes(4).toString('hex');
    if (process.platform === 'win32') {
        return `\\\\.\\pipe\\viewerlab-mpv-${process.pid}-${suffix}`;
    }
    return path.join(os.tmpdir(), `viewerlab-mpv-${process.pid}-${suffix}.sock`);
}

class MpvManager extends EventEmitter {
    constructor(options = {}) {
        super();
        // Spawn failures are also surfaced through start()'s rejection; this
        // listener prevents an unhandled 'error' event from crashing the host
        // when the consumer does not subscribe.
        this.on('error', () => {});
        this.binaryPath = options.binaryPath || defaultBinaryPath();
        this.pipeName = options.pipeName || defaultPipeName();
        this.extraArgs = Array.isArray(options.extraArgs) ? options.extraArgs : [];
        this._process = null;
        this._socket = null;
        this._connected = false;
        this._buffer = '';
        this._nextRequestId = 1;
        this._pending = new Map();
        this._closing = false;
        this._properties = {
            'time-pos': 0,
            'duration': 0,
            pause: false,
            'idle-active': true,
            'eof-reached': false,
            'video-params/w': 0,
            'video-params/h': 0,
            'video-bitrate': 0,
            'paused-for-cache': false,
            'media-title': '',
        };
    }

    isAvailable() {
        if (path.isAbsolute(this.binaryPath)) {
            return fs.existsSync(this.binaryPath);
        }
        return true; // let spawn() resolve it from PATH
    }

    get isRunning() {
        return this._process !== null && this._connected;
    }

    /**
     * Start mpv and connect to its IPC endpoint.
     * Resolves once commands can be sent.
     */
    async start() {
        if (this._process) {
            return;
        }
        this._closing = false;

        const args = [
            `--input-ipc-server=${this.pipeName}`,
            '--idle=once',
            '--force-window=yes',
            '--fullscreen',
            '--keepaspect',
            '--keep-open=yes',
            '--osc=no',
            '--no-terminal',
            '--hr-seek=yes',
            '--volume=100',
            '--sub-auto=no',
            '--cursor-autohide=1000',
            '--title=ViewerLAB Player',
            '--focus-on=never',
            '--demuxer-lavf-o=protocol_whitelist=[file,http,https,tcp,tls,crypto,data]',
            ...this.extraArgs,
        ];

        const child = spawn(this.binaryPath, args, {
            stdio: 'ignore',
            windowsHide: true,
        });
        this._process = child;

        child.on('error', (error) => {
            if (this._process !== child) return;
            this.emit('error', error);
            this._reset();
        });

        child.on('exit', (code, signal) => {
            if (this._process !== child) return;
            const wasClosing = this._closing;
            this._reset();
            if (!wasClosing) {
                this.emit('quit', { code, signal });
            }
        });

        try {
            await this._connectWithRetry();
        } catch (error) {
            this._kill();
            this._reset();
            throw error;
        }

        for (let i = 0; i < OBSERVED_PROPERTIES.length; i += 1) {
            await this._send(['observe_property', i + 1, OBSERVED_PROPERTIES[i]]).catch(() => {});
        }
    }

    /**
     * Load a media URL, optionally with per-request HTTP headers.
     * @param {string} url
     * @param {{referer?: string, userAgent?: string, headers?: Record<string,string>}} [options]
     */
    async load(url, options = {}) {
        if (!url) {
            throw new Error('load() requires a URL');
        }

        const fields = [];
        const seen = new Set();
        const push = (name, value) => {
            if (!value) return;
            if (/[\r\n:]/.test(name) || /[\r\n]/.test(String(value))) {
                throw new Error(`Invalid HTTP header: ${name}`);
            }
            const key = name.toLowerCase();
            if (seen.has(key)) return;
            seen.add(key);
            fields.push(`${name}: ${value}`);
        };

        push('User-Agent', options.userAgent);
        push('Referer', options.referer);
        for (const [name, value] of Object.entries(options.headers || {})) {
            push(name, value);
        }

        await this.setProperty('http-header-fields', fields);
        await this._send(['loadfile', url, 'replace']);
    }

    async setProperty(name, value) {
        return this._send(['set_property', name, value]);
    }

    async getProperty(name) {
        return this._send(['get_property', name]);
    }

    async seekTo(seconds) {
        const target = Math.max(0, Number(seconds) || 0);
        return this._send(['seek', target, 'absolute+exact']);
    }

    async seekBy(deltaSeconds) {
        const delta = Number(deltaSeconds) || 0;
        return this._send(['seek', delta, 'relative']);
    }

    async togglePause() {
        return this._send(['cycle', 'pause']);
    }

    async setPause(paused) {
        return this.setProperty('pause', Boolean(paused));
    }

    getState() {
        const p = this._properties;
        return {
            positionMs: Math.max(0, Number(p['time-pos']) || 0) * 1000,
            durationMs: Math.max(0, Number(p.duration) || 0) * 1000,
            paused: Boolean(p.pause),
            idle: Boolean(p['idle-active']),
            eof: Boolean(p['eof-reached']),
            videoWidth: Number(p['video-params/w']) || 0,
            videoHeight: Number(p['video-params/h']) || 0,
            videoBitrate: Number(p['video-bitrate']) || 0,
            buffering: Boolean(p['paused-for-cache']),
            title: p['media-title'] || '',
            connected: this._connected,
        };
    }

    async quit() {
        this._closing = true;
        if (this._connected) {
            try {
                await this._send(['quit']);
            } catch {
                this._kill();
            }
        } else {
            this._kill();
        }
        this._reset();
    }

    /**
     * Synchronous teardown for app shutdown paths where awaiting is not possible.
     */
    destroy() {
        this._closing = true;
        this._kill();
        this._reset();
    }

    // ---------------------------------------------------------------------
    // IPC internals
    // ---------------------------------------------------------------------

    _connectWithRetry() {
        const maxAttempts = 60;
        let attempt = 0;

        return new Promise((resolve, reject) => {
            let settled = false;

            const tryOnce = () => {
                attempt += 1;
                const socket = net.connect(this.pipeName);

                const onConnectError = () => {
                    socket.destroy();
                    if (settled) {
                        return;
                    }
                    if (!this._process) {
                        settled = true;
                        reject(new Error(`mpv process exited before IPC was ready (${this.binaryPath})`));
                        return;
                    }
                    if (attempt >= maxAttempts) {
                        settled = true;
                        reject(new Error(`Unable to connect to mpv IPC endpoint "${this.pipeName}"`));
                        return;
                    }
                    setTimeout(tryOnce, 100);
                };

                socket.once('error', onConnectError);
                socket.once('connect', () => {
                    settled = true;
                    socket.removeListener('error', onConnectError);
                    this._socket = socket;
                    this._connected = true;
                    this._buffer = '';
                    socket.setEncoding('utf8');
                    socket.on('data', (chunk) => this._onData(chunk));
                    socket.on('error', () => {
                        this._connected = false;
                    });
                    socket.on('close', () => {
                        this._connected = false;
                        if (!this._closing) {
                            this.emit('disconnected');
                        }
                    });
                    resolve();
                });
            };

            tryOnce();
        });
    }

    _onData(chunk) {
        this._buffer += chunk;
        let newlineIndex = this._buffer.indexOf('\n');
        while (newlineIndex !== -1) {
            const line = this._buffer.slice(0, newlineIndex).trim();
            this._buffer = this._buffer.slice(newlineIndex + 1);
            if (line) {
                try {
                    this._onMessage(JSON.parse(line));
                } catch {
                    // mpv occasionally emits partial/non-JSON output; ignore it.
                }
            }
            newlineIndex = this._buffer.indexOf('\n');
        }
    }

    _onMessage(message) {
        if (typeof message.request_id === 'number') {
            const pending = this._pending.get(message.request_id);
            if (pending) {
                this._pending.delete(message.request_id);
                clearTimeout(pending.timer);
                if (message.error === 'success') {
                    pending.resolve(message.data);
                } else {
                    pending.reject(new Error(message.error || 'mpv command failed'));
                }
            }
            return;
        }

        if (!message.event) {
            return;
        }

        this.emit('event', message);

        if (message.event === 'property-change' && message.name) {
            this._properties[message.name] = message.data;
            if (message.name === 'time-pos' || message.name === 'pause' ||
                message.name === 'paused-for-cache' || message.name === 'duration') {
                this.emit('state', this.getState());
            }
            this.emit('property-change', message.name, message.data);
        } else if (message.event === 'file-loaded') {
            this.emit('file-loaded');
            this.emit('state', this.getState());
        } else if (message.event === 'end-file') {
            this.emit('end-file', message.reason || 'unknown');
        } else if (message.event === 'seek') {
            this.emit('seek');
        }
    }

    _send(command, timeoutMs = 5000) {
        return new Promise((resolve, reject) => {
            if (!this._connected || !this._socket) {
                reject(new Error('mpv IPC is not connected'));
                return;
            }

            const requestId = this._nextRequestId;
            this._nextRequestId += 1;

            const timer = setTimeout(() => {
                this._pending.delete(requestId);
                reject(new Error(`mpv command timed out: ${command[0]}`));
            }, timeoutMs);
            if (typeof timer.unref === 'function') {
                timer.unref();
            }

            this._pending.set(requestId, { resolve, reject, timer });

            try {
                this._socket.write(`${JSON.stringify({ command, request_id: requestId })}\n`);
            } catch (error) {
                this._pending.delete(requestId);
                clearTimeout(timer);
                reject(error);
            }
        });
    }

    _kill() {
        if (this._process) {
            try {
                this._process.kill();
            } catch {
                // already gone
            }
        }
    }

    _reset() {
        this._connected = false;
        if (this._socket) {
            try {
                this._socket.destroy();
            } catch {
                // ignore
            }
            this._socket = null;
        }
        this._process = null;
        this._buffer = '';
        for (const pending of this._pending.values()) {
            clearTimeout(pending.timer);
            pending.reject(new Error('mpv process ended'));
        }
        this._pending.clear();
        this._properties = {
            'time-pos': 0,
            'duration': 0,
            pause: false,
            'idle-active': true,
            'eof-reached': false,
            'video-params/w': 0,
            'video-params/h': 0,
            'video-bitrate': 0,
            'paused-for-cache': false,
            'media-title': '',
        };
    }
}

module.exports = { MpvManager };
