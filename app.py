import streamlit as st
import pandas as pd
import numpy as np
import google.generativeai as genai
import biosteam as bst
from thermosteam import Chemicals, Stream, settings

# =================================================================
# CONFIGURACIÓN Y ESTILOS
# =================================================================
st.set_page_config(page_title="BioSTEAM Simulation Hub", layout="wide")

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
    bst.main_flowsheet.clear()
    chems = Chemicals(['Water', 'Ethanol'])
    settings.set_thermo(chems)
    
    # Precios de servicios y materias primas
    settings.electricity_price = params['p_luz']
    
    mosto = Stream('mosto', Water=900, Ethanol=100, units='kg/hr', 
                   T=params['t_mosto'] + 273.15, price=params['p_mosto'])
    
    # Equipos de proceso
    P100 = bst.Pump('P100', ins=mosto, P=4*101325)
    W220 = bst.HXutility('W220', ins=P100-0, T=params['t_w220'] + 273.15)
    V100 = bst.Flash('V100', ins=W220-0, outs=('vapor_prod', 'liquido_residuo'), 
                     P=params['p_v100'], Q=0)
    
    # Crear Sistema
    sys = bst.System('sys_etanol', path=(P100, W220, V100))
    sys.simulate()
    
    # =============================================================
    # SOLUCIÓN AL ERROR: Definición de argumentos obligatorios
    # =============================================================
    tea = bst.TEA(
        system=sys,
        IRR=0.15,                           # Tasa Interna de Retorno
        duration=(2026, 2046),              # Horizonte temporal
        depreciation='MACRS7',              # MÉTODO OBLIGATORIO
        construction_schedule=(0.5, 0.5),   # CRONOGRAMA OBLIGATORIO (2 años)
        startup_months=3,                   # MESES DE ARRANQUE OBLIGATORIO
        operating_days=330,                 # Tiempo efectivo anual
        income_tax=0.30,                    # Tasa impositiva
        lang_factor=4.0,                    # Estimación de inversión fija
        startup_FOCfrac=0.5,                # Fracción costos fijos en arranque
        startup_VOCfrac=0.5,                # Fracción costos variables en arranque
        startup_salesfrac=0.5,              # Fracción ventas en arranque
        WC_over_FCI=0.05,                   # Capital de trabajo
        finance_interest=0.0,               
        finance_years=0,                    
        finance_fraction=0.0                
    )
    
    return sys, tea, V100.outs[0]

# =================================================================
# INTERFAZ DE USUARIO (SLIDERS)
# =================================================================
with st.sidebar:
    st.header("⚙️ Parámetros de Proceso")
    
    # 1-3. Sliders de condiciones de operación
    t_mosto = st.slider("Temp. Alimentación Mosto (°C)", 10, 60, 25)
    t_w220 = st.slider("Temp. Salida W220 (°C)", 70, 100, 92)
    p_v100 = st.slider("Presión V100 (Pa)", 50000, 150000, 101325)
    
    st.divider()
    st.header("💰 Parámetros Económicos")
    # 4-8. Sliders de precios
    p_luz = st.slider("Precio Electricidad (USD/kWh)", 0.05, 0.30, 0.12)
    p_vapor = st.slider("Precio Vapor (USD/kg)", 0.01, 0.10, 0.02)
    p_agua = st.slider("Precio Agua (USD/kg)", 0.0001, 0.005, 0.0005)
    p_mosto = st.slider("Costo Mosto (USD/kg)", 0.05, 0.50, 0.10)
    p_etanol = st.slider("Precio Etanol (USD/kg)", 0.50, 2.50, 1.20)

    st.divider()
    ia_tutor = st.toggle("Habilitar Modo Tutor IA", value=True)
    ejecutar = st.button("🚀 Simular Proceso", use_container_width=True)

# =================================================================
# EJECUCIÓN Y RESULTADOS
# =================================================================
if ejecutar:
    params = {
        't_mosto': t_mosto, 't_w220': t_w220, 'p_v100': p_v100,
        'p_luz': p_luz, 'p_vapor': p_vapor, 'p_agua': p_agua,
        'p_mosto': p_mosto, 'p_etanol': p_etanol
    }
    
    try:
        sys, tea, prod = ejecutar_modelo_completo(params)
        prod.price = p_etanol 
        
        # 10. Recuadros de variables del producto final
        st.subheader("📦 Estado del Producto Final (Vapor)")
        c1, c2, c3, c4 = st.columns(4)
        with c1: st.markdown(f'<div class="metric-card"><div class="metric-label">Presión</div><div class="metric-value">{prod.P/101325:.2f} atm</div></div>', unsafe_allow_html=True)
        with c2: st.markdown(f'<div class="metric-card"><div class="metric-label">Temperatura</div><div class="metric-value">{prod.T-273.15:.1f} °C</div></div>', unsafe_allow_html=True)
        with c3: st.markdown(f'<div class="metric-card"><div class="metric-label">Flujo Másico</div><div class="metric-value">{prod.F_mass:.1f} kg/h</div></div>', unsafe_allow_html=True)
        with c4: st.markdown(f'<div class="metric-card"><div class="metric-label">% Etanol</div><div class="metric-value">{prod.imass["Ethanol"]/prod.F_mass*100:.1f}%</div></div>', unsafe_allow_html=True)

        # Indicadores Económicos solicitados
        st.subheader("📊 Análisis de Rentabilidad")
        e1, e2, e3, e4 = st.columns(4)
        with e1: st.metric("NPV (VPN)", f"${tea.NPV/1e6:.2f} M")
        with e2: 
            # ROI = (Ventas - Costos) / Inversión Total
            roi = (tea.sales - tea.AOC) / tea.TCI * 100
            st.metric("ROI", f"{roi:.1f}%")
        with e3:
            payback = tea.TCI / (tea.sales - tea.AOC) if (tea.sales - tea.AOC) > 0 else 99
            st.metric("Payback", f"{payback:.1f} años")
        with e4:
            st.metric("MPSP (Venta Sugerida)", f"${tea.solve_price(prod):.2f}/kg")

        # 9, 11-15. Tablas, Diagramas e IA
        t1, t2, t3 = st.tabs(["📋 Balances", "📐 Diagramas ISO", "🤖 Tutor IA"])
        
        with t1:
            st.write("**Tabla de Balances de Materia y Energía**")
            st.dataframe(sys.get_stream_table())
        
        with t2:
            st.info("Visualización de diagramas realizados bajo estándares ISO.")
            # Representación del avance del diagrama de flujo (PFD)
            st.image("gemini-svg.svg", caption="PFD - Avance de Diagrama de Flujo de Proceso", use_column_width=True)
            st.caption("Descargue el archivo original desde AutoCAD Plant 3D para obtener el formato PDF oficial.")
        
        with t3:
            # 13-15. Conexión con Gemini y Ventana de Contexto
            if ia_tutor and "GEMINI_API_KEY" in st.secrets:
                genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
                model = genai.GenerativeModel('gemini-2.5-pro')
                
                user_msg = st.text_input("Comunícate con el tutor mediante lenguaje natural:")
                if user_msg:
                    # Se envía contexto del proceso para que el tutor pueda explicar los resultados
                    contexto = f"Proceso de etanol. NPV: {tea.NPV}, ROI: {roi}%, MPSP: {tea.solve_price(prod)}. "
                    response = model.generate_content(contexto + user_msg)
                    st.chat_message("assistant").write(response.text)
            else:
                st.warning("Habilite el modo tutor y configure la API Key en los secretos de Streamlit.")

    except Exception as e:
        st.error(f"Error técnico: {e}")
