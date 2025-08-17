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

# Fontes RSS diretas de alta credibilidade
DIRECT_RSS_FEEDS = {
    "Mining.com": "https://www.mining.com/feed/",
    "Global Mining Review": "https://www.globalminingreview.com/rss/news/",
    "Mining Technology": "https://www.mining-technology.com/feed/",
    "Notícias de Mineração Brasil": "https://www.noticiasdemineracao.com/feed/",
    "IBRAM": "https://ibram.org.br/feed/",
}

# Nível de confiabilidade pré-definido para fontes conhecidas
TRUSTED_SOURCES_RANKING = {
    "Reuters": 10, "Associated Press": 10, "Bloomberg": 10,
    "Financial Times": 9, "The Wall Street Journal": 9, "BBC News": 9,
    "Mining.com": 9, "Global Mining Review": 8, "Mining Technology": 8,
    "Notícias de Mineração Brasil": 8, "IBRAM": 7, "G1": 7, "Folha de S. Paulo": 8,
}

def is_yesterday(dt_utc, tz=TZ ):
    """Verifica se a data da notícia corresponde a ontem."""
    yesterday = (datetime.now(tz).date() - timedelta(days=1))
    return dt_utc.astimezone(tz).date() == yesterday

def fetch_news_from_feed(feed_url, source_name, translator):
    """Busca e processa notícias de um feed RSS específico."""
    print(f"Buscando no feed: {source_name}...")
    items = []
    try:
        fp = feedparser.parse(feed_url, agent=USER_AGENT_STRING)
        for entry in fp.entries:
            dt_utc = None
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                dt_utc = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
            
            if dt_utc and is_yesterday(dt_utc):
                title = entry.title
                summary = entry.get("summary", "")
                link = entry.link
                
                # Traduz se a fonte for internacional (não-português)
                if source_name in ["Mining.com", "Global Mining Review", "Mining Technology"]:
                    title = translator.translate(title, src='en', dest='pt').text
                    summary = translator.translate(summary, src='en', dest='pt').text

                items.append({
                    "title": title.strip(),
                    "summary": summary.strip(),
                    "link": link,
                    "source": source_name,
                    "reliability": TRUSTED_SOURCES_RANKING.get(source_name, 6) # Default 6 se não listado
                })
    except Exception as e:
        print(f"  -> Erro ao buscar em {source_name}: {e}")
    return items

def collect_all_news():
    """Coleta notícias de todas as fontes, incluindo RSS direto e buscas no Google."""
    translator = Translator()
    all_news = []
    seen_links = set()

    # 1. Busca em feeds RSS diretos
    for name, url in DIRECT_RSS_FEEDS.items():
        news = fetch_news_from_feed(url, name, translator)
        for item in news:
            if item['link'] not in seen_links:
                all_news.append(item)
                seen_links.add(item['link'])
    
    print(f"Total de notícias coletadas até agora: {len(all_news)}")
    return all_news

