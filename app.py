import streamlit as st

# Verificación de entorno e importaciones
try:
    import biosteam as bst
    import thermosteam as tmo
    import pandas as pd
    import google.generativeai as genai
except ImportError as e:
    st.error(f"Error en librerías: {e}. Revisa tu requirements.txt.")
    st.stop()

# =================================================================
# CONFIGURACIÓN DE PÁGINA
# =================================================================
st.set_page_config(page_title="BioSteam Simulation Hub", layout="wide")

st.title("⚗️ Simulador Químico Profesional")
st.markdown("---")

# =================================================================
# FUNCIÓN DE SIMULACIÓN BIOSTEAM
# =================================================================
def simular_proceso(flujo_agua, flujo_etanol, temp_c):
    # Limpiar flowsheet para evitar conflictos de ID en reruns de Streamlit
    bst.main_flowsheet.clear()
    
    # Configuración Termodinámica
    chemicals = tmo.Chemicals(["Water", "Ethanol"])
    bst.settings.set_thermo(chemicals)

    # Corrientes
    mosto = bst.Stream("1_MOSTO", Water=flujo_agua, Ethanol=flujo_etanol, units="kg/hr", T=temp_c + 273.15)
    vinazas_ret = bst.Stream("Retorno", Water=200, T=95+273.15)

    # Equipos
    P100 = bst.Pump("P100", ins=mosto, P=4*101325)
    W210 = bst.HXprocess("W210", ins=(P100-0, vinazas_ret), outs=("Pre", "Drain"), phase0="l", phase1="l")
    W210.outs[0].T = 85 + 273.15
    W220 = bst.HXutility("W220", ins=W210-0, outs="Hot", T=92+273.15)
    V100 = bst.IsenthalpicValve("V100", ins=W220-0, outs="Mix", P=101325)
    
    # Flash Adiabático
    V1 = bst.Flash("V1", ins=V100-0, outs=("Vapor", "Líquido"), P=101325, Q=0)
    
    W310 = bst.HXutility("W310", ins=V1-0, outs="Producto", T=25 + 273.15)
    P200 = bst.Pump("P200", ins=V1-1, outs=vinazas_ret, P=3*101325)

    # Sistema
    sys = bst.System("etanol_sys", path=(P100, W210, W220, V100, V1, W310, P200))
    sys.simulate()
    return sys
    
    # --- CÁLCULOS TEA (Indicadores Económicos) ---
    capital = 180000 # Inversión estimada en USD
    
    # Cálculo manual de costos de utilidad para mayor precisión
    costo_vapor = (sum([u.utility_cost for u in sys.units])) * 8000 # Simplificado
    costo_materia_prima = mosto.F_mass * p_mosto * 8000
    ingresos = W310.F_mass * p_etanol * 8000
    
    ganancia_anual = ingresos - costo_vapor - costo_materia_prima
    roi = (ganancia_anual / capital) * 100
    pb = capital / ganancia_anual if ganancia_anual > 0 else 0
    npv = sum([ganancia_anual / (1.1**i) for i in range(1, 11)]) - capital

    return sys, W310, npv, pb, roi, ganancia_anual

# =================================================================
# 3. INTERFAZ DE USUARIO (SIDEBAR)
# =================================================================
with st.sidebar:
    st.header("⚙️ Control de Planta ISO")
    
    with st.expander("🌡️ Operación", expanded=True):
        t_feed = st.slider("T Alimentación (°C)", 10.0, 50.0, 25.0)
        t_w220 = st.slider("T Salida W220 (°C)", 70.0, 110.0, 92.0)
        p_flash = st.slider("P Separador (atm)", 0.2, 2.0, 1.0)
        
    with st.expander("💸 Precios de Insumos", expanded=True):
        p_elec = st.slider("Luz (USD/kWh)", 0.05, 0.5, 0.12)
        p_steam = st.slider("Vapor (USD/ton)", 10.0, 60.0, 30.0)
        p_water = st.slider("Agua (USD/m3)", 0.1, 5.0, 0.8)
        p_mosto = st.slider("Mosto (USD/kg)", 0.01, 0.4, 0.06)
        p_etanol = st.slider("Etanol (USD/kg)", 0.5, 3.0, 1.3)

    st.divider()
    modo_tutor = st.toggle("🎓 Activar Tutor IA")
    btn_run = st.button("🚀 ACTUALIZAR PROCESO", use_container_width=True)

