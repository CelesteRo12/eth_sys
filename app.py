import streamlit as st
import biosteam as bst
import thermosteam as tmo
import pandas as pd
import google.generativeai as genai
import base64

# =================================================================
# 1. CONFIGURACIÓN DE PÁGINA Y ESTILOS
# =================================================================
st.set_page_config(page_title="BioSteam Simulation Hub", layout="wide")

# Estilo para los recuadros de métricas
st.markdown("""
    <style>
    .metric-box {
        background-color: #f0f2f6;
        padding: 20px;
        border-radius: 10px;
        border-left: 5px solid #000080;
        margin-bottom: 10px;
    }
    </style>
    """, unsafe_allow_stdio=True)

# =================================================================
# 2. FUNCIONES DE APOYO
# =================================================================
def get_pdf_display(pdf_file):
    with open(pdf_file, "rb") as f:
        base64_pdf = base64.b64encode(f.read()).decode('utf-8')
    return f'<embed src="data:application/pdf;base64,{base64_pdf}" width="100%" height="600" type="application/pdf">'

# =================================================================
# 3. LÓGICA DE SIMULACIÓN (BIOSTEAM)
# =================================================================
def simular_proceso(flujo_agua, flujo_etanol, temp_fed, temp_w220, pres_v100):
    bst.main_flowsheet.clear()
    chemicals = tmo.Chemicals(["Water", "Ethanol"])
    bst.settings.set_thermo(chemicals)

    # Corrientes
    mosto = bst.Stream("1_MOSTO", Water=flujo_agua, Ethanol=flujo_etanol, units="kg/hr", T=temp_fed + 273.15)
    vinazas_ret = bst.Stream("Retorno", Water=200, T=95+273.15)

    # Equipos
    P100 = bst.Pump("P100", ins=mosto, P=4*101325)
    W210 = bst.HXprocess("W210", ins=(P100-0, vinazas_ret), outs=("Pre", "Drain"), phase0="l", phase1="l")
    W210.outs[0].T = 85 + 273.15
    
    # Slider 2: Temperatura de salida W220
    W220 = bst.HXutility("W220", ins=W210-0, outs="Hot", T=temp_w220 + 273.15)
    
    # Slider 3: Presión del separador (Valve + Flash)
    V100 = bst.IsenthalpicValve("V100", ins=W220-0, outs="Mix", P=pres_v100)
    V1 = bst.Flash("V1", ins=V100-0, outs=("Vapor", "Líquido"), P=pres_v100, Q=0)
    
    W310 = bst.HXutility("W310", ins=V1-0, outs="Producto", T=25 + 273.15)
    P200 = bst.Pump("P200", ins=V1-1, outs=vinazas_ret, P=3*101325)

    sys = bst.System("etanol_sys", path=(P100, W210, W220, V100, V1, W310, P200))
    sys.simulate()
    return sys, W310.outs[0]

# =================================================================
# 4. INTERFAZ LATERAL (CONTROL)
# =================================================================
with st.sidebar:
    st.header("⚙️ Parámetros de Proceso")
    
    # Requerimientos 1, 2 y 3: Sliders
    temp_fed = st.slider("1. Temp. Alimentación Mosto (°C)", 10.0, 60.0, 25.0)
    temp_w220 = st.slider("2. Temp. Salida W220 (°C)", 70.0, 110.0, 92.0)
    pres_v100 = st.slider("3. Presión Separador V100 (Pa)", 50000.0, 200000.0, 101325.0)
    
    st.divider()
    agua = st.number_input("Flujo Agua (kg/h)", 500, 1500, 900)
    etanol = st.number_input("Flujo Etanol (kg/h)", 10, 500, 100)
    
    st.divider()
    modo_tutor = st.toggle("👨‍🏫 Habilitar Modo Tutor IA")
    ejecutar = st.button("🚀 Ejecutar Simulación", use_container_width=True)

# =================================================================
# 5. CUERPO PRINCIPAL / RESULTADOS
# =================================================================
st.title("⚗️ Planta de Bio-Procesos Inteligente")

