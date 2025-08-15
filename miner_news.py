#!/usr/bin/env python3
import os
import sys
import requests
import feedparser
from datetime import datetime, timedelta, timezone
from googletrans import Translator
from zoneinfo import ZoneInfo

# Configurações de fuso horário
TZ = ZoneInfo("America/Bahia")  # seu fuso
UA = {"User-Agent": "Mozilla/5.0 (+news-bot)"}

# Função para verificar se a notícia é de ontem
def is_yesterday(dt_utc, tz=TZ):
    yday = (datetime.now(tz).date() - timedelta(days=1))
    return dt_utc.astimezone(tz).date() == yday

# Função para buscar notícias diretamente pela web
def search_news_on_web(query):
    search_url = f"https://api.openai.com/v1/engines/gpt-4o-mini/completions"
    openai_api_key = os.environ.get("OPENAI_API_KEY")
    if not openai_api_key:
        print("Faltou OPENAI_API_KEY no ambiente.", file=sys.stderr)
        sys.exit(1)

    prompt = f"""
    Busque por notícias no setor de mineração para o seguinte termo: "{query}"
    As notícias devem ser de fontes variadas e atuais, abordando tópicos como mineração, setor mineral, novas tecnologias e inovações.
    Faça uma pesquisa completa na web para encontrar os links mais relevantes sobre o tema.
    """

    headers = {
        "Authorization": f"Bearer {openai_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": "Você é um assistente que busca e resume notícias sobre mineração."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.3,
    }

    r = requests.post(search_url, headers=headers, json=payload, timeout=60)
    r.raise_for_status()
    data = r.json()
    return data['choices'][0]['message']['content']

# Função para traduzir texto para português
def translate_text(text):
    translator = Translator()
    translated = translator.translate(text, src='en', dest='pt')
    return translated.text

# Função para chamar a API OpenAI para gerar o resumo e notícias categorizadas
def call_openai(headlines_text, yday_date, openai_api_key):
    prompt = f"""
Você é um analista de notícias sobre mineração.
A seguir estão manchetes coletadas APENAS da data {yday_date}, no contexto de mineração (setor mineral, não incluir criptoativos).

Tarefas:
1) Produza um resumo em português do Brasil (PT-BR), direto ao ponto, com 5–10 tópicos do que realmente IMPORTA, sem floreio, sem opinião e sem redundância.
2) Na seção "Principais manchetes", liste de 8 a 15 notícias.  
   - Para cada notícia, escreva o título seguido da fonte entre parênteses.  
   - Logo abaixo, insira um parágrafo com 4 a 8 linhas explicando o conteúdo da notícia de forma clara e objetiva.  
   - Atribua uma categoria e defina um tom conforme a categoria:
     - **Mapa do Conhecimento Prospect**: Público-alvo: Universidades, pesquisadores, estudantes. Tom: educativo, formativo, inspirador. Slug: mapa-do-conhecimento-prospect
     - **Prospect Capital**: Público-alvo: Interessados em investimentos e negócios em mineração. Tom: estratégico, econômico, visão de mercado. Slug: prospect-capital
     - **Prospect Pro**: Público-alvo: Geólogos, engenheiros, mineradoras, consultores. Tom: técnico, profissional, detalhado. Slug: prospect-pro
     - **Prospect Rochas & Histórias**: Público-alvo: Público geral interessado em mineração e meio ambiente. Tom: acessível, envolvente, curioso. Slug: prospect-rochas-e-historias
3) Na seção "Links-chave", inclua apenas 3–5 URLs mais relevantes e atuais.
4) Ignore completamente qualquer manchete que não seja de {yday_date} ou que seja de anos anteriores, mesmo que pareça relevante.
5) Use {yday_date} como data de referência no título e no conteúdo.
6) Confirme que gerou no mínimo 3 notícias, com as categorias mencionadas acima.
7) Se alguma manchete estiver em inglês, traduza para o português.
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
        "model": "gpt-4o-mini",
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

# Função principal
def main():
    openai_api_key = os.environ.get("OPENAI_API_KEY")
    if not openai_api_key:
        print("Faltou OPENAI_API_KEY no ambiente.", file=sys.stderr)
        sys.exit(1)

    yday_date = (datetime.now(TZ).date() - timedelta(days=1)).strftime("%d/%m/%Y")
    query = "notícias sobre mineração, setor mineral, novas tecnologias"
    news_text = search_news_on_web(query)
    print(f"Notícias buscadas sobre mineração: {news_text[:200]}...")

    try:
        summary = call_openai(news_text, yday_date, openai_api_key)
        print(f"Resumo gerado: {summary[:200]}...")
    except Exception as e:
        summary = "Não foi possível gerar o resumo hoje. Erro: " + str(e)
        print(f"Erro na API: {str(e)}")

    now_ba = datetime.now(TZ).strftime("%d/%m/%Y %H:%M")
    out = [
        f"Resumo diário de mineração — {yday_date}",
        f"(Gerado em {now_ba} BRT)\n",
        summary,
        "\n— Fonte automatizada via GPT (PT-BR/BR)."
    ]
    text = "\n".join(out).strip() + "\n"
    print(f"Texto final a ser salvo: {text[:200]}...")

    with open("resumo-mineracao.txt", "w", encoding="utf-8") as f:
        f.write(text)
        print("Arquivo salvo com sucesso!")

if __name__ == "__main__":
    main()
