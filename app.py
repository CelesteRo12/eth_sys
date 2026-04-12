import streamlit as st
import biosteam as bst
import thermosteam as tmo
import pandas as pd
import google.generativeai as genai

# =================================================================
# 1. CONFIGURACIÓN VISUAL
# =================================================================
st.set_page_config(page_title="Simulador Etanol ISO-Pro", layout="wide")

st.markdown("""
    <style>
    .metric-card {
        background-color: #f9f9f9;
        padding: 15px;
        border-radius: 10px;
        border-top: 4px solid #1f77b4;
        text-align: center;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
        margin-bottom: 15px;
    }
    .metric-label { font-size: 0.85rem; color: #666; font-weight: bold; }
    .metric-value { font-size: 1.2rem; color: #222; font-weight: bold; }
    </style>
""", unsafe_allow_html=True)

# =================================================================
# 2. LÓGICA DE INGENIERÍA (Corrección de AttributeError)
# =================================================================
def simular_sistema_seguro(t_f, t_w, p_v, p_l, p_vap, p_h, p_m, p_e):
    # Reset del flowsheet
    bst.main_flowsheet.clear()
    chemicals = tmo.Chemicals(["Water", "Ethanol"])
    bst.settings.set_thermo(chemicals)
    
    # Configuración de precios
    bst.settings.electricity_price = p_l

    # Corrientes
    mosto = bst.Stream('mosto', Water=900, Ethanol=100, units='kg/hr', T=t_f+273.15, price=p_m)
    reciclo = bst.Stream('reciclo', Water=200, T=95+273.15)

    # Equipos
    P100 = bst.Pump('P100', ins=mosto, P=4*101325)
    W210 = bst.HXprocess('W210', ins=(P100-0, reciclo), outs=('S1', 'S2'), phase0='l', phase1='l')
    W210.outs[0].T = 85 + 273.15
    W220 = bst.HXutility('W220', ins=W210-0, outs='S3', T=t_w+273.15)
    V100 = bst.IsenthalpicValve('V100', ins=W220-0, outs='S4', P=p_v*101325)
    V1 = bst.Flash('V1', ins=V100-0, outs=('Vapor', 'Vinazas'), P=p_v*101325, Q=0)
    
    # Corriente de producto final (Aquí es donde reside el F_mass)
    W310 = bst.HXutility('W310', ins=V1-0, outs='Producto_Final', T=25+273.15)
    producto = W310.outs[0] # Esta es la CORRIENTE de salida
    
    P200 = bst.Pump('P200', ins=V1-1, outs=reciclo, P=3*101325)

    # Simulación
    sys = bst.System('sys', path=(P100, W210, W220, V100, V1, W310, P200))
    sys.simulate()

    # --- CÁLCULO ECONÓMICO SEGURO ---
    horas_año = 8000
    inv_cap = 195000
    
    # Suma de utilidades evitando errores de tipo None
    costos_u = [u.utility_cost for u in sys.units if u.utility_cost is not None]
    costo_op_total = (sys.power_utility.cost + sum(costos_u)) * horas_año
    
    # CORRECCIÓN: Usamos 'producto' (la corriente) en lugar de 'W310' (el equipo)
    ingresos = producto.F_mass * p_e * horas_año
    materia_prima = mosto.F_mass * p_m * horas_año
    
    neto = ingresos - costo_op_total - materia_prima
    roi = (neto / inv_cap) * 100
    pb = inv_cap / neto if neto > 0 else 0
    npv = sum([neto / (1.1**i) for i in range(1, 11)]) - inv_cap

    return sys, producto, npv, pb, roi, neto

# =================================================================
# 3. INTERFAZ DE USUARIO (Sliders)
# =================================================================
with st.sidebar:
    st.header("⚙️ Configuración de Planta")
    
    # Sliders de Operación
    v_tf = st.slider("T Alimentación Mosto (°C)", 10.0, 50.0, 25.0)
    v_tw = st.slider("T Salida W220 (°C)", 75.0, 105.0, 92.0)
    v_pv = st.slider("Presión V100 (atm)", 0.2, 1.8, 1.0)
    
    st.divider()
    # Sliders de Precios
    v_pl = st.slider("Precio Luz (USD/kWh)", 0.05, 0.4, 0.12)
    v_pvap = st.slider("Precio Vapor (USD/ton)", 10.0, 60.0, 30.0)
    v_ph = st.slider("Precio Agua (USD/m3)", 0.1, 4.0, 0.5)
    v_pm = st.slider("Precio Mosto (USD/kg)", 0.01, 0.3, 0.05)
    v_pe = st.slider("Precio Etanol (USD/kg)", 0.5, 3.0, 1.3)
    
    st.divider()
    tutor_on = st.toggle("🎓 Habilitar Tutor IA")
    btn = st.button("🚀 ACTUALIZAR PROCESO", use_container_width=True)

