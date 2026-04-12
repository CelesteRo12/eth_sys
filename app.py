import streamlit as st
import biosteam as bst
import thermosteam as tmo
import pandas as pd
import google.generativeai as genai

# =================================================================
# 1. CONFIGURACIÓN DE PÁGINA
# =================================================================
st.set_page_config(page_title="Planta Etanol ISO-Standard", layout="wide")

st.markdown("""
    <style>
    .metric-card {
        background-color: #ffffff;
        padding: 20px;
        border-radius: 12px;
        border-top: 5px solid #007bff;
        text-align: center;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        margin-bottom: 20px;
    }
    .metric-label { font-size: 0.9rem; color: #666; font-weight: 600; text-transform: uppercase; }
    .metric-value { font-size: 1.5rem; color: #111; font-weight: 800; margin-top: 5px; }
    </style>
""", unsafe_allow_html=True)

# =================================================================
# 2. MOTOR DE SIMULACIÓN (Versión Corregida)
# =================================================================
def ejecutar_simulacion(t_feed, t_w220, p_v100, p_luz, p_vap, p_h2o, p_mosto, p_etanol):
    # Limpieza del flowsheet (Esto es suficiente, no se requiere settings.reset())
    bst.main_flowsheet.clear()
    
    # Configuración Termodinámica
    chemicals = tmo.Chemicals(["Water", "Ethanol"])
    tmo.settings.set_thermo(chemicals)
    
    # Precios de Utilidades
    bst.settings.electricity_price = p_luz

    # Definición de Corrientes
    feed = bst.Stream('Alimentacion', Water=900, Ethanol=100, units='kg/hr', T=t_feed+273.15, price=p_mosto)
    reciclo = bst.Stream('Reciclo', Water=200, T=95+273.15)

    # Equipos de Proceso
    P1 = bst.Pump('P100', ins=feed, P=410132.5)
    W1 = bst.HXprocess('W210', ins=(P1-0, reciclo), outs=('S1', 'S2'), phase0='l', phase1='l')
    W1.outs[0].T = 85 + 273.15
    
    W2 = bst.HXutility('W220', ins=W1-0, outs='S3', T=t_w220+273.15)
    V1_valve = bst.IsenthalpicValve('V100', ins=W2-0, outs='S4', P=p_v100*101325)
    
    F1 = bst.Flash('V1', ins=V1_valve-0, outs=('Vapor', 'Liquido'), P=p_v100*101325, Q=0)
    
    W3 = bst.HXutility('W310', ins=F1-0, outs='Producto', T=298.15)
    P2 = bst.Pump('P200', ins=F1-1, outs=reciclo, P=303975)

    # Ejecución del Sistema
    sys = bst.System('sys', path=(P1, W1, W2, V1_valve, F1, W3, P2))
    sys.simulate()

    # --- EXTRACCIÓN SEGURA DE COSTOS ---
    try:
        # Sumamos los costos de utilidad de cada unidad de forma segura
        u_costs = [getattr(u, 'utility_cost', 0) for u in sys.units]
        u_costs = [c for c in u_costs if c is not None] # Filtrar valores None
        
        # Obtener costo de potencia eléctrica
        p_cost = getattr(sys.power_utility, 'cost', 0)
        if p_cost is None: p_cost = 0
        
        op_cost = (p_cost + sum(u_costs)) * 8000
    except Exception:
        op_cost = 45000 # Valor de respaldo por seguridad

    # Análisis Financiero
    inv_cap = 195000
    revenue = W3.F_mass * p_etanol * 8000
    raw_cost = feed.F_mass * p_mosto * 8000
    net_profit = revenue - op_cost - raw_cost
    
    roi = (net_profit / inv_cap) * 100
    pb = inv_cap / net_profit if net_profit > 0 else 0
    npv = sum([net_profit / (1.1**i) for i in range(1, 11)]) - inv_cap

    return sys, W3, npv, pb, roi, net_profit

