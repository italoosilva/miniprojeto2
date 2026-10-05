"""
Etapa 1 — coleta de dados de tabuademares.com/br/paraiba/joao-pessoa.

Objetivo: gravar em data/raw/ os CSVs que as Etapas 2 e 3 vão consumir.

    mares_<ano>.csv      tábua de marés do ano (4 marés por dia)
    mares_previsao.csv   marés do mês corrente, para cruzar com a previsão
    ondas.csv            altura de onda hora a hora (~7 dias à frente)
    vento.csv            velocidade do vento hora a hora (~7 dias à frente)

As funções abaixo estão vazias de propósito. Abra o site no navegador, use o
DevTools para descobrir onde cada dado vive no HTML e implemente o parse.
As colunas de cada CSV são sua decisão — só precisam sustentar as etapas
seguintes (ver README).

Rodar com: uv run python src/scrape.py
"""
import re
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup

# Os imports acima são o ponto de partida: você vai usar todos eles.
# Seu editor pode marcá-los como não usados até você preencher as funções.

URL_BASE = "https://tabuademares.com/br/paraiba/joao-pessoa"
URL_ONDAS = f"{URL_BASE}/previsao/ondas"
URL_VENTO = f"{URL_BASE}/previsao/vento"

# Servidores rejeitam clientes sem User-Agent. Identifique-se.
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

# Segundos de pausa entre requests. Não tire isso.
PAUSA = 1.5

DIR_RAW = Path(__file__).resolve().parent.parent / "data" / "raw"


def baixar_html(url: str, dados_post: dict | None = None) -> str:
    """Baixa uma página e devolve o HTML."""
    
    time.sleep(PAUSA)
    
    if dados_post:
        resp = requests.post(url, headers=HEADERS, data=dados_post, timeout=15)
    else:
        resp = requests.get(url, headers=HEADERS, timeout=15)

    resp.raise_for_status()
    return resp.text


def parsear_mares(html: str, ano: int, mes: int) -> list[dict]:
    """Extrai da tábua mensal uma linha por evento de maré."""
    soup = BeautifulSoup(html, "html.parser")
    eventos = []

    tabela = soup.find(id="tabla_mareas")
    if not tabela:
        return eventos

    linhas = tabela.find_all("tr")
    dia_atual = None

    for linha in linhas:
        for celula in linha.find_all(["td", "th"]):
            classes = celula.get("class", [])
            if any("dia" in c or "fecha" in c for c in classes):
                texto_dia = celula.get_text(strip=True)
                digitos = "".join(c for c in texto_dia if c.isdigit())
                if digitos:
                    dia_atual = int(digitos)

        coeficiente = None
        coef_tag = linha.find(
            lambda tag: tag.has_attr("class")
            and any("coeficiente" in c for c in tag["class"])
        )
        if coef_tag:
            texto_coef = coef_tag.get_text(strip=True)
            digitos_coef = "".join(c for c in texto_coef if c.isdigit())
            if digitos_coef:
                coeficiente = coef_tag.get_text(strip=True) if coef_tag else None
        
        horas = linha.find_all(
            lambda tag: tag.has_attr("class")
            and any("hora" in c for c in tag["class"])
        )
        alturas = linha.find_all(
            lambda tag: tag.has_attr("class")
            and any("altura" in c for c in tag["class"])
        )

        for h, a in zip(horas, alturas):
            hora_txt = h.get_text(strip=True)
            altura_txt = a.get_text(strip=True)

            if hora_txt and altura_txt and dia_atual is not None:
                data_hora = f"{ano}-{mes:02d}-{dia_atual:02d} {hora_txt}"

                eventos.append({
                    "data_hora": data_hora,
                    "altura_m": altura_txt,
                    "coeficiente": coeficiente,
                })

    return eventos


