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
    "Reuters": 5, "Associated Press": 5, "Bloomberg": 5, "Financial Times": 5, "The Wall Street Journal": 5,
    "BBC News": 4, "The Guardian": 4, "Mining.com": 4, "Folha de S. Paulo": 4, "Estadão": 4,
    "G1": 3, "Mining Technology": 3, "Notícias de Mineração Brasil": 3,
    "IBRAM": 2,
}

def is_yesterday(dt_utc, tz=TZ):
    if not dt_utc: return False
    yesterday = (datetime.now(tz).date() - timedelta(days=1))
    return dt_utc.astimezone(tz).date() == yesterday

def search_google_news(query, language_code, translator):
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
    formatted_news = ""
    for item in news_items:
        formatted_news += f"- Título: {item['title']}\n"
        formatted_news += f"  Fonte: {item['source']} (Confiabilidade: {item['reliability']}/5)\n"
        formatted_news += f"  Link: {item['link']}\n\n"

    # --- INÍCIO DA CORREÇÃO ---
    # As chaves que são parte do texto (e não variáveis) foram duplicadas para {{ e }}
    prompt = f"""
Você é um jornalista e editor-chefe de um portal de notícias sobre mineração. Sua tarefa é analisar as manchetes do dia {yday_date} e escrever notícias completas e originais para o seu público.

**SUA MISSÃO:**
Transformar uma lista de manchetes em um boletim de notícias bem escrito. Para cada evento significativo, você deve **redigir uma notícia completa**, não um resumo.

**REGRAS DE OURO:**
1.  **NÃO RESUMA, ESCREVA:** Para cada evento, crie um texto jornalístico. Comece com um parágrafo principal (lide), desenvolva o contexto nos parágrafos seguintes e, se possível, adicione uma análise sobre o impacto. A notícia deve ter entre 3 e 5 parágrafos.
2.  **SINTETIZE FONTES:** Se várias manchetes cobrem o mesmo fato, use-as para enriquecer uma única notícia. Combine as informações para criar a matéria mais completa possível.
3.  **TÍTULO ORIGINAL:** Crie um título chamativo e informativo para cada notícia que você escrever.
4.  **ESTRUTURA DE CATEGORIAS OBRIGATÓRIA:** Organize as notícias que você escreveu DENTRO das seguintes categorias. Estas categorias são fixas e devem estar presentes no output. Se não houver notícia para uma categoria, escreva "Nenhuma notícia relevante para esta categoria hoje."

---
**BOLETIM DE NOTÍCIAS DE MINERAÇÃO - {yday_date}**

**### Prospect Capital**
*(Notícias para investidores e mercado financeiro. Foco em M&A, resultados de empresas, investimentos, tendências de commodities, projetos de expansão.)*

**(Aqui você escreve a(s) notícia(s) completa(s) para esta categoria)**
**Título da Notícia 1**
(Texto da notícia com 3-5 parágrafos)
*Fontes: [Nome da Fonte 1], [Nome da Fonte 2]*
*Links: [Link 1], [Link 2]*

---
**### Prospect Pro**
*(Notícias para profissionais do setor. Foco em tecnologia, geologia, inovações em engenharia, segurança operacional, novos equipamentos e regulamentação técnica.)*

**(Aqui você escreve a(s) notícia(s) completa(s) para esta categoria)**

---
**### Mapa do Conhecimento**
*(Notícias para a academia e pesquisadores. Foco em P&D, estudos científicos, parcerias com universidades, novas descobertas e artigos relevantes.)*

**(Aqui você escreve a(s) notícia(s) completa(s) para esta categoria)**

---
**### Rochas & Histórias**
*(Notícias para o público geral. Foco em sustentabilidade, meio ambiente, impacto social, curiosidades sobre minerais, história e relação com comunidades.)*

**(Aqui você escreve a(s) notícia(s) completa(s) para esta categoria)**

---
**Manchetes Brutas para sua Análise:**
{formatted_news}
"""
    # --- FIM DA CORREÇÃO ---

    print("Enviando requisição para a API da OpenAI com o prompt final focado em notícias completas...")
    headers = {"Authorization": f"Bearer {openai_api_key}", "Content-Type": "application/json"}
    payload = {
        "model": "gpt-4o",
        "messages": [{"role": "system", "content": "Você é um jornalista que escreve notícias completas sobre mineração para um blog."}, {"role": "user", "content": prompt}],
        "temperature": 0.6,
        "max_tokens": 3800,
    }
    
    try:
        response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload, timeout=400 )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"Erro Crítico: Falha ao comunicar com a API da OpenAI. Erro: {e}", file=sys.stderr)
        return f"**FALHA NA GERAÇÃO DAS NOTÍCIAS**\n\nOcorreu um erro ao contatar a API da OpenAI: {e}"

def main():
    openai_api_key = os.environ.get("OPENAI_API_KEY")
    if not openai_api_key:
        print("Erro Crítico: OPENAI_API_KEY não encontrada.", file=sys.stderr)
        sys.exit(1)

    yday_date = (datetime.now(TZ).date() - timedelta(days=1)).strftime("%d/%m/%Y")
    translator = Translator()
    
    all_news = []
    seen_links = set()
    
    queries = {
        "mineração OR 'setor mineral'": "pt-BR",
        "mining industry OR mineral sector OR mining technology": "en-US"
    }
    
    for query, lang in queries.items():
        news_items = search_google_news(query, lang, translator)
        for item in news_items:
            if item['link'] not in seen_links:
                all_news.append(item)
                seen_links.add(item['link'])

    if not all_news:
        print("Nenhuma notícia de ontem foi encontrada. O script será encerrado.")
        return

    print(f"Total de {len(all_news)} notícias únicas encontradas para análise.")
    analysis = call_openai_for_analysis(all_news, yday_date, openai_api_key)
    
    with open(OUTPUT_FILENAME, "w", encoding="utf-8") as f:
        f.write(analysis)
    print(f"Sucesso! O boletim de notícias foi salvo em '{OUTPUT_FILENAME}'.")

if __name__ == "__main__":
    main()
