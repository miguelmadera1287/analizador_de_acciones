# app_mejorado.py

import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
from datetime import datetime, timedelta
import io
from tenacity import retry, stop_after_attempt, wait_exponential

# --- Configuración de página ---
st.set_page_config(
    page_title="Analizador de Acciones Pro",
    layout="wide",
    page_icon="💹"
)

# --- CSS personalizado ---
st.markdown("""
<style>
    .recommendation {
        padding: 20px;
        border-radius: 8px;
        margin-bottom: 20px;
        font-weight: bold;
        font-size: 18px;
    }
    .buy { background-color: #e6f7ee; border-left: 6px solid #28a745; }
    .sell { background-color: #fde8e8; border-left: 6px solid #dc3545; }
    .hold { background-color: #fff8e6; border-left: 6px solid #ffc107; }
</style>
""", unsafe_allow_html=True)

# --- Funciones auxiliares ---
@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=8))
def safe_download(ticker, start_date, end_date):
    data = yf.download(ticker, start=start_date, end=end_date, progress=False)
    if data.empty:
        raise ValueError("No se encontraron datos.")
    return data

def calcular_indicadores(data, indicadores):
    if indicadores.get("sma"):
        data["SMA50"] = data["Precio"].rolling(50).mean()
        data["SMA200"] = data["Precio"].rolling(200).mean()
    if indicadores.get("rsi"):
        delta = data["Precio"].diff()
        gain = delta.where(delta > 0, 0.0)
        loss = -delta.where(delta < 0, 0.0)
        avg_gain = gain.rolling(14).mean()
        avg_loss = loss.rolling(14).mean()
        rs = avg_gain / avg_loss
        data["RSI"] = 100 - (100 / (1 + rs))
    if indicadores.get("macd"):
        ema12 = data["Precio"].ewm(span=12, adjust=False).mean()
        ema26 = data["Precio"].ewm(span=26, adjust=False).mean()
        data["MACD"] = ema12 - ema26
        data["Signal"] = data["MACD"].ewm(span=9, adjust=False).mean()
    return data

def generar_recomendacion(data):
    try:
        p = data["Precio"].iloc[-1]
        sma50 = data["SMA50"].iloc[-1]
        sma200 = data["SMA200"].iloc[-1]
        rsi = data["RSI"].iloc[-1]
    except:
        return "MANTENER", "hold", ["Faltan indicadores para generar una recomendación."]

    condiciones = []
    score = 0

    if p > sma200 and sma50 > sma200:
        condiciones.append("Tendencia alcista (Precio > SMA200 > SMA50)")
        score += 1
    elif p < sma200 and sma50 < sma200:
        condiciones.append("Tendencia bajista (Precio < SMA200 < SMA50)")
        score -= 1

    if sma50 > sma200:
        condiciones.append("Golden Cross (SMA50 > SMA200)")
        score += 1
    elif sma50 < sma200:
        condiciones.append("Death Cross (SMA50 < SMA200)")
        score -= 1

    if rsi > 70:
        condiciones.append("RSI alto (>70) - posible sobrecompra")
        score -= 1
    elif rsi < 30:
        condiciones.append("RSI bajo (<30) - posible sobreventa")
        score += 1

    if score >= 2:
        return "COMPRA", "buy", condiciones
    elif score <= -2:
        return "VENTA", "sell", condiciones
    else:
        return "MANTENER", "hold", condiciones

# --- Sidebar ---
st.sidebar.header("🔧 Configuración")

ticker = st.sidebar.selectbox("Selecciona un activo:", [
    "AAPL", "MSFT", "GOOGL", "TSLA", "AMZN", "META", "NVDA", "BTC-USD", "ETH-USD"
], index=0)

end_date = datetime.today()
start_date = st.sidebar.date_input("Desde:", end_date - timedelta(days=365))
indicadores = {
    "sma": st.sidebar.checkbox("SMA 50/200", True),
    "rsi": st.sidebar.checkbox("RSI (14)", True),
    "macd": st.sidebar.checkbox("MACD", True),
}

# --- Carga de datos ---
st.title(f"📊 Análisis técnico: {ticker}")

with st.spinner("Cargando datos..."):
    df = safe_download(ticker, start_date, end_date)

# --- Preparar datos ---
price_col = next((c for c in ['Adj Close', 'Close'] if c in df.columns), None)
if not price_col:
    st.error("No se encontró columna de precios válida.")
    st.stop()

data = df[[price_col]].copy()
data.columns = ["Precio"]

if "Volume" in df.columns:
    data["Volumen"] = df["Volume"]

data = calcular_indicadores(data, indicadores)

