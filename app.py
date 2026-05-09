import streamlit as st
import pandas as pd
import numpy as np
import google.generativeai as genai
import biosteam as bst
from thermosteam import Chemicals, Stream, settings

# =================================================================
# CONFIGURACIÓN Y ESTILOS
# =================================================================
st.set_page_config(page_title="BioSTEAM Process Designer", layout="wide")

st.markdown("""
    <style>
    .metric-card {
        background-color: #ffffff;
        padding: 20px;
        border-radius: 15px;
        border-left: 5px solid #1e40af;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
        margin-bottom: 10px;
    }
    .metric-value { font-size: 22px; font-weight: bold; color: #1e293b; }
    .metric-label { font-size: 13px; color: #64748b; text-transform: uppercase; }
    </style>
""", unsafe_allow_html=True)

# =================================================================
# LÓGICA DE SIMULACIÓN (SEGÚN DIAGRAMA ADJUNTO)
# =================================================================
def ejecutar_modelo_pfd(params):
    # 1. Configuración Termodinámica
    bst.main_flowsheet.clear()
    chems = Chemicals(['Water', 'Ethanol'])
    settings.set_thermo(chems)
    
    # 2. Corriente de Entrada
    feed = Stream('feed', Water=900, Ethanol=100, units='kg/hr', 
                  T=params['t_feed'] + 273.15, P=3*101325)
    
    # 3. Diseño de Equipos según PFD
    # Intercambiador de calor (Coraza y tubos en el diagrama)
    H1 = bst.HXutility('H1', ins=feed, T=params['t_h1'] + 273.15)
    
    # Válvula de expansión (Reducción de presión antes del Flash)
    V1 = bst.Valve('V1', ins=H1-0, P=params['p_flash'])
    
    # Separador Flash
    F1 = bst.Flash('F1', ins=V1-0, outs=('vapor_raw', 'liquid_raw'), 
                   P=params['p_flash'], Q=0)
    
    # Válvula en la salida de vapor (según círculo X a la derecha del flash)
    V2 = bst.Valve('V2', ins=F1-0, P=101325) 
    
    # Bomba en la salida de líquido (según icono inferior en el diagrama)
    P1 = bst.Pump('P1', ins=F1-1, P=2*101325)
    
    # Crear Sistema
    sys = bst.System('sys_pfd', path=(H1, V1, F1, V2, P1))
    sys.simulate()
    
    return sys, V2.outs[0], P1.outs[0]

# =================================================================
# INTERFAZ DE USUARIO
# =================================================================
with st.sidebar:
    st.header("⚙️ Parámetros del PFD")
    
    with st.expander("🌡️ Condiciones Térmicas", expanded=True):
        t_feed = st.slider("Temp. Entrada (°C)", 10, 50, 25)
        t_h1 = st.slider("Temp. Salida Intercambiador (°C)", 60, 120, 95)
        
    with st.expander("☁️ Separación Flash", expanded=True):
        p_flash = st.slider("Presión de Operación (Pa)", 10000, 200000, 101325)
        
    st.divider()
    ia_tutor = st.toggle("Activar Tutor de Ingeniería", value=False)
    simular = st.button("🚀 Simular Proceso", use_container_width=True)

# =================================================================
# RESULTADOS
# =================================================================
if simular:
    params = {'t_feed': t_feed, 't_h1': t_h1, 'p_flash': p_flash}
    sys, vapor, liquido = ejecutar_modelo_pfd(params)
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("💨 Salida de Vapor (V2)")
        st.markdown(f'''<div class="metric-card">
            <div class="metric-label">Flujo Vapor</div><div class="metric-value">{vapor.F_mass:.2f} kg/h</div>
            <div class="metric-label">Pureza Etanol</div><div class="metric-value">{vapor.imass["Ethanol"]/vapor.F_mass*100 if vapor.F_mass>0 else 0:.1f} %</div>
        </div>''', unsafe_allow_html=True)

    with col2:
        st.subheader("💧 Salida de Líquido (P1)")
        st.markdown(f'''<div class="metric-card">
            <div class="metric-label">Flujo Líquido</div><div class="metric-value">{liquido.F_mass:.2f} kg/h</div>
            <div class="metric-label">Temperatura</div><div class="metric-value">{liquido.T-273.15:.1f} °C</div>
        </div>''', unsafe_allow_html=True)

    tab1, tab2, tab3 = st.tabs(["📝 Tabla de Corrientes", "🖼️ PFD Correspondiente", "🤖 Consulta Técnica"])
    
    with tab1:
        st.dataframe(sys.get_stream_table())
    
    with tab2:
        st.image("https://raw.githubusercontent.com/user-attachments/assets/tu-enlace-aqui", 
                 caption="Diagrama de flujo implementado basado en tu imagen.", use_column_width=True)
        st.info("El sistema ahora incluye: Intercambiador -> Válvula -> Flash -> Válvula(V) / Bomba(L)")

    with tab3:
        if ia_tutor:
            if "GEMINI_API_KEY" in st.secrets:
                genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
                model = genai.GenerativeModel('gemini-2.5-pro')
                query = st.text_input("Pregunta sobre la eficiencia de la separación:")
                if query:
                    contexto = f"Simulación de un flash a {p_flash} Pa. El vapor sale con {vapor.F_mass} kg/h."
                    response = model.generate_content(contexto + query)
                    st.chat_message("assistant").write(response.text)
            else:
                st.warning("Configura la API Key en los secretos de Streamlit.")
