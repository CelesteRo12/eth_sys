import streamlit as st
import pandas as pd
import numpy as np
import google.generativeai as genai
import biosteam as bst
from thermosteam import Chemicals, Stream, settings
import base64

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
    bst.main_flowsheet.clear()
    
    # 1. Configuración Termodinámica
    chems = Chemicals(['Water', 'Ethanol'])
    settings.set_thermo(chems)
    
    # 2. Creación de Corrientes
    mosto = Stream('mosto', Water=900, Ethanol=100, units='kg/hr', 
                    T=params['t_mosto'] + 273.15)
    
    # 3. Diseño de Equipos (Mapeados según tu nuevo SVG)
    P100 = bst.Pump('P100', ins=mosto, P=4*101325)
    W220 = bst.HXutility('W220', ins=P100-0, T=params['t_w220'] + 273.15)
    V100 = bst.Flash('V100', ins=W220-0, outs=('vapor_prod', 'liquido_residuo'), 
                     P=params['p_v100'], Q=0)
    
    sys = bst.System('sys_proceso', path=(P100, W220, V100))
    sys.simulate()
    
    return sys, V100.outs[0], chems

# =================================================================
# FUNCIÓN PARA MOSTRAR EL SVG ADJUNTO
# =================================================================
def render_svg(svg_content):
    b64 = base64.b64encode(svg_content.encode('utf-8')).decode("utf-8")
    html = f'<img src="data:image/svg+xml;base64,{b64}" style="width:100%; height:auto;"/>'
    st.write(html, unsafe_allow_html=True)

# Contenido del archivo gemini-svg.html que proporcionaste
SVG_CODE = """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 600" width="100%" height="100%">
  <defs>
    <style>
      .equipment { fill: #f0f8ff; stroke: #000080; stroke-width: 2; cursor: pointer; transition: all 0.3s ease; }
      .equipment:hover { fill: #add8e6; stroke-width: 3; filter: drop-shadow(3px 3px 2px rgba(0,0,0,0.3)); }
      .pipe { fill: none; stroke: #000080; stroke-width: 2; }
      .label { font-family: Arial, sans-serif; font-size: 12px; font-weight: bold; pointer-events: none; }
    </style>
  </defs>
  <g id="P-100" class="equipment" transform="translate(150, 150)">
    <circle cx="0" cy="0" r="20" /><polygon points="-10,-10 -10,10 10,0" fill="#000080"/>
    <text x="25" y="5" class="label">P-100</text>
  </g>
  <g id="V-210" class="equipment" transform="translate(250, 130)">
    <rect x="0" y="0" width="100" height="40" rx="20" />
    <line x1="0" y1="10" x2="100" y2="10" stroke="#000080" stroke-width="1"/>
    <line x1="0" y1="30" x2="100" y2="30" stroke="#000080" stroke-width="1"/>
    <text x="110" y="25" class="label">V-210</text>
  </g>
  <g id="W-310" class="equipment" transform="translate(300, 250)">
    <circle cx="0" cy="0" r="25" />
    <path d="M -18 -18 L 18 18 M -18 18 L 18 -18" stroke="#000080" stroke-width="2"/>
    <text x="30" y="5" class="label">W-310</text>
  </g>
  <g id="R-410" class="equipment" transform="translate(400, 350)">
    <rect x="-25" y="-40" width="50" height="80" rx="10" />
    <text x="35" y="0" class="label">R-410</text>
  </g>
  <g id="V-510" class="equipment" transform="translate(550, 350)">
    <circle cx="0" cy="0" r="25" />
    <path d="M -18 -18 L 18 18 M -18 18 L 18 -18" stroke="#000080" stroke-width="2"/>
    <text x="30" y="5" class="label">V-510</text>
  </g>
  <g id="P-510" class="equipment" transform="translate(400, 500)">
    <circle cx="0" cy="0" r="20" /><polygon points="-10,-10 -10,10 10,0" fill="#000080"/>
    <text x="25" y="5" class="label">P-510</text>
  </g>
  <path class="pipe" d="M 170 150 L 250 150" />
  <path class="pipe" d="M 300 170 L 300 225" />
  <path class="pipe" d="M 300 275 L 300 390 L 375 390" />
  <path class="pipe" d="M 400 430 L 400 480" />
  <path class="pipe" d="M 425 350 L 525 350" />
</svg>
"""

# =================================================================
# INTERFAZ DE USUARIO
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

if simular:
    params = {'t_mosto': t_mosto, 't_w220': t_w220, 'p_v100': p_v100}
    sys, prod, chems = ejecutar_simulacion_tecnica(params)
    
    st.subheader("🎯 Resultados de la Corriente de Vapor")
    c1, c2, c3, c4 = st.columns(4)
    with c1: st.markdown(f'<div class="metric-card"><div class="metric-label">Presión</div><div class="metric-value">{prod.P/101325:.2f} atm</div></div>', unsafe_allow_html=True)
    with c2: st.markdown(f'<div class="metric-card"><div class="metric-label">Temperatura</div><div class="metric-value">{prod.T-273.15:.1f} °C</div></div>', unsafe_allow_html=True)
    with c3: st.markdown(f'<div class="metric-card"><div class="metric-label">Flujo Másico</div><div class="metric-value">{prod.F_mass:.1f} kg/h</div></div>', unsafe_allow_html=True)
    with c4:
        pureza = (prod.imass['Ethanol'] / prod.F_mass * 100) if prod.F_mass > 0 else 0
        st.markdown(f'<div class="metric-card"><div class="metric-label">Pureza Etanol</div><div class="metric-value">{pureza:.1f} %</div></div>', unsafe_allow_html=True)

    tab1, tab2, tab3 = st.tabs(["📊 Balances de Masa", "📐 Diagramas", "🤖 Asistente IA"])
    
    with tab1:
        st.write("**Tabla de Balance de Materia Completa**")
        chemical_ids = [c.ID for c in chems]
        data = []
        for s in sys.streams:
            row = {"Stream": s.ID, "T [°C]": f"{s.T - 273.15:.2f}", "P [atm]": f"{s.P / 101325:.2f}", "Total [kg/h]": f"{s.F_mass:.2f}"}
            for cid in chemical_ids: row[f"{cid} [kg/h]"] = f"{s.imass[cid]:.2f}"
            data.append(row)
        st.dataframe(pd.DataFrame(data), use_container_width=True)
    
    with tab2:
        st.info("Diagrama de Flujo de Proceso (PFD) Personalizado")
        # Aquí renderizamos el SVG que pasaste
        render_svg(SVG_CODE)

    with tab3:
        if ia_tutor:
            if "GEMINI_API_KEY" in st.secrets:
                genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
                model = genai.GenerativeModel('gemini-1.5-flash')
                chat_input = st.text_input("Haz una consulta técnica:")
                if chat_input:
                    contexto = f"Sistema a {prod.P} Pa, pureza {pureza:.2f}%, flujo {prod.F_mass} kg/h. "
                    response = model.generate_content(contexto + chat_input)
                    st.chat_message("assistant").write(response.text)
            else:
                st.error("Falta API Key de Gemini.")