# =================================================================
# 4. DASHBOARD DE RESULTADOS
# =================================================================
if btn_run:
    sys, prod, npv, pb, roi, neta = simular_proceso_iso(t_feed, t_w220, p_flash, p_elec, p_steam, p_water, p_mosto, p_etanol)
    
    # 4.1 Recuadros de Producto Final
    st.subheader("📦 Características del Producto Final")
    m1, m2, m3, m4 = st.columns(4)
    with m1: st.markdown(f"<div class='metric-box'><div class='metric-title'>Presión</div><div class='metric-value'>{prod.P/101325:.2f} atm</div></div>", unsafe_allow_html=True)
    with m2: st.markdown(f"<div class='metric-box'><div class='metric-title'>Temperatura</div><div class='metric-value'>{prod.T-273.15:.1f} °C</div></div>", unsafe_allow_html=True)
    with m3: st.markdown(f"<div class='metric-box'><div class='metric-title'>Flujo Másico</div><div class='metric-value'>{prod.F_mass:.1f} kg/h</div></div>", unsafe_allow_html=True)
    comp_eth = (prod.imass['Ethanol']/prod.F_mass)*100 if prod.F_mass > 0 else 0
    with m4: st.markdown(f"<div class='metric-box'><div class='metric-title'>Comp. Etanol</div><div class='metric-value'>{comp_eth:.1f} %</div></div>", unsafe_allow_html=True)

    # 4.2 Indicadores TEA
    st.divider()
    st.subheader("📊 Análisis Financiero y Rentabilidad")
    f1, f2, f3, f4 = st.columns(4)
    f1.metric("Costo Real Prod.", f"{p_mosto * 1.15:.3f} USD/kg")
    f2.metric("NPV (10 años)", f"{npv/1000:.1f}k USD")
    f3.metric("Payback", f"{pb:.1f} años")
    f4.metric("ROI", f"{roi:.1f} %")

    # 4.3 Tablas de Balances
    st.divider()
    tab1, tab2 = st.tabs(["Balance de Materia", "Balance de Energía"])
    with tab1:
        st.table(pd.DataFrame([{"Corriente": s.ID, "Flujo (kg/h)": round(s.F_mass, 2), "T (°C)": round(s.T-273.15, 1)} for s in sys.streams if s.F_mass > 0]))
    with tab2:
        st.table(pd.DataFrame([{"Equipo": u.ID, "Carga Térmica (kW)": round(sum([h.duty for h in u.heat_utilities])/3600, 2)} for u in sys.units]))

    # 4.4 Diagramas ISO (Botones de descarga)
    st.divider()
    st.subheader("📂 Documentación ISO (AutoCAD Plant 3D)")
    d1, d2 = st.columns(2)
    d1.download_button("📥 Descargar Diagrama de Bloques (ISO)", data="PDF_DATA", file_name="Diagrama_Bloques_ISO.pdf", use_container_width=True)
    d2.download_button("📥 Descargar PFD Avanzado (ISO)", data="PDF_DATA", file_name="PFD_Etanol_ISO.pdf", use_container_width=True)

    # 4.5 Tutor IA
    if modo_tutor:
        st.divider()
        st.subheader("💬 Ventana de Diálogo con Tutor IA")
        
        if "chat_history" not in st.session_state:
            st.session_state.chat_history = []

        for msg in st.session_state.chat_history:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

        if prompt := st.chat_input("¿Cómo puedo optimizar el NPV de esta planta?"):
            st.session_state.chat_history.append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.markdown(prompt)

            if "GEMINI_API_KEY" in st.secrets:
                genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
                model = genai.GenerativeModel('gemini-2.5-pro')
                
                context = f"Contexto: Planta de Etanol. ROI: {roi:.1f}%, Pureza: {comp_eth:.1f}%. Usuario pregunta: {prompt}"
                response = model.generate_content(context)
                
                with st.chat_message("assistant"):
                    st.markdown(response.text)
                st.session_state.chat_history.append({"role": "assistant", "content": response.text})
            else:
                st.warning("⚠️ Error: Configura tu GEMINI_API_KEY en los Secrets de Streamlit.")

else:
    st.info("💡 Configure los parámetros en el panel lateral y presione 'ACTUALIZAR PROCESO'.")
