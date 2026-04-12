import streamlit as st
import biosteam as bst
import thermosteam as tmo
import pandas as pd
import google.generativeai as genai

# =================================================================
# 1. CONFIGURACIÓN DE PÁGINA Y ESTILOS
# =================================================================
st.set_page_config(page_title="Simulador Proceso Etanol v5.0", layout="wide")

st.markdown("""
    <style>
    .stMetric { background-color: #f0f2f6; padding: 10px; border-radius: 10px; }
    .stTable { font-size: 0.8em; }
    </style>
""", unsafe_allow_html=True)

# =================================================================
# 2. LÓGICA DE SIMULACIÓN (BioSTEAM)
# =================================================================
def ejecutar_simulacion(f_agua, f_etanol, t_feed, p_elec, p_steam, p_water, p_mosto, p_etanol_v):
    # Reset del flowsheet
    bst.main_flowsheet.clear()
    
    # Termodinámica
    chemicals = tmo.Chemicals(["Water", "Ethanol"])
    bst.settings.set_thermo(chemicals)
    
    # Configuración de precios en BioSTEAM
    bst.settings.electricity_price = p_elec
    # Los precios de utilidades de calor se pueden ajustar globalmente o por unidad
    
    # Corrientes
    mosto = bst.Stream('Alimentacion', Water=f_agua, Ethanol=f_etanol, units='kg/hr', T=t_feed+273.15, price=p_mosto)
    reciclo = bst.Stream('Reciclo_Vinaza', Water=200, T=95+273.15)

    # Equipos
    P100 = bst.Pump('P100', ins=mosto, P=4*101325)
    W210 = bst.HXprocess('W210', ins=(P100-0, reciclo), outs=('S1', 'S2'), phase0='l', phase1='l')
    W210.outs[0].T = 85 + 273.15
    W220 = bst.HXutility('W220', ins=W210-0, outs='S3', T=92+273.15)
    V100 = bst.IsenthalpicValve('V100', ins=W220-0, outs='S4', P=101325)
    V1 = bst.Flash('V1', ins=V100-0, outs=('Vapor', 'Vinazas'), P=101325, Q=0)
    W310 = bst.HXutility('W310', ins=V1-0, outs='Producto_Final', T=25+273.15)
    P200 = bst.Pump('P200', ins=V1-1, outs=reciclo, P=3*101325)

    # Sistema
    sys = bst.System('sys_etanol', path=(P100, W210, W220, V100, V1, W310, P200))
    sys.simulate()
    
    # Cálculos económicos simples
    ingresos = W310.F_mass * p_etanol_v
    costos_op = (sum([u.utility_cost for u in sys.units])) + (mosto.F_mass * p_mosto)
    margen = ingresos - costos_op

    return sys, W310, margen

# =================================================================
# 3. INTERFAZ DE USUARIO (Sidebar)
# =================================================================
with st.sidebar:
    st.header("⚙️ Parámetros de Planta")
    
    with st.expander("📦 Flujos y Temperatura", expanded=True):
        f_agua = st.slider("Agua en Mosto (kg/h)", 500, 1500, 900)
        f_etanol = st.slider("Etanol en Mosto (kg/h)", 10, 500, 100)
        t_feed = st.slider("Temperatura Alimentación (°C)", 10, 50, 25)
    
    with st.expander("💰 Precios de Mercado", expanded=True):
        p_elec = st.slider("Precio Luz (USD/kWh)", 0.05, 0.50, 0.12)
        p_steam = st.slider("Precio Vapor (USD/ton)", 10.0, 60.0, 30.0)
        p_water = st.slider("Precio Agua (USD/m3)", 0.1, 5.0, 0.8)
        p_mosto = st.slider("Costo Mosto (USD/kg)", 0.01, 0.40, 0.06)
        p_etanol_v = st.slider("Venta Etanol (USD/kg)", 0.5, 3.0, 1.5)

    st.divider()
    tutor_ia = st.toggle("🎓 Habilitar Tutor IA")
    btn_simular = st.button("🚀 EJECUTAR PLANTA", use_container_width=True)

# =================================================================
# 4. DASHBOARD PRINCIPAL
# =================================================================
st.title("⚗️ Centro de Simulación ISO: Etanol")

if btn_simular:
    sys, prod, margen = ejecutar_simulacion(f_agua, f_etanol, t_feed, p_elec, p_steam, p_water, p_mosto, p_etanol_v)
    
    # Métricas rápidas
    m1, m2, m3 = st.columns(3)
    m1.metric("Producción Etanol", f"{prod.F_mass:.2f} kg/h")
    m2.metric("Pureza Obtenida", f"{(prod.imass['Ethanol']/prod.F_mass)*100:.1f} %")
    m3.metric("Margen Operativo", f"{margen:.2f} USD/h", delta=f"{margen:.2f}")

    # Tablas de Balance
    st.divider()
    col_a, col_b = st.columns(2)
    
    with col_a:
        st.subheader("📋 Balance de Materia")
        df_materia = pd.DataFrame([
            {"Corriente": s.ID, "Masa (kg/h)": round(s.F_mass, 2), "T (°C)": round(s.T-273.15, 1)} 
            for s in sys.streams if s.F_mass > 0.01
        ])
        st.table(df_materia)

    with col_b:
        st.subheader("⚡ Balance de Energía")
        df_energia = pd.DataFrame([
            {"Equipo": u.ID, "Calor (kW)": round(sum([h.duty for h in u.heat_utilities])/3600, 2), "Costo (USD/h)": round(u.utility_cost, 3)}
            for u in sys.units
        ])
        st.table(df_energia)

    # Almacenar resultados para la IA
    st.session_state.res_actual = f"Prod: {prod.F_mass}kg/h, Pureza: {(prod.imass['Ethanol']/prod.F_mass)*100:.1f}%, Margen: {margen}USD/h"

# =================================================================
# 5. VENTANA DE CONTEXTO / TUTOR IA
# =================================================================
if tutor_ia:
    st.divider()
    st.subheader("💬 Consultoría Técnica (Tutor IA)")
    
    if "messages" not in st.session_state:
        st.session_state.messages = []

    # Mostrar historial
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    if prompt := st.chat_input("¿Cómo puedo mejorar el margen operativo?"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        # Respuesta de Gemini
        if "GEMINI_API_KEY" in st.secrets:
            try:
                genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
                model = genai.GenerativeModel('gemini-1.5-flash')
                
                contexto = f"El usuario está simulando una planta de etanol. Datos actuales: {st.session_state.get('res_actual', 'No hay datos aún')}. Pregunta: {prompt}"
                response = model.generate_content(contexto)
                
                with st.chat_message("assistant"):
                    st.markdown(response.text)
                st.session_state.messages.append({"role": "assistant", "content": response.text})
            except Exception as e:
                st.error(f"Error en IA: {e}")
        else:
            st.error("Por favor, configura GEMINI_API_KEY en los Secrets de Streamlit.")
