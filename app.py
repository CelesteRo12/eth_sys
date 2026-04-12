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
# 2. LÓGICA DE INGENIERÍA (Cálculos de BioSTEAM)
# =================================================================
def simular_sistema(t_feed, t_w220, p_v100, p_luz, p_vapor, p_agua, p_mosto, p_etanol):
    # Reset del flowsheet para evitar duplicar equipos en memoria
    bst.main_flowsheet.clear()
    chemicals = tmo.Chemicals(["Water", "Ethanol"])
    bst.settings.set_thermo(chemicals)

    # Configuración de precios
    bst.settings.electricity_price = p_luz
    
    # Corrientes
    mosto = bst.Stream('mosto', Water=900, Ethanol=100, units='kg/hr', T=t_feed+273.15, price=p_mosto)
    reciclo = bst.Stream('reciclo', Water=200, T=95+273.15)

    # Unidades de Proceso
    P100 = bst.Pump('P100', ins=mosto, P=4*101325)
    W210 = bst.HXprocess('W210', ins=(P100-0, reciclo), outs=('S1', 'S2'), phase0='l', phase1='l')
    W210.outs[0].T = 85 + 273.15
    
    W220 = bst.HXutility('W220', ins=W210-0, outs='S3', T=t_w220+273.15)
    V100 = bst.IsenthalpicValve('V100', ins=W220-0, outs='S4', P=p_v100*101325)
    
    V1 = bst.Flash('V1', ins=V100-0, outs=('Vapor', 'Vinazas'), P=p_v100*101325, Q=0)
    
    W310 = bst.HXutility('W310', ins=V1-0, outs='Producto_Final', T=25+273.15)
    P200 = bst.Pump('P200', ins=V1-1, outs=reciclo, P=3*101325)

    # Simulación
    sys = bst.System('etanol_sys', path=(P100, W210, W220, V100, V1, W310, P200))
    sys.simulate()

    # --- ANÁLISIS ECONÓMICO ---
    horas_operacion = 8000
    inv_total = 185000 # USD Estimado
    
    costo_operativo = (sys.power_utility.cost + sum([u.utility_cost for u in sys.units])) * horas_operacion
    costo_materia_prima = mosto.F_mass * p_mosto * horas_operacion
    ingresos = W310.F_mass * p_etanol * horas_operacion
    
    beneficio_neto = ingresos - costo_operativo - costo_materia_prima
    
    roi = (beneficio_neto / inv_total) * 100
    payback = inv_total / beneficio_neto if beneficio_neto > 0 else 0
    npv = sum([beneficio_neto / (1.1**i) for i in range(1, 11)]) - inv_total

    return sys, W310, npv, payback, roi, beneficio_neto

# =================================================================
# 3. INTERFAZ DE USUARIO (Captura de Entradas)
# =================================================================
with st.sidebar:
    st.header("⚙️ Configuración del Proceso")
    
    with st.expander("🌡️ Parámetros Operativos", expanded=True):
        val_t_feed = st.slider("Temp. Alimentación Mosto (°C)", 10.0, 50.0, 25.0)
        val_t_w220 = st.slider("Temp. Salida W220 (°C)", 75.0, 110.0, 92.0)
        val_p_v100 = st.slider("Presión V100 (atm)", 0.2, 2.0, 1.0)

    with st.expander("💰 Precios y Mercado", expanded=True):
        val_p_luz = st.slider("Precio Luz (USD/kWh)", 0.05, 0.50, 0.12)
        val_p_vap = st.slider("Precio Vapor (USD/ton)", 10.0, 60.0, 30.0)
        val_p_h2o = st.slider("Precio Agua (USD/m3)", 0.1, 5.0, 0.5)
        val_p_mosto = st.slider("Precio Mosto (USD/kg)", 0.01, 0.30, 0.05)
        val_p_etanol = st.slider("Precio Etanol (USD/kg)", 0.50, 3.00, 1.30)

    st.divider()
    tutor_ia = st.toggle("🎓 Habilitar Modo Tutor con IA")
    btn_simular = st.button("🚀 ACTUALIZAR SIMULACIÓN", use_container_width=True)

