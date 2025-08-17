#!/usr/bin/env python3
import os
import sys
import requests
import feedparser
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from urllib.parse import quote
from googletrans import Translator

# --- CONFIGURAÇÕES ---
TZ = ZoneInfo("America/Bahia")
USER_AGENT_STRING = "Mozilla/5.0 (compatible; NewsBot/1.0; +https://github.com/features/actions )"
OUTPUT_FILENAME = "resumo-mineracao.txt"

# Escala de Confiabilidade (0-5)
SOURCE_RELIABILITY = {
    # Tier 5 (Muito Confiável): Agências de notícias globais e jornais financeiros de topo
    "Reuters": 5, "Associated Press": 5, "Bloomberg": 5, "Financial Times": 5, "The Wall Street Journal": 5,
    # Tier 4 (Confiável): Grandes portais de notícias e publicações especializadas renomadas
    "BBC News": 4, "The Guardian": 4, "Mining.com": 4, "Folha de S. Paulo": 4, "Estadão": 4,
    # Tier 3 (Moderadamente Confiável): Portais de notícias populares e publicações de nicho
    "G1": 3, "Mining Technology": 3, "Notícias de Mineração Brasil": 3,
    # Tier 2 (Requer Cautela): Fontes com viés conhecido ou menor rigor editorial
    "IBRAM": 2, # Informativo institucional, não jornalismo
    # Tier 1 (Pouco Confiável): Fontes com histórico de imprecisão
    # Tier 0 (Nada Confiável): Fontes não verificadas
}

def is_yesterday(dt_utc, tz=TZ):
    """Verifica se a data da notícia corresponde a ontem."""
    if not dt_utc:
        return False
    yesterday = (datetime.now(tz).date() - timedelta(days=1))
    return dt_utc.astimezone(tz).date() == yesterday

def search_google_news(query, language_code, translator):
    """Busca notícias no Google News, filtra e traduz se necessário."""
    query_encoded = quote(query)
    search_url = f"https://news.google.com/rss/search?q={query_encoded}&hl={language_code}&gl={language_code.split('-' )[1]}"
    
    print(f"Buscando notícias com a query: '{query}' (Idioma: {language_code})")
    fp = feedparser.parse(search_url, agent=USER_AGENT_STRING)
    
    items = []
    for entry in fp.entries:
        dt_utc = None
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            dt_utc = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)

        if is_yesterday(dt_utc):
            title = entry.title
            source_name = entry.source.get('title', 'Fonte desconhecida')
            link = entry.link

            if language_code == 'en-US':
                try:
                    title = translator.translate(title, src='en', dest='pt').text
                except Exception as e:
                    print(f"  -> Alerta: Falha ao traduzir título. Usando original. Erro: {e}")

            items.append({
                "title": title.strip(),
                "link": link,
                "source": source_name,
                "reliability": SOURCE_RELIABILITY.get(source_name, 2)
            })
    return items

def call_openai_for_analysis(news_items, yday_date, openai_api_key):
    """Chama a API da OpenAI com o prompt refeito para gerar notícias completas por categoria."""
    
    formatted_news = ""
    for item in news_items:
        formatted_news += f"- Título: {item['title']}\n"
        formatted_news += f"  Fonte: {item['source']} (Confiabilidade: {item['reliability']}/5)\n"
        formatted_news += f"  Link: {item['link']}\n\n"

    # --- PROMPT TOTALMENTE REFEITO ---
    prompt = f"""
Você é um jornalista e editor-chefe de um portal de notícias sobre mineraç