def call_openai_for_synthesis(news_items, yday_date, openai_api_key):
    """Chama a API da OpenAI com o novo prompt focado em síntese e análise."""
    
    # Formata os dados para o prompt
    formatted_news = ""
    for item in news_items:
        formatted_news += f"- FONTE: {item['source']} (Confiabilidade: {item['reliability']}/10)\n"
        formatted_news += f"  TÍTULO: {item['title']}\n"
        formatted_news += f"  RESUMO: {item['summary']}\n"
        formatted_news += f"  LINK: {item['link']}\n\n"

    prompt = f"""
Você é um analista de inteligência de mercado sênior, especializado no setor global de mineração. Sua tarefa é criar um briefing diário para executivos, baseado nas notícias coletadas de {yday_date}.

**Diretrizes Fundamentais:**
1.  **SINTETIZE, NÃO APENAS LISTE:** Seu principal valor é conectar informações. Se múltiplas fontes (ex: Mining.com e Reuters) cobrem o mesmo evento (ex: a aquisição da empresa X pela Y), **não crie duas notícias separadas**. Crie uma única análise coesa sobre o evento, citando ambas as fontes. Ex: "O mercado reagiu à aquisição da Empresa X pela Y (fontes: Mining.com, Reuters), com analistas destacando...".
2.  **FOCO NO "E DAÍ?":** Para cada notícia sintetizada, explique o impacto e a relevância. Por que um executivo deveria se importar? É uma nova tendência, um risco, uma oportunidade?
3.  **AVALIAÇÃO DE CONFIABILIDADE:** Use a pontuação de confiabilidade fornecida para cada fonte para ponderar sua análise. Dê mais peso a fontes com pontuação 9-10. Se uma notícia vem apenas de uma fonte de baixa confiabilidade, mencione isso como um ponto de atenção.
4.  **ESTRUTURA OBRIGATÓRIA:** Organize o briefing exatamente nas seguintes categorias. Para cada categoria, gere de 1 a 3 análises sintetizadas. Se não houver notícias relevantes para uma categoria, escreva "Nenhuma análise significativa para esta categoria hoje."

---
**BRIEFING DE INTELIGÊNCIA DE MINERAÇÃO - {yday_date}**

**1. Resumo Executivo (Visão Geral Estratégica)**
*   (3 a 5 bullet points destacando os movimentos mais críticos do dia, as tendências emergentes e os principais riscos ou oportunidades identificados na sua análise.)

**2. Análises por Categoria:**

   **a) Mercados e Finanças (Prospect Capital)**
   *(Análises sobre fusões e aquisições, investimentos, flutuações de preços de commodities, resultados financeiros de grandes players, projetos de capital e tendências de mercado.)*

   **b) Tecnologia e Operações (Prospect Pro)**
   *(Análises sobre inovações tecnológicas, automação, digitalização, novas técnicas de exploração e processamento, segurança operacional e eficiência.)*

   **c) ESG, Regulação e Geopolítica (Prospect Sustentável)**
   *(Análises sobre sustentabilidade, licenciamento ambiental, relações com comunidades, mudanças regulatórias, riscos geopolíticos e pautas de governança corporativa.)*

---
**Dados Brutos Coletados para sua Análise:**
{formatted_news}
"""
    print("Enviando requisição para a API da OpenAI com prompt de síntese...")
    headers = {"Authorization": f"Bearer {openai_api_key}", "Content-Type": "application/json"}
    payload = {
        "model": "gpt-4o",
        "messages": [
            {"role": "system", "content": "Você é um analista de inteligência de mercado sênior para o setor de mineração."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.4, # Um pouco mais de criatividade para a síntese
        "max_tokens": 3500,
    }
    
    try:
        response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload, timeout=300 ) # Timeout de 5 minutos
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"].strip()
    except requests.RequestException as e:
        print(f"Erro Crítico: Falha ao comunicar com a API da OpenAI. Erro: {e}", file=sys.stderr)
        return f"**FALHA NA GERAÇÃO DA ANÁLISE**\n\nOcorreu um erro ao contatar a API da OpenAI para gerar o briefing de hoje.\n\nDetalhes do erro: {e}"

def main():
    openai_api_key = os.environ.get("OPENAI_API_KEY")
    if not openai_api_key:
        print("Erro Crítico: A variável de ambiente OPENAI_API_KEY não foi encontrada.", file=sys.stderr)
        sys.exit(1)

    yday_date = (datetime.now(TZ).date() - timedelta(days=1)).strftime("%d/%m/%Y")
    
    news_items = collect_all_news()

    if not news_items:
        print("Nenhuma notícia de ontem foi encontrada em nenhuma das fontes. Encerrando.")
        # Opcional: criar um arquivo dizendo que não houve notícias
        with open(OUTPUT_FILENAME, "w", encoding="utf-8") as f:
            f.write(f"# Análise de Inteligência de Mineração - {yday_date}\n\n")
            f.write("Nenhuma notícia relevante encontrada nas fontes monitoradas para o dia de ontem.")
        return

    print(f"Total de {len(news_items)} notícias únicas enviadas para análise.")
    analysis = call_openai_for_synthesis(news_items, yday_date, openai_api_key)
    
    try:
        with open(OUTPUT_FILENAME, "w", encoding="utf-8") as f:
            f.write(analysis)
        print(f"Sucesso! A análise de inteligência foi salva em '{OUTPUT_FILENAME}'.")
    except IOError as e:
        print(f"Erro Crítico: Falha ao escrever no arquivo '{OUTPUT_FILENAME}'. Erro: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
