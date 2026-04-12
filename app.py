import streamlit as st
import biosteam as bst
import thermosteam as tmo
import pandas as pd
import google.generativeai as genai

# =================================================================
# 1. CONFIGURACIÓN DE PÁGINA Y ESTILO
# =================================================================
st.set_page_config(page_title="Planta Etanol ISO-Pro", layout="wide")

st.markdown("""
    <style>
    .metric-card {
        background-color: #ffffff;
        padding: 15px;
        border-radius: 10px;
        border-top: 4px solid #1f77b4;
        text-align: center;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        margin-bottom: 10px;
    }
    .metric-label { font-size: 0.8rem; color: #666; font-weight: bold; }
    .metric-value { font-size: 1.1rem; color: #111; font-weight: bold; }
    </style>
""", unsafe_allow_html=True)

# =================================================================
# 2. MOTOR DE CÁLCULO (Blindado)
# =================================================================
def ejecutar_simulacion(t_feed, p_v100, p_luz, p_vap, p_h2o, p_mosto, p_etanol):
    # Limpieza de memoria
    bst.main_flowsheet.clear()
    
    # Configuración Termodinámica
    chemicals = tmo.Chemicals(["Water", "Ethanol"])
    tmo.settings.set_thermo(chemicals)
    
    # Precios
    bst.settings.electricity_price = p_luz

    # Corrientes
    feed = bst.Stream('mosto', Water=900, Ethanol=100, units='kg/hr', T=t_feed+273.15, price=p_mosto)
    reciclo = bst.Stream('reciclo', Water=200, T=95+273.15)

    # Equipos (Usando una configuración estándar robusta)
    P1 = bst.Pump('P100', ins=feed, P=303975)
    W1 = bst.HXutility('W220', ins=P1-0, outs='S1', T=365.15) # Intercambiador W220
    V1_valv = bst.IsenthalpicValve('V100_v', ins=W1-0, outs='S2', P=p_v100*101325)
    F1 = bst.Flash('V100', ins=V1_valv-0, outs=('Vapor', 'Liquido'), P=p_v100*101325, Q=0)
    W2 = bst.HXutility('W310', ins=F1-0, outs='Producto', T=298.15)
    P2 = bst.Pump('P200', ins=F1-1, outs=reciclo, P=303975)

    # Simulación
    sys = bst.System('sys', path=(P1, W1, V1_valv, F1, W2, P2))
    sys.simulate()

    # --- EXTRACCIÓN SEGURA DE COSTOS ---
    try:
        u_costs = [getattr(u, 'utility_cost', 0) for u in sys.units if getattr(u, 'utility_cost', 0) is not None]
        p_cost = getattr(sys.power_utility, 'cost', 0) or 0
        op_cost = (p_cost + sum(u_costs)) * 8000
    except:
        op_cost = 50000 

    # Análisis TEA
    inv = 180000
    ingresos = W2.F_mass * p_etanol * 8000
    costo_m = feed.F_mass * p_mosto * 8000
    neto = ingresos - op_cost - costo_m
    
    roi = (neto / inv) * 100
    pb = inv / neto if neto > 0 else 0
    npv = sum([neto / (1.1**i) for i in range(1, 11)]) - inv

    return sys, W2, npv, pb, roi, neto

# =================================================================
# 3. INTERFAZ (SIDEBAR)
# =================================================================
with st.sidebar:
    st.header("⚙️ Variables de Proceso")
    s_tf = st.slider("Temp. Mosto (°C)", 15.0, 50.0, 25.0)
    s_pv = st.slider("Presión V100 (atm)", 0.2, 1.8, 1.0)
    
    st.divider()
    st.header("💵 Mercado")
    s_pl = st.slider("Luz (USD/kWh)", 0.05, 0.45, 0.12)
    s_pvap = st.slider("Vapor (USD/ton)", 10.0, 60.0, 25.0)
    s_ph = st.slider("Agua (USD/m3)", 0.1, 5.0, 0.6)
    s_pm = st.slider("Mosto (USD/kg)", 0.01, 0.35, 0.05)
    s_pe = st.slider("Etanol (USD/kg)", 0.5, 3.0, 1.4)
    
    st.divider()
    tutor_on = st.toggle("🎓 Habilitar Tutor IA")
    btn = st.button("🚀 CALCULAR", use_container_width=True)

