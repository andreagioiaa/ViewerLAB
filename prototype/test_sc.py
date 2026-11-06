import sys
sys.path.insert(0, '.')
import httpx, json, re, html as html_lib
from urllib.parse import quote_plus

headers_std = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,*/*;q=0.8',
    'Accept-Language': 'it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7',
}

base = 'https://streamingcommunityz.boo'

with httpx.Client(follow_redirects=True, timeout=30.0) as client:
    # Prendi versione inertia
    r0 = client.get(base + '/it', headers=headers_std)
    html_text = r0.text
    m = re.findall(r'data-page="([^"]+)"', html_text)
    decoded = html_lib.unescape(m[0])
    jd = json.loads(decoded)
    inertia_version = jd.get('version', '1')
    
    print('Inertia version:', inertia_version)
    
    # Ricerca tramite Inertia
    xsrf = client.cookies.get('XSRF-TOKEN', '')
    headers_inertia = {
        **headers_std,
        'Accept': 'application/json, */*',
        'X-Inertia': 'true',
        'X-Inertia-Version': inertia_version,
        'Referer': base + '/it',
        'X-XSRF-TOKEN': xsrf,
    }
    
    r2 = client.get(base + '/it/search?q=forrest', headers=headers_inertia)
    print(f'Inertia search -> {r2.status_code}')
    if r2.status_code == 200:
        jres = r2.json()
        # La risposta NON ha "props" ma è direttamente la risposta paginata
        print('Keys:', list(jres.keys()))
        if 'data' in jres:
            data = jres['data']
            print(f'Found {len(data)} results:')
            for item in data[:5]:
                title = item.get('name') or item.get('title', '')
                slug = item.get('slug', '')
                id_ = item.get('id', '')
                type_ = item.get('type', '')
                score = item.get('score', '')
                print(f'  - [{id_}] {title} ({type_}) score={score} -> /it/titles/{id_}-{slug}')
    
    # Alternativa: ricerca HTML con estrazione Inertia
    r3 = client.get(base + '/it/search?q=forrest', headers=headers_std)
    if r3.status_code == 200:
        html3 = r3.text
        m3 = re.findall(r'data-page="([^"]+)"', html3)
        if m3:
            jd3 = json.loads(html_lib.unescape(m3[0]))
            props3 = jd3.get('props', {})
            titles = props3.get('titles', [])
            print(f'\nHTML+Inertia search found {len(titles)} results:')
            for t in titles[:5]:
                name = t.get('name', '')
                id_ = t.get('id', '')
                slug = t.get('slug', '')
                type_ = t.get('type', '')
                poster_imgs = t.get('images', [])
                poster = poster_imgs[0].get('filename', '') if poster_imgs else ''
                print(f'  [{id_}] {name} ({type_}) -> /it/titles/{id_}-{slug}')
                if poster:
                    print(f'       poster: {poster}')
