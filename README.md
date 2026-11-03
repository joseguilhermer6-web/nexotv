# NexoTV

Interface Flask com player HLS e catálogo de 332 canais importado de https://github.com/scherrer556/IPTV-open-source . A disponibilidade das fontes depende dos servidores de origem e da compatibilidade com o navegador. Os 10 itens de anime/filmes ainda usam URLs de exemplo.

## Deploy no Render

Crie um Web Service conectado a este repositório, com runtime Python.

- Build Command: `pip install -r requirements.txt`
- Start Command: `gunicorn app:app --bind 0.0.0.0:$PORT`

Execução local: `pip install -r requirements.txt` e `python app.py`.

O catálogo é lido da pasta do app. Edições em tempo de execução no disco efêmero da hospedagem não persistem em novos deploys.

## Placar ao vivo

No Render, em Environment, configure `API_FOOTBALL_KEY` com a chave da API-Football/API-Sports. Se a chave veio do RapidAPI, configure também `API_FOOTBALL_PROVIDER=rapidapi`. Não envie a chave ao GitHub. O botão **Carregar jogos e placares** aparece ao abrir um canal. Escolha manualmente a partida: o nome do programa e o canal não identificam o jogo com segurança. As consultas são compartilhadas entre visitantes e limitadas a uma por 20 minutos e 90 em qualquer janela de 24 horas por instância. O placar pode estar à frente do vídeo. O atraso da transmissão do player incorporado não pode ser medido pelo servidor Flask.

## Animes, séries e filmes

O site aceita `episodios` em cada item de `catalogo_canais.json`. Exemplo:

```json
{
  "nome": "Naruto Clássico",
  "tipo": "anime",
  "categoria": "Naruto",
  "logo": "",
  "episodios": [
    {"numero": 1, "nome": "Episódio 1", "arco": "País das Ondas", "url": "https://SEU-ARMAZENAMENTO/naruto-001.mp4"}
  ]
}
```

O seletor só mostra episódios com URL de vídeo. Arquivos locais no celular ou computador precisam ser enviados a um serviço de armazenamento que forneça URL direta HTTPS e permita reprodução no navegador. Vídeos `.mp4` com H.264/AAC tendem a funcionar melhor em TVs antigas. O site não hospeda os arquivos de vídeo e o GitHub não é indicado para armazenar temporadas completas.
