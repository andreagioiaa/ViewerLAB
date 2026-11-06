'use strict';

/**
 * Preload for the main window.
 *
 * Exposes a small, explicit API. The demo page uses window.ViewerLAB; the
 * ExoPlayer shim at the bottom is optional and only there to make a compatible
 * web front-end work without touching its playback code.
 */

const { contextBridge, ipcRenderer } = require('electron');

function subscribe(channel, callback) {
    const listener = (_event, payload) => callback(payload);
    ipcRenderer.on(channel, listener);
    return () => ipcRenderer.removeListener(channel, listener);
}

contextBridge.exposeInMainWorld('ViewerLAB', {
    info: () => ipcRenderer.invoke('app:info'),

    player: {
        show: (options) => ipcRenderer.invoke('player:show', options),
        setStream: (options) => ipcRenderer.invoke('player:set-stream', options),
        seekTo: (seconds) => ipcRenderer.invoke('player:seek-to', seconds),
        seekBy: (deltaSeconds) => ipcRenderer.invoke('player:seek-by', deltaSeconds),
        togglePlay: () => ipcRenderer.invoke('player:toggle-play'),
        setPaused: (paused) => ipcRenderer.invoke('player:set-paused', paused),
        getState: () => ipcRenderer.invoke('player:get-state'),
        close: () => ipcRenderer.invoke('player:close'),
        onState: (callback) => subscribe('player:state', callback),
        onEvent: (callback) => subscribe('player:event', callback),
        onError: (callback) => subscribe('player:error', callback),
        onClosed: (callback) => subscribe('player:closed', callback),
    },

    proxy: {
        start: (options) => ipcRenderer.invoke('proxy:start', options),
        stop: () => ipcRenderer.invoke('proxy:stop'),
        info: () => ipcRenderer.invoke('proxy:info'),
        quote: (url) => ipcRenderer.invoke('proxy:quote', url),
        setToken: (query, patterns) => ipcRenderer.invoke('proxy:set-token', query, patterns),
        startRefresh: (options) => ipcRenderer.invoke('proxy:start-refresh', options),
        stopRefresh: () => ipcRenderer.invoke('proxy:stop-refresh'),
    },
});

// ---------------------------------------------------------------------------
// Optional compatibility shim: legacy Cordova-style stats bridge
// ---------------------------------------------------------------------------
// The method names match the bridge a Cordova-era front-end normally calls.
// All of them route to this prototype's loopback proxy.

contextBridge.exposeInMainWorld('stats', {
    proxy(headers, success, error) {
        ipcRenderer.invoke('stats-proxy', headers)
            .then((baseUrl) => { if (success) success(baseUrl); })
            .catch((err) => { if (error) error(err.message); });
    },
    stopProxy(success, error) {
        ipcRenderer.invoke('stats-stop-proxy')
            .then((value) => { if (success) success(value); })
            .catch((err) => { if (error) error(err.message); });
    },
    setHlsToken(query, patterns, success, error) {
        ipcRenderer.invoke('stats-set-hls-token', query, patterns)
            .then((value) => { if (success) success(value); })
            .catch((err) => { if (error) error(err.message); });
    },
    startNativeHlsRefresh(tokenUrl, headers, patterns, success, error) {
        ipcRenderer.invoke('stats-start-hls-refresh', tokenUrl, headers, patterns)
            .then((value) => { if (success) success(value); })
            .catch((err) => { if (error) error(err.message); });
    },
    stopNativeHlsRefresh(success, error) {
        ipcRenderer.invoke('stats-stop-hls-refresh')
            .then((value) => { if (success) success(value); })
            .catch((err) => { if (error) error(err.message); });
    },
});

// ---------------------------------------------------------------------------
// Optional compatibility shim
// ---------------------------------------------------------------------------
// Mirrors the small subset of the Cordova ExoPlayer bridge that a web front-end
// normally calls. It is presentation-agnostic: no provider or site logic.

let exoEventCallback = null;
let exoErrorCallback = null;

ipcRenderer.on('player:state', (_event, state) => {
    if (exoEventCallback) {
        exoEventCallback({
            event: 'state',
            position: state.positionMs,
            duration: state.durationMs,
            paused: state.paused,
            buffering: state.buffering,
        });
    }
});

ipcRenderer.on('player:error', (_event, error) => {
    if (exoErrorCallback) {
        exoErrorCallback({ errorMessage: error.message });
    }
});

contextBridge.exposeInMainWorld('ExoPlayer', {
    show(parameters, successCallback, errorCallback) {
        const options = typeof parameters === 'string' ? { url: parameters } : (parameters || {});
        exoEventCallback = successCallback || null;
        exoErrorCallback = errorCallback || null;
        return ipcRenderer.invoke('player:show', {
            url: options.url || options.streamUrl,
            title: options.title,
            referer: options.referer,
            userAgent: options.userAgent,
            headers: options.headers,
            startPosition: options.position || options.startPosition,
        }).catch((error) => {
            if (exoErrorCallback) {
                exoErrorCallback({ errorMessage: error.message });
            }
        });
    },

    setStream(url, _controller, successCallback, errorCallback) {
        exoEventCallback = successCallback || exoEventCallback;
        exoErrorCallback = errorCallback || exoErrorCallback;
        return ipcRenderer.invoke('player:set-stream', { url });
    },

    seekTo(seconds) {
        return ipcRenderer.invoke('player:seek-to', seconds);
    },

    seekBy(deltaSeconds) {
        return ipcRenderer.invoke('player:seek-by', deltaSeconds);
    },

    playPause() {
        return ipcRenderer.invoke('player:toggle-play');
    },

    getState() {
        return ipcRenderer.invoke('player:get-state');
    },

    hide() {
        return ipcRenderer.invoke('player:close');
    },
});
