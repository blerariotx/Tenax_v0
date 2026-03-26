"""
Issuer Analysis Dashboard — Tenax Capital
==========================================
Requirements:  pip install dash pandas openpyxl plotly
Usage:         python issuer_dashboard.py
Open:          http://127.0.0.1:8050
"""

import dash
from dash import dcc, html, dash_table, Input, Output
import pandas as pd
import numpy as np
import plotly.graph_objects as go

EXCEL_FILE = r"Planilha_Controle_FundosTenax.xlsm"
DADOS_FILE = r"dados.xlsm"   # Planilha separada com precos de ativos
CSV_CARTEIRA_TX = None
CSV_CARTEIRA_NEW_ATUAL = None
CSV_SUMMARY_TX = None

# TENAX BRAND COLORS
TENAX_DARK = "#023440"
TENAX_PRIMARY = "#005F69"
TENAX_ACCENT = "#1A8D8E"
TENAX_LIGHT = "#99BBB8"
TENAX_WHITE = "#FFFFFF"
TENAX_BG = "#F4F7F6"
TENAX_CARD_BORDER = "#E0ECEA"
FONT_LINK = "https://fonts.googleapis.com/css2?family=Montserrat:wght@400;500;600;700&display=swap"

def load_data():
    date_carteira = "N/A"
    if CSV_CARTEIRA_TX and CSV_CARTEIRA_NEW_ATUAL and CSV_SUMMARY_TX:
        carteira_tx = pd.read_csv(CSV_CARTEIRA_TX)
        carteira_new = pd.read_csv(CSV_CARTEIRA_NEW_ATUAL)
        summary_tx = pd.read_csv(CSV_SUMMARY_TX)
    else:
        print(f"Loading data from {EXCEL_FILE} ...")
        carteira_tx = pd.read_excel(EXCEL_FILE, sheet_name="CarteiraTX")
        carteira_new = pd.read_excel(EXCEL_FILE, sheet_name="CarteiraNew_Atual")
        summary_tx = pd.read_excel(EXCEL_FILE, sheet_name="Summary_TX", header=3)
        try:
            meta_tx = pd.read_excel(EXCEL_FILE, sheet_name="Summary_TX", header=None, nrows=10)
            date_carteira = meta_tx.iloc[4, 2]
        except Exception as e:
            print("Could not read date from C5", e)
        print("Data loaded successfully.")
    if hasattr(carteira_tx, "attrs"):
        carteira_tx.attrs["data_atualizacao"] = date_carteira
    return carteira_tx, carteira_new, summary_tx

def prepare_globals(carteira_tx, carteira_new, summary_tx):
    mask = (
        (carteira_tx["emissorRisco"] != "")
        & (carteira_tx["emissorRisco"].notna())
        & (carteira_tx["emissorRisco"] != "SECRETARIA DO TESOURO NACIONAL")
        & (carteira_tx["book"] != "MASTER")
        & (carteira_tx["emissorRisco"] != "PARAMIS - LEGATO LIQUIDEZ FIF")
    )
    issuers = sorted(carteira_tx.loc[mask, "emissorRisco"].unique().tolist())
    pl_total = summary_tx.loc[summary_tx["Feeder or Master"] == "Master", "AuM (R$ MM)"].sum() * 1_000_000
    ALLOWED_FUNDS = [
        "Tenax RFA Incentivado Master FIF",
        "Tenax RFA Prev Master FIFE",
    ]
    fund_mapping = []
    for _, row in summary_tx.iterrows():
        fund_name = row.get("Fund", "")
        feeder_or_master = row.get("Feeder or Master", "")
        if pd.isna(fund_name) or fund_name == "":
            continue
        if fund_name not in ALLOWED_FUNDS:
            continue
        fund_mapping.append({"fund_name": fund_name, "feeder_or_master": feeder_or_master})

    # Available funds for Lamina tab (exclude FIF CIC)
    EXCLUDE_FUNDS = ["Tenax RFA Incentivado FIF CIC"]
    lamina_funds = carteira_tx["TradingDesk"].dropna().unique().tolist()
    lamina_funds = sorted([f for f in lamina_funds if f and f != "" and f not in EXCLUDE_FUNDS])

    return issuers, pl_total, fund_mapping, lamina_funds

