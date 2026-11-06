'use strict';

/**
 * End-to-end check for the loopback HLS proxy using a public test stream.
 * Run with: npm run smoke
 */

const { HlsProxy } = require('../hls-proxy');

const MASTER = 'https://test-streams.mux.dev/x36xhzz/x36xhzz.m3u8';

function urisOf(manifest) {
    return manifest
        .split(/\r?\n/)
        .map((line) => line.trim())
        .filter((line) => line !== '' && !line.startsWith('#'));
}

async function main() {
    const proxy = new HlsProxy();
    const base = await proxy.start();
    console.log('proxy:', base);

    try {
        const masterResponse = await fetch(proxy.quote(MASTER));
        const master = await masterResponse.text();
        assert(masterResponse.ok, `master HTTP ${masterResponse.status}`);
        assert(master.includes('#EXTM3U'), 'master is not an HLS manifest');

        const variants = urisOf(master);
        assert(variants.length > 0, 'master has no variants');
        assert(variants.every((uri) => uri.includes('/p/')), 'variant URIs were not rewritten');

        const variantResponse = await fetch(variants[0]);
        const variant = await variantResponse.text();
        assert(variantResponse.ok, `variant HTTP ${variantResponse.status}`);
        assert(variant.includes('#EXTM3U'), 'variant is not an HLS manifest');

        const segments = urisOf(variant);
        assert(segments.length > 0, 'variant has no segments');
        assert(segments.every((uri) => uri.includes('/p/')), 'segment URIs were not rewritten');

        const segmentResponse = await fetch(segments[0], {
            headers: { Range: 'bytes=0-2047' },
        });
        const bytes = await segmentResponse.arrayBuffer();
        assert(segmentResponse.ok, `segment HTTP ${segmentResponse.status}`);
        assert(bytes.byteLength > 0, 'segment is empty');

        console.log('variants:', variants.length);
        console.log('segments:', segments.length);
        console.log('segment bytes:', bytes.byteLength);
        console.log('content-range:', segmentResponse.headers.get('content-range'));
        console.log('SMOKE OK');
    } finally {
        proxy.stop();
    }
}

function assert(condition, message) {
    if (!condition) {
        throw new Error(message);
    }
}

main().catch((error) => {
    console.error('SMOKE FAILED:', error.message);
    process.exitCode = 1;
});
