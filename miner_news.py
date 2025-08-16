#!/usr/bin/env python3
import os
import sys
import requests
import feedparser
import json
from datetime import datetime, timedelta, timezone
from googletrans import Translator
from zoneinfo import ZoneInfo
from urllib.parse import quote
from fpdf import FPDF  # Biblioteca para gerar PDFs
from sklearn.linear_model import LinearRegression  # Exemplo de modelo para prever tendências
from weasyprint import HTML # Biblioteca para gerar PDFs a partir de HTML/CSS

# Configurações de fuso horário
TZ = ZoneInfo("America/Bahia")
UA = {"User-Agent": "Mozilla/5.0 (+news-bot)"}

# Função para verificar se a notícia é de ontem
def is_yesterday(dt_utc, tz=TZ):
    yday = (datetime.now(tz).date() - timedelta(days=1))
    return dt_utc.astimezone(tz).date() == yday

# Função para encurtar o link usando o TinyURL
def shorten_url(url):
    api_url = f"http://tinyurl.com/api-create.php?url={url}"
    response = requests.get(api_url)
    if response.status_code == 200:
        return response.text
    else:
        print(f"Erro ao encurtar o link: {url}")
        return url

# Função para verificar se a fonte é confiável
def is_trustworthy(source):
    # Fontes confiáveis locais e internacionais
    trusted_sources = {
        "Reuters": (10, "Fonte globalmente reconhecida com uma abordagem jornalística rigorosa."),
        "BBC": (10, "Fonte internacional com grande credibilidade."),
        "The Guardian": (9, "Fonte internacional com bom histórico de reportagens bem apuradas."),
        "Nature": (9, "Fonte acadêmica respeitada na área de ciências e pesquisa."),
        "Science": (9, "Fonte científica altamente confiável."),
        "Folha de S. Paulo": (8, "Fonte nacional amplamente respeitada e de longa trajetória."),
        "O Globo": (8, "Fonte nacional com grande audiência e histórica credibilidade."),
        "Estadão": (8, "Fonte de grande circulação no Brasil com notícias bem apuradas."),
        "G1": (7, "Fonte nacional que oferece uma boa cobertura de notícias, embora com algumas falhas ocasionais."),
        "Veja": (7, "Fonte de renome, mas com uma abordagem mais voltada para opiniões e posicionamentos."),
        "Correio Braziliense": (6, "Fonte local com boa cobertura, mas com algumas críticas sobre imparcialidade."),
        "Diário de Pernambuco": (6, "Fonte local importante, mas com limitações em algumas áreas de cobertura."),
    }
    # Pontuação e justificativa para a confiabilidade
    if source in trusted_sources:
        score, reason = trusted_sources[source]
    else:
        score, reason = (5, "Fonte não reconhecida. Requer análise crítica adicional.")
    return score, reason

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
        # Se a data não estiver presente, ignoramos ou atribuimos uma data padrão
        if not dt:
            print(f"Data não encontrada para a notícia: {getattr(e, 'title', 'Título não disponível')}")
            continue  # Ignorar ou atribuir data padrão, dependendo da necessidade
        if is_yesterday(dt):
            title = getattr(e, "title", "").strip()
            source = getattr(getattr(e, "source", {}), "title", "") or getattr(e, "source", "")
            score, reason = is_trustworthy(source)
            shortened_link = shorten_url(link)  # Encurtar o link antes de adicionar
            items.append({"title": title, "link": shortened_link, "source": source, "dt": dt, "score": score, "reason": reason})
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
2) Organize as notícias conforme o público-alvo:
   - **Mapa do Conhecimento Prospect**: Público-alvo: Universidades, pesquisadores, estudantes. Tom: educativo, formativo, inspirador. Slug: mapa-do-conhecimento-prospect
   - **Prospect Capital**: Público-alvo: Interessados em investimentos e negócios em mineração. Tom: estratégico, econômico, visão de mercado. Slug: prospect-capital
   - **Prospect Pro**: Público-alvo: Geólogos, engenheiros, mineradoras, consultores. Tom: técnico, profissional, detalhado. Slug: prospect-pro
   - **Prospect Rochas & Histórias**: Público-alvo: Público geral interessado em mineração e meio ambiente. Tom: acessível, envolvente, curioso. Slug: prospect-rochas-e-historias

3) Para cada público, escreva o título seguido da fonte entre parênteses.
4) Abaixo de cada notícia, forneça um resumo com 4 a 8 linhas explicando o conteúdo da notícia de forma clara e objetiva.
5) Coloque os links das fontes diretamente abaixo de cada notícia, se possível.
6) Se houver mais de um site com o mesmo assunto, inclua as informações de ambos os sites, detalhando as fontes. Caso contrário, forneça apenas a fonte encontrada.
7) Informe o **rank de confiabilidade da fonte** de 1 a 10, onde 1 é pouco confiável e 10 é muito confiável.
8) Forneça uma **justificativa** sobre a confiabilidade de cada fonte, explicando o porquê.
9) Ignore completamente qualquer manchete que não seja de {yday_date} ou que seja de anos anteriores, mesmo que pareça relevante.
10) Use {yday_date} como data de referência no título e no conteúdo.
11) Confirme que gerou no mínimo 3 notícias para cada público.

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
    r = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload, timeout=600 )  # Aumentando o timeout para 10 minutos
    r.raise_for_status()
    data = r.json()
    return data["choices"][0]["message"]["content"].strip()

# Função para prever tendências com IA
def predict_trends(news_data):
    # Exemplo simples de previsão com LinearRegression
    model = LinearRegression()
    X = [[i] for i in range(len(news_data))]  # Índices como variável independente
    y = [news["dt"].timestamp() for news in news_data]  # Timestamps das notícias
    model.fit(X, y)
    trend = model.predict([[len(news_data)]])  # Prevendo a tendência futura
    return trend

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

    # Prevendo tendências com IA (exemplo simples)
    trend = predict_trends(items)
    print(f"Tendência prevista: {trend}")

if __name__ == "__main__":
    main()