def analyze_issuer(issuer, carteira_tx, carteira_new, pl_total, fund_mapping):
    if not issuer:
        return [], {}
    products = carteira_tx.loc[carteira_tx["emissorRisco"] == issuer, "Product"].unique().tolist()
    if len(products) == 0:
        return [], {}
    rows = []
    totals = {"position_total": 0, "exposure_total": 0}
    fund_totals = {}
    for product in products:
        row = {"Issuer": issuer, "Ticker": product}
        match = carteira_new.loc[carteira_new["codAtivo"] == product]
        if len(match) > 0:
            row["Index"] = match.iloc[0].get("Index_", "")
            cdi_plus = match.iloc[0].get("Retorno em CDI+", None)
            row["Carrego (CDI+)"] = cdi_plus if pd.notna(cdi_plus) else None
            duration_raw = match.iloc[0].get("duration", None)
            row["Duration (anos)"] = duration_raw / 252 if pd.notna(duration_raw) else None
        else:
            row["Index"] = ""
            row["Carrego (CDI+)"] = None
            row["Duration (anos)"] = None
        position = carteira_tx.loc[carteira_tx["Product"] == product, "Position"].sum()
        row["Exposição Total (R$)"] = position
        row["Exposição Total (%)"] = position / pl_total if pl_total else 0
        totals["position_total"] += position
        totals["exposure_total"] += row["Exposição Total (%)"]
        for fm in fund_mapping:
            fund_name = fm["fund_name"]
            feeder_or_master = fm["feeder_or_master"]
            fund_position = carteira_tx.loc[
                (carteira_tx["Product"] == product) & (carteira_tx["TradingDesk"] == fund_name), "Position"
            ].sum()
            expo_col = "exposicaoMaster" if feeder_or_master == "Master" else "exposicaoFeeder"
            fund_expo = carteira_tx.loc[
                (carteira_tx["Product"] == product) & (carteira_tx["TradingDesk"] == fund_name), expo_col
            ].sum()
            row[f"{fund_name} (R$)"] = fund_position
            row[f"{fund_name} (%)"] = fund_expo
            fund_totals.setdefault(f"{fund_name} (R$)", 0)
            fund_totals.setdefault(f"{fund_name} (%)", 0)
            fund_totals[f"{fund_name} (R$)"] += fund_position
            fund_totals[f"{fund_name} (%)"] += fund_expo
        row["Exposição Total R$ (%)"] = f"{position:,.1f} ({row['Exposição Total (%)']:.2%})"
        for fm in fund_mapping:
            fn = fm["fund_name"]
            row[f"{fn} R$ (%)"] = f"{row[f'{fn} (R$)']:,.1f} ({row[f'{fn} (%)']:.2%})"
        rows.append(row)
    total_row = {"Issuer": "Total", "Ticker": "Total", "Index": ""}
    positions = [r["Exposição Total (R$)"] for r in rows]
    carregos = [r["Carrego (CDI+)"] or 0 for r in rows]
    durations = [r["Duration (anos)"] or 0 for r in rows]
    total_pos = sum(positions)
    if total_pos > 0:
        total_row["Carrego (CDI+)"] = sum(c * p for c, p in zip(carregos, positions)) / total_pos
        total_row["Duration (anos)"] = sum(d * p for d, p in zip(durations, positions)) / total_pos
    else:
        total_row["Carrego (CDI+)"] = 0
        total_row["Duration (anos)"] = 0
    total_row["Exposição Total (R$)"] = totals["position_total"]
    total_row["Exposição Total (%)"] = totals["exposure_total"]
    total_row["Exposição Total R$ (%)"] = f"{totals['position_total']:,.1f} ({totals['exposure_total']:.2%})"
    for fm in fund_mapping:
        fn = fm["fund_name"]
        total_row[f"{fn} (R$)"] = fund_totals.get(f"{fn} (R$)", 0)
        total_row[f"{fn} (%)"] = fund_totals.get(f"{fn} (%)", 0)
        total_row[f"{fn} R$ (%)"] = f"{total_row[f'{fn} (R$)']:,.1f} ({total_row[f'{fn} (%)']:.2%})"
    rows.append(total_row)
    return rows, {"issuer": issuer, "pl_total": pl_total}


def build_lamina(fund, ver_tickers, so_cp, carteira_tx, carteira_new):
    """Build the data for the Lâmina Fundo tab."""
    if not fund:
        return [], go.Figure()

    df = carteira_tx[carteira_tx["TradingDesk"] == fund].copy()

    # Filter CP only
    if so_cp == "Sim":
        df = df[df["flagNewAtivoCredito"] == 1]

    if len(df) == 0:
        return [], go.Figure()

    pl = df["PL"].iloc[0] if "PL" in df.columns else 1

    # Determine exposure column by checking which has non-zero values
    master_sum = df["exposicaoMaster"].abs().sum() if "exposicaoMaster" in df.columns else 0
    feeder_sum = df["exposicaoFeeder"].abs().sum() if "exposicaoFeeder" in df.columns else 0
    expo_col = "exposicaoMaster" if master_sum >= feeder_sum else "exposicaoFeeder"

    # Merge with carteira_new for ticker details (deduplicate first)
    cn = carteira_new[["codAtivo", "tipoAtivo", "duration", "Retorno em CDI+", "Index_"]].drop_duplicates("codAtivo")
    merged = df.merge(cn, left_on="Product", right_on="codAtivo", how="left")

    # Build rows grouped by emissor, then ticker inside
    rows = []
    emissores = merged.groupby("emissorRisco", sort=False).agg(
        pos_rs=("Position", "sum"),
        pos_pct=(expo_col, "sum"),
    ).reset_index().sort_values("pos_rs", ascending=False)

    for _, em_row in emissores.iterrows():
        emissor = em_row["emissorRisco"]
        em_pos_rs = em_row["pos_rs"]
        em_pos_pct = em_row["pos_pct"]

        # Emissor summary row
        rows.append({
            "Emissor": emissor,
            "Posição Emissor R$ (%)": f"{em_pos_rs:,.0f}  ({em_pos_pct:.2%})",
            "Ticker": "",
            "tipoAtivo": "",
            "Duration": "",
            "Carrego (CDI+)": "",
            "Posição Ticker R$ (%)": "",
            "_is_emissor": True,
            "_pos_pct": em_pos_pct,
        })

        if ver_tickers == "Sim":
            em_merged = merged[merged["emissorRisco"] == emissor]
            # Sum Position and expo_col per ticker (same ticker can appear in multiple rows)
            ticker_agg = em_merged.groupby("Product").agg(
                tk_pos=("Position", "sum"),
                tk_pct=(expo_col, "sum"),
            ).reset_index()
            # Get static attributes from first row per ticker
            ticker_attrs = em_merged.drop_duplicates("Product").set_index("Product")
            for _, tk_row in ticker_agg.iterrows():
                product = tk_row["Product"]
                tk_pos = tk_row["tk_pos"]
                tk_pct = tk_row["tk_pct"]
                attrs = ticker_attrs.loc[product] if product in ticker_attrs.index else {}
                dur = attrs.get("duration", None) if isinstance(attrs, pd.Series) else None
                dur_anos = f"{dur/252:.2f}" if dur is not None and pd.notna(dur) else ""
                cdi_plus = attrs.get("Retorno em CDI+", None) if isinstance(attrs, pd.Series) else None
                carrego = f"{cdi_plus:.2%}" if cdi_plus is not None and pd.notna(cdi_plus) else ""
                tipo = attrs.get("tipoAtivo", "") if isinstance(attrs, pd.Series) else ""
                tipo = tipo if pd.notna(tipo) else ""
                rows.append({
                    "Emissor": "",
                    "Posição Emissor R$ (%)": "",
                    "Ticker": product,
                    "tipoAtivo": tipo,
                    "Duration": dur_anos,
                    "Carrego (CDI+)": carrego,
                    "Posição Ticker R$ (%)": f"{tk_pos:,.0f}  ({tk_pct:.2%})",
                    "_is_emissor": False,
                    "_pos_pct": tk_pct,
                })

    # Build chart — all emissores sorted by exposure
    chart_df = emissores.sort_values("pos_pct", ascending=True)
    fig = go.Figure(go.Bar(
        x=chart_df["pos_pct"],
        y=chart_df["emissorRisco"],
        orientation="h",
        marker_color=TENAX_ACCENT,
        text=[f"{v:.2%}" for v in chart_df["pos_pct"]],
        textposition="outside",
        textfont=dict(size=10, color=TENAX_DARK),
    ))
    fig.update_layout(
        title=dict(text=f"Exposição por Emissor — {fund}", font=dict(size=13, color=TENAX_DARK), x=0),
        xaxis=dict(tickformat=".1%", showgrid=True, gridcolor=TENAX_CARD_BORDER, title=""),
        yaxis=dict(showgrid=False, title="", tickfont=dict(size=10)),
        plot_bgcolor=TENAX_WHITE,
        paper_bgcolor=TENAX_WHITE,
        margin=dict(l=20, r=60, t=50, b=20),
        height=max(300, len(chart_df) * 28 + 80),
        font=dict(family="Montserrat, sans-serif"),
    )

    return rows, fig



