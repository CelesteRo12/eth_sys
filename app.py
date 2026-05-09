import streamlit as st
import pandas as pd
import numpy as np
import google.generativeai as genai
import biosteam as bst
from biosteam.evaluation import TEA
from thermosteam import Chemicals, Stream, settings

# =================================================================
# CONFIGURACIÓN Y ESTILOS
# =================================================================
st.set_page_config(page_title="BioSTEAM Simulation Hub", layout="wide")

# Estilo personalizado para recuadros de resultados
st.markdown("""
    <style>
    .metric-card {
        background-color: #ffffff;
        padding: 20px;
        border-radius: 15px;
        border-left: 5px solid #10b981;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
        margin-bottom: 10px;
    }
    .metric-value { font-size: 24px; font-weight: bold; color: #0f172a; }
    .metric-label { font-size: 14px; color: #64748b; text-transform: uppercase; }
    </style>
""", unsafe_allow_html=True)

# =================================================================
# LÓGICA DE SIMULACIÓN Y ECONOMÍA (TEA)
# =================================================================
def ejecutar_modelo_completo(params):
    # 1. Configuración Termodinámica
    bst.main_flowsheet.clear()
    chems = Chemicals(['Water', 'Ethanol'])
    settings.set_thermo(chems)
    
    # 2. Definición de Precios (Basado en Sliders)
    # BioSTEAM usa USD/kg por defecto
    settings.electricity_price = params['p_luz']
    price_water = params['p_agua']
    price_etanol = params['p_etanol']
    price_mosto = params['p_mosto']
    
    # 3. Creación de Corrientes
    mosto = Stream('mosto', Water=900, Ethanol=100, units='kg/hr', 
                   T=params['t_mosto'] + 273.15, price=price_mosto)
    etanol_prod = Stream('etanol_producto', Water=1, Ethanol=1, units='kg/hr', price=price_etanol)
    
    # 4. Diseño de Equipos
    P100 = bst.Pump('P100', ins=mosto, P=4*101325)
    
    # Simulación del intercambiador W220 (Ajuste de temperatura solicitado)
    W220 = bst.HXutility('W220', ins=P100-0, T=params['t_w220'] + 273.15)
    
    # Separador V100 (Ajuste de presión solicitado)
    V100 = bst.Flash('V100', ins=W220-0, outs=('vapor_prod', 'liquido_residuo'), 
                     P=params['p_v100'], Q=0)
    
    # 5. Análisis Económico (TEA) - Basado en tu Guía HTML
    class BioTEA(bst.TEA):
        """Clase TEA personalizada basada en los parámetros del curso"""
        def __init__(self, system, IRR, duration, operating_days, income_tax, 
                     lang_factor, startup_FOCfrac, startup_VOCfrac, 
                     startup_salesfrac, WC_over_FCI):
            super().__init__(system, IRR, duration, operating_days, income_tax, 
                             lang_factor, startup_FOCfrac, startup_VOCfrac, 
                             startup_salesfrac, WC_over_FCI)

    # Crear Sistema
    sys = bst.System('sys_etanol', path=(P100, W220, V100))
    sys.simulate()
    
    # Instanciar TEA con parámetros estándar (de tu HTML)
    tea = BioTEA(sys, IRR=0.15, duration=(2026, 2046), operating_days=330,
                income_tax=0.30, lang_factor=4.0, startup_FOCfrac=0.5,
                startup_VOCfrac=0.5, startup_salesfrac=0.5, WC_over_FCI=0.05)
    
    return sys, tea, V100.outs[0]

# =================================================================
# INTERFAZ DE USUARIO (SLIDERS)
# =================================================================
with st.sidebar:
    st.header("🎮 Parámetros de Control")
    
    with st.expander("🌡️ Temperaturas y Presión", expanded=True):
        t_mosto = st.slider("Temp. Alimentación Mosto (°C)", 10, 60, 25)
        t_w220 = st.slider("Temp. Salida W220 (°C)", 70, 100, 92)
        p_v100 = st.slider("Presión V100 (Pa)", 50000, 150000, 101325)
        
    with st.expander("💰 Precios de Mercado", expanded=True):
        p_luz = st.slider("Precio Electricidad (USD/kWh)", 0.05, 0.30, 0.12)
        p_vapor = st.slider("Precio Vapor (USD/kg)", 0.01, 0.10, 0.02)
        p_agua = st.slider("Precio Agua (USD/kg)", 0.0001, 0.005, 0.0005)
        p_mosto = st.slider("Costo Mosto (USD/kg)", 0.05, 0.50, 0.10)
        p_etanol = st.slider("Precio Etanol (USD/kg)", 0.50, 2.50, 1.20)

    st.divider()
    ia_tutor = st.toggle("Habilitar Modo Tutor IA", value=False)
    simular = st.button("🚀 Ejecutar Simulación", use_container_width=True)

