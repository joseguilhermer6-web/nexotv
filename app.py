from flask import Flask, jsonify, render_template_string, request
import json
import os
import sqlite3
import re
import time
import threading
import urllib.request
from urllib.parse import urlsplit

app = Flask(__name__)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CATALOGO_PATH = os.path.join(BASE_DIR, 'catalogo_canais.json')


CONTEUDO_INICIAL = [{'nome': 'Cultura HD Ao Vivo', 'categoria': 'Canais Públicos', 'tipo': 'live', 'logo': 'https://wikimedia.org', 'fontes': 'https://jmvstream.com'}, {'nome': 'Record News HD', 'categoria': 'Notícias', 'tipo': 'live', 'logo': 'https://wikimedia.org', 'fontes': 'https://amazonaws.com'}, {'nome': 'CNN Brasil', 'categoria': 'Notícias', 'tipo': 'live', 'logo': 'https://wikimedia.org', 'fontes': 'https://cnnbrasil.com.br'}, {'nome': 'Dragon Ball (1986) - Clássico Full', 'categoria': 'StrefaDB (mainSite5)', 'tipo': 'anime', 'logo': 'https://wikimedia.org', 'fontes': 'https://googleapis.com'}, {'nome': 'Dragon Ball Z - Completo', 'categoria': 'StrefaDB (mainSite5)', 'tipo': 'anime', 'logo': 'https://wikimedia.org', 'fontes': 'https://googleapis.com'}, {'nome': 'Dragon Ball Super - Sagas', 'categoria': 'StrefaDB (mainSite5)', 'tipo': 'anime', 'logo': 'https://wikimedia.org', 'fontes': 'https://googleapis.com'}, {'nome': 'Naruto Shippuden - Lista de Episódios', 'categoria': 'AnimeOnline (mainSite2)', 'tipo': 'anime', 'logo': 'https://wikimedia.org', 'fontes': 'https://googleapis.com'}, {'nome': 'One Piece - Wano Arc', 'categoria': 'AnimeZone (mainSite7)', 'tipo': 'anime', 'logo': 'https://wikimedia.org', 'fontes': 'https://googleapis.com'}, {'nome': 'Bleach - Thousand-Year Blood War', 'categoria': 'Anime-Odcinki (mainSite4)', 'tipo': 'anime', 'logo': 'https://wikimedia.org', 'fontes': 'https://googleapis.com'}, {'nome': 'Attack on Titan (Shingeki no Kyojin)', 'categoria': 'Senpai (mainSite10)', 'tipo': 'anime', 'logo': 'https://wikimedia.org', 'fontes': 'https://googleapis.com'}, {'nome': 'Demon Slayer (Kimetsu no Yaiba)', 'categoria': 'Anime-Joy (mainSite3)', 'tipo': 'anime', 'logo': 'https://wikimedia.org', 'fontes': 'https://googleapis.com'}, {'nome': 'Dragon Ball Super: Broly - O Filme', 'categoria': 'Filmes Anime', 'tipo': 'movie', 'logo': 'https://wikimedia.org', 'fontes': 'https://googleapis.com'}, {'nome': 'Your Name (Kimi no Na wa)', 'categoria': 'Filmes Anime', 'tipo': 'movie', 'logo': 'https://wikimedia.org', 'fontes': 'https://googleapis.com'}]

def atualizar_banco_dados_completo():
    """Restore the bundled example catalog explicitly."""
    with open(CATALOGO_PATH, 'w', encoding='utf-8') as arquivo:
        json.dump(CONTEUDO_INICIAL, arquivo, indent=4, ensure_ascii=False)


def carregar_conteudo():
    if not os.path.exists(CATALOGO_PATH):
        return CONTEUDO_INICIAL
    with open(CATALOGO_PATH, encoding='utf-8') as arquivo:
        return json.load(arquivo)


RDC_API = 'https://api.reidoscanais.my/channels'
_rdc_cache = {'until': 0, 'data': []}
_rdc_lock = threading.Lock()


def converter_api(payload):
    if not isinstance(payload, dict) or payload.get('success') is not True or not isinstance(payload.get('data'), list):
        raise ValueError('Resposta de catálogo inválida')
    resultado = []
    for canal in payload['data']:
        if not isinstance(canal, dict) or not canal.get('name'):
            continue
        fontes = []
        for fonte in canal.get('embeds', []) or []:
            if not isinstance(fonte, dict):
                continue
            url = fonte.get('embed_url', '')
            if not isinstance(url, str):
                continue
            parsed = urlsplit(url)
            if parsed.scheme == 'https' and parsed.hostname == 'rdcanais.org' and not parsed.username and not parsed.password and parsed.port in (None, 443):
                fontes.append(url)
        if fontes:
            resultado.append(dict(nome=canal['name'], categoria=canal.get('category', ''),
                                  tipo='live', logo=canal.get('logo_url', ''), fontes=fontes,
                                  formato='embed', origem='rdc', id=canal.get('id', '')))
    return resultado


@app.route('/api/canais-externos')
def canais_externos():
    with _rdc_lock:
        if time.monotonic() < _rdc_cache['until']:
            return jsonify(_rdc_cache['response'])
        try:
            snapshot = os.path.join(BASE_DIR, 'canais_api.json')
            if os.path.exists(snapshot):
                with open(snapshot, encoding='utf-8') as arquivo:
                    payload = json.load(arquivo)
            else:
                with urllib.request.urlopen(RDC_API, timeout=8) as resposta:
                    raw = resposta.read(5_000_001)
                if len(raw) > 5_000_000:
                    raise ValueError('Catálogo grande demais')
                payload = json.loads(raw)
            dados = converter_api(payload)
            if not dados:
                raise ValueError('Catálogo sem players compatíveis')
            _rdc_cache['data'] = dados
            response = dict(success=True, data=dados)
            ttl = 300
        except Exception as erro:
            app.logger.warning('Falha no catálogo externo: %s', type(erro).__name__)
            response = dict(success=False, data=_rdc_cache['data'], message='Catálogo externo indisponível. Os canais locais continuam disponíveis.')
            ttl = 60
        _rdc_cache.update(until=time.monotonic() + ttl, response=response)
        return jsonify(response)



