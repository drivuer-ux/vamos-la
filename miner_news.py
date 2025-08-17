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
    # Ex: &hl=pt-BR&gl=BR
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

            # Traduz se a busca for em inglês
            if language_code == 'en-US':
                try:
                    title = translator.translate(title, src='en', dest='pt').text
                except Exception as e:
                    print(f"  -> Alerta: Falha ao traduzir título. Usando original. Erro: {e}")

            items.append({
                "title": title.strip(),
                "link": link,
                "source": source_name,
                "reliability": SOURCE_RELIABILITY.get(source_name, 2) # Default 2 para fontes não listadas
            })
    return items

def call_openai_for_analysis(news_items, yday_date, openai_api_key):
    """Chama a API da OpenAI com um prompt focado em criar análises únicas."""
    
    formatted_news = ""
    for item in news_items:
        formatted_news += f"- Título: {item['title']}\n"
        formatted_news += f"  Fonte: {item['source']} (Confiabilidade: {item['reliability']}/5)\n"
        formatted_news += f"  Link: {item['link']}\n\n"

    prompt = f"""
Você é um analista de mercado especializado em mineração. Sua missão é criar um briefing conciso e inteligente para executivos, baseado nas manchetes do dia {yday_date}.

**Sua principal tarefa é SINTETIZAR.**
Se várias manchetes falam sobre o mesmo evento (ex: "Vale anuncia novo projeto na Amazônia" e "Ações da Vale sobem após anúncio"), você deve **combiná-las em uma única notícia analítica**. Não liste as notícias, crie um parágrafo coeso que conecte os fatos e explique o impacto.

**REGRAS:**
1.  **Crie Notícias Únicas:** Para cada evento importante, escreva uma análise original. Comece com um título seu, que resuma o evento.
2.  **Cite as Fontes:** Ao final de cada análise, cite as fontes usadas entre parênteses. Ex: (Fontes: Reuters, G1).
3.  **Use a Confiabilidade:** Dê mais importância para notícias de fontes com confiabilidade 4 ou 5. Se uma notícia vier de uma fonte de baixa confiabilidade (0-2), trate-a com ceticismo.
4.  **Organize por Categoria:** Distribua suas análises nas categorias abaixo. Crie de 1 a 3 análises por categoria. Se não houver nada relevante, escreva "Nenhuma análise relevante para esta categoria hoje."

---
**ANÁLISE DE MERCADO DE MINERAÇÃO - {yday_date}**

**1. Resumo Executivo**
*(Escreva de 3 a 4 tópicos curtos resumindo os eventos mais críticos do dia. Qual foi o grande destaque?)*

**2. Análises Detalhadas**

   **a) Finanças e Grandes Empresas**
   *(Análises sobre investimentos, resultados financeiros, movimentações de ações, fusões e aquisições.)*

   **b) Tecnologia, Inovação e Operações**
   *(Análises sobre novas tecnologias, automação, descobertas geológicas e eficiência operacional.)*

   **c) Meio Ambiente, Social e Governança (ESG)**
   *(Análises sobre sustentabilidade, legislação, licenciamento e relações com comunidades.)*

---
**Manchetes Coletadas para sua Análise:**
{formatted_news}
"""
    print("Enviando requisição para a API da OpenAI com o prompt revisado...")
    headers = {"Authorization": f"Bearer {openai_api_key}", "Content-Type": "application/json"}
    payload = {
        "model": "gpt-4o",
        "messages": [{"role": "system", "content": "Você é um analista de mineração que sintetiza notícias para executivos."}, {"role": "user", "content": prompt}],
        "temperature": 0.5,
        "max_tokens": 3000,
    }
    
    try:
        response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload, timeout=300 )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"Erro Crítico: Falha ao comunicar com a API da OpenAI. Erro: {e}", file=sys.stderr)
        return f"**FALHA NA GERAÇÃO DA ANÁLISE**\n\nOcorreu um erro ao contatar a API da OpenAI: {e}"

def main():
    openai_api_key = os.environ.get("OPENAI_API_KEY")
    if not openai_api_key:
        print("Erro Crítico: OPENAI_API_KEY não encontrada.", file=sys.stderr)
        sys.exit(1)

    yday_date = (datetime.now(TZ).date() - timedelta(days=1)).strftime("%d/%m/%Y")
    translator = Translator()
    
    # Coleta de notícias em português e inglês
    all_news = []
    seen_links = set()
    
    queries = {
        "mineração OR 'setor mineral'": "pt-BR",
        "mining industry OR mineral sector": "en-US"
    }
    
    for query, lang in queries.items():
        news_items = search_google_news(query, lang, translator)
        for item in news_items:
            if item['link'] not in seen_links:
                all_news.append(item)
                seen_links.add(item['link'])

    if not all_news:
        print("Nenhuma notícia de ontem foi encontrada. O script será encerrado.")
        # Para evitar um commit vazio, podemos não criar o arquivo ou criar um com uma mensagem.
        # Por enquanto, vamos apenas sair para que o passo de commit não encontre mudanças.
        return

    print(f"Total de {len(all_news)} notícias únicas encontradas para análise.")
    analysis = call_openai_for_analysis(all_news, yday_date, openai_api_key)
    
    with open(OUTPUT_FILENAME, "w", encoding="utf-8") as f:
        f.write(analysis)
    print(f"Sucesso! A análise foi salva em '{OUTPUT_FILENAME}'.")

if __name__ == "__main__":
    main()
