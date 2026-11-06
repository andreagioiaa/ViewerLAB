'use strict';

/**
 * ViewerLAB prototype — main process.
 *
 * Flow:
 *   renderer (demo page or a configured web app)
 *     -> IPC
 *     -> MpvManager (mpv over JSON IPC)
 *     -> optional HlsProxy (loopback manifest/segment proxy)
 *
 * The transparent overlay window sits above mpv and owns the transport
 * controls. mpv is a regular fullscreen window of its own.
 */

const { app, BrowserWindow, ipcMain, Menu, screen, shell } = require('electron');
const path = require('node:path');

const { MpvManager } = require('./mpv-manager');
const { HlsProxy } = require('./hls-proxy');

const REMOTE_URL = process.env.VIEWERLAB_URL || '';
const USE_DEMO_PAGE = REMOTE_URL.length === 0;

let mainWindow = null;
let overlayWindow = null;
let mpv = null;
let proxy = null;
let stateTimer = null;
let closing = false;

// ---------------------------------------------------------------------------
// Windows / lifecycle
// ---------------------------------------------------------------------------

function createMainWindow() {
    mainWindow = new BrowserWindow({
        width: 1280,
        height: 800,
        minWidth: 900,
        minHeight: 600,
        title: 'ViewerLAB',
        backgroundColor: '#101014',
        autoHideMenuBar: true,
        show: false,
        webPreferences: {
            preload: path.join(__dirname, 'preload.js'),
            contextIsolation: true,
            nodeIntegration: false,
            sandbox: false,
            spellcheck: false,
        },
    });

    mainWindow.once('ready-to-show', () => mainWindow.show());

    mainWindow.webContents.setWindowOpenHandler(({ url }) => {
        shell.openExternal(url);
        return { action: 'deny' };
    });

    if (USE_DEMO_PAGE) {
        mainWindow.loadFile(path.join(__dirname, 'www', 'index.html'));
    } else {
        mainWindow.loadURL(REMOTE_URL);
    }

    mainWindow.on('closed', () => {
        mainWindow = null;
        closePlayer().catch(() => {});
    });
}

function getMpv() {
    if (!mpv) {
        mpv = new MpvManager();
        mpv.on('state', (state) => broadcast('player:state', state));
        mpv.on('file-loaded', () => broadcast('player:event', { type: 'file-loaded' }));
        mpv.on('end-file', (reason) => broadcast('player:event', { type: 'end-file', reason }));
        mpv.on('error', (error) => broadcast('player:error', { message: error.message }));
        mpv.on('quit', () => {
            if (!closing) {
                closePlayer().catch(() => {});
            }
        });
    }
    return mpv;
}

function getProxy() {
    if (!proxy) {
        proxy = new HlsProxy({
            allowPrivateHosts: process.env.VIEWERLAB_ALLOW_PRIVATE === '1',
            insecureTls: process.env.VIEWERLAB_INSECURE_TLS === '1',
        });
    }
    return proxy;
}

function createOverlay(title) {
    if (overlayWindow && !overlayWindow.isDestroyed()) {
        overlayWindow.show();
        return overlayWindow;
    }

    const display = screen.getDisplayMatching(
        mainWindow && !mainWindow.isDestroyed()
            ? mainWindow.getBounds()
            : screen.getPrimaryDisplay().bounds,
    );
    const { x, y, width, height } = display.bounds;

    overlayWindow = new BrowserWindow({
        x,
        y,
        width,
        height,
        transparent: true,
        frame: false,
        resizable: false,
        movable: false,
        minimizable: false,
        maximizable: false,
        fullscreenable: false,
        skipTaskbar: true,
        alwaysOnTop: true,
        hasShadow: false,
        backgroundColor: '#00000000',
        show: false,
        webPreferences: {
            preload: path.join(__dirname, 'player-preload.js'),
            contextIsolation: true,
            nodeIntegration: false,
            sandbox: false,
        },
    });

    overlayWindow.setAlwaysOnTop(true, 'screen-saver');
    overlayWindow.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true });
    overlayWindow.loadFile(path.join(__dirname, 'player-overlay.html'), {
        query: { title: title || '' },
    });
    overlayWindow.once('ready-to-show', () => overlayWindow.show());
    overlayWindow.on('closed', () => {
        overlayWindow = null;
        stopStateLoop();
        closePlayer().catch(() => {});
    });

    return overlayWindow;
}

function broadcast(channel, payload) {
    for (const win of [mainWindow, overlayWindow]) {
        if (win && !win.isDestroyed()) {
            win.webContents.send(channel, payload);
        }
    }
}

function startStateLoop() {
    stopStateLoop();
    stateTimer = setInterval(() => {
        if (!mpv || !mpv.isRunning) {
            return;
        }
        broadcast('player:state', mpv.getState());
    }, 400);
    if (typeof stateTimer.unref === 'function') {
        stateTimer.unref();
    }
}

function stopStateLoop() {
    if (stateTimer) {
        clearInterval(stateTimer);
        stateTimer = null;
    }
}

function teardownPlayerWindows() {
    stopStateLoop();
    if (overlayWindow && !overlayWindow.isDestroyed()) {
        overlayWindow.close();
    }
    overlayWindow = null;
}

async function closePlayer() {
    if (closing) {
        return;
    }
    closing = true;
    stopStateLoop();
    try {
        if (mpv) {
            await mpv.quit();
        }
    } catch {
        // ignore
    }
    teardownPlayerWindows();
    broadcast('player:closed', {});
    closing = false;
}

async function startProxy(options = {}) {
    const instance = getProxy();
    if (options.headers) {
        instance.setHeaders(options.headers);
    }
    if (Object.prototype.hasOwnProperty.call(options, 'token')) {
        instance.setToken(options.token);
    }
    return instance.start();
}

