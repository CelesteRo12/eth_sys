import streamlit as st
import pandas as pd
import numpy as np
import google.generativeai as genai
import biosteam as bst  # Importación principal
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
    
    # Equipos
    P100 = bst.Pump('P100', ins=mosto, P=4*101325)
    W220 = bst.HXutility('W220', ins=P100-0, T=params['t_w220'] + 273.15)
    V100 = bst.Flash('V100', ins=W220-0, outs=('vapor_prod', 'liquido_residuo'), 
                     P=params['p_v100'], Q=0)
    
    # Sistema
    sys = bst.System('sys_etanol', path=(P100, W220, V100))
    sys.simulate()
    
    # =============================================================
    # SOLUCIÓN AL ERROR DE IMPORTACIÓN:
    # Usamos bst.TEA que es la forma más estable de acceder a la clase
    # =============================================================
    tea = bst.TEA(
        system=sys,
        IRR=0.15,                           # Tasa Interna de Retorno
        duration=(2026, 2046),              # Horizonte temporal
        operating_days=330,                 # Días de operación
        income_tax=0.30,                    # Impuesto sobre la renta
        lang_factor=4.0,                    # Factor de Lang
        startup_FOCfrac=0.5,                # Fracción FOC startup
        startup_VOCfrac=0.5,                # Fracción VOC startup
        startup_salesfrac=0.5,              # Fracción ventas startup
        WC_over_FCI=0.05,                   # Capital de trabajo
        finance_interest=0.0,               # Sin intereses (Autofinanciamiento)
        finance_years=0,                    # Sin años de deuda
        finance_fraction=0.0                # Sin deuda externa
    )
    
    return sys, tea, V100.outs[0]

# =================================================================
# INTERFAZ DE USUARIO (SLIDERS)
# =================================================================
with st.sidebar:
    st.header("⚙️ Parámetros")
    
    t_mosto = st.slider("Temp. Alimentación Mosto (°C)", 10, 60, 25)
    t_w220 = st.slider("Temp. Salida W220 (°C)", 70, 100, 92)
    p_v100 = st.slider("Presión V100 (Pa)", 50000, 150000, 101325)
    
    st.divider()
    p_luz = st.slider("Precio Luz (USD/kWh)", 0.05, 0.30, 0.12)
    p_mosto = st.slider("Precio Mosto (USD/kg)", 0.05, 0.50, 0.10)
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
        'p_luz': p_luz, 'p_mosto': p_mosto, 'p_etanol': p_etanol
    }
    
    try:
        sys, tea, prod = ejecutar_modelo_completo(params)
        prod.price = p_etanol # Asignar precio para cálculos de ventas
        
        # Recuadros de variables del producto
        st.subheader("📦 Estado del Producto Final")
        c1, c2, c3, c4 = st.columns(4)
        with c1: st.markdown(f'<div class="metric-card"><div class="metric-label">Presión</div><div class="metric-value">{prod.P/101325:.2f} atm</div></div>', unsafe_allow_html=True)
        with c2: st.markdown(f'<div class="metric-card"><div class="metric-label">Temperatura</div><div class="metric-value">{prod.T-273.15:.1f} °C</div></div>', unsafe_allow_html=True)
        with c3: st.markdown(f'<div class="metric-card"><div class="metric-label">Flujo</div><div class="metric-value">{prod.F_mass:.1f} kg/h</div></div>', unsafe_allow_html=True)
        with c4: st.markdown(f'<div class="metric-card"><div class="metric-label">% Etanol</div><div class="metric-value">{prod.imass["Ethanol"]/prod.F_mass*100:.1f}%</div></div>', unsafe_allow_html=True)

        # Indicadores Económicos
        st.subheader("💰 Indicadores Económicos")
        e1, e2, e3 = st.columns(3)
        with e1: st.metric("NPV", f"${tea.NPV/1e6:.2f} M")
        with e2: st.metric("MPSP (Costo Sugerido)", f"${tea.solve_price(prod):.2f}/kg")
        with e3: 
            # ROI aproximado: (Ventas - Costos) / Inversión
            roi = (tea.sales - tea.AOC) / tea.TCI * 100
            st.metric("ROI", f"{roi:.1f}%")

        # Tablas y Diagramas
        t1, t2 = st.tabs(["📊 Balances", "🤖 Tutor IA"])
        with t1:
            st.write("**Balance de Materia y Energía**")
            st.dataframe(sys.get_stream_table())
        
        with t2:
            if ia_tutor and "GEMINI_API_KEY" in st.secrets:
                genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
                model = genai.GenerativeModel('gemini-1.5-flash')
                prompt = f"Explica como tutor de ingeniería: NPV={tea.NPV}, MPSP={tea.solve_price(prod)}. ¿Es rentable?"
                response = model.generate_content(prompt)
                st.info(response.text)

    except Exception as e:
        st.error(f"Error en la simulación: {e}")