_epg_cache = {'until': 0, 'data': {}, 'available': False}
_epg_lock = threading.Lock()


def extrair_programacao(payload, agora):
    if not isinstance(payload, dict) or payload.get('success') is not True or not isinstance(payload.get('data'), list):
        raise ValueError('Programacao invalida')
    resultado = {}
    for canal in payload['data']:
        if not isinstance(canal, dict):
            continue
        epg = canal.get('epg')
        if not isinstance(epg, dict):
            continue
        atual = None
        for campo in ('current', 'next'):
            programa = epg.get(campo)
            if not isinstance(programa, dict):
                continue
            inicio, fim = programa.get('start_time'), programa.get('end_time')
            if isinstance(inicio, (int, float)) and isinstance(fim, (int, float)) and inicio <= agora < fim:
                atual = dict(title=str(programa.get('title', '')), description=str(programa.get('description', '')),
                             start_time=inicio, end_time=fim)
                break
        if atual:
            chaves = [canal.get('id')]
            for embed in canal.get('embeds', []) or []:
                if isinstance(embed, dict) and isinstance(embed.get('embed_url'), str):
                    chaves.append(urlsplit(embed['embed_url']).path.strip('/'))
            for chave in chaves:
                if isinstance(chave, str) and chave:
                    resultado[chave] = atual
    return resultado


@app.route('/api/programacao')
def programacao():
    with _epg_lock:
        if time.monotonic() >= _epg_cache['until']:
            try:
                with urllib.request.urlopen(RDC_API, timeout=5) as resposta:
                    raw = resposta.read(5_000_001)
                if len(raw) > 5_000_000:
                    raise ValueError('Resposta muito grande')
                dados = extrair_programacao(json.loads(raw), time.time())
                _epg_cache.update(data=dados, available=True)
            except Exception as erro:
                app.logger.warning('Programacao indisponivel: %s', type(erro).__name__)
                _epg_cache['available'] = False
            _epg_cache['until'] = time.monotonic() + 60
        agora = time.time()
        atuais = {k: v for k, v in _epg_cache['data'].items() if v['start_time'] <= agora < v['end_time']}
        resposta = jsonify(success=_epg_cache['available'], data=atuais)
        resposta.headers['Cache-Control'] = 'no-store'
        return resposta



SCORE_DB = os.environ.get('SCORE_CACHE_PATH', '/tmp/nexotv-scores.sqlite3')
SCORE_INTERVAL = 20 * 60


def score_database():
    db = sqlite3.connect(SCORE_DB, timeout=10)
    db.execute('CREATE TABLE IF NOT EXISTS score_state (id INTEGER PRIMARY KEY, next_at REAL, payload TEXT)')
    db.execute('CREATE TABLE IF NOT EXISTS score_requests (at REAL)')
    db.commit()
    return db


@app.route('/api/placares')
def placares():
    key = os.environ.get('API_FOOTBALL_KEY', '').strip()
    if not key:
        return jsonify(success=False, data=[], message='Chave de placares não configurada.')
    now = time.time()
    db = score_database()
    try:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT next_at, payload FROM score_state WHERE id=1').fetchone()
        if row and now < row[0]:
            db.commit()
            return jsonify(json.loads(row[1]))
        db.execute('DELETE FROM score_requests WHERE at <= ?', (now - 86400,))
        used = db.execute('SELECT COUNT(*) FROM score_requests').fetchone()[0]
        if used >= 90:
            db.commit()
            return jsonify(success=False, data=[], message='Limite de consultas reservado para hoje. Tente mais tarde.')
        # Reserve before calling the provider, including failures. Shared across workers.
        pending = dict(success=False, data=[], message='Consultando jogos. Aguarde alguns segundos.')
        db.execute('INSERT INTO score_requests VALUES (?)', (now,))
        db.execute('INSERT OR REPLACE INTO score_state VALUES (1, ?, ?)', (now + SCORE_INTERVAL, json.dumps(pending)))
        db.commit()
    finally:
        db.close()
    result = dict(success=False, data=[], message='Placares indisponíveis. A transmissão continua normalmente.')
    try:
        via_rapidapi = os.environ.get('API_FOOTBALL_PROVIDER', 'apisports').lower() == 'rapidapi'
        host = 'api-football-v1.p.rapidapi.com' if via_rapidapi else 'v3.football.api-sports.io'
        path = '/v3/fixtures?live=all' if via_rapidapi else '/fixtures?live=all'
        headers = {'x-rapidapi-key': key, 'x-rapidapi-host': host} if via_rapidapi else {'x-apisports-key': key}
        req = urllib.request.Request('https://' + host + path, headers=headers)
        with urllib.request.urlopen(req, timeout=8) as response:
            raw = response.read(5_000_001)
        if len(raw) > 5_000_000:
            raise ValueError('Resposta muito grande')
        payload = json.loads(raw)
        if not isinstance(payload, dict) or payload.get('errors') or not isinstance(payload.get('response'), list):
            raise ValueError('Resposta de placares inválida')
        games = []
        for game in payload['response']:
            try:
                fixture, teams, goals = game['fixture'], game['teams'], game['goals']
                status = fixture['status']
                home, away = str(teams['home']['name']), str(teams['away']['name'])
                games.append(dict(id=fixture['id'], home=home, away=away, home_goals=goals.get('home'),
                                  away_goals=goals.get('away'), minute=status.get('elapsed'),
                                  status=str(status.get('short', '')), league=str(game.get('league', {}).get('name', ''))))
            except (KeyError, TypeError):
                continue
        result = dict(success=True, data=games, updated_at=time.time(),
                      message='Atualização a cada 20 minutos. O placar pode estar à frente do vídeo.')
    except Exception as error:
        # Never log the request, headers, key, or provider response.
        app.logger.warning('Falha nos placares: %s', type(error).__name__)
    db = score_database()
    try:
        db.execute('UPDATE score_state SET payload=? WHERE id=1', (json.dumps(result),))
        db.commit()
    finally:
        db.close()
    response = jsonify(result)
    response.headers['Cache-Control'] = 'no-store'
    return response