// ---------------------------------------------------------------------------
// IPC
// ---------------------------------------------------------------------------

function registerIpc() {
    ipcMain.handle('app:info', () => {
        const manager = getMpv();
        return {
            version: app.getVersion(),
            electron: process.versions.electron,
            chrome: process.versions.chrome,
            node: process.versions.node,
            demoPage: USE_DEMO_PAGE,
            appUrl: USE_DEMO_PAGE ? null : REMOTE_URL,
            mpvAvailable: manager.isAvailable(),
            mpvBinary: manager.binaryPath,
            proxyBaseUrl: proxy ? proxy.baseUrl : null,
        };
    });

    ipcMain.handle('player:show', async (_event, options = {}) => {
        const url = options.url;
        if (!url) {
            throw new Error('player:show requires a url');
        }

        const manager = getMpv();
        if (!manager.isAvailable()) {
            throw new Error(
                `mpv not found at "${manager.binaryPath}". Set MPV_PATH to the mpv executable.`,
            );
        }

        await manager.start();
        createOverlay(options.title);
        startStateLoop();

        if (Number(options.startPosition) > 0) {
            await manager.setProperty('start', Number(options.startPosition)).catch(() => {});
        }

        await manager.load(url, {
            referer: options.referer,
            userAgent: options.userAgent,
            headers: options.headers,
        });

        return manager.getState();
    });

    ipcMain.handle('player:set-stream', async (_event, options = {}) => {
        const manager = getMpv();
        await manager.load(options.url, {
            referer: options.referer,
            userAgent: options.userAgent,
            headers: options.headers,
        });
        return manager.getState();
    });

    ipcMain.handle('player:seek-to', async (_event, seconds) => {
        await getMpv().seekTo(seconds);
    });

    ipcMain.handle('player:seek-by', async (_event, deltaSeconds) => {
        await getMpv().seekBy(deltaSeconds);
    });

    ipcMain.handle('player:toggle-play', async () => {
        await getMpv().togglePause();
    });

    ipcMain.handle('player:set-paused', async (_event, paused) => {
        await getMpv().setPause(Boolean(paused));
    });

    ipcMain.handle('player:get-state', () => {
        return mpv ? mpv.getState() : null;
    });

    ipcMain.handle('player:close', async () => {
        await closePlayer();
    });

    ipcMain.handle('proxy:start', async (_event, options = {}) => {
        return startProxy(options);
    });

    ipcMain.handle('proxy:start-refresh', async (_event, options = {}) => {
        const instance = getProxy();
        instance.startRefresh(options.tokenUrl, options.headers || {}, options.patterns || []);
        return true;
    });

    ipcMain.handle('proxy:stop-refresh', () => {
        if (proxy) {
            proxy.stopRefresh();
        }
        return true;
    });

    ipcMain.handle('proxy:set-token', (_event, query, patterns) => {
        getProxy().setToken({ query, patterns });
        return true;
    });

    ipcMain.handle('proxy:stop', () => {
        if (proxy) {
            proxy.stop();
        }
        return null;
    });

    ipcMain.handle('proxy:info', () => {
        return {
            running: Boolean(proxy && proxy.running),
            baseUrl: proxy ? proxy.baseUrl : null,
        };
    });

    ipcMain.handle('proxy:quote', (_event, url) => {
        if (!proxy || !proxy.running) {
            throw new Error('proxy is not running');
        }
        return proxy.quote(String(url));
    });

    // Compatibility bridge: same method names a Cordova-era front-end expects.
    ipcMain.handle('stats-proxy', async (_event, headers) => {
        return startProxy({ headers: headers || {} });
    });

    ipcMain.handle('stats-stop-proxy', () => {
        if (proxy) {
            proxy.stop();
        }
        return true;
    });

    ipcMain.handle('stats-set-hls-token', (_event, query, patterns) => {
        getProxy().setToken({ query, patterns: patterns || [] });
        return true;
    });

    ipcMain.handle('stats-start-hls-refresh', (_event, tokenUrl, headers, patterns) => {
        getProxy().startRefresh(tokenUrl, headers || {}, patterns || []);
        return true;
    });

    ipcMain.handle('stats-stop-hls-refresh', () => {
        if (proxy) {
            proxy.stopRefresh();
        }
        return true;
    });
}

// ---------------------------------------------------------------------------
// Bootstrap
// ---------------------------------------------------------------------------

app.commandLine.appendSwitch('autoplay-policy', 'no-user-gesture-required');
app.commandLine.appendSwitch('disable-features', 'CrossOriginOpenerPolicy,CrossOriginEmbedderPolicy');

const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
    app.quit();
} else {
    app.on('second-instance', () => {
        if (mainWindow) {
            if (mainWindow.isMinimized()) mainWindow.restore();
            mainWindow.focus();
        }
    });

    app.whenReady().then(() => {
        registerIpc();

        Menu.setApplicationMenu(Menu.buildFromTemplate([
            {
                label: 'ViewerLAB',
                submenu: [
                    { role: 'reload' },
                    { role: 'toggleDevTools' },
                    { type: 'separator' },
                    { role: 'quit' },
                ],
            },
        ]));

        createMainWindow();

        app.on('activate', () => {
            if (BrowserWindow.getAllWindows().length === 0) {
                createMainWindow();
            }
        });
    });

    app.on('window-all-closed', () => {
        if (process.platform !== 'darwin') {
            app.quit();
        }
    });

    app.on('will-quit', () => {
        stopStateLoop();
        if (proxy) {
            proxy.stop();
        }
        if (mpv) {
            mpv.destroy();
        }
    });
}
