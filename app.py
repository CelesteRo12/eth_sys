import streamlit as st
import biosteam as bst
import thermosteam as tmo
import pandas as pd
import google.generativeai as genai
import numpy as np

# =================================================================
# 1. CONFIGURACIÓN Y ESTILOS
# =================================================================
st.set_page_config(page_title="Planta Etanol ISO-Standard", layout="wide")

st.markdown("""
    <style>
    .metric-box {
        background-color: #f0f2f6;
        padding: 20px;
        border-radius: 10px;
        border-left: 5px solid #ff4b4b;
        margin-bottom: 10px;
    }
    </style>
""", unsafe_allow_html=True)

# =================================================================
# 2. LÓGICA DE SIMULACIÓN Y ECONOMÍA
# =================================================================
def simular_planta_completa(t_feed, t_w220, p_v100, p_luz, p_vapor, p_agua, p_mosto, p_etanol):
    bst.main_flowsheet.clear()
    chemicals = tmo.Chemicals(["Water", "Ethanol"])
    bst.settings.set_thermo(chemicals)

    # Precios de utilidad (Conversión a unidades BioSTEAM)
    bst.settings.electricity_price = p_luz 
    
    # Corrientes de Entrada
    mosto = bst.Stream('Mosto_Alimentacion', Water=900, Ethanol=100, units='kg/hr', T=t_feed+273.15, price=p_mosto)
    vinazas_rec = bst.Stream('Reciclo', Water=200, T=95+273.15)

    # Equipos
    P100 = bst.Pump('P100', ins=mosto, P=4*101325)
    W210 = bst.HXprocess('W210', ins=(P100-0, vinazas_rec), outs=('S1', 'S2'), phase0='l', phase1='l')
    W210.outs[0].T = 85 + 273.15
    
    W220 = bst.HXutility('W220', ins=W210-0, outs='S3', T=t_w220+273.15)
    # Configurar precio de vapor en el servicio del intercambiador
    W220.heat_utilities[0].agent = bst.HeatUtility.get_agent('low_pressure_steam')
    
    V100 = bst.IsenthalpicValve('V100', ins=W220-0, outs='S4', P=p_v100*101325)
    V1 = bst.Flash('V1', ins=V100-0, outs=('Vapor', 'Vinazas'), P=p_v100*101325, Q=0)
    
    W310 = bst.HXutility('W310', ins=V1-0, outs='Producto_Final', T=25+273.15)
    W310.price = p_etanol # Precio de venta del producto
    
    P200 = bst.Pump('P200', ins=V1-1, outs=vinazas_rec, P=3*101325)

    # Crear Sistema y Simular
    sys = bst.System('etanol_iso_sys', path=(P100, W210, W220, V100, V1, W310, P200))
    sys.simulate()
    
    # --- CÁLCULOS FINANCIEROS SIMPLIFICADOS ---
    capital_investment = 150000  # USD (Estimado)
    costo_operativo = (sys.power_utility.cost + sum([u.utility_cost for u in sys.units])) * 8000
    ingresos_anuales = W310.F_mass * p_etanol * 8000
    ganancia_neta = ingresos_anuales - costo_operativo - (mosto.F_mass * p_mosto * 8000)
    
    roi = (ganancia_neta / capital_investment) * 100
    payback = capital_investment / ganancia_neta if ganancia_neta > 0 else 0
    npv = sum([ganancia_neta / (1.1**i) for i in range(1, 11)]) - capital_investment

    return sys, W310, npv, payback, roi, ganancia_neta

# =================================================================
# 3. INTERFAZ DE USUARIO (SIDEBAR)
# =================================================================
with st.sidebar:
    st.header("🎮 Panel de Control")
    
    with st.expander("🌡️ Temperaturas y Presión", expanded=True):
        t_mosto = st.slider("T Alimentación Mosto (°C)", 10, 50, 25)
        t_salida_w220 = st.slider("T Salida W220 (°C)", 70, 110, 92)
        p_v100 = st.slider("P Separador V100 (atm)", 0.1, 2.0, 1.0)
    
    with st.expander("💰 Precios de Mercado", expanded=True):
        p_elec = st.slider("Precio Electricidad (USD/kWh)", 0.05, 0.5, 0.12)
        p_steam = st.slider("Precio Vapor (USD/ton)", 10, 50, 25)
        p_h2o = st.slider("Precio Agua (USD/m3)", 0.1, 5.0, 0.5)
        p_m_raw = st.slider("Precio Mosto (USD/kg)", 0.01, 0.5, 0.05)
        p_e_sale = st.slider("Precio Etanol (USD/kg)", 0.5, 3.0, 1.2)

    st.divider()
    modo_tutor = st.toggle("🎓 Habilitar Modo Tutor IA")
    btn_run = st.button("🚀 ACTUALIZAR PROCESO", use_container_width=True)

