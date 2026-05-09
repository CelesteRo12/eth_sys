import streamlit as st
import pandas as pd
import numpy as np
import google.generativeai as genai
import biosteam as bst
from thermosteam import Chemicals, Stream, settings

# =================================================================
# CONFIGURACIÓN Y ESTILOS
# =================================================================
st.set_page_config(page_title="BioSTEAM Process Simulation", layout="wide")

st.markdown("""
    <style>
    .metric-card {
        background-color: #ffffff;
        padding: 20px;
        border-radius: 15px;
        border-left: 5px solid #3b82f6;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
        margin-bottom: 10px;
    }
    .metric-value { font-size: 24px; font-weight: bold; color: #1e293b; }
    .metric-label { font-size: 14px; color: #64748b; text-transform: uppercase; }
    </style>
""", unsafe_allow_html=True)

# =================================================================
# LÓGICA DE SIMULACIÓN TÉCNICA
# =================================================================
def ejecutar_simulacion_tecnica(params):
    # Limpiar flowsheet para evitar errores de nombres duplicados
    bst.main_flowsheet.clear()
    
    # 1. Configuración Termodinámica
    chems = Chemicals(['Water', 'Ethanol'])
    settings.set_thermo(chems)
    
    # 2. Creación de Corrientes
    mosto = Stream('mosto', Water=900, Ethanol=100, units='kg/hr', 
                    T=params['t_mosto'] + 273.15)
    
    # 3. Diseño de Equipos
    P100 = bst.Pump('P100', ins=mosto, P=4*101325)
    
    # Intercambiador de calor
    W220 = bst.HXutility('W220', ins=P100-0, T=params['t_w220'] + 273.15)
    
    # Separador Flash
    V100 = bst.Flash('V100', ins=W220-0, outs=('vapor_prod', 'liquido_residuo'), 
                     P=params['p_v100'], Q=0)
    
    # Crear y Simular Sistema
    sys = bst.System('sys_proceso', path=(P100, W220, V100))
    sys.simulate()
    
    return sys, V100.outs[0]

# =================================================================
# INTERFAZ DE USUARIO (OPERACIÓN)
# =================================================================
with st.sidebar:
    st.header("🎮 Parámetros Operativos")
    
    with st.expander("🌡️ Condiciones de Proceso", expanded=True):
        t_mosto = st.slider("Temp. Alimentación Mosto (°C)", 10, 60, 25)
        t_w220 = st.slider("Temp. Salida Intercambiador (°C)", 70, 100, 92)
        p_v100 = st.slider("Presión del Flash (Pa)", 50000, 150000, 101325)
        
    st.divider()
    ia_tutor = st.toggle("Habilitar Asistente Técnico IA", value=False)
    simular = st.button("🚀 Ejecutar Simulación", use_container_width=True)

# =================================================================
# DESPLIEGUE DE RESULTADOS
# =================================================================
if simular:
    params = {
        't_mosto': t_mosto, 
        't_w220': t_w220, 
        'p_v100': p_v100
    }
    
    sys, prod = ejecutar_simulacion_tecnica(params)
    
    # 1. Indicadores de Corriente de Salida
    st.subheader("🎯 Resultados de la Corriente de Vapor")
    c1, c2, c3, c4 = st.columns(4)
    with c1: 
        st.markdown(f'<div class="metric-card"><div class="metric-label">Presión</div><div class="metric-value">{prod.P/101325:.2f} atm</div></div>', unsafe_allow_html=True)
    with c2: 
        st.markdown(f'<div class="metric-card"><div class="metric-label">Temperatura</div><div class="metric-value">{prod.T-273.15:.1f} °C</div></div>', unsafe_allow_html=True)
    with c3: 
        st.markdown(f'<div class="metric-card"><div class="metric-label">Flujo Másico</div><div class="metric-value">{prod.F_mass:.1f} kg/h</div></div>', unsafe_allow_html=True)
    with c4: 
        pureza = (prod.imass["Ethanol"]/prod.F_mass*100) if prod.F_mass > 0 else 0
        st.markdown(f'<div class="metric-card"><div class="metric-label">Pureza Etanol</div><div class="metric-value">{pureza:.1f} %</div></div>', unsafe_allow_html=True)

    # 2. Análisis y Visualización
    tab1, tab2, tab3 = st.tabs(["📊 Balances de Masa", "📐 Diagramas", "🤖 Asistente IA"])
    
    with tab1:
        st.write("**Tabla de Balance de Materia Completa**")
        # --- SOLUCIÓN AL ERROR DE ATRIBUTO ---
        # Intentamos obtener la tabla de corrientes de la forma más compatible posible
        try:
            # Opción A: Usar la utilidad de reporte de BioSTEAM
            df_streams = bst.report.generate_stream_table(sys.streams)
        except AttributeError:
            # Opción B: Si la anterior falla, construirla manualmente con pandas (Universal)
            data = []
            for s in sys.streams:
                row = {
                    "Stream": s.ID,
                    "T [K]": f"{s.T:.2f}",
                    "P [Pa]": f"{s.P:.0f}",
                    "Flow [kg/h]": f"{s.F_mass:.2f}"
                }
                # Añadir flujos por componente
                for name, val in s.imass.items():
                    row[f"{name} [kg/h]"] = f"{val:.2f}"
                data.append(row)
            df_streams = pd.DataFrame(data)
        
        st.dataframe(df_streams)
    
    with tab2:
        st.info("Visualización del Diagrama de Flujo de Proceso (PFD)")
        # En lugar de buscar un archivo externo, BioSTEAM puede generar el diagrama
        try:
            # Esto intentará mostrar el diagrama generado por BioSTEAM si Graphviz está instalado
            st.image("gemini-svg.svg", caption="Diagrama de Proceso", use_container_width=True)
        except:
            st.warning("Diagrama visual no disponible. Verifique el archivo 'gemini-svg.svg'.")

    with tab3:
        if ia_tutor:
            if "GEMINI_API_KEY" in st.secrets:
                genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
                model = genai.GenerativeModel('gemini-1.5-flash')
                
                chat_input = st.text_input("Haz una consulta técnica sobre el balance:")
                if chat_input:
                    contexto = (f"El sistema opera a {prod.P} Pa. La pureza de etanol obtenida es {pureza:.2f}% "
                                f"con un flujo total de {prod.F_mass} kg/h. ")
                    response = model.generate_content(contexto + chat_input)
                    st.chat_message("assistant").write(response.text)
            else:
                st.error("Configura 'GEMINI_API_KEY' en Streamlit Secrets.")
