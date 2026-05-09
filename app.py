import streamlit as st
import pandas as pd
import numpy as np
import google.generativeai as genai
import biosteam as bst
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
# LÓGICA DE SIMULACIÓN Y TEA
# =================================================================
def ejecutar_modelo_completo(params):
    # Limpieza de flowsheet para evitar duplicidad de IDs en cada ejecución
    bst.main_flowsheet.clear()
    
    # Configuración Termodinámica
    chems = Chemicals(['Water', 'Ethanol'])
    settings.set_thermo(chems)
    
    # Precios de servicios
    settings.electricity_price = params['p_luz']
    
    # Corrientes
    mosto = Stream('mosto', Water=900, Ethanol=100, units='kg/hr', 
                   T=params['t_mosto'] + 273.15, price=params['p_mosto'])
    
    # Equipos
    P100 = bst.Pump('P100', ins=mosto, P=4*101325)
    W220 = bst.HXutility('W220', ins=P100-0, T=params['t_w220'] + 273.15)
    V100 = bst.Flash('V100', ins=W220-0, outs=('vapor_prod', 'liquido_residuo'), 
                     P=params['p_v100'], Q=0)
    
    # Sistema
    sys = bst.System('sys_etanol', path=(P100, W220, V100))
    sys.simulate()
    
    # Precio de venta para ingresos anuales
    V100.outs[0].price = params['p_etanol']
    
    # Configuración TEA Profesional
    tea = bst.TEA(
        system=sys,
        IRR=0.15,
        duration=(2026, 2046),
        depreciation='MACRS7',
        construction_schedule=(0.5, 0.5),
        startup_months=3,
        operating_days=330,
        income_tax=0.30,
        lang_factor=4.0,
        startup_FOCfrac=0.5,
        startup_VOCfrac=0.5,
        startup_salesfrac=0.5,
        WC_over_FCI=0.05,
        finance_interest=0.0,
        finance_years=0,
        finance_fraction=0.0
    )
    
    return sys, tea, V100.outs[0]

# =================================================================
# INTERFAZ DE USUARIO
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

if ejecutar:
    params = {
        't_mosto': t_mosto, 't_w220': t_w220, 'p_v100': p_v100,
        'p_luz': p_luz, 'p_mosto': p_mosto, 'p_etanol': p_etanol
    }
    
    try:
        sys, tea, prod = ejecutar_modelo_completo(params)
        
        st.subheader("📦 Estado del Producto Final")
        c1, c2, c3, c4 = st.columns(4)
        with c1: st.markdown(f'<div class="metric-card"><div class="metric-label">Presión</div><div class="metric-value">{prod.P/101325:.2f} atm</div></div>', unsafe_allow_html=True)
        with c2: st.markdown(f'<div class="metric-card"><div class="metric-label">Temperatura</div><div class="metric-value">{prod.T-273.15:.1f} °C</div></div>', unsafe_allow_html=True)
        with c3: st.markdown(f'<div class="metric-card"><div class="metric-label">Flujo</div><div class="metric-value">{prod.F_mass:.1f} kg/h</div></div>', unsafe_allow_html=True)
        with c4: st.markdown(f'<div class="metric-card"><div class="metric-label">% Etanol</div><div class="metric-value">{prod.imass["Ethanol"]/prod.F_mass*100:.1f}%</div></div>', unsafe_allow_html=True)

        st.subheader("📊 Análisis Financiero")
        e1, e2, e3, e4 = st.columns(4)
        with e1: st.metric("NPV (VPN)", f"${tea.NPV/1e6:.2f} M")
        with e2: 
            roi = (tea.sales - tea.AOC) / tea.TCI * 100 if tea.TCI != 0 else 0
            st.metric("ROI", f"{roi:.1f}%")
        with e3:
            payback = tea.TCI / (tea.sales - tea.AOC) if (tea.sales - tea.AOC) > 0 else 0
            st.metric("Payback", f"{payback:.1f} años")
        with e4:
            st.metric("MPSP", f"${tea.solve_price(prod):.2f}/kg")

        t1, t2 = st.tabs(["📝 Datos Técnicos", "🤖 Tutor IA"])
        with t1:
            st.dataframe(sys.get_stream_table())
        
        with t2:
            if ia_tutor and "GEMINI_API_KEY" in st.secrets:
                genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
                model = genai.GenerativeModel('gemini-2.5-pro')
                contexto = f"Simulación Etanol: NPV={tea.NPV/1e6:.2f}M, ROI={roi:.1f}%."
                res = model.generate_content(f"{contexto} Explica brevemente la viabilidad.")
                st.info(res.text)
    except Exception as e:
        st.error(f"Error: {e}")