# ─────────────────────────────────────────────────────
# TAB 3 — PREÇOS DE ATIVOS (CDI Liquidez)
# ─────────────────────────────────────────────────────
import math as _math

_SIZE_SLOPE     = 0.9327
_SIZE_INTERCEPT = 8.0007
_SIZE_MIN       = 6.0

def _calc_size(vol_fin):
    if vol_fin and vol_fin > 0:
        return _SIZE_SLOPE * _math.log(vol_fin) + _SIZE_INTERCEPT
    return _SIZE_MIN

def _safe_float(val, default=None):
    try:
        v = float(val)
        return v if not _math.isnan(v) else default
    except (TypeError, ValueError):
        return default

def load_precos():
    import os
    if not os.path.exists(DADOS_FILE):
        print(f"[AVISO] Arquivo de precos nao encontrado: {DADOS_FILE}")
        return pd.DataFrame()
    print(f"Loading precos from {DADOS_FILE} ...")
    df_raw = pd.read_excel(DADOS_FILE, sheet_name="CockPit Secundário - Tabela", header=None)
    data_rows = df_raw.iloc[11:].reset_index(drop=True)
    records = []
    
    def safe_get_col(r, idx, raw=False):
        if len(r) <= idx: return None
        return r.iloc[idx] if raw else _safe_float(r.iloc[idx])

    for _, row in data_rows.iterrows():
        ticker    = safe_get_col(row, 1, raw=True)
        emissor   = safe_get_col(row, 2, raw=True)
        setor     = safe_get_col(row, 3, raw=True)
        incentivada = safe_get_col(row, 5, raw=True)  # Coluna F
        rating    = safe_get_col(row, 9, raw=True)  # Coluna J
        vol_raw   = safe_get_col(row, 8, raw=True)
        indexador = safe_get_col(row, 13, raw=True)  # Coluna N
        duration  = safe_get_col(row, 17, raw=True)  # Coluna R

        if not isinstance(ticker, str) or ticker.strip() == "":
            continue
        if not isinstance(indexador, str) or indexador not in ("CDI", "IPCA"):
            continue

        dur = _safe_float(duration)
        if dur is None:
            continue

        vol_fin = _safe_float(vol_raw, default=0.0) or 0.0
        rat = str(rating).strip() if isinstance(rating, str) else "sem rating"
        if rat in ("0", "nan", ""):
            rat = "sem rating"

        set_str = str(setor).strip() if isinstance(setor, str) else "Não Classificado"
        if set_str in ("nan", "None", ""):
            set_str = "Não Classificado"
            
        em_str = str(emissor).strip() if isinstance(emissor, str) else "Não Classificado"
        if em_str in ("nan", "None", ""):
            em_str = "Não Classificado"

        inc_str = "Sim" if str(incentivada).strip().lower() == "sim" else "Não"

        records.append({
            "Ticker":    ticker.strip(),
            "Emissor":   em_str,
            "Setor":     set_str,
            "Incentivada": inc_str,
            "Rating":    rat,
            "Indexador": indexador,
            "Duration":  round(dur, 4),
            "Vol_Fin":   vol_fin,
            "Size":      round(_calc_size(vol_fin), 4),
            "Yield_Absoluto_Bruto": safe_get_col(row, 18),
            "Spread_CDI_Bruto": safe_get_col(row, 19),
            "Spread_IPCA_Bruto": safe_get_col(row, 20),
            "Spread_PctCDI_Bruto": safe_get_col(row, 21),
            "Yield_Absoluto_GrossUp": safe_get_col(row, 22),
            "Spread_CDI_GrossUp": safe_get_col(row, 23),
            "Spread_IPCA_GrossUp": safe_get_col(row, 24),
            "Spread_PctCDI_GrossUp": safe_get_col(row, 25),
            "Yield_Absoluto_GrossDown": safe_get_col(row, 26),
            "Spread_CDI_GrossDown": safe_get_col(row, 27),
            "Spread_IPCA_GrossDown": safe_get_col(row, 28),
            "Spread_PctCDI_GrossDown": safe_get_col(row, 29),
        })
    print(f"Precos loaded: {len(records)} ativos.")
    df_out = pd.DataFrame(records)
    try:
        df_out.attrs["data_atualizacao"] = df_raw.iloc[2, 1]
    except Exception:
        df_out.attrs["data_atualizacao"] = "N/A"
    return df_out