JIKAN_IDS = {20, 1735, 11061, 136}
_jikan_cache = {}
_jikan_lock = threading.Lock()


def jikan_get(anime_id, section, page=1):
    if anime_id not in JIKAN_IDS or section not in ('episodes', 'streaming') or not 1 <= page <= 30:
        return None
    key = (anime_id, section, page)
    now = time.monotonic()
    with _jikan_lock:
        entry = _jikan_cache.get(key)
        if entry and now < entry['until']:
            return entry['value']
    url = 'https://api.jikan.moe/v4/anime/{}/{}'.format(anime_id, section)
    if section == 'episodes':
        url += '?page={}'.format(page)
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'NexoTV/1.0 (anime metadata)'})
        with urllib.request.urlopen(req, timeout=6) as response:
            raw = response.read(1_000_001)
        if len(raw) > 1_000_000:
            raise ValueError('Resposta muito grande')
        payload = json.loads(raw)
        if not isinstance(payload, dict) or not isinstance(payload.get('data'), list):
            raise ValueError('Resposta inválida')
        if section == 'episodes':
            value = dict(success=True, data=[
                dict(numero=ep.get('mal_id'), nome=ep.get('title') or 'Episódio {}'.format(ep.get('mal_id')),
                     filler=bool(ep.get('filler'))) for ep in payload['data'] if isinstance(ep, dict)
            ], has_next=bool(payload.get('pagination', {}).get('has_next_page')))
        else:
            value = dict(success=True, data=[
                dict(nome=p.get('name', ''), url=p.get('url', '')) for p in payload['data']
                if isinstance(p, dict) and isinstance(p.get('url'), str) and p['url'].startswith('https://')
            ])
        ttl = 86400
    except Exception as error:
        app.logger.warning('Metadados Jikan indisponíveis: %s', type(error).__name__)
        value = dict(success=False, data=[], message='Lista indisponível agora. Tente novamente mais tarde.')
        ttl = 300
    with _jikan_lock:
        _jikan_cache[key] = dict(value=value, until=time.monotonic()+ttl)
    return value


@app.route('/api/anime/<int:anime_id>/<section>')
def anime_metadata(anime_id, section):
    try:
        page = int(request.args.get('page', '1'))
    except ValueError:
        page = 0
    result = jikan_get(anime_id, section, page)
    if result is None:
        return jsonify(success=False, data=[], message='Consulta inválida.'), 404
    return jsonify(result)