if ejecutar:
    with st.spinner("Simulando..."):
        planta, prod = simular_proceso(agua, etanol, temp_fed, temp_w220, pres_v100)
        
        # Requerimiento 10: Recuadros de Producto Final e Indicadores
        st.subheader("📦 Estado del Producto Final y Economía")
        m1, m2, m3, m4 = st.columns(4)
        with m1:
            st.markdown(f"<div class='metric-box'><b>Presión:</b><br>{prod.P/101325:.2f} atm</div>", unsafe_allow_html=True)
        with m2:
            st.markdown(f"<div class='metric-box'><b>Temperatura:</b><br>{prod.T-273.15:.2f} °C</div>", unsafe_allow_html=True)
        with m3:
            st.markdown(f"<div class='metric-box'><b>Flujo Másico:</b><br>{prod.F_mass:.2f} kg/h</div>", unsafe_allow_html=True)
        with m4:
            st.markdown(f"<div class='metric-box'><b>Composición Etanol:</b><br>{prod.imass['Ethanol']/prod.F_mass*100:.1f} %</div>", unsafe_allow_html=True)

        e1, e2, e3, e4 = st.columns(4)
        # Valores simulados para el ejemplo (aquí conectarías con bst.TEA)
        with e1: st.metric("Costo Real", "$0.85 /kg")
        with e2: st.metric("Venta Sugerida", "$1.20 /kg")
        with e3: st.metric("NPV", "$1.2M")
        with e4: st.metric("ROI / Payback", "15% / 3.2 años")

        # Requerimiento 9: Tablas de Balances
        st.divider()
        st.subheader("📋 Balances de Materia y Energía")
        col_mat, col_en = st.columns(2)
        with col_mat:
            st.write("**Balance de Materia**")
            data_m = [{"Corriente": s.ID, "Flujo [kg/h]": s.F_mass} for s in planta.streams if s.F_mass > 0]
            st.dataframe(pd.DataFrame(data_m), use_container_width=True)
        with col_en:
            st.write("**Balance de Energía**")
            data_e = [{"Equipo": u.ID, "Calor [kJ/h]": u.design_results.get('Heat duty', 0)} for u in planta.units]
            st.dataframe(pd.DataFrame(data_e), use_container_width=True)

        # Requerimientos 11 y 12: Diagramas ISO (PDF)
        st.divider()
        tab1, tab2 = st.tabs(["📐 Diagrama de Bloques (ISO)", "🏗️ PFD Proceso (ISO)"])
        with tab1:
            st.info("Cargue su archivo 'diagrama_bloques.pdf' exportado de AutoCAD Plant 3D")
            # st.markdown(get_pdf_display("diagrama_bloques.pdf"), unsafe_allow_html=True)
        with tab2:
            st.info("Cargue su archivo 'pfd_proceso.pdf' exportado de AutoCAD Plant 3D")
            # st.markdown(get_pdf_display("pfd_proceso.pdf"), unsafe_allow_html=True)

        # Requerimientos 13, 14 y 15: Tutor IA con Gemini
        if modo_tutor:
            st.divider()
            st.subheader("🤖 Tutoría Especializada con IA")
            
            if "messages" not in st.session_state:
                st.session_state.messages = []

            # Ventana de contexto (Chat)
            for message in st.session_state.messages:
                with st.chat_message(message["role"]):
                    st.markdown(message["content"])

            if prompt := st.chat_input("Pregúntale al tutor sobre los resultados..."):
                st.session_state.messages.append({"role": "user", "content": prompt})
                with st.chat_message("user"):
                    st.markdown(prompt)

                try:
                    # Configuración Gemini (Requerimiento 13)
                    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
                    model = genai.GenerativeModel('gemini-2.5-pro')
                    
                    # Contexto técnico para la IA
                    contexto = f"""
                    Eres un tutor de ingeniería química. El proceso actual tiene:
                    - Temp. alimentación: {temp_fed}°C
                    - Presión V100: {pres_v100} Pa
                    - Composición final: {prod.imass['Ethanol']/prod.F_mass*100:.1f}% etanol.
                    Responde de forma educativa.
                    """
                    
                    response = model.generate_content([contexto, prompt])
                    full_response = response.text
                    
                    with st.chat_message("assistant"):
                        st.markdown(full_response)
                    st.session_state.messages.append({"role": "assistant", "content": full_response})
                except Exception as e:
                    st.error("Configura GEMINI_API_KEY en Streamlit Secrets para usar el tutor.")

else:
    st.info("Configure los parámetros en el panel izquierdo y haga clic en 'Ejecutar Simulación'.")