def build_precos_fig(df_precos, view_col, gross_col, indexador_filter, rating_filter, setor_filter, emissor_filter, color_by="Setor"):
    if df_precos.empty:
        return go.Figure()

    df = df_precos.copy()
    
    # Filters
    if indexador_filter:
        df = df[df["Indexador"].isin(indexador_filter)]
    else:
        df = df.iloc[0:0]
    
    if rating_filter:
        df = df[df["Rating"].isin(rating_filter)]

    if setor_filter:
        df = df[df["Setor"].isin(setor_filter)]

    if emissor_filter:
        df = df[df["Emissor"].isin(emissor_filter)]

    if df.empty:
        return go.Figure()

    # Determine Y Column
    col_map = {
        ("Yields Absolutos", "Retorno Bruto"): "Yield_Absoluto_Bruto",
        ("Yields Absolutos", "Retorno com Gross-Up"): "Yield_Absoluto_GrossUp",
        ("Yields Absolutos", "Retorno com Gross-Down"): "Yield_Absoluto_GrossDown",
        ("Spread Equivalente CDI+", "Retorno Bruto"): "Spread_CDI_Bruto",
        ("Spread Equivalente CDI+", "Retorno com Gross-Up"): "Spread_CDI_GrossUp",
        ("Spread Equivalente CDI+", "Retorno com Gross-Down"): "Spread_CDI_GrossDown",
        ("Spread Equivalente IPCA+", "Retorno Bruto"): "Spread_IPCA_Bruto",
        ("Spread Equivalente IPCA+", "Retorno com Gross-Up"): "Spread_IPCA_GrossUp",
        ("Spread Equivalente IPCA+", "Retorno com Gross-Down"): "Spread_IPCA_GrossDown",
        ("Spread Equivalente %CDI", "Retorno Bruto"): "Spread_PctCDI_Bruto",
        ("Spread Equivalente %CDI", "Retorno com Gross-Up"): "Spread_PctCDI_GrossUp",
        ("Spread Equivalente %CDI", "Retorno com Gross-Down"): "Spread_PctCDI_GrossDown",
    }

    mapped_col = col_map.get((view_col, gross_col), "Yield_Absoluto_Bruto")

    if "Tenax_Expo_Pct" in df.columns:
        expo_str = df["Tenax_Expo_Pct"].apply(lambda x: f" ({x:.2%})" if x > 0 else "")
    else:
        expo_str = ""

    df["HoverText"] = (
        "<b>Ticker:</b> " + df["Ticker"] + expo_str + "<br>" +
        "<b>Emissor:</b> " + df["Emissor"] + "<br>" +
        "<b>Setor:</b> " + df["Setor"] + "<br>" +
        "<b>Incentivada:</b> " + df["Incentivada"] + "<br>" +
        "<b>Rating:</b> " + df["Rating"] + "<br>" +
        f"<b>{view_col} ({gross_col}):</b> " + df[mapped_col].apply(lambda x: f"{x:.2%}" if pd.notna(x) else "N/A") + "<br>" +
        "<b>Duration:</b> " + df["Duration"].round(2).astype(str) + " anos<br>" +
        "<b>Vol Fin:</b> R$ " + df["Vol_Fin"].apply(lambda x: f"{x:,.0f}")
    )

    if color_by == "Tenax x Mercado":
        def calc_plot_size(row):
            if row["Tenax x Mercado"] == "Mercado":
                return 7
            return min(100, max(7, 8 + row["Tenax_Expo_Pct"] * 1000))
        df["PlotSize"] = df.apply(calc_plot_size, axis=1)
    else:
        df["PlotSize"] = df["Size"]

    import plotly.colors
    color_map = {}
    colors_list = plotly.colors.qualitative.Plotly + plotly.colors.qualitative.Set3 + plotly.colors.qualitative.D3
    
    unique_vals = list(df[color_by].unique())
    if color_by == "Rating":
        r_order = {"AAA": 1, "AA+": 2, "AA": 3, "AA-": 4, "A+": 5, "A": 6, "A-": 7, "BBB+": 8, "BBB": 9, "BB+": 10, "sem rating": 11}
        unique_vals.sort(key=lambda x: r_order.get(x, 99))
    elif color_by == "Tenax x Mercado":
        unique_vals = sorted(unique_vals, key=lambda x: 0 if x == "Tenax" else 1)
    else:
        unique_vals.sort()

    for s in unique_vals:
        if s not in color_map:
            if color_by == "Tenax x Mercado":
                color_map[s] = TENAX_PRIMARY if s == "Tenax" else TENAX_LIGHT
            else:
                color_map[s] = colors_list[len(color_map) % len(colors_list)]

    fig = go.Figure()

    for s in unique_vals:
        df_sub = df[df[color_by] == s]
        fig.add_trace(go.Scatter(
            x=df_sub["Duration"],
            y=df_sub[mapped_col],
            mode='markers',
            marker=dict(size=df_sub["PlotSize"], color=color_map[s], opacity=0.8,
                        line=dict(width=1, color='white')),
            name=str(s),
            text=df_sub["HoverText"],
            hoverinfo="text",
            # textposition="top center", # Removed text labels on points for cleaner look
            # textfont=dict(size=10, color="#aaa"),
            showlegend=True
        ))

    x_label = "Duration (anos)"
    y_label = f"{view_col} ({gross_col})"

    fig.update_layout(
        title=dict(text="Preços de Ativos — Análise de Taxas", font=dict(size=14, color=TENAX_DARK), x=0),
        xaxis=dict(title=x_label, showgrid=True, gridcolor=TENAX_CARD_BORDER, zeroline=False),
        yaxis=dict(title=y_label, tickformat=".2%", showgrid=True, gridcolor=TENAX_CARD_BORDER, zeroline=False),
        plot_bgcolor=TENAX_WHITE,
        paper_bgcolor=TENAX_WHITE,
        margin=dict(l=60, r=160, t=60, b=60),
        height=650,
        font=dict(family="Montserrat, sans-serif", size=11),
        legend=dict(orientation="v", title=color_by, yanchor="top", y=1, xanchor="left", x=1.02),
        hovermode="closest",
    )
    return fig


