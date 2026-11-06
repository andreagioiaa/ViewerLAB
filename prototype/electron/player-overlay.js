'use strict';

/**
 * Transparent overlay renderer: transport controls for the mpv window below.
 */

const api = window.Player;

const overlay = document.getElementById('overlay');
const titleElement = document.getElementById('title');
const playButton = document.getElementById('play-button');
const playIcon = document.getElementById('play-icon');
const pauseIcon = document.getElementById('pause-icon');
const backButton = document.getElementById('back-button');
const forwardButton = document.getElementById('forward-button');
const closeButton = document.getElementById('close-button');
const timeline = document.getElementById('timeline');
const currentTime = document.getElementById('current-time');
const durationTime = document.getElementById('duration');
const meta = document.getElementById('meta');
const spinner = document.getElementById('spinner');

const HIDE_DELAY_MS = 3000;

let durationMs = 0;
let dragging = false;
let hideTimer = null;
let lastState = null;

function formatTime(ms) {
    const total = Math.max(0, Math.round((Number(ms) || 0) / 1000));
    const hours = Math.floor(total / 3600);
    const minutes = Math.floor((total % 3600) / 60);
    const seconds = total % 60;
    if (hours > 0) {
        return `${hours}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
    }
    return `${minutes}:${String(seconds).padStart(2, '0')}`;
}

function showControls() {
    overlay.classList.remove('idle');
    if (hideTimer) {
        clearTimeout(hideTimer);
    }
    hideTimer = setTimeout(() => {
        if (!lastState || !lastState.paused) {
            overlay.classList.add('idle');
        }
    }, HIDE_DELAY_MS);
}

function renderState(state) {
    if (!state) return;
    lastState = state;
    durationMs = state.durationMs || 0;

    const position = Math.min(state.positionMs || 0, durationMs || state.positionMs || 0);
    if (!dragging) {
        timeline.value = String(position);
        timeline.max = String(Math.max(1000, durationMs || 1000));
        const progress = durationMs > 0 ? (position / durationMs) * 100 : 0;
        timeline.style.setProperty('--progress', `${progress}%`);
        currentTime.textContent = formatTime(position);
    }

    durationTime.textContent = formatTime(durationMs);
    playIcon.hidden = !state.paused;
    pauseIcon.hidden = state.paused;
    spinner.hidden = !state.buffering;

    const bits = [];
    if (state.videoWidth && state.videoHeight) {
        bits.push(`${state.videoWidth}×${state.videoHeight}`);
    }
    if (state.videoBitrate) {
        bits.push(`${Math.round(state.videoBitrate / 1000)} kb/s`);
    }
    if (state.paused) {
        bits.push('pausa');
    }
    meta.textContent = bits.join(' · ');

    if (state.paused) {
        overlay.classList.remove('idle');
    }
}

const titleFromQuery = new URLSearchParams(window.location.search).get('title');
if (titleFromQuery) {
    titleElement.textContent = titleFromQuery;
}

if (api) {
    api.onState(renderState);
    api.onClosed(() => window.close());
    api.getState().then(renderState).catch(() => {});
}

playButton.addEventListener('click', () => api && api.togglePlay());
backButton.addEventListener('click', () => api && api.seekBy(-10));
forwardButton.addEventListener('click', () => api && api.seekBy(10));
closeButton.addEventListener('click', () => api && api.close());

timeline.addEventListener('pointerdown', () => {
    dragging = true;
});

timeline.addEventListener('input', () => {
    const position = Number(timeline.value) || 0;
    currentTime.textContent = formatTime(position);
    const progress = durationMs > 0 ? (position / durationMs) * 100 : 0;
    timeline.style.setProperty('--progress', `${progress}%`);
});

timeline.addEventListener('change', () => {
    dragging = false;
    if (api) {
        api.seekTo((Number(timeline.value) || 0) / 1000);
    }
});

document.addEventListener('mousemove', showControls);
document.addEventListener('mousedown', showControls);

document.addEventListener('keydown', (event) => {
    if (!api) return;
    if (event.key === 'Escape') {
        api.close();
    } else if (event.key === ' ' || event.code === 'Space') {
        event.preventDefault();
        api.togglePlay();
    } else if (event.key === 'ArrowLeft') {
        api.seekBy(-10);
    } else if (event.key === 'ArrowRight') {
        api.seekBy(10);
    }
    showControls();
});

window.addEventListener('focus', showControls);
showControls();
