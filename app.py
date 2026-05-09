import streamlit as st
import pandas as pd
import numpy as np
import google.generativeai as genai
import biosteam as bst
from thermosteam import Chemicals, Stream, settings

# =================================================================
# CONFIGURACIÓN DE PÁGINA E INTERFAZ
# =================================================================
st.set_page_config(page_title="BioSTEAM Hub Pro", layout="wide")

st.markdown("""
    <style>
    .metric-card {
        background-color: #ffffff; padding: 15px; border-radius: 12px;
        border-left: 5px solid #059669; box-shadow: 0 2px 4px rgba(0,0,0,0.05);
        margin-bottom: 10px;
    }
    .metric-value { font-size: 20px; font-weight: bold; color: #1e293b; }
    .metric-label { font-size: 12px; color: #64748b; text-transform: uppercase; }
    </style>
""", unsafe_allow_html=True)

# =================================================================
# LÓGICA DE PROCESO Y TEA
# =================================================================
def ejecutar_simulacion(p):
    bst.main_flowsheet.clear()
    
    # Termodinámica básica
    chems = Chemicals(['Water', 'Ethanol'])
    settings.set_thermo(chems)
    
    # Servicios y Precios
    settings.electricity_price = p['p_luz']
    
    # Definición de Corrientes (Basado en requerimientos 1, 7, 8)
    mosto = Stream('mosto', Water=900, Ethanol=100, units='kg/hr', 
                   T=p['t_mosto'] + 273.15, price=p['p_mosto'])
    
    # Unidades de Proceso (Requerimientos 2 y 3)
    P100 = bst.Pump('P100', ins=mosto, P=4*101325)
    W220 = bst.HXutility('W220', ins=P100-0, T=p['t_w220'] + 273.15)
    V100 = bst.Flash('V100', ins=W220-0, outs=('vapor_prod', 'residuo'), 
                     P=p['p_v100'], Q=0)
    
    # Simulación del sistema
    sys = bst.System('sys_proceso', path=(P100, W220, V100))
    sys.simulate()
    
    # Precio de venta del producto (Requerimiento 8)
    V100.outs[0].price = p['p_etanol']
    
    # Análisis Económico (TEA) - Evita errores de versión 3.x
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
# SIDEBAR: SLIDERS (Requerimientos 1-8)
# =================================================================
with st.sidebar:
    st.header("🎮 Panel de Control")
    
    with st.expander("Operación", expanded=True):
        t_mosto = st.slider("Temp. Alimentación (°C)", 10, 60, 25)
        t_w220 = st.slider("Temp. Salida W220 (°C)", 70, 100, 92)
        p_v100 = st.slider("Presión V100 (Pa)", 50000, 150000, 101325)
        
    with st.expander("Mercado (Precios)", expanded=True):
        p_luz = st.slider("Luz (USD/kWh)", 0.05, 0.30, 0.12)
        p_vap = st.slider("Vapor (USD/kg)", 0.01, 0.10, 0.02)
        p_agu = st.slider("Agua (USD/kg)", 0.0001, 0.005, 0.0005)
        p_mos = st.slider("Mosto (USD/kg)", 0.05, 0.50, 0.10)
        p_eta = st.slider("Etanol (USD/kg)", 0.50, 2.50, 1.20)

    st.divider()
    ia_tutor = st.toggle("Habilitar Tutor IA", value=True)
    ejecutar = st.button("🚀 Ejecutar Simulación", use_container_width=True)

# =================================================================
# RESULTADOS (Requerimientos 9-15)
# =================================================================
if ejecutar:
    params = {
        't_mosto': t_mosto, 't_w220': t_w220, 'p_v100': p_v100,
        'p_luz': p_luz, 'p_vapor': p_vap, 'p_agua': p_agu,
        'p_mosto': p_mos, 'p_etanol': p_eta
    }
    
    try:
        sys, tea, prod = ejecutar_simulacion(params)
        
        # Fichas de producto (Requerimiento 10)
        st.subheader("📦 Indicadores de Producto y Rentabilidad")
        c1, c2, c3, c4 = st.columns(4)
        with c1: st.markdown(f'<div class="metric-card"><div class="metric-label">Presión / Temp</div><div class="metric-value">{prod.P/101325:.2f} atm / {prod.T-273.15:.1f} °C</div></div>', unsafe_allow_html=True)
        with c2: st.markdown(f'<div class="metric-card"><div class="metric-label">Flujo / % Etanol</div><div class="metric-value">{prod.F_mass:.1f} kg/h / {prod.imass["Ethanol"]/prod.F_mass*100:.1f}%</div></div>', unsafe_allow_html=True)
        with c3: st.markdown(f'<div class="metric-card"><div class="metric-label">NPV (VPN)</div><div class="metric-value">${tea.NPV/1e6:.2f} M</div></div>', unsafe_allow_html=True)
        with c4: st.markdown(f'<div class="metric-card"><div class="metric-label">ROI / Payback</div><div class="metric-value">{(tea.sales-tea.AOC)/tea.TCI*100:.1f}% / {tea.TCI/(tea.sales-tea.AOC) if (tea.sales-tea.AOC)>0 else 0:.1f} a</div></div>', unsafe_allow_html=True)

        tab1, tab2, tab3 = st.tabs(["📋 Balances", "📐 Diagramas ISO", "🤖 Tutor IA"])
        
        with tab1:
            st.write("**Balances de Materia y Energía**")
            st.table(sys.get_stream_table().iloc[:, :5]) # Tabla simplificada
        
        with tab2:
            st.image("gemini-svg.svg", caption="PFD Estándar ISO (AutoCAD Plant 3D)", use_column_width=True)
        
        with tab3:
            if ia_tutor and "GEMINI_API_KEY" in st.secrets:
                genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
                model = genai.GenerativeModel('gemini-2.5-pro')
                contexto = f"Resultados: NPV=${tea.NPV/1e6:.2f}M, MPSP=${tea.solve_price(prod):.2f}/kg."
                pregunta = st.text_input("Pregunta al tutor:")
                if pregunta:
                    res = model.generate_content(contexto + " " + pregunta)
                    st.info(res.text)
    except Exception as e:
        st.error(f"Error técnico: {e}")