def _precos_tab_layout(df_precos, date_precos=""):
    indexadores = ["CDI", "IPCA"]
    views = ["Yields Absolutos", "Spread Equivalente CDI+", "Spread Equivalente IPCA+", "Spread Equivalente %CDI"]
    gross = ["Retorno Bruto", "Retorno com Gross-Up", "Retorno com Gross-Down"]
    
    ideal_order = {"AAA": 1, "AA+": 2, "AA": 3, "AA-": 4, "A+": 5, "A": 6, "A-": 7, "BBB+": 8, "BBB": 9, "BB+": 10, "sem rating": 11}
    ratings_raw = df_precos["Rating"].dropna().unique().tolist() if not df_precos.empty else []
    ratings = sorted(ratings_raw, key=lambda x: ideal_order.get(x, 99))
    
    setores = sorted(df_precos["Setor"].dropna().unique().tolist()) if not df_precos.empty else []
    emissores = sorted(df_precos["Emissor"].dropna().unique().tolist()) if not df_precos.empty else []

    return html.Div([
        # Controls Row 1
        html.Div(style={"display": "flex", "gap": "20px", "alignItems": "flex-end",
                        "marginBottom": "16px", "flexWrap": "wrap"}, children=[
            html.Div(style={"minWidth": "200px", "flex": "1"}, children=[
                html.Label("INDEXADOR", style=_label_style()),
                dcc.Dropdown(id="precos-indexador",
                             options=[{"label": i, "value": i} for i in indexadores],
                             value=["CDI", "IPCA"], clearable=True, multi=True, placeholder="Todos",
                             style={"fontSize": "13px", "fontFamily": "'Montserrat', sans-serif"}),
            ]),
            html.Div(style={"minWidth": "200px", "flex": "1"}, children=[
                html.Label("MÉTRICA DE CARREGO", style=_label_style()),
                dcc.Dropdown(id="precos-view",
                             options=[{"label": v, "value": v} for v in views],
                             value="Yields Absolutos", clearable=False, multi=False,
                             style={"fontSize": "13px", "fontFamily": "'Montserrat', sans-serif"}),
            ]),
            html.Div(style={"minWidth": "200px", "flex": "1"}, children=[
                html.Label("MÉTRICA DE IMPOSTO", style=_label_style()),
                dcc.Dropdown(id="precos-gross",
                             options=[{"label": g, "value": g} for g in gross],
                             value="Retorno Bruto", clearable=False, multi=False,
                             style={"fontSize": "13px", "fontFamily": "'Montserrat', sans-serif"}),
            ]),
            html.Div(style={"minWidth": "200px", "flex": "1"}, children=[
                html.Label("COR DAS BOLHAS", style=_label_style()),
                dcc.Dropdown(id="precos-color-by",
                             options=[{"label": "Setor", "value": "Setor"},
                                      {"label": "Rating", "value": "Rating"},
                                      {"label": "Indexador", "value": "Indexador"},
                                      {"label": "Incentivada", "value": "Incentivada"},
                                      {"label": "Tenax x Mercado", "value": "Tenax x Mercado"}],
                             value="Setor", clearable=False, multi=False,
                             style={"fontSize": "13px", "fontFamily": "'Montserrat', sans-serif"}),
            ]),
        ]),
        # Controls Row 2
        html.Div(style={"display": "flex", "gap": "20px", "alignItems": "flex-end",
                        "marginBottom": "24px", "flexWrap": "wrap"}, children=[
            html.Div(style={"minWidth": "250px", "flex": "1"}, children=[
                html.Label("RATING", style=_label_style()),
                dcc.Dropdown(id="precos-rating",
                             options=[{"label": r, "value": r} for r in ratings],
                             value=[], clearable=True, multi=True, placeholder="Todos",
                             style={"fontSize": "13px", "fontFamily": "'Montserrat', sans-serif"}),
            ]),
            html.Div(style={"minWidth": "250px", "flex": "1"}, children=[
                html.Label("SETOR", style=_label_style()),
                dcc.Dropdown(id="precos-setor",
                             options=[{"label": s, "value": s} for s in setores],
                             value=[], clearable=True, multi=True, placeholder="Todos",
                             style={"fontSize": "13px", "fontFamily": "'Montserrat', sans-serif"}),
            ]),
            html.Div(style={"minWidth": "250px", "flex": "1"}, children=[
                html.Label("EMISSOR", style=_label_style()),
                dcc.Dropdown(id="precos-emissor",
                             options=[{"label": e, "value": e} for e in emissores],
                             value=[], clearable=True, multi=True, placeholder="Todos",
                             style={"fontSize": "13px", "fontFamily": "'Montserrat', sans-serif"}),
            ]),
            html.Div(style={"marginLeft": "auto", "display": "flex", "flexDirection": "column", "justifyContent": "flex-end", "textAlign": "right"}, children=[
                html.Div("ATUALIZAÇÃO DE MERCADO", style={"fontSize": "10px", "fontWeight": "600", "color": TENAX_LIGHT, "letterSpacing": "1.5px", "marginBottom": "2px"}),
                html.Div(str(date_precos), style={"fontWeight": "700", "color": TENAX_DARK, "fontSize": "13px"}),
            ]),
        ]),
        # Bubble chart
        html.Div(style=_table_wrapper_style(), children=[
            dcc.Graph(id="precos-chart", config={"displayModeBar": True, "scrollZoom": True}),
        ]),
    ])