# =================================================================
# 4. CUERPO PRINCIPAL
# =================================================================
col_a, col_b = st.columns([1, 1])

if btn_run:
    sys, prod, npv, pb, roi, neta = simular_planta_completa(t_mosto, t_salida_w220, p_v100, p_elec, p_steam, p_h2o, p_m_raw, p_e_sale)
    
    with col_a:
        st.subheader("📍 Indicadores de Producto Final")
        c1, c2 = st.columns(2)
        with c1:
            st.markdown(f"<div class='metric-box'><b>Presión:</b><br>{prod.P/101325:.2f} atm</div>", unsafe_allow_html=True)
            st.markdown(f"<div class='metric-box'><b>Temperatura:</b><br>{prod.T-273.15:.1f} °C</div>", unsafe_allow_html=True)
        with c2:
            st.markdown(f"<div class='metric-box'><b>Flujo Másico:</b><br>{prod.F_mass:.2f} kg/h</div>", unsafe_allow_html=True)
            comp = (prod.imass['Ethanol']/prod.F_mass)*100 if prod.F_mass > 0 else 0
            st.markdown(f"<div class='metric-box'><b>Comp. Etanol:</b><br>{comp:.1f} %</div>", unsafe_allow_html=True)

    with col_b:
        st.subheader("📈 Análisis Financiero")
        f1, f2 = st.columns(2)
        with f1:
            st.metric("NPV (10 años)", f"{npv/1000:.1f}k USD")
            st.metric("ROI", f"{roi:.1f} %")
        with f2:
            st.metric("Payback Period", f"{pb:.1f} años")
            st.metric("Costo Real Prod.", f"{p_m_raw*1.2:.3f} USD/kg")

    st.divider()
    
    # 5. TABLAS DE BALANCE
    t1, t2 = st.tabs(["Material Balance", "Energy Balance"])
    with t1:
        st.table(pd.DataFrame([{"ID": s.ID, "kg/h": s.F_mass, "T(C)": s.T-273.15} for s in sys.streams if s.F_mass > 0]))
    with t2:
        st.table(pd.DataFrame([{"Unit": u.ID, "kW": sum([h.duty for h in u.heat_utilities])/3600} for u in sys.units]))

    # 6. DIAGRAMAS (Simulación de descarga PDF/ISO)
    st.divider()
    st.subheader("🛠️ Documentación Técnica ISO (AutoCAD Plant 3D)")
    d1, d2 = st.columns(2)
    with d1:
        st.info("📄 Diagrama de Bloques (ISO 10628)")
        st.download_button("Descargar PDF Bloques", data="Contenido binario ficticio", file_name="PFD_Bloques_ISO.pdf")
    with d2:
        st.info("📄 P&ID Avanzado (ISO 14617)")
        st.download_button("Descargar PDF P&ID", data="Contenido binario ficticio", file_name="PID_Etanol_ISO.pdf")

    # 7. VENTANA DE CONTEXTO / TUTOR IA
    if modo_tutor:
        st.divider()
        st.subheader("💬 Consultoría con Tutor IA")
        if "messages" not in st.session_state:
            st.session_state.messages = []

        for message in st.session_state.messages:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])

        if prompt := st.chat_input("Pregunta al tutor sobre los resultados..."):
            st.session_state.messages.append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.markdown(prompt)

            if "GEMINI_API_KEY" in st.secrets:
                genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
                model = genai.GenerativeModel('gemini-2.5-pro')
                
                contexto_tecnico = f"""
                Resultados Planta: ROI {roi}%, Payback {pb} años, Pureza {comp}%.
                El usuario pregunta: {prompt}
                Responde como un tutor experto en Bioingeniería.
                """
                
                response = model.generate_content(contexto_tecnico)
                with st.chat_message("assistant"):
                    st.markdown(response.text)
                st.session_state.messages.append({"role": "assistant", "content": response.text})
            else:
                st.error("Configura GEMINI_API_KEY en los Secrets.")
else:
    st.warning("Configure los sliders y presione 'ACTUALIZAR PROCESO' para ver los resultados e indicadores financieros.")
