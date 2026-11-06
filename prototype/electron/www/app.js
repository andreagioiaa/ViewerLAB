'use strict';

const api = window.ViewerLAB;

if (!api) {
    throw new Error('ViewerLAB preload is not available');
}

const STREAMS = {
    hls: 'https://test-streams.mux.dev/x36xhzz/x36xhzz.m3u8',
    mp4: 'https://media.w3.org/2010/05/sintel/trailer.mp4',
};

const elements = {
    mpvPill: document.getElementById('mpv-pill'),
    proxyPill: document.getElementById('proxy-pill'),
    playerPill: document.getElementById('player-pill'),
    proxyBase: document.getElementById('proxy-base'),
    envInfo: document.getElementById('env-info'),
    mpvInfo: document.getElementById('mpv-info'),
    referer: document.getElementById('referer'),
    userAgent: document.getElementById('user-agent'),
    log: document.getElementById('log'),
    startProxy: document.getElementById('start-proxy'),
    stopProxy: document.getElementById('stop-proxy'),
    closePlayer: document.getElementById('close-player'),
    clearLog: document.getElementById('clear-log'),
};

function log(message, kind = 'info') {
    const item = document.createElement('li');
    const time = document.createElement('time');
    time.textContent = new Date().toLocaleTimeString('it-IT', { hour12: false });
    const text = document.createElement('span');
    text.textContent = message;
    if (kind === 'error') {
        text.className = 'error';
    }
    item.append(time, text);
    elements.log.prepend(item);
    while (elements.log.children.length > 120) {
        elements.log.lastElementChild.remove();
    }
}

function formatTime(ms) {
    const total = Math.max(0, Math.round((Number(ms) || 0) / 1000));
    const minutes = Math.floor(total / 60);
    const seconds = total % 60;
    return `${minutes}:${String(seconds).padStart(2, '0')}`;
}

function requestHeaders() {
    const headers = {};
    const referer = elements.referer.value.trim();
    const userAgent = elements.userAgent.value.trim();
    if (referer) headers.Referer = referer;
    if (userAgent) headers['User-Agent'] = userAgent;
    return { referer, userAgent, headers };
}

async function refreshProxyInfo() {
    try {
        const info = await api.proxy.info();
        elements.proxyBase.textContent = info.baseUrl || '—';
        elements.proxyPill.textContent = info.running ? 'proxy: attivo' : 'proxy: off';
        elements.proxyPill.classList.toggle('ok', info.running);
    } catch (error) {
        log(`proxy info: ${error.message}`, 'error');
    }
}

async function ensureProxy() {
    const info = await api.proxy.info();
    if (info.running) {
        return info.baseUrl;
    }
    const baseUrl = await api.proxy.start({ headers: requestHeaders().headers });
    log(`proxy avviato su ${baseUrl}`);
    await refreshProxyInfo();
    return baseUrl;
}

async function playStream(streamKey, mode) {
    const source = STREAMS[streamKey];
    if (!source) {
        log(`stream sconosciuto: ${streamKey}`, 'error');
        return;
    }

    const { referer, userAgent, headers } = requestHeaders();
    let url = source;

    try {
        if (mode === 'proxy') {
            await ensureProxy();
            url = await api.proxy.quote(source);
            log(`proxy quote: ${url}`);
        }

        await api.player.show({
            url,
            title: streamKey === 'hls' ? 'Mux test stream (HLS)' : 'Sintel trailer (MP4)',
            referer: referer || undefined,
            userAgent: userAgent || undefined,
            headers,
        });
        log(`player avviato (${mode}): ${source}`);
        elements.playerPill.textContent = 'player: in avvio';
        elements.playerPill.classList.add('warn');
    } catch (error) {
        log(`impossibile avviare il player: ${error.message}`, 'error');
        elements.playerPill.textContent = 'player: errore';
        elements.playerPill.classList.remove('ok');
        elements.playerPill.classList.add('warn');
    }
}

for (const card of document.querySelectorAll('.card[data-stream]')) {
    const streamKey = card.dataset.stream;
    for (const button of card.querySelectorAll('[data-play]')) {
        button.addEventListener('click', () => {
            playStream(streamKey, button.dataset.play);
        });
    }
}

elements.startProxy.addEventListener('click', async () => {
    try {
        const baseUrl = await api.proxy.start({ headers: requestHeaders().headers });
        log(`proxy avviato: ${baseUrl}`);
        await refreshProxyInfo();
    } catch (error) {
        log(`avvio proxy fallito: ${error.message}`, 'error');
    }
});

elements.stopProxy.addEventListener('click', async () => {
    try {
        await api.proxy.stop();
        log('proxy fermato');
        await refreshProxyInfo();
    } catch (error) {
        log(`stop proxy fallito: ${error.message}`, 'error');
    }
});

elements.closePlayer.addEventListener('click', async () => {
    try {
        await api.player.close();
        log('richiesta chiusura player');
    } catch (error) {
        log(`chiusura player fallita: ${error.message}`, 'error');
    }
});

elements.clearLog.addEventListener('click', () => {
    elements.log.replaceChildren();
});

api.player.onState((state) => {
    if (!state) return;
    const position = formatTime(state.positionMs);
    const duration = formatTime(state.durationMs);
    const flags = [];
    if (state.paused) flags.push('pausa');
    if (state.buffering) flags.push('buffer');
    const suffix = flags.length > 0 ? ` (${flags.join(', ')})` : '';
    elements.playerPill.textContent = `player: ${position} / ${duration}${suffix}`;
    elements.playerPill.classList.remove('warn');
    elements.playerPill.classList.add('ok');
});

api.player.onError((error) => {
    log(`errore player: ${error.message}`, 'error');
});

api.player.onClosed(() => {
    elements.playerPill.textContent = 'player: chiuso';
    elements.playerPill.classList.remove('ok', 'warn');
    log('player chiuso');
});

(async function init() {
    try {
        const info = await api.info();
        elements.mpvPill.textContent = info.mpvAvailable ? 'mpv: trovato' : 'mpv: non trovato';
        elements.mpvPill.classList.add(info.mpvAvailable ? 'ok' : 'warn');
        elements.mpvInfo.textContent = info.mpvBinary;
        elements.envInfo.textContent = `Electron ${info.electron} · Chromium ${info.chrome}`;
        log(`avvio ViewerLAB ${info.version}`);
        if (!info.mpvAvailable) {
            log('mpv non trovato: imposta la variabile MPV_PATH prima di avviare il player.', 'error');
        }
        await refreshProxyInfo();
    } catch (error) {
        log(`init: ${error.message}`, 'error');
    }
})();