def create_app(carteira_tx, carteira_new, summary_tx, issuers, pl_total, fund_mapping, lamina_funds, df_precos):
    
    # Computar Tenax x Mercado no df_precos com base na exp total
    pos_por_ticker = carteira_tx.groupby("Product")["Position"].sum()
    def get_tenax_expo(ticker):
        if ticker in pos_por_ticker:
            pos = pos_por_ticker[ticker]
            if pos > 0:
                return pos / pl_total if pl_total else 0
        return 0
    df_precos["Tenax_Expo_Pct"] = df_precos["Ticker"].apply(get_tenax_expo)
    df_precos["Tenax x Mercado"] = df_precos["Tenax_Expo_Pct"].apply(lambda x: "Tenax" if x > 0 else "Mercado")

    app = dash.Dash(__name__, title="Tenax - Credit Dashboard", suppress_callback_exceptions=True)
    
    date_carteira = getattr(carteira_tx, "attrs", {}).get("data_atualizacao", "N/A")
    date_precos = getattr(df_precos, "attrs", {}).get("data_atualizacao", "N/A")
    
    if pd.notna(date_carteira) and hasattr(date_carteira, "strftime"):
        date_carteira = date_carteira.strftime("%d/%m/%Y")
    elif pd.notna(date_carteira):
        date_carteira = str(date_carteira).split()[0][:10]
        
    if pd.notna(date_precos) and hasattr(date_precos, "strftime"):
        date_precos = date_precos.strftime("%d/%m/%Y")
    elif pd.notna(date_precos):
        date_precos = str(date_precos).split()[0][:10]

    # --- Tab 1 columns ---
    base_columns = [
        {"name": "Issuer", "id": "Issuer"},
        {"name": "Ticker", "id": "Ticker"},
        {"name": "Index", "id": "Index"},
        {"name": "Carrego (CDI+)", "id": "Carrego (CDI+)", "type": "numeric",
         "format": dash_table.FormatTemplate.percentage(2)},
        {"name": "Duration (anos)", "id": "Duration (anos)", "type": "numeric",
         "format": dash_table.Format.Format(precision=2, scheme=dash_table.Format.Scheme.fixed)},
        {"name": "Exposição Total R$ (%)", "id": "Exposição Total R$ (%)"},
    ]
    fund_columns = []
    for fm in fund_mapping:
        fn = fm["fund_name"]
        short = fn.replace("Tenax ", "").replace(" FIF", "").replace(" FIFE", "")
        fund_columns.append({"name": f"{short} R$ (%)", "id": f"{fn} R$ (%)"})
    all_columns = base_columns + fund_columns

    # --- Tab 2 columns ---
    lamina_columns = [
        {"name": "Emissor", "id": "Emissor"},
        {"name": "Posição Emissor R$ (%)", "id": "Posição Emissor R$ (%)"},
        {"name": "Ticker", "id": "Ticker"},
        {"name": "Tipo Ativo", "id": "tipoAtivo"},
        {"name": "Duration (anos)", "id": "Duration"},
        {"name": "Carrego (CDI+)", "id": "Carrego (CDI+)"},
        {"name": "Posição Ticker R$ (%)", "id": "Posição Ticker R$ (%)"},
    ]

    # --- Shared navbar ---
    navbar = html.Div(
        style={"backgroundColor": TENAX_DARK, "padding": "16px 32px", "display": "flex",
               "alignItems": "center", "justifyContent": "space-between",
               "boxShadow": "0 2px 8px rgba(0,0,0,0.2)"},
        children=[
            html.Div(style={"display": "flex", "alignItems": "center", "gap": "14px"}, children=[
                html.Div("T", style={"width": "40px", "height": "40px", "borderRadius": "8px",
                                     "backgroundColor": TENAX_ACCENT, "color": "white",
                                     "display": "flex", "alignItems": "center", "justifyContent": "center",
                                     "fontSize": "22px", "fontWeight": "700"}),
                html.Div(children=[
                    html.Span("TENAX", style={"color": TENAX_WHITE, "fontSize": "20px",
                                              "fontWeight": "700", "letterSpacing": "3px"}),
                    html.Span("  CAPITAL", style={"color": TENAX_LIGHT, "fontSize": "20px",
                                                  "fontWeight": "400", "letterSpacing": "3px"}),
                ]),
            ]),
            html.Div("Gerando Alpha com Tenacidade", style={"color": TENAX_LIGHT, "fontSize": "14px",
                                               "fontWeight": "500", "letterSpacing": "1px"}),
        ],
    )

    app.layout = html.Div(
        style={"fontFamily": "'Montserrat', 'Segoe UI', Arial, sans-serif", "padding": "0",
               "backgroundColor": TENAX_BG, "minHeight": "100vh"},
        children=[
            html.Link(rel="stylesheet", href=FONT_LINK),
            navbar,
            html.Div(style={"padding": "24px 32px", "maxWidth": "1600px", "margin": "0 auto"}, children=[
                dcc.Tabs(
                    id="main-tabs",
                    value="tab-issuer",
                    children=[
                        dcc.Tab(label="ANÁLISE POR EMISSOR", value="tab-issuer",
                                style=_tab_style(), selected_style=_tab_selected_style()),
                        dcc.Tab(label="Lâmina Fundo", value="tab-lamina",
                                style=_tab_style(), selected_style=_tab_selected_style()),
                        dcc.Tab(label="Preços de Ativos", value="tab-precos",
                                style=_tab_style(), selected_style=_tab_selected_style()),
                    ],
                    style={"marginBottom": "24px", "borderBottom": f"2px solid {TENAX_CARD_BORDER}"},
                    colors={"border": TENAX_CARD_BORDER, "primary": TENAX_PRIMARY, "background": TENAX_BG},
                ),
                # Both tabs always in DOM — visibility toggled via callback
                html.Div(id="tab-issuer-content", children=_issuer_tab_layout(issuers, pl_total, all_columns, date_carteira)),
                html.Div(id="tab-lamina-content", children=_lamina_tab_layout(lamina_funds, lamina_columns, date_carteira), style={"display": "none"}),
                html.Div(id="tab-precos-content", children=_precos_tab_layout(df_precos, date_precos), style={"display": "none"}),
            ]),
            html.Div(style={"textAlign": "center", "marginTop": "16px", "paddingBottom": "24px",
                            "color": TENAX_LIGHT, "fontSize": "11px", "letterSpacing": "1px"},
                     children=[html.P("TENAX CAPITAL")]),
        ],
    )

    # --- Toggle tab visibility ---
    @app.callback(
        [Output("tab-issuer-content", "style"), Output("tab-lamina-content", "style"), Output("tab-precos-content", "style")],
        Input("main-tabs", "value"),
    )
    def toggle_tabs(tab):
        if tab == "tab-issuer":
            return {"display": "block"}, {"display": "none"}, {"display": "none"}
        elif tab == "tab-lamina":
            return {"display": "none"}, {"display": "block"}, {"display": "none"}
        else:
            return {"display": "none"}, {"display": "none"}, {"display": "block"}

    # --- Tab 1 callback ---
    @app.callback(
        [Output("issuer-table", "data"), Output("summary-cards", "children")],
        Input("issuer-dropdown", "value"),
    )
    def update_dashboard(selected_issuer):
        rows, summary = analyze_issuer(selected_issuer, carteira_tx, carteira_new, pl_total, fund_mapping)
        if not rows:
            return [], []
        total_row = rows[-1] if rows else {}
        total_exposure_pct = total_row.get("Exposição Total (%)", 0)
        total_exposure_rs = total_row.get("Exposição Total (R$)", 0)
        n_products = len(rows) - 1
        cards = [
            _make_card("Emissor", selected_issuer, TENAX_ACCENT),
            _make_card("Nº de Títulos", str(n_products), TENAX_PRIMARY),
            _make_card("Exposição Total", f"R$ {total_exposure_rs:,.0f}", TENAX_DARK),
            _make_card("% do PL", f"{total_exposure_pct:.2%}", TENAX_ACCENT),
        ]
        return rows, cards

    # --- Tab 2 callback ---
    @app.callback(
        [Output("lamina-table", "data"), Output("lamina-chart", "figure")],
        [Input("lamina-fund-dropdown", "value"),
         Input("lamina-ver-tickers", "value"),
         Input("lamina-so-cp", "value")],
    )
    def update_lamina(fund, ver_tickers, so_cp):
        rows, fig = build_lamina(fund, ver_tickers, so_cp, carteira_tx, carteira_new)
        # Remove internal keys before passing to table
        clean_rows = [{k: v for k, v in r.items() if not k.startswith("_")} for r in rows]
        # Row styling: emissor rows bold
        return clean_rows, fig

    # --- Tab 3 callback ---
    @app.callback(
        Output("precos-chart", "figure"),
        [Input("precos-view", "value"),
         Input("precos-gross", "value"),
         Input("precos-indexador", "value"),
         Input("precos-rating", "value"),
         Input("precos-setor", "value"),
         Input("precos-emissor", "value"),
         Input("precos-color-by", "value")]
    )
    def update_precos_chart(view_col, gross_col, indexador_filter, rating_filter, setor_filter, emissor_filter, color_by):
        return build_precos_fig(df_precos, view_col, gross_col, indexador_filter, rating_filter, setor_filter, emissor_filter, color_by)

    return app


