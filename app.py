from flask import Flask, jsonify, render_template_string
import json
import os
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
                                  formato='embed', origem='rdc'))
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


HTML_IBO_INTERFACE = r"""
<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>IBO IPTV Server</title>
<script src="https://cdn.jsdelivr.net/npm/hls.js@1.6.13/dist/hls.min.js"></script>
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
<label for="sourceSelect">Fonte da transmissão:</label>
<select id="sourceSelect" style="max-width:100%;margin:12px" aria-label="Fonte da transmissão"></select>
<iframe id="embedPlayer" title="Player do canal" style="display:none;width:100%;aspect-ratio:16/9;border:0" allow="autoplay; fullscreen; picture-in-picture" allowfullscreen></iframe>
<a id="externalPlayerLink" target="_blank" rel="noopener noreferrer" style="display:none;color:#38bdf8">Abrir player no site de origem</a>
<video id="mainVideoPlayer" controls playsinline></video>
<h3 id="videoTitle" style="color:#38bdf8"></h3>
<p id="playerStatus" role="status" aria-live="polite"></p>
</div>
<div class="content-section" id="contentSection">
<button class="back-btn" onclick="voltarProPainel()">⬅ Voltar ao Painel</button>
<h2 id="sectionTitle" style="color:#38bdf8">Conteúdo</h2>
<input id="channelSearch" type="search" placeholder="Buscar canal ou anime" aria-label="Buscar canal ou anime">
<p id="catalogStatus" role="status"></p>
<div class="content-grid" id="contentGrid"></div>
<button class="back-btn" id="loadMore" style="display:none" onclick="maisCanais()">Mostrar mais</button>
</div>
<script>
let bancoDados = {{ conteudo | tojson }};
const el = id => document.getElementById(id);
const video = el('mainVideoPlayer');
let secaoAtual = '';
let hls = null;
let itemAtual = null;
el('sourceSelect').addEventListener('change', () => reproduzirFonte(itemAtual, el('sourceSelect').value));
function limparPlayer() {
    el('embedPlayer').src = 'about:blank';
    el('embedPlayer').style.display = 'none';
    el('externalPlayerLink').style.display = 'none';
    el('externalPlayerLink').removeAttribute('href');
    video.style.display = 'block';
    if (hls) { hls.destroy(); hls = null; }
    video.pause();
    video.removeAttribute('src');
    video.load();
    el('playerStatus').textContent = '';
}
let externosCarregados = false;
async function carregarExternos() {
    if (externosCarregados) return;
    externosCarregados = true;
    el('catalogStatus').textContent = 'Buscando catálogo externo…';
    try {
        const response = await fetch('/api/canais-externos');
        if (!response.ok) throw new Error();
        const result = await response.json();
        if (!Array.isArray(result.data)) throw new Error();
        const normalize = name => name.toLowerCase().replace(/[^a-z0-9]/g, '');
        const nomes = new Set(result.data.map(item => normalize(item.nome)));
        bancoDados = [...result.data, ...bancoDados.filter(item => item.tipo !== 'live' || !nomes.has(normalize(item.nome)))];
        el('catalogStatus').textContent = result.success ? 'Players externos carregados.' : result.message;
        if (secaoAtual === 'live' && el('contentSection').style.display === 'block') renderizarSecao('live');
    } catch (_) {
        el('catalogStatus').textContent = 'Catálogo externo indisponível. Os canais locais continuam disponíveis.';
    }
}
function mostrarSecao(tipo) {
    fecharPlayer();
    secaoAtual = tipo;
    el('mainDashboard').style.display = 'none';
    el('contentSection').style.display = 'block';
    el('sectionTitle').textContent = {live:'TV Ao Vivo', movie:'Filmes Anime', series:'Séries', anime:'Animes Hub'}[tipo];
    limiteCanais = 48;
    el('channelSearch').value = '';
    renderizarSecao(tipo);
    el('channelSearch').focus();
    if (tipo === 'live') carregarExternos();
}
let limiteCanais = 48;
el('channelSearch').addEventListener('input', function () { limiteCanais = 48; renderizarSecao(secaoAtual); });
function maisCanais() {
    const anterior = limiteCanais;
    limiteCanais += 48;
    renderizarSecao(secaoAtual);
    const botoes = el('contentGrid').querySelectorAll('button');
    if (botoes[anterior]) botoes[anterior].focus();
}
function renderizarSecao(tipo) {
    const grid = el('contentGrid');
    grid.textContent = '';
    const busca = el('channelSearch').value.toLowerCase().trim();
    const itens = bancoDados.filter(item => item.tipo === tipo && item.nome.toLowerCase().includes(busca));
    el('loadMore').style.display = itens.length > limiteCanais ? 'block' : 'none';
    itens.slice(0, limiteCanais).forEach(item => {
        const card = document.createElement('div'); card.className = 'media-card';
        const img = document.createElement('img'); img.src = item.logo; img.alt = item.nome; img.loading = 'lazy';
        const title = document.createElement('h4'); title.textContent = item.nome;
        const button = document.createElement('button'); button.className = 'play-btn'; button.textContent = '▶ Assistir';
        button.addEventListener('click', () => abrirPlayer(item));
        card.appendChild(img); card.appendChild(title); card.appendChild(button); grid.appendChild(card);
    });
    if (!grid.children.length) grid.textContent = 'Nenhum conteúdo nesta seção.';
}
function abrirPlayer(item) {
    itemAtual = item;
    el('videoPlayerContainer').style.display = 'block';
    el('fullscreenButton').focus();
    const fontes = Array.isArray(item.fontes) ? item.fontes : [item.fontes];
    const select = el('sourceSelect');
    select.textContent = '';
    fontes.forEach((fonte, i) => {
        const option = document.createElement('option');
        option.value = fonte;
        try { option.textContent = `Fonte ${i + 1} — ${new URL(fonte).hostname}`; }
        catch (_) { option.textContent = `Fonte ${i + 1}`; }
        select.appendChild(option);
    });
    reproduzirFonte(item, fontes[0]);
}
function reproduzirFonte(item, fonte) {
    limparPlayer();
    el('videoPlayerContainer').style.display = 'block';
    el('videoTitle').textContent = item.nome;
    let url;
    try { url = new URL(fonte); if (!['http:', 'https:'].includes(url.protocol)) throw new Error(); }
    catch (_) { el('playerStatus').textContent = 'URL de mídia inválida.'; return; }
    // Explicit formato supports HLS endpoints without a .m3u8 extension.
    if (location.protocol === 'https:' && url.protocol === 'http:') {
        el('playerStatus').textContent = 'Esta fonte usa HTTP e pode ser bloqueada nesta página HTTPS. Selecione outra fonte.';
        return;
    }
    if (item.formato === 'embed') {
        if (url.protocol !== 'https:' || url.hostname !== 'rdcanais.org' || url.username || url.password || (url.port && url.port !== '443')) {
            el('playerStatus').textContent = 'Endereço de player não permitido.'; return;
        }
        video.style.display = 'none';
        el('embedPlayer').src = url.href;
        el('embedPlayer').style.display = 'block';
        el('externalPlayerLink').href = url.href;
        el('externalPlayerLink').style.display = 'block';
        el('playerStatus').textContent = 'Se o player não abrir aqui, use o link para o site de origem.';
        el('videoPlayerContainer').scrollIntoView({behavior:'smooth'});
        return;
    }
    const isHls = /\.m3u8$/i.test(url.pathname) || item.formato === 'hls';
    if (isHls && !video.canPlayType('application/vnd.apple.mpegurl')) {
        if (!window.Hls || !Hls.isSupported()) {
            el('playerStatus').textContent = 'Este navegador não oferece suporte a HLS.'; return;
        }
        hls = new Hls();
        hls.on(Hls.Events.ERROR, (_, data) => {
            if (data.fatal) {
                el('playerStatus').textContent = 'Falha ao carregar HLS. Verifique o link e as permissões CORS da origem.';
                hls.destroy(); hls = null;
            }
        });
        hls.loadSource(url.href); hls.attachMedia(video);
    } else { video.src = url.href; }
    video.play().catch(() => { el('playerStatus').textContent = 'Pressione Play para iniciar a reprodução.'; });
    el('videoPlayerContainer').scrollIntoView({behavior:'smooth'});
}
video.addEventListener('error', () => {
    if (video.getAttribute('src')) el('playerStatus').textContent = 'Não foi possível reproduzir. Verifique o link e o formato do vídeo.';
});
video.addEventListener('playing', () => { el('playerStatus').textContent = ''; });
function fecharPlayer() { limparPlayer(); el('videoPlayerContainer').style.display = 'none'; if (el('contentSection').style.display === 'block') el('channelSearch').focus(); }
function voltarProPainel() {
    fecharPlayer(); el('contentSection').style.display = 'none'; el('mainDashboard').style.display = 'grid';
    document.querySelector('.ibo-box').focus();
}

function telaCheia() {
    const box = el('videoPlayerContainer');
    if (document.fullscreenElement && document.exitFullscreen) {
        document.exitFullscreen(); return;
    }
    if (box.requestFullscreen) {
        const result = box.requestFullscreen();
        if (result && result.catch) result.catch(function () { el('playerStatus').textContent = 'Use o botão de tela cheia do próprio player.'; });
    } else {
        el('playerStatus').textContent = 'Use o botão de tela cheia do próprio player.';
    }
}
// Navigation only handles the parent page; embedded players own their controls.
document.addEventListener('keydown', function (event) {
    const active = document.activeElement;
    const editing = active && (active.tagName === 'INPUT' || active.tagName === 'SELECT');
    if (!editing && (event.key === 'Escape' || event.keyCode === 461)) {
        event.preventDefault();
        if (el('videoPlayerContainer').style.display === 'block') fecharPlayer(); else voltarProPainel();
        return;
    }
    const direction = {ArrowLeft: [-1,0], ArrowRight:[1,0], ArrowUp:[0,-1], ArrowDown:[0,1]}[event.key];
    if (!direction || editing || (active && active.tagName === 'VIDEO')) return;
    const candidates = Array.from(document.querySelectorAll('button, a[href], select, input, iframe, video')).filter(function (node) {
        return !node.disabled && node.getClientRects().length && getComputedStyle(node).visibility !== 'hidden';
    });
    if (!candidates.length) return;
    if (candidates.indexOf(active) < 0) { event.preventDefault(); candidates[0].focus(); return; }
    const rect = active.getBoundingClientRect();
    const x = rect.left + rect.width / 2, y = rect.top + rect.height / 2;
    let best = null, score = Infinity;
    candidates.forEach(function (node) {
        if (node === active) return;
        const r = node.getBoundingClientRect();
        const dx = r.left + r.width/2 - x, dy = r.top + r.height/2 - y;
        const forward = dx * direction[0] + dy * direction[1];
        const sideways = Math.abs(dx * direction[1] + dy * direction[0]);
        const value = forward + sideways * 3;
        if (forward > 1 && value < score) { best = node; score = value; }
    });
    if (best) { event.preventDefault(); best.focus(); best.scrollIntoView({block:'nearest'}); }
});
document.querySelector('.ibo-box').focus();
</script>
</body>
</html>
"""


@app.route('/')
def index():
    return render_template_string(HTML_IBO_INTERFACE, conteudo=carregar_conteudo())


@app.route('/api/catalogo')
def catalogo():
    return jsonify(carregar_conteudo())


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))
