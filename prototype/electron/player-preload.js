'use strict';

/**
 * Preload for the transparent overlay window.
 */

const { contextBridge, ipcRenderer } = require('electron');

function subscribe(channel, callback) {
    const listener = (_event, payload) => callback(payload);
    ipcRenderer.on(channel, listener);
    return () => ipcRenderer.removeListener(channel, listener);
}

contextBridge.exposeInMainWorld('Player', {
    seekTo: (seconds) => ipcRenderer.invoke('player:seek-to', seconds),
    seekBy: (deltaSeconds) => ipcRenderer.invoke('player:seek-by', deltaSeconds),
    togglePlay: () => ipcRenderer.invoke('player:toggle-play'),
    getState: () => ipcRenderer.invoke('player:get-state'),
    close: () => ipcRenderer.invoke('player:close'),
    onState: (callback) => subscribe('player:state', callback),
    onClosed: (callback) => subscribe('player:closed', callback),
});