def parsear_previsao(html: str, ano: int) -> list[dict]:
    """Extrai leituras horárias das páginas de previsão de onda e de vento."""
    soup = BeautifulSoup(html, "html.parser")
    dados_previsao = []

    tipo = "ondas" if "ola" in html.lower() or "onda" in html.lower() else "vento"

    meses_map = {
        "jan": 1, "fev": 2, "mar": 3, "abr": 4, "mai": 5, "jun": 6,
        "jul": 7, "ago": 8, "set": 9, "out": 10, "nov": 11, "dez": 12
    }

    fichas = soup.find_all("div", class_="ficha")
    for ficha in fichas:
        elem_dia = ficha.find("span", class_="dia")
        elem_mes = ficha.find("span", class_="mes")

        if not elem_dia or not elem_mes:
            continue

        texto_dia = elem_dia.get_text(strip=True)
        digitos_dia = "".join(c for c in texto_dia if c.isdigit())
        if not digitos_dia:
            continue
        dia_num = int(digitos_dia)
        texto_mes = elem_mes.get_text(strip=True).lower()[:3]
        mes_num = meses_map.get(texto_mes, 1)

        horas_blocos = ficha.find_all("div", class_="f_temp_horas")
        for bloco in horas_blocos:
            textos_hora = bloco.find_all("div", class_="f_temp_hora")

            if textos_hora:
                hora = textos_hora[0].get_text(strip=True)
                direcao = textos_hora[1].get_text(strip=True) if len(textos_hora) > 1 else None

                barra_grafico = bloco.find("div", class_="grafico_temp_barra_relleno")
                valor_medido = barra_grafico.get_text(strip=True) if barra_grafico else None

                data_hora = f"{ano}-{mes_num:02d}-{dia_num:02d} {hora}"
                evento = {"data_hora": data_hora}

                if tipo == "ondas":
                    evento["direcao_onda"] = direcao
                    evento["altura_onda"]  = valor_medido

                elif tipo == "vento":
                    evento["direcao_vento"]    = direcao
                    evento["velocidade_vento"] = valor_medido

                dados_previsao.append(evento)
                
    return dados_previsao


def coletar_mares_do_ano(ano: int) -> pd.DataFrame:
    """Junta os 12 meses da tábua de marés de `ano` num DataFrame."""
    eventos_mares = []

    for mes in range(1, 13):
        print(f"Coletando marés do mês {mes:02d}/{ano}...")

        dados_form = {"fecha": f"{mes:02d}"}
        html = baixar_html(URL_BASE, dados_post=dados_form)

        eventos_mes = parsear_mares(html, ano, mes)
        eventos_mares.extend(eventos_mes)

    return pd.DataFrame(eventos_mares)


def main(ano: int = 2025) -> None:
    DIR_RAW.mkdir(parents=True, exist_ok=True)
    hoje = datetime.now()

    # 1. Tábua de marés do ano inteiro  -> mares_{ano}.csv
    df_mares_ano = coletar_mares_do_ano(ano)
    caminho_mares_ano = DIR_RAW / f"mares_{ano}.csv"
    df_mares_ano.to_csv(caminho_mares_ano, index=False, encoding="utf-8")
    print(f"-> {len(df_mares_ano)} linhas salvas em {caminho_mares_ano.name}")

    # 2. Marés do mês corrente  -> mares_previsao.csv
    print(f"Coletando marés do mês atual ({hoje.month:02d}/{hoje.year})...")
    html_mes_atual = baixar_html(URL_BASE, dados_post={"fecha": f"{hoje.month:02d}"})
    eventos_mes_atual = parsear_mares(html_mes_atual, hoje.year, hoje.month)
    df_mares_previsao = pd.DataFrame(eventos_mes_atual)
    caminho_mares_prev = DIR_RAW / "mares_previsao.csv"
    df_mares_previsao.to_csv(caminho_mares_prev, index=False, encoding="utf-8")
    print(f"-> {len(df_mares_previsao)} linhas salvas em {caminho_mares_prev.name}")

    # 3. Previsão de Ondas  -> ondas.csv
    print("Coletando previsão de ondas...")
    html_ondas = baixar_html(URL_ONDAS)
    dados_ondas = parsear_previsao(html_ondas, hoje.year)
    df_ondas = pd.DataFrame(dados_ondas)
    caminho_ondas = DIR_RAW / "ondas.csv"
    df_ondas.to_csv(caminho_ondas, index=False, encoding="utf-8")
    print(f"-> {len(df_ondas)} linhas salvas em {caminho_ondas.name}")

    # 4. Previsão de Vento  -> vento.csv
    print("Coletando previsão de vento...")
    html_vento = baixar_html(URL_VENTO)
    dados_vento = parsear_previsao(html_vento, hoje.year)
    df_vento = pd.DataFrame(dados_vento)
    caminho_vento = DIR_RAW / "vento.csv"
    df_vento.to_csv(caminho_vento, index=False, encoding="utf-8")
    print(f"-> {len(df_vento)} linhas salvas em {caminho_vento.name}")


if __name__ == "__main__":
    main()