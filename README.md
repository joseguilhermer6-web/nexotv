# NexoTV

Interface Flask com player HLS e catálogo de 332 canais importado de https://github.com/scherrer556/IPTV-open-source . A disponibilidade das fontes depende dos servidores de origem e da compatibilidade com o navegador. Os 10 itens de anime/filmes ainda usam URLs de exemplo.

## Deploy no Render

Crie um Web Service conectado a este repositório, com runtime Python.

- Build Command: `pip install -r requirements.txt`
- Start Command: `gunicorn app:app --bind 0.0.0.0:$PORT`

Execução local: `pip install -r requirements.txt` e `python app.py`.

O catálogo é lido da pasta do app. Edições em tempo de execução no disco efêmero da hospedagem não persistem em novos deploys.