# =================================================================
# DESPLIEGUE DE RESULTADOS
# =================================================================
if simular:
    params = {
        't_mosto': t_mosto, 't_w220': t_w220, 'p_v100': p_v100,
        'p_luz': p_luz, 'p_vapor': p_vapor, 'p_agua': p_agua,
        'p_mosto': p_mosto, 'p_etanol': p_etanol
    }
    
    sys, tea, prod = ejecutar_modelo_completo(params)
    
    # 1. Indicadores de Producto Final
    st.subheader("🎯 Corriente de Producto (Vapor)")
    c1, c2, c3, c4 = st.columns(4)
    with c1: st.markdown(f'<div class="metric-card"><div class="metric-label">Presión</div><div class="metric-value">{prod.P/101325:.2f} atm</div></div>', unsafe_allow_html=True)
    with c2: st.markdown(f'<div class="metric-card"><div class="metric-label">Temperatura</div><div class="metric-value">{prod.T-273.15:.1f} °C</div></div>', unsafe_allow_html=True)
    with c3: st.markdown(f'<div class="metric-card"><div class="metric-label">Flujo Másico</div><div class="metric-value">{prod.F_mass:.1f} kg/h</div></div>', unsafe_allow_html=True)
    with c4: st.markdown(f'<div class="metric-card"><div class="metric-label">Comp. Etanol</div><div class="metric-value">{prod.imass["Ethanol"]/prod.F_mass*100:.1f} %</div></div>', unsafe_allow_html=True)

    # 2. Indicadores Económicos (NPV, ROI, Payback)
    st.subheader("💹 Indicadores Financieros (TEA)")
    e1, e2, e3, e4 = st.columns(4)
    with e1: st.metric("NPV (Valor Presente Neto)", f"${tea.NPV/1e6:.2f} M")
    with e2: 
        # Cálculo manual de ROI simple para el ejemplo
        roi = (tea.sales - tea.AOC) / tea.TCI * 100
        st.metric("ROI (Retorno Inversión)", f"{roi:.2f} %")
    with e3: 
        payback = tea.TCI / (tea.sales - tea.AOC) if (tea.sales - tea.AOC) > 0 else np.inf
        st.metric("Payback (Recuperación)", f"{payback:.1f} años")
    with e4:
        mpsp = tea.solve_price(prod)
        st.metric("MPSP (Costo Sugerido)", f"${mpsp:.2f}/kg")

    # 3. Balances y Diagramas
    tab1, tab2, tab3 = st.tabs(["📊 Balances", "📐 Diagramas ISO", "🤖 Tutor IA"])
    
    with tab1:
        st.write("**Balance de Materia por Corriente**")
        st.dataframe(sys.get_stream_table())
    
    with tab2:
        st.info("Aquí se muestran los diagramas cargados desde AutoCAD Plant 3D (SVG/PDF)")
        # Simulación de carga de archivos adjuntos
        st.image("gemini-svg.svg", caption="Diagrama de Flujo de Proceso (Estándar ISO)", use_column_width=True)
        st.warning("Nota: Para descarga en PDF, use el botón de imprimir de su navegador sobre este elemento.")

    with tab3:
        if ia_tutor:
            # Configuración de Gemini
            if "GEMINI_API_KEY" in st.secrets:
                genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
                model = genai.GenerativeModel('gemini-2.5-pro')
                
                chat_input = st.text_input("Pregunta al Tutor IA sobre los resultados:")
                if chat_input:
                    contexto = f"El NPV es {tea.NPV}, el MPSP es {mpsp} y el flujo de etanol es {prod.imass['Ethanol']}. "
                    response = model.generate_content(contexto + chat_input)
                    st.chat_message("assistant").write(response.text)
            else:
                st.error("Por favor, configura 'GEMINI_API_KEY' en Streamlit Secrets.")