HTML_IBO_INTERFACE = r"""
<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>IBO IPTV Server</title>

<style>
body { font-family: 'Segoe UI', sans-serif; background: #080c14; color: #fff; margin: 0; padding: 20px; }
.header { text-align: center; padding: 15px 0; border-bottom: 1px solid #1e293b; }
.header h1 { color: #38bdf8; font-size: 2rem; margin: 0; text-transform: uppercase; letter-spacing: 2px; }
.ibo-dashboard { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; max-width: 1000px; margin: 40px auto; }
.ibo-box { color: inherit; font: inherit; background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%); border: 2px solid #334155; border-radius: 16px; padding: 30px 15px; text-align: center; cursor: pointer; transition: 0.3s; }
.ibo-box:hover { transform: translateY(-5px); border-color: #38bdf8; box-shadow: 0 0 20px rgba(56,189,248,.3); }
.icon { font-size: 3rem; margin-bottom: 10px; display: block; }
.live { border-left: 6px solid #ef4444; } .movies { border-left: 6px solid #eab308; }
.series { border-left: 6px solid #3b82f6; } .animes { border-left: 6px solid #a855f7; }
.content-section { display: none; max-width: 1200px; margin: 20px auto; }
.content-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); gap: 20px; }
.media-card { background: #141b2d; border-radius: 12px; overflow: hidden; border: 1px solid #222f48; text-align: center; display: flex; flex-direction: column; justify-content: space-between; }
.media-card img { width: 100%; height: 220px; object-fit: cover; background: #000; }
.media-card h4 { margin: 8px; font-size: .95rem; }
.video-container { display: none; max-width: 850px; margin: 20px auto; text-align: center; }
video { width: 100%; border-radius: 12px; border: 2px solid #38bdf8; background: #000; box-shadow: 0 0 30px rgba(0,0,0,.8); }
.play-btn { border: 0; background: #38bdf8; color: #000; padding: 10px; font-weight: bold; cursor: pointer; border-radius: 0 0 10px 10px; }
.back-btn { background: #1e293b; color: white; border: 1px solid #334155; padding: 10px 20px; border-radius: 8px; cursor: pointer; margin-bottom: 20px; font-weight: bold; }
#playerStatus { color: #fbbf24; }

* { box-sizing: border-box; }
button, select, input, a { touch-action: manipulation; }
button, select, input { min-height: 48px; font-size: 1rem; }
button:focus, a:focus, select:focus, input:focus, iframe:focus, video:focus { outline: 4px solid #fbbf24; outline-offset: 4px; }
select, input { background: #1e293b; color: white; padding: 12px; border: 1px solid #64748b; border-radius: 8px; max-width: 100%; }
.media-card img { height: 150px; object-fit: contain; }
#embedPlayer { height: 56.25vw; max-height: 478px; }
#loadMore { margin-top: 24px; }
.tv-hint { color: #cbd5e1; text-align: center; }
.video-container:fullscreen { max-width: none; width: 100%; height: 100%; overflow: auto; padding: 20px; background: #080c14; }
.video-container:fullscreen #embedPlayer, .video-container:fullscreen video { height: 75vh; }
@media (min-width: 1400px) {
 body { padding: 40px; font-size: 22px; }
 button, select, input { font-size: 22px; min-height: 60px; }
 .video-container { max-width: 1200px; }
 #embedPlayer { height: 675px; max-height: 675px; }
 .content-grid { grid-template-columns: repeat(5, 1fr); }
 .media-card h4 { font-size: 1.1rem; }
}

/* Flex and margins support older webOS browsers without CSS Grid or gap. */
.ibo-dashboard, .content-grid { display: flex; flex-wrap: wrap; gap: 0; }
.ibo-box { flex: 1 1 200px; margin: 10px; }
.media-card { width: calc(25% - 20px); margin: 10px; }
.ibo-box, video { box-shadow: none; transition: none; }
.ibo-box:hover { transform: none; box-shadow: none; }
@media(max-width:700px) { .media-card { width: calc(50% - 20px); } }
</style>
</head>
<body>
<div class="header"><h1>IBO IPTV Hub v2.0 🌐</h1></div>
<p class="tv-hint">Use as setas e OK/Enter para navegar. Esc/Voltar retorna.</p>
<div class="ibo-dashboard" id="mainDashboard">
<button class="ibo-box live" onclick="mostrarSecao('live')"><span class="icon">📺</span><h2>TV Ao Vivo</h2><p>Canais Operacionais</p></button>
<button class="ibo-box movies" onclick="mostrarSecao('movie')"><span class="icon">🎬</span><h2>Filmes Anime</h2><p>Filmes Longos</p></button>
<button class="ibo-box series" onclick="mostrarSecao('series')"><span class="icon">🍿</span><h2>Séries</h2><p>Episódios Gerais</p></button>
<button class="ibo-box animes" onclick="mostrarSecao('anime')"><span class="icon">💥</span><h2>Animes Hub</h2><p>Lista do Repositório</p></button>
</div>
<div class="video-container" id="videoPlayerContainer">
<button class="back-btn" onclick="fecharPlayer()">⬅ Fechar Transmissão</button>
<button class="back-btn" id="fullscreenButton" onclick="telaCheia()">⛶ Tela cheia</button>
<div id="episodePanel" style="display:none;text-align:left;padding:12px;background:#141b2d;border-radius:8px">
<label for="episodeSelect">Episódio:</label>
<select id="episodeSelect" style="width:100%"></select>
</div>
<label for="sourceSelect" id="sourceLabel">Fonte da transmissão:</label>
<select id="sourceSelect" style="max-width:100%;margin:12px" aria-label="Fonte da transmissão"></select>
<iframe id="embedPlayer" title="Player do canal" style="display:none;width:100%;aspect-ratio:16/9;border:0" allow="autoplay; fullscreen; picture-in-picture" allowfullscreen></iframe>
<a id="externalPlayerLink" target="_blank" rel="noopener noreferrer" style="display:none;color:#38bdf8">Abrir player no site de origem</a>
<video id="mainVideoPlayer" controls playsinline></video>
<h3 id="videoTitle" style="color:#38bdf8"></h3>
<div id="programInfo" style="text-align:left;padding:16px;background:#141b2d;border-radius:8px;display:none" aria-live="polite"><strong id="programTitle"></strong><p id="programDescription"></p></div>
<div id="scorePanel" style="display:none;text-align:left;padding:16px">
<button class="back-btn" onclick="buscarPlacares(true)">Carregar jogos e placares</button>
<label for="scoreGame">Selecione a partida que está assistindo:</label>
<select id="scoreGame" style="width:100%"><option value="">Escolher partida</option></select>
<p id="scoreText" role="status">O placar pode estar à frente do vídeo. Atualização a cada 20 minutos.</p>
</div>
<button class="back-btn" id="liveButton" onclick="voltarAoVivo()">↻ Voltar ao vivo</button>
<p id="playerStatus" role="status" aria-live="polite"></p>
</div>
<div class="content-section" id="contentSection">
<button class="back-btn" onclick="voltarProPainel()">⬅ Voltar ao Painel</button>
<h2 id="sectionTitle" style="color:#38bdf8">Conteúdo</h2>
<input id="channelSearch" type="search" placeholder="Buscar canal ou anime" aria-label="Buscar canal ou anime">
<p id="catalogStatus" role="status"></p>
<div id="animeDetails" style="display:none">
<button class="back-btn" onclick="fecharListaEpisodios()">⬅ Voltar aos animes</button>
<h2 id="animeDetailsTitle"></h2>
<p id="animeDetailsStatus" role="status"></p>
<div id="officialLinks"></div>
<div id="episodeList" class="content-grid"></div>
<button class="back-btn" id="nextEpisodes" style="display:none" onclick="proximaPaginaAnime()">Mais episódios</button>
</div>
<div class="content-grid" id="contentGrid"></div>
<button class="back-btn" id="loadMore" style="display:none" onclick="maisCanais()">Mostrar mais</button>
</div>
<script>

var bancoDados = {{ conteudo | tojson }};
function el(id) { return document.getElementById(id); }
var video = el('mainVideoPlayer'), hls = null, itemAtual = null, secaoAtual = '';
var limiteCanais = 24, externosCarregados = bancoDados.some(function (c) { return c.origem === 'rdc'; }), geracao = 0, epg = {}, epgBusy = false;
function getJSON(url, done) {
    var xhr = new XMLHttpRequest();
    xhr.open('GET', url, true); xhr.timeout = 12000;
    xhr.onload = function () {
        try { if (xhr.status !== 200) throw new Error(); done(null, JSON.parse(xhr.responseText)); }
        catch (e) { done(e); }
    };
    xhr.onerror = xhr.ontimeout = function () { done(new Error('Rede indisponível')); };
    xhr.send();
}
function normalizar(nome) { return nome.toLowerCase().replace(/[^a-z0-9]/g, ''); }
function endereco(fonte) {
    var a = document.createElement('a');
    if (typeof fonte !== 'string' || !/^https?:\/\//i.test(fonte)) return null;
    a.href = fonte;
    return a;
}
function limparPlayer() {
    geracao++;
    el('embedPlayer').src = 'about:blank'; el('embedPlayer').style.display = 'none';
    el('externalPlayerLink').style.display = 'none'; el('externalPlayerLink').removeAttribute('href');
    video.style.display = 'block';
    if (hls) { hls.destroy(); hls = null; }
    video.pause(); video.removeAttribute('src'); video.load();
    el('playerStatus').textContent = '';
}
function carregarExternos() {
    if (externosCarregados) return;
    externosCarregados = true;
    el('catalogStatus').textContent = 'Carregando canais…';
    getJSON('/api/canais-externos', function (erro, result) {
        if (erro || !result || !Array.isArray(result.data)) {
            el('catalogStatus').textContent = 'Usando catálogo local.'; externosCarregados = false; return;
        }
        var nomes = {};
        result.data.forEach(function (c) { nomes[normalizar(c.nome)] = true; });
        bancoDados = result.data.concat(bancoDados.filter(function (c) { return c.tipo !== 'live' || !nomes[normalizar(c.nome)]; }));
        el('catalogStatus').textContent = result.success ? 'Canais carregados.' : 'Usando catálogo local.';
        if (secaoAtual === 'live' && el('contentSection').style.display === 'block') renderizarSecao('live');
    });
}
function mostrarSecao(tipo) {
    fecharPlayer(); secaoAtual = tipo; limiteCanais = 24;
    el('channelSearch').value = '';
    el('mainDashboard').style.display = 'none'; el('contentSection').style.display = 'block';
    el('sectionTitle').textContent = {live:'TV Ao Vivo',movie:'Filmes Anime',series:'Séries',anime:'Animes Hub'}[tipo];
    fecharListaEpisodios(); renderizarSecao(tipo); el('channelSearch').focus();
    if (tipo === 'live') carregarExternos();
}
function renderizarSecao(tipo) {
    var grid = el('contentGrid'), focused = document.activeElement;
    var focusName = focused && focused.getAttribute('data-channel');
    grid.textContent = '';
    var busca = el('channelSearch').value.toLowerCase().trim();
    var itens = bancoDados.filter(function (c) { return c.tipo === tipo && c.nome.toLowerCase().indexOf(busca) >= 0; });
    var fragment = document.createDocumentFragment();
    itens.slice(0, limiteCanais).forEach(function (item) {
        var card = document.createElement('div'); card.className = 'media-card';
        var img = document.createElement('img'); img.alt = item.nome; img.loading = 'lazy';
        img.width = 160; img.height = 150;
        img.onerror = function () { this.style.display = 'none'; };
        if (item.logo && item.logo !== 'https://wikimedia.org') img.src = item.logo;
        var title = document.createElement('h4'); title.textContent = item.nome;
        var button = document.createElement('button'); button.className = 'play-btn';
        var episodios = Array.isArray(item.episodios) ? item.episodios : [];
        var temVideo = item.tipo === 'live' || episodios.some(function (ep) { return fonteValida(ep.url || ep.fontes); }) || fonteValida(item.fontes);
        button.textContent = item.jikan_id ? 'Ver episódios' : (temVideo ? (episodios.length ? '▶ Episódios' : '▶ Assistir') : 'Vídeo pendente');
        button.disabled = !temVideo && !item.jikan_id;
        button.setAttribute('data-channel', item.nome);
        button.onclick = function () { if (item.jikan_id) abrirListaEpisodios(item); else abrirPlayer(item); };
        card.appendChild(img); card.appendChild(title); card.appendChild(button); fragment.appendChild(card);
    });
    grid.appendChild(fragment);
    el('loadMore').style.display = itens.length > limiteCanais ? 'block' : 'none';
    if (!itens.length) grid.textContent = 'Nenhum conteúdo encontrado.';
    if (focusName) {
        var buttons = grid.querySelectorAll('button');
        for (var i = 0; i < buttons.length; i++) if (buttons[i].getAttribute('data-channel') === focusName) buttons[i].focus();
    }
}
var buscaTimer;
el('channelSearch').oninput = function () {
    clearTimeout(buscaTimer);
    buscaTimer = setTimeout(function () { limiteCanais = 24; renderizarSecao(secaoAtual); }, 180);
};
function maisCanais() {
    var antes = limiteCanais; limiteCanais += 24; renderizarSecao(secaoAtual);
    var buttons = el('contentGrid').querySelectorAll('button');
    if (buttons[antes]) buttons[antes].focus();
}
function fonteValida(fonte) {
    if (Array.isArray(fonte)) return fonte.some(fonteValida);
    return typeof fonte === 'string' && /^https?:\/\//i.test(fonte) &&
        !/^https?:\/\/(googleapis\.com|jmvstream\.com|amazonaws\.com|cnnbrasil\.com)\/?$/i.test(fonte);
}
function abrirPlayer(item) {
    itemAtual = item;
    placarEscolhido = ''; el('scoreGame').value = '';
    el('scorePanel').style.display = item.tipo === 'live' ? 'block' : 'none';
    mostrarPlacar();
    el('videoPlayerContainer').style.display = 'block';
    var episodes = Array.isArray(item.episodios) ? item.episodios.filter(function (ep) {
        return fonteValida(ep.url || ep.fontes);
    }) : [];
    var select = el('episodeSelect'); select.textContent = '';
    el('episodePanel').style.display = episodes.length ? 'block' : 'none';
    episodes.forEach(function (ep, index) {
        var option = document.createElement('option'); option.value = String(index);
        option.textContent = (ep.arco ? ep.arco + ' — ' : '') + (ep.nome || 'Episódio ' + ep.numero);
        select.appendChild(option);
    });
    if (episodes.length) {
        select.onchange = function () { abrirEpisodio(item, episodes[Number(this.value)]); };
        abrirEpisodio(item, episodes[0]);
    } else {
        preencherFontes(item, item.fontes, item.nome);
    }
    el('fullscreenButton').focus();
    atualizarPrograma(); buscarProgramacao();
}
function abrirEpisodio(serie, episodio) {
    if (!episodio) return;
    var titulo = serie.nome + ' — ' + (episodio.nome || 'Episódio ' + episodio.numero);
    preencherFontes(serie, episodio.fontes || episodio.url, titulo);
}
function preencherFontes(item, fontesOriginais, titulo) {
    var fontes = Array.isArray(fontesOriginais) ? fontesOriginais : [fontesOriginais];
    var select = el('sourceSelect'); select.textContent = '';
    fontes.forEach(function (fonte, i) {
        var option = document.createElement('option'); option.value = fonte;
        option.textContent = 'Fonte ' + (i + 1);
        select.appendChild(option);
    });
    el('sourceLabel').textContent = item.tipo === 'live' ? 'Fonte da transmissão:' : 'Fonte do vídeo:';
    reproduzirFonte(item, fontes[0], titulo);
}
el('sourceSelect').onchange = function () {
    if (itemAtual) { reproduzirFonte(itemAtual, this.value, el('videoTitle').textContent); atualizarPrograma(); }
};
function tentarPlay(token) {
    var result = video.play();
    if (result && result.catch) result.catch(function () {
        if (token === geracao) el('playerStatus').textContent = 'Pressione Play para iniciar.';
    });
}
function reproduzirFonte(item, fonte, titulo) {
    limparPlayer();
    var token = geracao, url = endereco(fonte);
    el('videoPlayerContainer').style.display = 'block'; el('videoTitle').textContent = titulo || item.nome;
    el('liveButton').style.display = item.tipo === 'live' ? 'inline-block' : 'none';
    if (!url) { el('playerStatus').textContent = 'URL de mídia inválida.'; return; }
    if (location.protocol === 'https:' && url.protocol === 'http:') {
        el('playerStatus').textContent = 'Esta fonte HTTP não é compatível com a página HTTPS. Escolha outra fonte.'; return;
    }
    if (item.formato === 'embed') {
        if (!/^https:\/\/rdcanais\.org(?::443)?\//i.test(fonte)) {
            el('playerStatus').textContent = 'Player não permitido.'; return;
        }
        video.style.display = 'none'; el('embedPlayer').src = fonte; el('embedPlayer').style.display = 'block';
        el('externalPlayerLink').href = fonte; el('externalPlayerLink').style.display = 'block';
        el('playerStatus').textContent = 'Se necessário, abra o player no site de origem.';
    } else {
        var isHls = /\.m3u8$/i.test(url.pathname) || item.formato === 'hls';
        if (isHls && !video.canPlayType('application/vnd.apple.mpegurl')) {
            iniciarHls(fonte, token);
        } else { video.src = fonte; tentarPlay(token); }
    }
    el('videoPlayerContainer').scrollIntoView(true);
}
function iniciarHls(fonte, token) {
    function start() {
        if (token !== geracao) return;
        if (!window.Hls || !window.Hls.isSupported()) {
            el('playerStatus').textContent = 'HLS não suportado neste navegador. Tente outra fonte.'; return;
        }
        var player = new window.Hls({lowLatencyMode:true, maxBufferLength:20, backBufferLength:10});
        hls = player;
        player.on(window.Hls.Events.ERROR, function (_, data) {
            if (data.fatal && token === geracao) {
                el('playerStatus').textContent = 'Falha na transmissão. Tente outra fonte.';
                player.destroy(); if (hls === player) hls = null;
            }
        });
        player.on(window.Hls.Events.MANIFEST_PARSED, function () { if (token === geracao) tentarPlay(token); });
        player.loadSource(fonte); player.attachMedia(video);
    }
    if (window.Hls) { start(); return; }
    var script = document.createElement('script');
    script.src = 'https://cdn.jsdelivr.net/npm/hls.js@1.6.13/dist/hls.min.js';
    script.onload = start;
    script.onerror = function () { if (token === geracao) el('playerStatus').textContent = 'Falha ao carregar o player HLS.'; };
    document.head.appendChild(script);
}
function voltarAoVivo() {
    if (!itemAtual) return;
    if (itemAtual.formato === 'embed') {
        reproduzirFonte(itemAtual, el('sourceSelect').value);
        el('playerStatus').textContent = 'Player reiniciado. O atraso depende da transmissão de origem.';
    } else if (video.seekable.length) {
        video.currentTime = Math.max(video.seekable.start(video.seekable.length-1), video.seekable.end(video.seekable.length-1)-2);
        tentarPlay(geracao);
    }
}
function atualizarPrograma() {
    var box = el('programInfo');
    if (!itemAtual || itemAtual.tipo !== 'live' || el('videoPlayerContainer').style.display !== 'block') { box.style.display = 'none'; return; }
    box.style.display = 'block';
    var url = endereco(el('sourceSelect').value), key = url ? url.pathname.replace(/^\/+|\/+$/g, '') : '';
    var programa = epg[key] || epg[itemAtual.id], agora = Date.now()/1000;
    if (!programa || !(programa.start_time <= agora && agora < programa.end_time)) {
        el('programTitle').textContent = 'Programação ao vivo indisponível';
        el('programDescription').textContent = 'O provedor não informou o programa atual. A reprodução pode continuar normalmente.';
        return;
    }
    el('programTitle').textContent = 'Agora: ' + programa.title;
    el('programDescription').textContent = programa.description || '';
}
function buscarProgramacao() {
    if (!itemAtual || itemAtual.tipo !== 'live' || document.hidden || epgBusy || el('videoPlayerContainer').style.display !== 'block') return;
    epgBusy = true;
    getJSON('/api/programacao', function (erro, result) {
        epgBusy = false;
        if (!erro && result && result.data) epg = result.data;
        atualizarPrograma();
    });
}
setInterval(buscarProgramacao, 60000);
setInterval(atualizarPrograma, 15000);
video.onerror = function () { if (video.getAttribute('src')) el('playerStatus').textContent = 'Falha ao reproduzir. Tente outra fonte.'; };
video.onplaying = function () { el('playerStatus').textContent = ''; };
function fecharPlayer() {
    limparPlayer(); itemAtual = null; el('programInfo').style.display = 'none';
    el('videoPlayerContainer').style.display = 'none';
    if (el('contentSection').style.display === 'block') el('channelSearch').focus();
}
function voltarProPainel() {
    fecharPlayer(); el('contentSection').style.display = 'none'; el('mainDashboard').style.display = 'flex';
    document.querySelector('.ibo-box').focus();
}
function telaCheia() {
    var box = el('videoPlayerContainer');
    if (document.fullscreenElement || document.webkitFullscreenElement) {
        var exit = document.exitFullscreen || document.webkitExitFullscreen; if (exit) exit.call(document); return;
    }
    var enter = box.requestFullscreen || box.webkitRequestFullscreen;
    if (enter) {
        try { var result = enter.call(box); if (result && result.catch) result.catch(function () { el('playerStatus').textContent = 'Use a tela cheia do player.'; }); }
        catch (_) { el('playerStatus').textContent = 'Use a tela cheia do player.'; }
    } else el('playerStatus').textContent = 'Use a tela cheia do player.';
}
document.addEventListener('keydown', function (event) {
    var active = document.activeElement;
    var editing = active && (active.tagName === 'INPUT' || active.tagName === 'SELECT');
    var code = event.keyCode;
    if (!editing && (code === 27 || code === 461)) {
        event.preventDefault();
        if (el('videoPlayerContainer').style.display === 'block') fecharPlayer(); else voltarProPainel();
        return;
    }
    var direction = {37:[-1,0],39:[1,0],38:[0,-1],40:[0,1]}[code];
    if (!direction || editing || (active && active.tagName === 'VIDEO')) return;
    var nodes = document.querySelectorAll('button,a[href],select,input,iframe,video'), candidates = [], i;
    for (i=0;i<nodes.length;i++) if (!nodes[i].disabled && nodes[i].getClientRects().length) candidates.push(nodes[i]);
    if (!candidates.length) return;
    if (candidates.indexOf(active)<0) { event.preventDefault(); candidates[0].focus(); return; }
    var rect=active.getBoundingClientRect(), x=rect.left+rect.width/2, y=rect.top+rect.height/2, best=null, score=Infinity;
    candidates.forEach(function (node) {
        if (node===active) return;
        var r=node.getBoundingClientRect(), dx=r.left+r.width/2-x, dy=r.top+r.height/2-y;
        var forward=dx*direction[0]+dy*direction[1], sideways=Math.abs(dx*direction[1]+dy*direction[0]);
        var value=forward+sideways*3;
        if (forward>1 && value<score) {best=node;score=value;}
    });
    if (best) {event.preventDefault();best.focus();}
});

var jogosPlacar = [], placarEscolhido = '', placarAtualizado = 0, placarAtivo = false, placarOcupado = false;
function mostrarPlacar() {
    var selected = null;
    jogosPlacar.forEach(function (g) { if (String(g.id) === placarEscolhido) selected = g; });
    if (!selected) { el('scoreText').textContent = 'Selecione a partida. O placar pode estar à frente do vídeo.'; return; }
    var home = selected.home_goals == null ? '–' : selected.home_goals;
    var away = selected.away_goals == null ? '–' : selected.away_goals;
    var minute = selected.minute == null ? '' : ' • ' + selected.minute + ' min';
    el('scoreText').textContent = selected.home + ' ' + home + ' × ' + away + ' ' + selected.away +
        minute + ' • ' + selected.status + ' • Consultado às ' + new Date(placarAtualizado*1000).toLocaleTimeString() +
        '. Atualização a cada 20 minutos; pode estar à frente do vídeo.';
}
el('scoreGame').onchange = function () { placarEscolhido = this.value; mostrarPlacar(); };
function buscarPlacares(manual) {
    if (!itemAtual || itemAtual.tipo !== 'live' || document.hidden || placarOcupado || (!manual && !placarAtivo)) return;
    placarAtivo = true; placarOcupado = true;
    el('scoreText').textContent = 'Consultando jogos…';
    getJSON('/api/placares', function (error, result) {
        placarOcupado = false;
        if (error || !result || !result.success || !Array.isArray(result.data)) {
            el('scoreText').textContent = result && result.message ? result.message : 'Não foi possível carregar os placares.';
            if (result && result.message === 'Consultando jogos. Aguarde alguns segundos.') setTimeout(function () { buscarPlacares(true); }, 5000);
            return;
        }
        jogosPlacar = result.data; placarAtualizado = result.updated_at;
        var select = el('scoreGame'); select.textContent = '';
        var empty = document.createElement('option'); empty.value = ''; empty.textContent = 'Escolher partida'; select.appendChild(empty);
        jogosPlacar.forEach(function (g) {
            var option = document.createElement('option'); option.value = String(g.id);
            option.textContent = g.home + ' × ' + g.away + ' — ' + g.league;
            select.appendChild(option);
        });
        select.value = placarEscolhido;
        if (!select.value) placarEscolhido = '';
        mostrarPlacar();
        if (!jogosPlacar.length) el('scoreText').textContent = 'Nenhum jogo ao vivo disponível nesta consulta.';
    });
}
setInterval(function () { buscarPlacares(false); }, 1200000);


var animeSelecionado = null, paginaAnime = 1;
function fecharListaEpisodios() {
    animeSelecionado = null; el('animeDetails').style.display = 'none';
    el('contentGrid').style.display = 'flex';
    el('channelSearch').style.display = 'inline-block';
    el('loadMore').style.display = 'none';
    if (secaoAtual) renderizarSecao(secaoAtual);
}
function abrirListaEpisodios(item) {
    animeSelecionado = item; paginaAnime = 1;
    el('contentGrid').style.display = 'none'; el('channelSearch').style.display = 'none';
    el('loadMore').style.display = 'none'; el('animeDetails').style.display = 'block';
    el('animeDetailsTitle').textContent = item.nome;
    el('episodeList').textContent = '';
    el('animeDetailsStatus').textContent = 'Carregando episódios…';
    el('officialLinks').textContent = '';
    buscarPaginaAnime();
    getJSON('/api/anime/' + item.jikan_id + '/streaming', function (error, result) {
        if (animeSelecionado !== item || error || !result || !result.success) return;
        var host = el('officialLinks');
        result.data.forEach(function (entry) {
            if (!/^https:\/\//i.test(entry.url)) return;
            var link = document.createElement('a');
            link.href = entry.url; link.target = '_blank'; link.rel = 'noopener noreferrer';
            link.textContent = 'Onde assistir: ' + entry.nome;
            link.style.display = 'block'; link.style.padding = '12px'; host.appendChild(link);
        });
    });
}
function buscarPaginaAnime() {
    var item = animeSelecionado, page = paginaAnime;
    if (!item) return;
    el('nextEpisodes').style.display = 'none';
    getJSON('/api/anime/' + item.jikan_id + '/episodes?page=' + page, function (error, result) {
        if (animeSelecionado !== item || paginaAnime !== page) return;
        if (error || !result || !result.success) {
            el('animeDetailsStatus').textContent = 'Lista indisponível agora. Tente novamente mais tarde.';
            return;
        }
        el('animeDetailsStatus').textContent = 'Dados dos episódios: Jikan. Vídeos disponíveis apenas quando cadastrados.';
        var owned = Array.isArray(item.episodios) ? item.episodios : [];
        var list = el('episodeList');
        result.data.forEach(function (ep) {
            var local = null;
            owned.forEach(function (candidate) {
                if (Number(candidate.numero) === Number(ep.numero) && fonteValida(candidate.url || candidate.fontes)) local = candidate;
            });
            var card = document.createElement('div'); card.className = 'media-card';
            var title = document.createElement('h4');
            title.textContent = 'Episódio ' + ep.numero + ' — ' + ep.nome + (ep.filler ? ' (filler)' : '');
            var button = document.createElement('button'); button.className = 'play-btn';
            button.textContent = local ? '▶ Assistir' : 'Vídeo pendente'; button.disabled = !local;
            if (local) button.onclick = function () { abrirPlayer(item); var validos = owned.filter(function (candidate) { return fonteValida(candidate.url || candidate.fontes); }); el('episodeSelect').value = String(validos.indexOf(local)); abrirEpisodio(item, local); };
            card.appendChild(title); card.appendChild(button); list.appendChild(card);
        });
        el('nextEpisodes').style.display = result.has_next ? 'inline-block' : 'none';
    });
}
function proximaPaginaAnime() { paginaAnime++; buscarPaginaAnime(); }

document.querySelector('.ibo-box').focus();

</script>
</body>
</html>
"""


@app.route('/')
def index():
    conteudo = carregar_conteudo()
    snapshot = os.path.join(BASE_DIR, 'canais_api.json')
    if os.path.exists(snapshot):
        try:
            with open(snapshot, encoding='utf-8') as arquivo:
                externos = converter_api(json.load(arquivo))
            normalizar = lambda nome: re.sub(r'[^a-z0-9]', '', nome.lower())
            nomes = {normalizar(c['nome']) for c in externos}
            conteudo = externos + [c for c in conteudo if c.get('tipo') != 'live' or normalizar(c['nome']) not in nomes]
        except (ValueError, OSError, TypeError, KeyError):
            app.logger.warning('Falha no catalogo local de players')
    return render_template_string(HTML_IBO_INTERFACE, conteudo=conteudo)


@app.route('/api/catalogo')
def catalogo():
    return jsonify(carregar_conteudo())


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))