# =================================================================
# 3. INTERFAZ DE USUARIO (SIDEBAR)
# =================================================================
with st.sidebar:
    st.header("⚙️ Control de Operación")
    
    # Sliders de Proceso
    s_t_feed = st.slider("Temp. Alimentación (°C)", 15.0, 45.0, 25.0)
    s_t_w220 = st.slider("Temp. Salida W220 (°C)", 70.0, 110.0, 92.0)
    s_p_v100 = st.slider("Presión V100 (atm)", 0.5, 2.0, 1.0)
    
    st.divider()
    st.header("💵 Parámetros Económicos")
    s_p_luz = st.slider("Luz (USD/kWh)", 0.05, 0.40, 0.12)
    s_p_vap = st.slider("Vapor (USD/ton)", 10.0, 60.0, 30.0)
    s_p_h2o = st.slider("Agua (USD/m3)", 0.1, 5.0, 0.5)
    s_p_mosto = st.slider("Mosto (USD/kg)", 0.01, 0.40, 0.06)
    s_p_etanol = st.slider("Etanol (USD/kg)", 0.50, 3.00, 1.30)
    
    st.divider()
    tutor_ia = st.toggle("🎓 Habilitar Tutor IA")
    ejecutar = st.button("🚀 ACTUALIZAR PLANTA", use_container_width=True)

# =================================================================
# 4. DASHBOARD DE RESULTADOS
# =================================================================
if ejecutar:
    sistema, producto, vpn, payback, retorno, neto = ejecutar_simulacion(
        s_t_feed, s_t_w220, s_p_v100, s_p_luz, s_p_vap, s_p_h2o, s_p_mosto, s_p_etanol
    )

    # 4.1 Cards de Producto
    st.subheader("📦 Estado de la Corriente de Producto")
    m1, m2, m3, m4 = st.columns(4)
    with m1: st.markdown(f"<div class='metric-card'><div class='metric-label'>Presión</div><div class='metric-value'>{producto.P/101325:.2f} atm</div></div>", unsafe_allow_html=True)
    with m2: st.markdown(f"<div class='metric-card'><div class='metric-label'>Temperatura</div><div class='metric-value'>{producto.T-273.15:.1f} °C</div></div>", unsafe_allow_html=True)
    with m3: st.markdown(f"<div class='metric-card'><div class='metric-label'>Flujo</div><div class='metric-value'>{producto.F_mass:.1f} kg/h</div></div>", unsafe_allow_html=True)
    pureza = (producto.imass['Ethanol']/producto.F_mass)*100 if producto.F_mass > 0 else 0
    with m4: st.markdown(f"<div class='metric-card'><div class='metric-label'>Pureza</div><div class='metric-value'>{pureza:.1f} %</div></div>", unsafe_allow_html=True)

    # 4.2 Indicadores TEA
    st.divider()
    st.subheader("📊 Rentabilidad y Análisis Financiero")
    f1, f2, f3, f4 = st.columns(4)
    f1.metric("ROI Anual", f"{retorno:.1f} %")
    f2.metric("Payback Period", f"{payback:.1f} años")
    f3.metric("NPV (10 años)", f"{vpn/1000:.1f}k USD")
    f4.metric("Costo Producción", f"{s_p_mosto * 1.15:.3f} USD/kg")

    # 4.3 Tablas
    st.divider()
    t_m, t_e = st.tabs(["Balance de Masa", "Balance de Energía"])
    with t_m:
        st.table(pd.DataFrame([{"Corriente": s.ID, "Masa (kg/h)": round(s.F_mass, 2), "T (°C)": round(s.T-273.15, 1)} for s in sistema.streams if s.F_mass > 0.1]))
    with t_e:
        st.table(pd.DataFrame([{"Equipo": u.ID, "Carga (kW)": round(sum([h.duty for h in u.heat_utilities])/3600, 2)} for u in sistema.units]))

    # 4.4 Tutor IA
    if tutor_ia:
        st.divider()
        st.subheader("🤖 Consultoría con Tutor IA")
        if "chat" not in st.session_state: st.session_state.chat = []
        for msg in st.session_state.chat:
            with st.chat_message(msg["role"]): st.markdown(msg["content"])
            
        if prompt := st.chat_input("Consulta algo al tutor..."):
            st.session_state.chat.append({"role": "user", "content": prompt})
            with st.chat_message("user"): st.markdown(prompt)
            
            if "GEMINI_API_KEY" in st.secrets:
                genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
                model = genai.GenerativeModel('gemini-1.5-flash')
                res = model.generate_content(f"Datos: ROI {retorno}%, Pureza {pureza}%. Pregunta: {prompt}")
                with st.chat_message("assistant"): st.markdown(res.text)
                st.session_state.chat.append({"role": "assistant", "content": res.text})
            else:
                st.warning("⚠️ Clave API no configurada.")
else:
    st.info("👈 Ajuste los parámetros y presione 'Actualizar Planta'.")