def _tab_style():
    return {
        "fontFamily": "'Montserrat', sans-serif", "fontSize": "12px", "fontWeight": "600",
        "color": TENAX_LIGHT, "backgroundColor": TENAX_BG, "border": "none",
        "padding": "10px 20px", "letterSpacing": "0.5px", "textTransform": "uppercase",
    }

def _tab_selected_style():
    return {
        "fontFamily": "'Montserrat', sans-serif", "fontSize": "12px", "fontWeight": "700",
        "color": TENAX_PRIMARY, "backgroundColor": TENAX_WHITE,
        "borderTop": f"3px solid {TENAX_PRIMARY}", "borderLeft": f"1px solid {TENAX_CARD_BORDER}",
        "borderRight": f"1px solid {TENAX_CARD_BORDER}", "borderBottom": "none",
        "padding": "10px 20px", "letterSpacing": "0.5px", "textTransform": "uppercase",
    }

def _issuer_tab_layout(issuers, pl_total, all_columns, date_carteira=""):
    return html.Div([
        # Controls row
        html.Div(style={"display": "flex", "gap": "20px", "alignItems": "flex-end",
                        "marginBottom": "24px", "flexWrap": "wrap"}, children=[
            html.Div(style={"flex": "1", "minWidth": "380px"}, children=[
                html.Label("EMISSOR", style=_label_style()),
                dcc.Dropdown(id="issuer-dropdown",
                             options=[{"label": i, "value": i} for i in issuers],
                             value=None, clearable=False, searchable=True,
                             placeholder="Buscar emissor...",
                             style={"fontSize": "14px", "fontFamily": "'Montserrat', sans-serif"}),
            ]),
            html.Div(style=_pl_card_style(), children=[
                html.Div("PL TOTAL", style={"fontSize": "10px", "fontWeight": "600",
                                            "color": TENAX_LIGHT, "letterSpacing": "1.5px", "marginBottom": "2px"}),
                html.Div(f"R$ {pl_total:,.2f}", style={"fontWeight": "700", "color": TENAX_PRIMARY, "fontSize": "18px"}),
            ]),
            html.Div(style={"marginLeft": "auto", "display": "flex", "flexDirection": "column", "justifyContent": "flex-end", "textAlign": "right"}, children=[
                html.Div("ATUALIZAÇÃO DA CARTEIRA", style={"fontSize": "10px", "fontWeight": "600", "color": TENAX_LIGHT, "letterSpacing": "1.5px", "marginBottom": "2px"}),
                html.Div(str(date_carteira), style={"fontWeight": "700", "color": TENAX_DARK, "fontSize": "13px"}),
            ]),
        ]),
        html.Div(id="summary-cards", style={"display": "flex", "gap": "16px", "marginBottom": "24px", "flexWrap": "wrap"}),
        html.Div(style=_table_wrapper_style(), children=[
            dash_table.DataTable(
                id="issuer-table", columns=all_columns, data=[],
                style_table={"overflowX": "auto", "borderRadius": "10px"},
                style_header=_table_header_style(),
                style_cell=_table_cell_style(),
                style_data=_table_data_style(),
                style_data_conditional=[
                    {"if": {"filter_query": '{Ticker} = "Total"'},
                     "fontWeight": "700", "borderTop": f"2px solid {TENAX_PRIMARY}",
                     "backgroundColor": "#EDF5F4", "color": TENAX_DARK},
                    {"if": {"row_index": "odd"}, "backgroundColor": "#F8FBFA"},
                    {"if": {"column_id": "Issuer"}, "fontWeight": "600", "color": TENAX_PRIMARY},
                ],
                style_as_list_view=False, page_action="none", sort_action="native",
                fixed_rows={"headers": True},
            ),
        ]),
    ])


