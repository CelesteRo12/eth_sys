import streamlit as st
import pandas as pd
import numpy as np
import google.generativeai as genai
import biosteam as bst
from biosteam import System
from biosteam import Stream
from biosteam import settings
from biosteam import Chemical
from biosteam import Chemicals
from biosteam import units
from biosteam import main_flowsheet
from biosteam import TEA
from biosteam import ConventionalTEA 
from thermosteam import Chemicals, Stream, settings

# =================================================================
# CONFIGURACIÓN DE LA INTERFAZ
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
# LÓGICA DE SIMULACIÓN Y TEA (CORREGIDA)
# =================================================================
def ejecutar_modelo_completo(params):
    main_flowsheet.clear()
    chems = bst.Chemicals(['Water', 'Ethanol'])
    settings.set_thermo(chems)
    
    # Precios de servicios (Utilities)
    settings.electricity_price = params['p_luz']
    
    # Corriente de entrada
    mosto = Stream('mosto', Water=900, Ethanol=100, units='kg/hr', 
                   T=params['t_mosto'] + 273.15, price=params['p_mosto'])
    
    # Diseño de Equipos
    P100 = bst.Pump('P100', ins=mosto, P=4*101325)
    W220 = bst.HXutility('W220', ins=P100-0, T=params['t_w220'] + 273.15)
    V100 = bst.Flash('V100', ins=W220-0, outs=('vapor_prod', 'liquido_residuo'), 
                     P=params['p_v100'], Q=0)
    
    # Creación y Simulación del Sistema
    sys = bst.System('sys_etanol', path=(P100, W220, V100))
    sys.simulate()
    
    # Asignación de precio al producto para cálculo de ventas
    V100.outs[0].price = params['p_etanol']
    
    # Configuración de TEA (Basada en Parámetros de Biosteam TEA Guide)
    # Se eliminó la dependencia de biosteam.evaluation.TEA
    tea = ConventionalTEA(
    system=sys,
    IRR=0.15,
    duration=(2026, 2046),
    depreciation='MACRS7',
    income_tax=0.30,
    operating_days=330,
    
    # Capital e instalación
    lang_factor=4.0,
    construction_schedule=(0.5, 0.5),
    startup_months=3,
    
    # Costos operativos
    startup_FOCfrac=0.5,
    startup_VOCfrac=0.5,
    startup_salesfrac=0.5,
    
    # Capital de trabajo
    WC_over_FCI=0.05,
    
    # Financiamiento
    finance_interest=0.0,
    finance_years=0,
    finance_fraction=0.0
)
    
    return sys, tea, V100.outs[0]

# =================================================================
# COMPONENTES DE LA BARRA LATERAL
# =================================================================
with st.sidebar:
    st.header("⚙️ Parámetros de Proceso")
    t_mosto = st.slider("Temp. Alimentación (°C)", 10, 60, 25)
    t_w220 = st.slider("Temp. Salida Intercambiador (°C)", 70, 100, 92)
    p_v100 = st.slider("Presión Flash (Pa)", 50000, 150000, 101325)
    
    st.divider()
    st.header("💰 Parámetros Económicos")
    p_luz = st.slider("Precio Electricidad (USD/kWh)", 0.05, 0.30, 0.12)
    p_mosto = st.slider("Costo Mosto (USD/kg)", 0.05, 0.50, 0.10)
    p_etanol = st.slider("Precio Venta Etanol (USD/kg)", 0.50, 2.50, 1.20)

    st.divider()
    ia_tutor = st.toggle("Habilitar Modo Tutor IA", value=True)
    ejecutar = st.button("🚀 Iniciar Simulación", use_container_width=True)

# =================================================================
# RENDERIZADO DE RESULTADOS
# =================================================================
if ejecutar:
    params = {
        't_mosto': t_mosto, 't_w220': t_w220, 'p_v100': p_v100,
        'p_luz': p_luz, 'p_mosto': p_mosto, 'p_etanol': p_etanol
    }
    
    try:
        sys, tea, prod = ejecutar_modelo_completo(params)
        
        st.subheader("📦 Estado del Producto Final (Vapor)")
        c1, c2, c3, c4 = st.columns(4)
        with c1: st.markdown(f'<div class="metric-card"><div class="metric-label">Presión</div><div class="metric-value">{prod.P/101325:.2f} atm</div></div>', unsafe_allow_html=True)
        with c2: st.markdown(f'<div class="metric-card"><div class="metric-label">Temperatura</div><div class="metric-value">{prod.T-273.15:.1f} °C</div></div>', unsafe_allow_html=True)
        with c3: st.markdown(f'<div class="metric-card"><div class="metric-label">Flujo Másico</div><div class="metric-value">{prod.F_mass:.1f} kg/h</div></div>', unsafe_allow_html=True)
        with c4: st.markdown(f'<div class="metric-card"><div class="metric-label">% Etanol</div><div class="metric-value">{prod.imass["Ethanol"]/prod.F_mass*100:.1f}%</div></div>', unsafe_allow_html=True)

        st.subheader("📊 Análisis de Rentabilidad")
        e1, e2, e3, e4 = st.columns(4)
        
        # Corrección de accesos a atributos para evitar error '_FOC'
        with e1: st.metric("NPV (VPN)", f"${tea.NPV/1e6:.2f} M")
        with e2: 
            # ROI basado en Ventas Anuales e Inversión Total (TCI)
            roi_val = (tea.sales - tea.AOC) / tea.TCI * 100 if tea.TCI != 0 else 0
            st.metric("ROI", f"{roi_val:.1f}%")
        with e3:
            # Payback calculado mediante flujo de caja operativo
            flujo_anual = tea.sales - tea.AOC
            payback = tea.TCI / flujo_anual if flujo_anual > 0 else 0
            st.metric("Payback", f"{payback:.1f} años")
        with e4:
            # Precio Mínimo de Venta Sugerido (MPSP)
            st.metric("MPSP", f"${tea.solve_price(prod):.2f}/kg")

        t1, t2 = st.tabs(["📝 Balances", "🤖 Tutor IA"])
        with t1:
            st.dataframe(sys.get_stream_table())
        
        with t2:
            if ia_tutor and "GEMINI_API_KEY" in st.secrets:
                genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
                model = genai.GenerativeModel('gemini-2.5-pro')
                contexto = f"Ingeniería Química: El NPV es {tea.NPV/1e6:.2f}M y el ROI es {roi_val:.1f}%."
                response = model.generate_content(f"{contexto} Explica brevemente si el proyecto es viable.")
                st.info(response.text)

    except Exception as e:
        st.error(f"Error en la simulación: {e}")
