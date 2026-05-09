import streamlit as st
import pandas as pd
import numpy as np
import google.generativeai as genai
import biosteam as bst
from thermosteam import Chemicals, Stream, settings
import base64
import json

# =================================================================
# CONFIGURACIÓN Y ESTILOS
# =================================================================
st.set_page_config(page_title="BioSTEAM Interactive Process", layout="wide")

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
    
    /* Estilos para el Info-Box del Diagrama */
    #info-box {
        position: absolute;
        background: rgba(255, 255, 255, 0.95);
        border: 1px solid #3b82f6;
        border-radius: 8px;
        padding: 10px;
        display: none;
        z-index: 1000;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        pointer-events: none;
        font-family: sans-serif;
        font-size: 12px;
    }
    </style>
    <div id="info-box"></div>
""", unsafe_allow_html=True)

# =================================================================
# LÓGICA DE SIMULACIÓN TÉCNICA
# =================================================================
def ejecutar_simulacion_tecnica(params):
    # Reiniciar flowsheet para evitar duplicados
    bst.main_flowsheet.clear()
    
    # 1. Configuración Termodinámica
    chems = Chemicals(['Water', 'Ethanol'])
    settings.set_thermo(chems)
    
    # 2. Creación de Corrientes
    mosto = Stream('mosto', Water=900, Ethanol=100, units='kg/hr', 
                    T=params['t_mosto'] + 273.15)
    
    # 3. Diseño de Equipos
    # Bomba
    P100 = bst.Pump('P100', ins=mosto, P=4*101325)
    # Intercambiador (V210 en el SVG)
    V210 = bst.HXutility('V210', ins=P100-0, T=params['t_w220'] + 273.15)
    # Flash (R410 en el SVG)
    R410 = bst.Flash('R410', ins=V210-0, outs=('vapor_prod', 'liquido_residuo'), 
                     P=params['p_v100'], Q=0)
    
    # Simulación del sistema
    sys = bst.System('sys_proceso', path=(P100, V210, R410))
    sys.simulate()
    
    # Extraer datos para el JS (convertidos a diccionarios simples)
    datos_equipos = {
        "P-100": {
            "T": f"{P100.outs[0].T - 273.15:.1f} °C",
            "P": f"{P100.outs[0].P / 101325:.2f} atm",
            "F": f"{P100.outs[0].F_mass:.1f} kg/h"
        },
        "V-210": {
            "T": f"{V210.outs[0].T - 273.15:.1f} °C",
            "P": f"{V210.outs[0].P / 101325:.2f} atm",
            "F": f"{V210.outs[0].F_mass:.1f} kg/h"
        },
        "R-410": {
            "T": f"{R410.outs[0].T - 273.15:.1f} °C",
            "P": f"{R410.outs[0].P / 101325:.2f} atm",
            "F": f"{R410.outs[0].F_mass:.1f} kg/h (Vapor)"
        }
    }
    
    return sys, R410.outs[0], chems, datos_equipos

# =================================================================
# FUNCIÓN RENDERIZADO INTERACTIVO
# =================================================================
def render_interactive_svg(datos_js):
    # Convertimos los datos de Python a JSON para el JavaScript
    json_data = json.dumps(datos_js)
    
    svg_html = f"""
    <div id="svg-container" style="position: relative; display: inline-block; width: 100%;">
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 600" width="100%" height="100%" id="process-svg">
          <defs>
            <style>
              .equipment {{ fill: #f0f8ff; stroke: #000080; stroke-width: 2; cursor: pointer; transition: all 0.3s ease; }}
              .equipment:hover {{ fill: #3b82f6; stroke-width: 3; }}
              .pipe {{ fill: none; stroke: #000080; stroke-width: 2; }}
              .label {{ font-family: Arial, sans-serif; font-size: 14px; font-weight: bold; pointer-events: none; }}
            </style>
          </defs>

          <g id="P-100" class="equipment" onclick="showData(this, 'P-100')" transform="translate(150, 150)">
            <circle cx="0" cy="0" r="25" />
            <polygon points="-10,-10 -10,10 15,0" fill="#000080"/>
            <text x="30" y="5" class="label">P-100</text>
          </g>

          <g id="V-210" class="equipment" onclick="showData(this, 'V-210')" transform="translate(300, 130)">
            <rect x="0" y="0" width="120" height="50" rx="25" />
            <line x1="10" y1="15" x2="110" y2="15" stroke="#000080" />
            <line x1="10" y1="35" x2="110" y2="35" stroke="#000080" />
            <text x="130" y="30" class="label">V-210</text>
          </g>

          <g id="R-410" class="equipment" onclick="showData(this, 'R-410')" transform="translate(500, 300)">
            <rect x="-30" y="-50" width="60" height="100" rx="15" />
            <line x1="-30" y1="0" x2="30" y2="0" stroke="#000080" stroke-dasharray="4"/>
            <text x="40" y="5" class="label">R-410</text>
          </g>

          <path class="pipe" d="M 175 150 L 300 155" />
          <path class="pipe" d="M 420 155 L 500 155 L 500 250" />
        </svg>
    </div>

    <script>
        const simData = {json_data};
        const infoBox = window.parent.document.getElementById('info-box');

        function showData(element, id) {{
            const data = simData[id];
            if (data) {{
                const rect = element.getBoundingClientRect();
                infoBox.style.display = 'block';
                infoBox.style.left = (rect.left + window.pageXOffset + 40) + 'px';
                infoBox.style.top = (rect.top + window.pageYOffset - 40) + 'px';
                infoBox.innerHTML = `
                    <strong style="color:#3b82f6">${{id}}</strong><br>
                    🌡️ Temp: ${{data.T}}<br>
                    Pa: ${{data.P}}<br>
                    ⚖️ Flujo: ${{data.F}}
                `;
            }}
        }}
        
        // Cerrar al hacer clic fuera
        window.parent.document.addEventListener('click', function(e) {{
            if (!e.target.closest('.equipment')) {{
                infoBox.style.display = 'none';
            }}
        }});
    </script>
    """
    st.components.v1.html(svg_html, height=500)

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
    ia_tutor = st.toggle("Habilitar Asistente Técnico IA", value=True)
    simular = st.button("🚀 Ejecutar Simulación", use_container_width=True)

if simular:
    params = {'t_mosto': t_mosto, 't_w220': t_w220, 'p_v100': p_v100}
    sys, prod, chems, datos_js = ejecutar_simulacion_tecnica(params)
    
    # 1. Dashboards
    st.subheader("🎯 Resultados de la Corriente de Vapor")
    c1, c2, c3, c4 = st.columns(4)
    pureza = (prod.imass['Ethanol'] / prod.F_mass * 100) if prod.F_mass > 0 else 0
    
    with c1: st.markdown(f'<div class="metric-card"><div class="metric-label">Presión</div><div class="metric-value">{prod.P/101325:.2f} atm</div></div>', unsafe_allow_html=True)
    with c2: st.markdown(f'<div class="metric-card"><div class="metric-label">Temperatura</div><div class="metric-value">{prod.T-273.15:.1f} °C</div></div>', unsafe_allow_html=True)
    with c3: st.markdown(f'<div class="metric-card"><div class="metric-label">Flujo Másico</div><div class="metric-value">{prod.F_mass:.1f} kg/h</div></div>', unsafe_allow_html=True)
    with c4: st.markdown(f'<div class="metric-card"><div class="metric-label">Pureza Etanol</div><div class="metric-value">{pureza:.1f} %</div></div>', unsafe_allow_html=True)

    tab1, tab2, tab3 = st.tabs(["📊 Balances", "📐 Diagrama Interactivo", "🤖 Asistente IA"])
    
    with tab1:
        chemical_ids = [c.ID for c in chems]
        data = []
        for s in sys.streams:
            row = {"Corriente": s.ID, "T [°C]": f"{s.T-273.15:.1f}", "Flujo [kg/h]": f"{s.F_mass:.1f}"}
            for cid in chemical_ids: row[cid] = f"{s.imass[cid]:.1f}"
            data.append(row)
        st.dataframe(pd.DataFrame(data), use_container_width=True)
    
    with tab2:
        st.info("💡 Haz clic en los equipos (P-100, V-210, R-410) para ver sus condiciones actuales.")
        render_interactive_svg(datos_js)

    with tab3:
        if ia_tutor:
            if "GEMINI_API_KEY" in st.secrets:
                genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
                model = genai.GenerativeModel('gemini-2.5-pro')
                pregunta = st.text_input("¿Qué deseas analizar del proceso?")
                if pregunta:
                    ctx = f"Proceso de separación agua-etanol. Flash a {p_v100} Pa. Pureza: {pureza:.1f}%. Temp: {prod.T-273.15:.1f}C."
                    res = model.generate_content(ctx + pregunta)
                    st.chat_message("assistant").write(res.text)
            else:
                st.warning("Agrega tu GEMINI_API_KEY en los secretos de Streamlit.")
