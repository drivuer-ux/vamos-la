#!/usr/bin/env python3
import os
import sys
import requests
import feedparser
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from urllib.parse import quote

# --- CONFIGURAÇÕES ---
# Fuso horário para referência do "dia anterior"
TZ = ZoneInfo("America/Bahia")
# User-Agent para evitar bloqueios em requisições HTTP
USER_AGENT_STRING = "Mozilla/5.0 (compatible; NewsBot/1.0; +https://github.com/features/actions )"
# Nome do arquivo de saída
OUTPUT_FILENAME = "resumo-mineracao.txt"

# --- FUNÇÕES AUXILIARES ---

def is_yesterday(dt_utc, tz=TZ):
    """Verifica se a data da notícia (em UTC) corresponde ao dia de ontem no fuso horário local."""
    yesterday = (datetime.now(tz).date() - timedelta(days=1))
    return dt_utc.astimezone(tz).date() == yesterday

def shorten_url(url):
    """Encurta uma URL usando a API do TinyURL."""
    try:
        api_url = f"http://tinyurl.com/api-create.php?url={quote(url )}"
        # Passamos o User-Agent como um header na requisição
        headers = {'User-Agent': USER_AGENT_STRING}
        response = requests.get(api_url, headers=headers, timeout=10)
        response.raise_for_status()
        return response.text
    except requests.RequestException as e:
        print(f"Alerta: Não foi possível encurtar a URL {url}. Erro: {e}. Usando a URL original.")
        return url

def search_news_on_web(query):
    """Busca notícias no Google News RSS, filtra as de ontem e organiza os dados."""
    query_encoded = quote(query)
    search_url = f"https://news.google.com/rss/search?q={query_encoded}&hl=pt-BR&gl=BR&ceid=BR:pt-419"
    
    print(f"Buscando notícias com a query: '{query}'" )
    
    # --- INÍCIO DA CORREÇÃO ---
    # O parâmetro 'agent' espera uma string, não um dicionário.
    # Passamos a string diretamente.
    fp = feedparser.parse(search_url, agent=USER_AGENT_STRING)
    # --- FIM DA CORREÇÃO ---
    
    items = []
    seen_links = set()

    for entry in fp.entries:
        link = getattr(entry, "link", "")
        if not link or link in seen_links:
            continue

        dt_utc = None
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            dt_utc = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
        
        if dt_utc and is_yesterday(dt_utc):
            title = getattr(entry, "title", "Título não disponível").strip()
            source = getattr(getattr(entry, "source", {}), "title", "Fonte não informada")
            
            items.append({
                "title": title,
                "link": shorten_url(link),
                "source": source,
                "dt": dt_utc
            })
            seen_links.add(link)
            
    items.sort(key=lambda x: x["dt"])
    print(f"Encontradas {len(items)} notícias de ontem.")
    return items

def call_openai(headlines_text, yday_date, openai_api_key):
    """Chama a API da OpenAI para gerar o resumo e categorizar as notícias."""
    prompt = f"""
Você é um analista sênior especializado no setor de mineração e escreve resumos para executivos.
A data de referência para as notícias é {yday_date}.

**Sua tarefa é:**
1.  **Resumo Executivo:** Crie um resumo em 5 a 7 tópicos (bullet points) sobre os eventos mais importantes do dia no setor mineral. Seja direto e foque no que é estratégico.
2.  **Categorização de Notícias:** Organize as manchetes abaixo em quatro categorias de público, conforme descrito. Para cada notícia, forneça:
    *   O título original.
    *   A fonte entre parênteses.
    *   Um resumo claro e objetivo de 4 a 6 linhas.
    *   O link encurtado.
    *   **Importante:** Se não encontrar notícias para uma categoria, escreva "Nenhuma notícia relevante encontrada para este público hoje."

**Categorias:**
*   **Prospect Capital (Para Investidores):** Foco em finanças, M&A, resultados de empresas, tendências de mercado e projetos de expansão.
*   **Prospect Pro (Para Profissionais do Setor):** Foco em tecnologia, geologia, inovações em engenharia, segurança operacional e regulamentação técnica.
*   **Mapa do Conhecimento (Para Academia):** Foco em pesquisa, desenvolvimento, estudos científicos e parcerias com universidades.
*   **Rochas & Histórias (Para Público Geral):** Foco em sustentabilidade, meio ambiente, impacto social, curiosidades e relação com comunidades.

**Manchetes Coletadas (ignore qualquer uma que não seja sobre o setor mineral):**
---
{headlines_text}
---
"""
    print("Enviando requisição para a API da OpenAI...")
    headers = {
        "Authorization": f"Bearer {openai_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "gpt-4o",
        "messages": [
            {"role": "system", "content": "Você é um analista de mineração que cria resumos diários."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.3,
        "max_tokens": 3000,
    }
    
    try:
        response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload, timeout=180 )
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"].strip()
    except requests.RequestException as e:
        print(f"Erro Crítico: Falha ao comunicar com a API da OpenAI. Erro: {e}", file=sys.stderr)
        sys.exit(1)

def main():
    """Função principal que orquestra a execução do script."""
    openai_api_key = os.environ.get("OPENAI_API_KEY")
    if not openai_api_key:
        print("Erro Crítico: A variável de ambiente OPENAI_API_KEY não foi encontrada.", file=sys.stderr)
        sys.exit(1)

    yday_date = (datetime.now(TZ).date() - timedelta(days=1)).strftime("%d/%m/%Y")
    query = "mineração OR setor mineral"
    
    items = search_news_on_web(query)

    if not items:
        print("Nenhuma notícia de ontem foi encontrada. O script será encerrado sem gerar um novo resumo.")
        return

    lines = [f"• Título: {it['title']}\n  Fonte: {it['source']}\n  Link: {it['link']}" for it in items]
    headlines_text = "\n\n".join(lines)
    
    print(f"Gerando resumo para as notícias de {yday_date}...")
    summary = call_openai(headlines_text, yday_date, openai_api_key)
    
    try:
        with open(OUTPUT_FILENAME, "w", encoding="utf-8") as f:
            f.write(f"# Resumo de Notícias sobre Mineração - {yday_date}\n\n")
            f.write(summary)
        print(f"Sucesso! O resumo foi salvo no arquivo '{OUTPUT_FILENAME}'.")
    except IOError as e:
        print(f"Erro Crítico: Falha ao escrever no arquivo '{OUTPUT_FILENAME}'. Erro: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