# =================================================================
# 4. RESULTADOS Y DASHBOARD
# =================================================================
if btn:
    sys, prod_stream, npv, pb, roi, neto = simular_sistema_seguro(v_tf, v_tw, v_pv, v_pl, v_pvap, v_ph, v_pm, v_pe)

    # 4.1 Recuadros de Producto Final
    st.subheader("📋 Parámetros de la Corriente de Producto")
    c1, c2, c3, c4 = st.columns(4)
    with c1: st.markdown(f"<div class='metric-card'><div class='metric-label'>Presión</div><div class='metric-value'>{prod_stream.P/101325:.2f} atm</div></div>", unsafe_allow_html=True)
    with c2: st.markdown(f"<div class='metric-card'><div class='metric-label'>Temperatura</div><div class='metric-value'>{prod_stream.T-273.15:.1f} °C</div></div>", unsafe_allow_html=True)
    with c3: st.markdown(f"<div class='metric-card'><div class='metric-label'>Flujo Másico</div><div class='metric-value'>{prod_stream.F_mass:.1f} kg/h</div></div>", unsafe_allow_html=True)
    
    eth_pureza = (prod_stream.imass['Ethanol']/prod_stream.F_mass)*100 if prod_stream.F_mass > 0 else 0
    with c4: st.markdown(f"<div class='metric-card'><div class='metric-label'>Pureza Etanol</div><div class='metric-value'>{eth_pureza:.1f} %</div></div>", unsafe_allow_html=True)

    # 4.2 Indicadores Económicos
    st.divider()
    st.subheader("💰 Análisis Financiero")
    e1, e2, e3, e4 = st.columns(4)
    e1.metric("Costo Sugerido Venta", f"{v_pe:.2f} USD/kg")
    e2.metric("NPV (10 años)", f"{npv/1000:.1f}k USD")
    e3.metric("Payback", f"{pb:.1f} años")
    e4.metric("ROI Anual", f"{roi:.1f} %")

    # 4.3 Balances en Tablas
    t_mat, t_en = st.tabs(["Balance de Materia", "Balance de Energía"])
    with t_mat:
        st.table(pd.DataFrame([{"ID": s.ID, "kg/h": round(s.F_mass, 2), "T(C)": round(s.T-273.15, 1)} for s in sys.streams if s.F_mass > 0.1]))
    with t_en:
        st.table(pd.DataFrame([{"Unidad": u.ID, "Carga (kW)": round(sum([h.duty for h in u.heat_utilities])/3600, 2)} for u in sys.units]))

    # 4.4 Tutor IA
    if tutor_on:
        st.divider()
        st.subheader("💬 Ventana de Diálogo con Tutor IA")
        if "chat" not in st.session_state: st.session_state.chat = []
        
        for m in st.session_state.chat:
            with st.chat_message(m["role"]): st.markdown(m["content"])
            
        if prompt := st.chat_input("Consulta al experto sobre los resultados..."):
            st.session_state.chat.append({"role": "user", "content": prompt})
            with st.chat_message("user"): st.markdown(prompt)
            
            if "GEMINI_API_KEY" in st.secrets:
                genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
                model = genai.GenerativeModel('gemini-2.5-pro')
                contexto = f"Planta Etanol. ROI: {roi:.1f}%. Pureza: {eth_pureza:.1f}%. Pregunta: {prompt}"
                res = model.generate_content(contexto)
                with st.chat_message("assistant"): st.markdown(res.text)
                st.session_state.chat.append({"role": "assistant", "content": res.text})
            else:
                st.warning("⚠️ Configura GEMINI_API_KEY en Secrets.")
else:
    st.info("Ajuste los parámetros en el panel lateral y presione el botón de ejecución.")