# =================================================================
# 4. DASHBOARD DE RESULTADOS
# =================================================================
if btn:
    sys, prod, vpn, pb, roi, neto = ejecutar_simulacion(s_tf, s_pv, s_pl, s_pvap, s_ph, s_pm, s_pe)

    # 4.1 Recuadros de Producto Final
    st.subheader("📦 Indicadores de la Corriente Final")
    c1, c2, c3, c4 = st.columns(4)
    with c1: st.markdown(f"<div class='metric-card'><div class='metric-label'>Presión</div><div class='metric-value'>{prod.P/101325:.2f} atm</div></div>", unsafe_allow_html=True)
    with c2: st.markdown(f"<div class='metric-card'><div class='metric-label'>Temperatura</div><div class='metric-value'>{prod.T-273.15:.1f} °C</div></div>", unsafe_allow_html=True)
    with c3: st.markdown(f"<div class='metric-card'><div class='metric-label'>Flujo</div><div class='metric-value'>{prod.F_mass:.1f} kg/h</div></div>", unsafe_allow_html=True)
    pureza = (prod.imass['Ethanol']/prod.F_mass)*100 if prod.F_mass > 0 else 0
    with c4: st.markdown(f"<div class='metric-card'><div class='metric-label'>Comp. Etanol</div><div class='metric-value'>{pureza:.1f} %</div></div>", unsafe_allow_html=True)

    # 4.2 Indicadores Económicos
    st.divider()
    f1, f2, f3, f4, f5 = st.columns(5)
    f1.metric("NPV (10a)", f"{vpn/1000:.1f}k USD")
    f2.metric("Payback", f"{pb:.1f} años")
    f3.metric("ROI", f"{roi:.1f} %")
    f4.metric("Costo Real", f"{s_pm * 1.22:.3f} USD")
    f5.metric("Sugerido Venta", f"{s_pe:.2f} USD")

    # 4.3 Tablas de Balances
    st.divider()
    t1, t2 = st.tabs(["Balance Materia", "Balance Energía"])
    with t1:
        st.table(pd.DataFrame([{"ID": s.ID, "kg/h": round(s.F_mass, 1), "T(C)": round(s.T-273.15, 1)} for s in sys.streams if s.F_mass > 0]))
    with t2:
        st.table(pd.DataFrame([{"Unit": u.ID, "Carga (kW)": round(sum([h.duty for h in u.heat_utilities])/3600, 2)} for u in sys.units]))

    # 4.4 Tutor IA
    if tutor_on:
        st.divider()
        st.subheader("💬 Ventana de Diálogo con Tutor IA (Gemini)")
        if "chat" not in st.session_state: st.session_state.chat = []
        for m in st.session_state.chat:
            with st.chat_message(m["role"]): st.markdown(m["content"])
        
        if prompt := st.chat_input("Consulta al tutor..."):
            st.session_state.chat.append({"role": "user", "content": prompt})
            with st.chat_message("user"): st.markdown(prompt)
            
            if "GEMINI_API_KEY" in st.secrets:
                genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
                model = genai.GenerativeModel('gemini-1.5-flash')
                ctx = f"Planta Etanol. ROI: {roi:.1f}%. Pureza: {pureza:.1f}%. Usuario: {prompt}"
                res = model.generate_content(ctx)
                with st.chat_message("assistant"): st.markdown(res.text)
                st.session_state.chat.append({"role": "assistant", "content": res.text})
            else:
                st.error("Falta la API Key en los secretos de Streamlit.")
else:
    st.info("Ajuste los sliders y presione el botón para iniciar la simulación.")