def _lamina_tab_layout(lamina_funds, lamina_columns, date_carteira=""):
    return html.Div([
        # Controls row
        html.Div(style={"display": "flex", "gap": "20px", "alignItems": "flex-end",
                        "marginBottom": "24px", "flexWrap": "wrap"}, children=[
            html.Div(style={"flex": "2", "minWidth": "320px"}, children=[
                html.Label("FUNDO", style=_label_style()),
                dcc.Dropdown(id="lamina-fund-dropdown",
                             options=[{"label": f, "value": f} for f in lamina_funds],
                             value=None, clearable=False, searchable=True,
                             placeholder="Selecionar fundo...",
                             style={"fontSize": "14px", "fontFamily": "'Montserrat', sans-serif"}),
            ]),
            html.Div(style={"minWidth": "160px"}, children=[
                html.Label("VER TICKERS?", style=_label_style()),
                dcc.RadioItems(id="lamina-ver-tickers",
                               options=[{"label": " Sim", "value": "Sim"}, {"label": " Não", "value": "Não"}],
                               value="Sim",
                               labelStyle={"display": "inline-block", "marginRight": "14px",
                                           "fontSize": "13px", "cursor": "pointer"},
                               inputStyle={"marginRight": "4px", "accentColor": TENAX_PRIMARY}),
            ]),
            html.Div(style={"minWidth": "160px"}, children=[
                html.Label("SÓ CP?", style=_label_style()),
                dcc.RadioItems(id="lamina-so-cp",
                               options=[{"label": " Sim", "value": "Sim"}, {"label": " Não", "value": "Não"}],
                               value="Sim",
                               labelStyle={"display": "inline-block", "marginRight": "14px",
                                           "fontSize": "13px", "cursor": "pointer"},
                               inputStyle={"marginRight": "4px", "accentColor": TENAX_PRIMARY}),
            ]),
            html.Div(style={"marginLeft": "auto", "display": "flex", "flexDirection": "column", "justifyContent": "flex-end", "textAlign": "right"}, children=[
                html.Div("ATUALIZAÇÃO DA CARTEIRA", style={"fontSize": "10px", "fontWeight": "600", "color": TENAX_LIGHT, "letterSpacing": "1.5px", "marginBottom": "2px"}),
                html.Div(str(date_carteira), style={"fontWeight": "700", "color": TENAX_DARK, "fontSize": "13px"}),
            ]),
        ]),
        # Table
        html.Div(style={**_table_wrapper_style(), "marginBottom": "28px"}, children=[
            dash_table.DataTable(
                id="lamina-table", columns=lamina_columns, data=[],
                style_table={"overflowX": "auto", "borderRadius": "10px"},
                style_header=_table_header_style(),
                style_cell=_table_cell_style(),
                style_data=_table_data_style(),
                style_data_conditional=[
                    # Emissor rows (non-empty Emissor column) get bold + teal tint
                    {"if": {"filter_query": '{Emissor} != ""'},
                     "fontWeight": "700", "backgroundColor": "#EDF5F4",
                     "color": TENAX_PRIMARY, "borderTop": f"1px solid {TENAX_LIGHT}"},
                    # Ticker rows get a slight indent feel
                    {"if": {"filter_query": '{Emissor} = ""'},
                     "color": TENAX_DARK, "backgroundColor": TENAX_WHITE},
                    {"if": {"row_index": "odd", "filter_query": '{Emissor} = ""'},
                     "backgroundColor": "#F8FBFA"},
                ],
                style_as_list_view=False, page_action="none", sort_action="none",
                fixed_rows={"headers": True},
            ),
        ]),
        # Chart
        html.Div(style=_table_wrapper_style(), children=[
            dcc.Graph(id="lamina-chart", config={"displayModeBar": False}),
        ]),
    ])


# --- Shared style helpers ---
def _label_style():
    return {"fontWeight": "600", "fontSize": "11px", "color": TENAX_PRIMARY,
            "marginBottom": "6px", "display": "block", "letterSpacing": "1.5px",
            "textTransform": "uppercase"}

def _pl_card_style():
    return {"backgroundColor": TENAX_WHITE, "borderRadius": "8px", "padding": "14px 24px",
            "boxShadow": "0 1px 4px rgba(0,0,0,0.06)", "border": f"1px solid {TENAX_CARD_BORDER}",
            "minWidth": "220px"}

def _table_wrapper_style():
    return {"backgroundColor": TENAX_WHITE, "borderRadius": "10px", "padding": "0",
            "boxShadow": "0 1px 6px rgba(0,0,0,0.06)", "border": f"1px solid {TENAX_CARD_BORDER}",
            "overflowX": "auto"}

def _table_header_style():
    return {"backgroundColor": TENAX_PRIMARY, "color": TENAX_WHITE, "fontWeight": "600",
            "fontSize": "11px", "textAlign": "center", "padding": "12px 10px",
            "whiteSpace": "normal", "height": "auto",
            "fontFamily": "'Montserrat', sans-serif", "letterSpacing": "0.5px",
            "borderBottom": f"2px solid {TENAX_DARK}"}

def _table_cell_style():
    return {"fontSize": "12px", "padding": "10px 12px", "textAlign": "center",
            "minWidth": "110px", "maxWidth": "280px", "whiteSpace": "nowrap",
            "overflow": "hidden", "textOverflow": "ellipsis",
            "fontFamily": "'Montserrat', sans-serif",
            "borderRight": f"1px solid {TENAX_CARD_BORDER}"}

def _table_data_style():
    return {"color": TENAX_DARK, "backgroundColor": TENAX_WHITE,
            "borderBottom": f"1px solid {TENAX_CARD_BORDER}"}


def _make_card(title, value, color):
    return html.Div(
        style={"backgroundColor": TENAX_WHITE, "borderRadius": "8px", "padding": "16px 22px",
               "boxShadow": "0 1px 4px rgba(0,0,0,0.06)", "border": f"1px solid {TENAX_CARD_BORDER}",
               "borderLeftColor": color, "borderLeftWidth": "4px", "borderLeftStyle": "solid",
               "minWidth": "170px", "flex": "1"},
        children=[
            html.Div(title, style={"fontSize": "10px", "fontWeight": "600", "color": TENAX_LIGHT,
                                   "textTransform": "uppercase", "letterSpacing": "1.5px", "marginBottom": "4px"}),
            html.Div(value, style={"fontSize": "17px", "fontWeight": "700", "color": color}),
        ],
    )


# Initialize data and app for the WSGI server
carteira_tx, carteira_new, summary_tx = load_data()
issuers, pl_total, fund_mapping, lamina_funds = prepare_globals(carteira_tx, carteira_new, summary_tx)
df_precos = load_precos()
app = create_app(carteira_tx, carteira_new, summary_tx, issuers, pl_total, fund_mapping, lamina_funds, df_precos)
server = app.server  # Expose WSGI server for Gunicorn

if __name__ == "__main__":
    print("\n✅ Tenax — Issuer Analysis Dashboard running at http://127.0.0.1:8050\n")
    app.run(debug=True, host="0.0.0.0", port=8050)
