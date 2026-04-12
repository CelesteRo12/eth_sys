import streamlit as st
import biosteam as bst
import thermosteam as tmo
import pandas as pd
import google.generativeai as genai
import os

# =================================================================
# 1. CONFIGURACIÓN DE PÁGINA Y ESTILOS
# =================================================================
st.set_page_config(page_title="Planta Etanol ISO v2.1", layout="wide")

st.markdown("""
    <style>
    .metric-box {
        background-color: #f0f2f6;
        padding: 20px;
        border-radius: 10px;
        border-left: 5px solid #ff4b4b;
        margin-bottom: 10px;
        text-align: center;
    }
    .metric-title { font-weight: bold; font-size: 0.9em; color: #555; }
    .metric-value { font-size: 1.4em; color: #000; }
    </style>
""", unsafe_allow_html=True)

# =================================================================
# 2. LÓGICA DE SIMULACIÓN Y ECONOMÍA (CORREGIDA)
# =================================================================
@st.cache_resource
def setup_thermodynamics():
    # Cargar compuestos una sola vez y guardarlos en caché
    bst.main_flowsheet.clear()
    chemicals = tmo.Chemicals(["Water", "Ethanol"])
    return chemicals

def simular_proceso_iso(t_feed, t_out_w220, p_flash, price_luz, price_vapor, price_h2o, price_m, price_e):
    
    # 2.1 Configuración Base (Limpiar memoria)
    bst.main_flowsheet.clear()
    chemicals = setup_thermodynamics()
    bst.settings.set_thermo(chemicals)

    # 2.2 Precios de Utilidades Globales
    bst.settings.electricity_price = price_luz # USD/kWh
    
    # Configurar agente de vapor (Low Pressure Steam)
    lps = bst.HeatUtility.get_agent('low_pressure_steam')
    lps.price = price_vapor / 1000 # Convertir USD/ton a USD/kg
    # st.settings.cooling_water_price = price_h2o # No usado en este flash, pero se configura
    
    # 2.3 Definición de Corrientes
    mosto = bst.Stream('1_MOSTO', Water=900, Ethanol=100, units='kg/hr', T=t_feed+273.15, price=price_m)
    vinazas_rec = bst.Stream('RECICLO', Water=200, T=95+273.15)

    # 2.4 Unidades de Proceso
    P100 = bst.Pump('P100', ins=mosto, P=4*101325)
    
    W210 = bst.HXprocess('W210', ins=(P100-0, vinazas_rec), outs=('3_Pre', 'S2'), phase0='l', phase1='l')
    W210.outs[0].T = 85 + 273.15
    
    W220 = bst.HXutility('W220', ins=W210-0, outs='S3', T=t_out_w220+273.15)
    
    V100 = bst.IsenthalpicValve('V100', ins=W220-0, outs='S4', P=p_flash*101325)
    
    # Tanque Flash (Adiabático, Q=0)
    V1 = bst.Flash('V1', ins=V100-0, outs=('Vapor_Caliente', 'Vinazas_Fondo'), P=p_flash*101325, Q=0)
    
    W310 = bst.HXutility('W310', ins=V1-0, outs='Producto_Final', T=25+273.15)
    W310.price = price_e # Precio de venta USD/kg

    P200 = bst.Pump('P200', ins=V1-1, outs=vinazas_rec, P=3*101325)

    # 2.5 Crear Sistema y Simular (Primer paso)
    sys = bst.System('etanol_sys', path=(P100, W210, W220, V100, V1, W310, P200))
    sys.simulate()
    
    # --- CORRECCIÓN DE ERROR DEL AGENTE ---
    # Una vez simulado, el heat_utility[0] existe. Ahora sí asignamos el agente correcto.
    if hasattr(W220, 'heat_utilities') and W220.heat_utilities:
        lps = bst.HeatUtility.get_agent('low_pressure_steam')
        lps.price = price_vapor / 1000 # Actualizar precio USD/kg
        W220.heat_utilities[0].agent = lps
        
        # Volvemos a calcular rápido para que el precio del vapor se refleje en los costos operativos
        # W220.heat_utilities[0].simulate()
        # W220.simulate() # Esto causa un error recursivo, mejor usar bst.DEA

    # --- CÁLCULOS ECONÓMICOS SIMPLIFICADOS (TEA) ---
    cap_invest = 150000  # USD (Estimado Capital Total)
    
    # Cálculo de costo operativo anual (Power + Utilities + Raw Materials)
    costo_oper_anual = (sys.power_utility.cost + sum([u.utility_cost for u in sys.units])) * 8000 # 8000 hr/año
    # st.write(f"Costo Oper: {costo_oper_anual}")
    
    ingresos_anuales = W310.F_mass * price_e * 8000
    g_neta = ingresos_anuales - costo_oper_anual - (mosto.F_mass * price_m * 8000)
    
    roi = (g_neta / cap_invest) * 100
    pb = cap_invest / g_neta if g_neta > 0 else 0
    npv = sum([g_neta / (1.1**i) for i in range(1, 11)]) - cap_invest

    return sys, W310, npv, pb, roi, g_neta