# =================================================================
# 4. DASHBOARD DE RESULTADOS
# =================================================================
if btn_simular:
    # Ejecutar lógica
    sys, prod, npv, pb, roi, neto = simular_sistema(
        val_t_feed, val_t_w220, val_p_v100, val_p_luz, val_p_vap, val_p_h2o, val_p_mosto, val_p_etanol
    )

    # 4.1 Indicadores de Corriente de Producto
    st.subheader("📦 Propiedades del Producto Final")
    c1, c2, c3, c4 = st.columns(4)
    with c1: st.markdown(f"<div class='metric-card'><div class='metric-label'>Presión</div><div class='metric-value'>{prod.P/101325:.2f} atm</div></div>", unsafe_allow_html=True)
    with c2: st.markdown(f"<div class='metric-card'><div class='metric-label'>Temperatura</div><div class='metric-value'>{prod.T-273.15:.1f} °C</div></div>", unsafe_allow_html=True)
    with c3: st.markdown(f"<div class='metric-card'><div class='metric-label'>Flujo Másico</div><div class='metric-value'>{prod.F_mass:.1f} kg/h</div></div>", unsafe_allow_html=True)
    comp_eth = (prod.imass['Ethanol']/prod.F_mass)*100 if prod.F_mass > 0 else 0
    with c4: st.markdown(f"<div class='metric-card'><div class='metric-label'>% Etanol</div><div class='metric-value'>{comp_eth:.1f} %</div></div>", unsafe_allow_html=True)

    # 4.2 Indicadores Económicos
    st.divider()
    st.subheader("📊 Análisis Tecno-Económico")
    e1, e2, e3, e4 = st.columns(4)
    e1.metric("Costo Real Prod.", f"{val_p_mosto*1.22:.3f} USD/kg")
    e2.metric("NPV (10 años)", f"{npv/1000:.1f}k USD")
    e3.metric("Payback Period", f"{pb:.1f} años")
    e4.metric("ROI", f"{roi:.1f} %")

    # 4.3 Tablas de Balances
    st.divider()
    tab_mat, tab_en = st.tabs(["Balance de Materia", "Balance de Energía"])
    with tab_mat:
        df_m = pd.DataFrame([{"ID": s.ID, "kg/h": round(s.F_mass, 2), "T(C)": round(s.T-273.15, 1)} for s in sys.streams if s.F_mass > 0.1])
        st.table(df_m)
    with tab_en:
        df_e = pd.DataFrame([{"Equipo": u.ID, "Calor (kW)": round(sum([h.duty for h in u.heat_utilities])/3600, 2)} for u in sys.units])
        st.table(df_e)

    # 4.4 Tutor IA (Ventana de Contexto)
    if tutor_ia:
        st.divider()
        st.subheader("💬 Consultoría con Tutor IA (Gemini)")
        
        if "chat_history" not in st.session_state:
            st.session_state.chat_history = []

        # Mostrar historial
        for msg in st.session_state.chat_history:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

        if prompt := st.chat_input("Pregunta al tutor sobre los resultados..."):
            st.session_state.chat_history.append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.markdown(prompt)

            if "GEMINI_API_KEY" in st.secrets:
                genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
                model = genai.GenerativeModel('gemini-2.5-pro')
                
                contexto = f"Datos: ROI {roi:.1f}%, Payback {pb:.1f} años, Pureza {comp_eth:.1f}%. Pregunta: {prompt}"
                res = model.generate_content(contexto)
                
                with st.chat_message("assistant"):
                    st.markdown(res.text)
                st.session_state.chat_history.append({"role": "assistant", "content": res.text})
            else:
                st.warning("⚠️ Registra tu GEMINI_API_KEY en los Secrets de Streamlit.")

else:
    st.info("👈 Ajusta los parámetros en el panel lateral y haz clic en 'Actualizar Simulación'.")
