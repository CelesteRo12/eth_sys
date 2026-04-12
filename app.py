import streamlit as st
import biosteam as bst
import thermosteam as tmo
import pandas as pd
import google.generativeai as genai

# =================================================================
# 1. CONFIGURACIÓN DE PÁGINA Y ESTILOS
# =================================================================
st.set_page_config(page_title="Simulador Pro Etanol v5.0", layout="wide")

st.markdown("""
    <style>
    .main { background-color: #f5f7f9; }
    .stMetric { background-color: #ffffff; padding: 15px; border-radius: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
    </style>
""", unsafe_allow_html=True)

# =================================================================
# 2. LÓGICA DE SIMULACIÓN (BioSTEAM)
# =================================================================
def ejecutar_simulacion(flujo_agua, flujo_etanol, temp_c, p_elec, p_steam, p_water, p_mosto, p_etanol):
    bst.main_flowsheet.clear()
    chemicals = tmo.Chemicals(["Water", "Ethanol"])
    bst.settings.set_thermo(chemicals)
    
    # Configurar precios en el entorno BioSTEAM
    bst.settings.electricity_price = p_elec
    
    # Definición de Corrientes
    mosto = bst.Stream('Alimentacion', Water=flujo_agua, Ethanol=flujo_etanol, units='kg/hr', T=temp_c+273.15, price=p_mosto)
    reciclo = bst.Stream('Reciclo', Water=200, T=95+273.15)

    # Unidades de Proceso
    P100 = bst.Pump('P100', ins=mosto, P=4*101325)
    W210 = bst.HXprocess('W210', ins=(P100-0, reciclo), outs=('S1', 'S2'), phase0='l', phase1='l')
    W210.outs[0].T = 85 + 273.15
    W220 = bst.HXutility('W220', ins=W210-0, outs='S3', T=92+273.15)
    V100 = bst.IsenthalpicValve('V100', ins=W220-0, outs='S4', P=101325)
    V1 = bst.Flash('V1', ins=V100-0, outs=('Vapor', 'Vinazas'), P=101325, Q=0)
    W310 = bst.HXutility('W310', ins=V1-0, outs='Producto', T=25+273.15)
    P200 = bst.Pump('P200', ins=V1-1, outs=reciclo, P=3*101325)

    sys = bst.System('sys_etanol', path=(P100, W210, W220, V100, V1, W310, P200))
    sys.simulate()
    
    # Cálculos económicos simplificados
    ingresos = W310.F_mass * p_etanol * 8000 # 8000 horas/año
    costos_op = (sum([u.utility_cost for u in sys.units]) + (mosto.F_mass * p_mosto)) * 8000
    utilidad = ingresos - costos_op
    
    return sys, W310, utilidad

# =================================================================
# 3. INTERFAZ DE USUARIO (SIDEBAR)
# =================================================================
with st.sidebar:
    st.header("⚙️ Parámetros del Proceso")
    val_agua = st.number_input("Agua en alimentación (kg/h)", 500, 2000, 900)
    val_etanol = st.number_input("Etanol en alimentación (kg/h)", 10, 500, 100)
    val_temp = st.slider("Temperatura de entrada (°C)", 10.0, 60.0, 25.0)
    
    st.divider()
    st.header("💰 Mercado y Precios")
    p_elec = st.slider("Luz (USD/kWh)", 0.05, 0.50, 0.12)
    p_steam = st.slider("Vapor (USD/ton)", 10.0, 60.0, 30.0)
    p_water = st.slider("Agua (USD/m3)", 0.1, 5.0, 0.8)
    p_mosto = st.slider("Mosto (USD/kg)", 0.01, 0.40, 0.06)
    p_etanol = st.slider("Etanol (USD/kg)", 0.5, 3.0, 1.3)
    
    st.divider()
    tutor_ia = st.toggle("🎓 Habilitar Tutor IA")
    btn_simular = st.button("🚀 EJECUTAR PLANTA", use_container_width=True)

# =================================================================
# 4. DASHBOARD DE RESULTADOS
# =================================================================
if btn_simular:
    sys, prod, utilidad = ejecutar_simulacion(val_agua, val_etanol, val_temp, p_elec, p_steam, p_water, p_mosto, p_etanol)
    
    st.title("📊 Resultados de la Simulación")
    
    # Métricas principales
    m1, m2, m3 = st.columns(3)
    m1.metric("Producción Etanol", f"{prod.F_mass:.1f} kg/h")
    m2.metric("Pureza Obtenida", f"{(prod.imass['Ethanol']/prod.F_mass)*100:.1f} %")
    m3.metric("Utilidad Estimada Anual", f"USD {utilidad/1e3:.1f}k")

    # Tablas de Balances
    st.divider()
    col_a, col_b = st.columns(2)
    
    with col_a:
        st.subheader("📋 Balance de Materia")
        df_materia = pd.DataFrame([
            {"Corriente": s.ID, "Flujo (kg/h)": round(s.F_mass, 2), "T (°C)": round(s.T-273.15, 1)}
            for s in sys.streams if s.F_mass > 0.1
        ])
        st.table(df_materia)

    with col_b:
        st.subheader("⚡ Balance de Energía")
        df_energia = pd.DataFrame([
            {"Equipo": u.ID, "Calor (kW)": round(sum([h.duty for h in u.heat_utilities])/3600, 2)}
            for u in sys.units
        ])
        st.table(df_energia)

    # Guardar datos para el tutor en session_state
    st.session_state.contexto_proceso = f"""
    Resultados: Producción {prod.F_mass} kg/h, Pureza {(prod.imass['Ethanol']/prod.F_mass)*100}%, 
    Utilidad {utilidad} USD. Balance Materia: {df_materia.to_dict()}. Balance Energía: {df_energia.to_dict()}.
    """

# =================================================================
# 5. VENTANA DE CONTEXTO / TUTOR IA
# =================================================================
if tutor_ia:
    st.divider()
    st.subheader("💬 Consultoría Técnica con Tutor IA")
    
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    # Mostrar historial
    for message in st.session_state.chat_history:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # Entrada de lenguaje natural
    if prompt := st.chat_input("¿Por qué la utilidad es baja? o ¿Cómo mejorar la pureza?"):
        if "GEMINI_API_KEY" not in st.secrets:
            st.error("Por favor configura la clave 'GEMINI_API_KEY' en los Secrets.")
        else:
            st.session_state.chat_history.append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.markdown(prompt)

            # Generar respuesta de IA
            genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
            model = genai.GenerativeModel('gemini-1.5-flash')
            
            contexto = st.session_state.get("contexto_proceso", "No hay datos de simulación aún.")
            full_prompt = f"Contexto del proceso: {contexto}. Usuario pregunta: {prompt}. Responde como un experto en Bioingeniería de forma concisa."
            
            with st.chat_message("assistant"):
                response = model.generate_content(full_prompt)
                st.markdown(response.text)
                st.session_state.chat_history.append({"role": "assistant", "content": response.text})

elif not btn_simular:
    st.info("Configura los parámetros en el panel izquierdo y presiona 'Ejecutar Planta' para ver los balances.")