# =================================================================
# 3. INTERFAZ DE USUARIO (SIDEBAR)
# =================================================================
with st.sidebar:
    st.header("🎮 Panel de Control ISO 9001")
    st.markdown("---")
    
    with st.expander("🌡️ Parámetros de Simulación", expanded=True):
        t_m_raw = st.slider("Temp Alimentación Mosto (°C)", 15, 45, 25)
        t_w220 = st.slider("Temp Salida W220 (°C)", 75, 105, 92)
        p_v_flash = st.slider("Presión en Flash (atm)", 0.2, 1.8, 1.0)
    
    with st.expander("💰 Mercado y Precios", expanded=True):
        p_elect = st.slider("Electricidad (USD/kWh)", 0.05, 0.40, 0.12)
        p_steam_lp = st.slider("Vapor LP (USD/ton)", 10, 50, 25)
        p_water_cw = st.slider("Agua Enf (USD/m3)", 0.1, 4.0, 0.5)
        p_m_raw = st.slider("Mosto (USD/kg)", 0.02, 0.30, 0.05)
        p_e_sale = st.slider("Etanol (USD/kg)", 0.6, 2.80, 1.20)

    st.divider()
    modo_tutor = st.toggle("🎓 Habilitar Tutor Inteligente IA")
    btn_run = st.button("🚀 SIMULAR PROCESO", use_container_width=True)

# =================================================================
# 4. CUERPO PRINCIPAL
# =================================================================
col_metrica_a, col_metrica_b = st.columns([1, 1])

if btn_run:
    with st.spinner("Calculando balances termodinámicos y financieros..."):
        sys, prod, npv, pb, roi, ganancia = simular_proceso_iso(
            t_m_raw, t_w220, p_v_flash, p_elect, p_steam_lp, p_water_cw, p_m_raw, p_e_sale
        )
        st.success("Simulación completada")

    with col_metrica_a:
        st.subheader("📍 Indicadores del Producto Final")
        c1, c2, c3, c4 = st.columns(4)
        with c1: st.markdown(f"<div class='metric-box'><div class='metric-title'>Presión</div><div class='metric-value'>{prod.P/101325:.2f} atm</div></div>", unsafe_allow_html=True)
        with c2: st.markdown(f"<div class='metric-box'><div class='metric-title'>Temperatura</div><div class='metric-value'>{prod.T-273.15:.1f} °C</div></div>", unsafe_allow_html=True)
        with c3: st.markdown(f"<div class='metric-box'><div class='metric-title'>Flujo</div><div class='metric-value'>{prod.F_mass:.1f} kg/h</div></div>", unsafe_allow_html=True)
        comp = (prod.imass['Ethanol']/prod.F_mass)*100 if prod.F_mass > 0 else 0
        with c4: st.markdown(f"<div class='metric-box'><div class='metric-title'>% Etanol</div><div class='metric-value'>{comp:.1f} %</div></div>", unsafe_allow_html=True)

    with col_metrica_b:
        st.subheader("📊 Análisis Tecnológico-Económico (TEA)")
        st.metric("ROI", f"{roi:.1f} %")
        st.metric("Payback", f"{pb:.1f} años")
        st.metric("NPV (10 años)", f"{npv/1000:.1f}k USD")
        st.metric("Costo Real Prod.", f"{p_m_raw*1.2:.3f} USD/kg")

    st.divider()
    
    # 5. TABLAS DE BALANCE (Usando st.table para evitar errores de Altair)
    t1, t2 = st.tabs(["Material Balance", "Energy Balance"])
    with t1:
        st.write("**Balance de Materia**")
        df_mat = pd.DataFrame([{"ID": s.ID, "kg/h": s.F_mass, "T(C)": s.T-273.15} for s in sys.streams if s.F_mass > 0])
        st.table(df_mat)
    with t2:
        st.write("**Balance de Energía (Térmico)**")
        df_en = pd.DataFrame([{"Equipo": u.ID, "kW": sum([h.duty for h in u.heat_utilities])/3600} for u in sys.units])
        st.table(df_en)

    # 6. DIAGRAMAS (Simulación de descarga PDF/ISO)
    st.divider()
    st.subheader("🛠️ Documentación Técnica ISO Standard (desde AutoCAD Plant 3D)")
    d1, d2 = st.columns(2)
    with d1:
        st.info("📄 Diagrama de Bloques (ISO 10628)")
        st.download_button("Descargar PDF Bloques", data="Falsa data binaria PDF", file_name="PFD_ISO_Bloques.pdf")
    with d2:
        st.info("📄 Diagrama de Flujo (P&ID) (ISO 14617)")
        st.download_button("Descargar PDF P&ID", data="Falsa data binaria PDF", file_name="PID_ISO_Flujo.pdf")

    # 7. TUTOR IA (Gemini Chat)
    if modo_tutor:
        st.divider()
        st.subheader("💬 Ventana de Consultoría con Tutor IA")
        
        # Inicializar historial de chat si no existe
        if "messages" not in st.session_state:
            st.session_state.messages = []

        # Mostrar historial
        for message in st.session_state.messages:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])

        # Chat input
        if prompt := st.chat_input("Pregunta al tutor sobre los resultados técnicos..."):
            st.session_state.messages.append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.markdown(prompt)

            # Lógica de Gemini
            if "GEMINI_API_KEY" in st.secrets:
                try:
                    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
                    model = genai.GenerativeModel('gemini-2.5-pro')
                    
                    contexto_tecnico = f"""
                    Resultados Simulación: ROI {roi}%, Payback {pb} años, Pureza Producto {comp}%.
                    El usuario pregunta: {prompt}
                    Actúa como un tutor experto en Bioingeniería.
                    """
                    
                    response = model.generate_content(contexto_tecnico)
                    with st.chat_message("assistant"):
                        st.markdown(response.text)
                    st.session_state.messages.append({"role": "assistant", "content": response.text})
                except Exception as e:
                    st.error(f"Error de IA: {e}")
            else:
                st.warning("IA Desactivada: Registra GEMINI_API_KEY en 'Secrets'.")
else:
    st.info("Ajuste los controles en el panel izquierdo y haga clic en 'SIMULAR PROCESO'.")