# --- Gráfico de precios + SMA ---
st.subheader("📈 Evolución de precios")

fig = go.Figure()
fig.add_trace(go.Scatter(x=data.index, y=data["Precio"], name="Precio", line=dict(color="blue")))
if indicadores["sma"]:
    fig.add_trace(go.Scatter(x=data.index, y=data["SMA50"], name="SMA 50", line=dict(color="orange")))
    fig.add_trace(go.Scatter(x=data.index, y=data["SMA200"], name="SMA 200", line=dict(color="green")))

fig.update_layout(height=500, margin=dict(l=10, r=10, t=40, b=20), legend=dict(orientation="h"))
st.plotly_chart(fig, use_container_width=True)

# --- Métricas clave ---
st.subheader("📌 Métricas")

precio_actual = data["Precio"].iloc[-1]
variacion = ((precio_actual - data["Precio"].iloc[0]) / data["Precio"].iloc[0]) * 100

col1, col2, col3 = st.columns(3)
col1.metric("Precio actual", f"${precio_actual:.2f}", f"{variacion:.2f}%")
if indicadores["sma"]:
    col2.metric("SMA 50", f"${data['SMA50'].iloc[-1]:.2f}")
    col3.metric("SMA 200", f"${data['SMA200'].iloc[-1]:.2f}")
else:
    col2.metric("SMA 50", "—")
    col3.metric("SMA 200", "—")

# --- Pestañas de indicadores ---
st.subheader("📊 Indicadores técnicos")

tabs = st.tabs(["RSI", "MACD", "Volumen"])

if indicadores["rsi"]:
    with tabs[0]:
        st.caption("RSI mide la fuerza relativa de las últimas subidas y bajadas de precio.")
        fig_rsi = go.Figure()
        fig_rsi.add_trace(go.Scatter(x=data.index, y=data["RSI"], name="RSI", line=dict(color="purple")))
        fig_rsi.add_hline(y=70, line_dash="dash", line_color="red")
        fig_rsi.add_hline(y=30, line_dash="dash", line_color="green")
        fig_rsi.update_layout(height=300, margin=dict(t=30))
        st.plotly_chart(fig_rsi, use_container_width=True)

if indicadores["macd"]:
    with tabs[1]:
        st.caption("MACD indica cambios en la fuerza, dirección y duración de la tendencia.")
        fig_macd = go.Figure()
        fig_macd.add_trace(go.Scatter(x=data.index, y=data["MACD"], name="MACD", line=dict(color="blue")))
        fig_macd.add_trace(go.Scatter(x=data.index, y=data["Signal"], name="Signal", line=dict(color="orange")))
        fig_macd.add_bar(x=data.index, y=data["MACD"] - data["Signal"],
                         marker_color=["green" if v > 0 else "red" for v in data["MACD"] - data["Signal"]])
        fig_macd.update_layout(height=300, margin=dict(t=30))
        st.plotly_chart(fig_macd, use_container_width=True)

if "Volumen" in data.columns:
    with tabs[2]:
        st.caption("El volumen puede confirmar la dirección de la tendencia.")
        fig_vol = go.Figure()
        fig_vol.add_trace(go.Bar(x=data.index, y=data["Volumen"], name="Volumen", marker_color="gray"))
        fig_vol.update_layout(height=300, margin=dict(t=30))
        st.plotly_chart(fig_vol, use_container_width=True)

# --- Recomendación automática ---
st.subheader("🧠 Recomendación técnica")

reco_texto, reco_tipo, condiciones = generar_recomendacion(data)
reco_clase = {"buy": "buy", "sell": "sell", "hold": "hold"}[reco_tipo]

st.markdown(f"""
<div class="recommendation {reco_clase}">
📌 <strong>{reco_texto}</strong>
<ul>
{''.join(f"<li>{c}</li>" for c in condiciones)}
</ul>
</div>
""", unsafe_allow_html=True)

# --- Exportación de datos ---
st.subheader("📤 Exportar análisis")

csv = data.to_csv().encode("utf-8")
st.download_button("⬇️ Descargar CSV", data=csv, file_name=f"{ticker}_analisis.csv", mime="text/csv")

excel_buffer = io.BytesIO()
with pd.ExcelWriter(excel_buffer, engine="xlsxwriter") as writer:
    data.to_excel(writer, sheet_name="Datos")
    writer.close()
st.download_button(
    "⬇️ Descargar Excel",
    data=excel_buffer.getvalue(),
    file_name=f"{ticker}_analisis.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)

# --- Nota legal ---
st.markdown("---")
st.caption("⚠️ Este análisis es con fines educativos. No constituye asesoría financiera.")

