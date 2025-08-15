#!/usr/bin/env python3
import os
import sys
import requests
import feedparser
from datetime import datetime, timedelta, timezone
from googletrans import Translator
from zoneinfo import ZoneInfo
from urllib.parse import quote  # Importando a função quote para codificar a URL

# Configurações de fuso horário
TZ = ZoneInfo("America/Bahia")  # seu fuso
UA = {"User-Agent": "Mozilla/5.0 (+news-bot)"}

# Função para verificar se a notícia é de ontem
def is_yesterday(dt_utc, tz=TZ):
    yday = (datetime.now(tz).date() - timedelta(days=1))
    return dt_utc.astimezone(tz).date() == yday

# Função para buscar notícias diretamente pela web
def search_news_on_web(query):
    query_encoded = quote(query)  # Codificando a query para evitar problemas com espaços
    search_url = f"https://news.google.com/rss/search?q={query_encoded}&hl=pt-BR&gl=BR&ceid=BR:pt-419"
    fp = feedparser.parse(search_url)
    print(f"Feed retornou {len(fp.entries)} entradas")
    items = []
    seen = set()
    for e in fp.entries:
        link = getattr(e, "link", "")
        if not link or link in seen:
            continue
        dt = None
        for attr in ("published_parsed", "updated_parsed"):
            t = getattr(e, attr, None)
            if t:
                dt = datetime(*t[:6], tzinfo=timezone.utc)
                break
        if not dt:
            continue
        if is_yesterday(dt):
            title = getattr(e, "title", "").strip()
            source = getattr(getattr(e, "source", {}), "title", "") or getattr(e, "source", "")
            items.append({"title": title, "link": link, "source": source, "dt": dt})
            seen.add(link)
    items.sort(key=lambda x: x["dt"])
    return items

# Função para chamar a API OpenAI para gerar o resumo e notícias categorizadas
def call_openai(headlines_text, yday_date, openai_api_key):
    prompt = f"""
Você é um analista que escreve para executivos.
A seguir estão manchetes coletadas APENAS da data {yday_date}, no contexto de mineração (setor mineral, não incluir criptoativos).

Tarefas:
1) Produza um resumo em português do Brasil (PT-BR), direto ao ponto, com 5–10 tópicos do que realmente IMPORTA, sem floreio, sem opinião e sem redundância.
2) Na seção "Principais manchetes", liste de 8 a 15 notícias.  
   - Para cada notícia, escreva o título seguido da fonte entre parênteses.  
   - Logo abaixo, insira um parágrafo com 4 a 8 linhas explicando o conteúdo da notícia de forma clara e objetiva.  
3) Na seção "Links-chave", inclua todas as URLs mais relevantes e atuais, os links devem ficar abaixo de cada noticia e não em uma seção separada.
4) Ignore completamente qualquer manchete que não seja de {yday_date} ou que seja de anos anteriores, mesmo que pareça relevante.
5) Use {yday_date} como data de referência no título e no conteúdo.
6) Confirme que gerou no mínimo 6 notícias

Manchetes:
---
{headlines_text}
---
"""
    headers = {
        "Authorization": f"Bearer {openai_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "gpt-4",  # Modelo atualizado
        "messages": [
            {"role": "system", "content": "Você resume notícias de forma clara e objetiva."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.3,
    }
    r = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload, timeout=60)
    r.raise_for_status()
    data = r.json()
    return data["choices"][0]["message"]["content"].strip()

def main():
    openai_api_key = os.environ.get("OPENAI_API_KEY")
    if not openai_api_key:
        print("Faltou OPENAI_API_KEY no ambiente.", file=sys.stderr)
        sys.exit(1)

    yday_date = (datetime.now(TZ).date() - timedelta(days=1)).strftime("%d/%m/%Y")
    query = "mineração setor mineral novas tecnologias"
    items = search_news_on_web(query)
    print(f"Procurando manchetes de {yday_date}, total de items: {len(items)}")

    if not items:
        print("Nenhuma notícia de ontem encontrada, utilizando fallback com as 10 mais recentes.")
        fp = feedparser.parse("https://news.google.com/rss/search?q=minera%C3%A7%C3%A3o&hl=pt-BR&gl=BR&ceid=BR:pt-419")
        items = [{"title": getattr(e, "title", "").strip(), "link": getattr(e, "link", ""), "source": getattr(getattr(e, "source", {}), "title", "")} for e in fp.entries[:10]]

    lines = [f"• {it['title']} — {it.get('source', '')} — {it['link']}" for it in items]
    headlines_text = "\n".join(lines)
    print(f"Texto enviado à API: {headlines_text[:200]}...")

    try:
        summary = call_openai(headlines_text, yday_date, openai_api_key)
        print(f"Resumo gerado: {summary[:200]}...")
    except Exception as e:
        summary = "Não foi possível gerar o resumo hoje. Erro: " + str(e)
        print(f"Erro na API: {str(e)}")

    now_ba = datetime.now(TZ).strftime("%d/%m/%Y %H:%M")
    out = [
        f"Resumo diário de mineração — {yday_date}",
        f"(Gerado em {now_ba} BRT)\n",
        summary,
        "\n— Fonte automatizada via Google News (PT-BR/BR)."
    ]
    text = "\n".join(out).strip() + "\n"
    print(f"Texto final a ser salvo: {text[:200]}...")

    with open("resumo-mineracao.txt", "w", encoding="utf-8") as f:
        f.write(text)
        print("Arquivo salvo com sucesso!")

if __name__ == "__main__":
    main()
