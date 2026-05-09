import streamlit as st
import pandas as pd
import numpy as np
import google.generativeai as genai
import biosteam as bst
from thermosteam import Chemicals, Stream, settings
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
    
    /* Estilos para el cuadro de información flotante */
    #info-box {
        position: absolute;
        background: rgba(255, 255, 255, 0.98);
        border: 2px solid #3b82f6;
        border-radius: 10px;
        padding: 12px;
        display: none;
        z-index: 1000;
        box-shadow: 0 10px 15px -3px rgba(0,0,0,0.1);
        pointer-events: none;
        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        min-width: 180px;
    }
    </style>
    <div id="info-box"></div>
""", unsafe_allow_html=True)

# =================================================================
# LÓGICA DE SIMULACIÓN TÉCNICA
# =================================================================
def ejecutar_simulacion_tecnica(params):
    bst.main_flowsheet.clear()
    
    # 1. Configuración Termodinámica
    chems = Chemicals(['Water', 'Ethanol'])
    settings.set_thermo(chems)
    
    # 2. Corriente de Entrada
    mosto = Stream('mosto', Water=900, Ethanol=100, units='kg/hr', 
                    T=params['t_mosto'] + 273.15)
    
    # 3. Diseño de Equipos (Mapeo completo con el diagrama SVG)
    P100 = bst.Pump('P100', ins=mosto, P=4*101325)
    V210 = bst.HXutility('V210', ins=P100-0, T=params['t_w220'] + 273.15)
    W310 = bst.HXutility('W310', ins=V210-0, T=params['t_w220'] + 5) # Simulación de calentamiento extra
    R410 = bst.Flash('R410', ins=W310-0, outs=('vapor_flash', 'liquido_flash'), 
                     P=params['p_v100'], Q=0)
    V510 = bst.HXutility('V510', ins=R410-0, T=310) # Condensador de vapor
    P510 = bst.Pump('P510', ins=R410-1, P=101325)   # Bomba de residuo líquido
    
    # Simulación
    sys = bst.System('sys_proceso', path=(P100, V210, W310, R410, V510, P510))
    sys.simulate()
    
    # Diccionario de datos interactivos para el SVG
    datos_equipos = {
        "P-100": {"T": f"{P100.outs[0].T-273.15:.1f} °C", "P": f"{P100.outs[0].P/101325:.2f} atm", "F": f"{P100.outs[0].F_mass:.1f} kg/h"},
        "V-210": {"T": f"{V210.outs[0].T-273.15:.1f} °C", "P": f"{V210.outs[0].P/101325:.2f} atm", "F": f"{V210.outs[0].F_mass:.1f} kg/h"},
        "W-310": {"T": f"{W310.outs[0].T-273.15:.1f} °C", "P": f"{W310.outs[0].P/101325:.2f} atm", "F": f"{W310.outs[0].F_mass:.1f} kg/h"},
        "R-410": {"T": f"{R410.outs[0].T-273.15:.1f} °C", "P": f"{R410.outs[0].P/101325:.2f} atm", "F": f"{R410.F_mass_in:.1f} kg/h"},
        "V-510": {"T": f"{V510.outs[0].T-273.15:.1f} °C", "P": f"{V510.outs[0].P/101325:.2f} atm", "F": f"{V510.outs[0].F_mass:.1f} kg/h"},
        "P-510": {"T": f"{P510.outs[0].T-273.15:.1f} °C", "P": f"{P510.outs[0].P/101325:.2f} atm", "F": f"{P510.outs[0].F_mass:.1f} kg/h"}
    }
    
    return sys, R410.outs[0], chems, datos_equipos

# =================================================================
# RENDERIZADO DEL DIAGRAMA COMPLETO
# =================================================================
def render_full_interactive_diagram(datos_js):
    json_str = json.dumps(datos_js)
    
    html_code = f"""
    <div style="position: relative; width: 100%; background: #f8fafc; border-radius: 15px; padding: 20px;">
        <svg viewBox="0 0 800 600" xmlns="http://www.w3.org/2000/svg" id="pfd-svg">
            <style>
                .equipment {{ fill: #ffffff; stroke: #1e293b; stroke-width: 2; cursor: pointer; transition: 0.3s; }}
                .equipment:hover {{ fill: #e0f2fe; stroke: #3b82f6; stroke-width: 3; }}
                .pipe {{ fill: none; stroke: #475569; stroke-width: 2.5; }}
                .label {{ font-family: sans-serif; font-size: 13px; font-weight: bold; fill: #1e293b; pointer-events: none; }}
            </style>

            <g id="P-100" class="equipment" onclick="showPopup(this, 'P-100')" transform="translate(100, 150)">
                <circle r="25" /><polygon points="-10,-12 -10,12 15,0" fill="#1e293b"/>
                <text x="30" y="5" class="label">P-100</text>
            </g>

            <g id="V-210" class="equipment" onclick="showPopup(this, 'V-210')" transform="translate(220, 125)">
                <rect width="100" height="50" rx="25" />
                <line x1="10" y1="15" x2="90" y2="15" stroke="#1e293b"/>
                <line x1="10" y1="35" x2="90" y2="35" stroke="#1e293b"/>
                <text x="20" y="70" class="label">V-210</text>
            </g>

            <g id="W-310" class="equipment" onclick="showPopup(this, 'W-310')" transform="translate(380, 150)">
                <circle r="25" />
                <path d="M-15,-15 L15,15 M-15,15 L15,-15" stroke="#1e293b" stroke-width="2"/>
                <text x="30" y="5" class="label">W-310</text>
            </g>

            <g id="R-410" class="equipment" onclick="showPopup(this, 'R-410')" transform="translate(520, 300)">
                <rect x="-35" y="-55" width="70" height="110" rx="15" />
                <text x="45" y="0" class="label">R-410</text>
            </g>

            <g id="V-510" class="equipment" onclick="showPopup(this, 'V-510')" transform="translate(680, 300)">
                <circle r="25" />
                <path d="M-15,-15 L15,15 M-15,15 L15,-15" stroke="#1e293b" stroke-width="2"/>
                <text x="30" y="5" class="label">V-510</text>
            </g>

            <g id="P-510" class="equipment" onclick="showPopup(this, 'P-510')" transform="translate(520, 500)">
                <circle r="25" /><polygon points="-10,-12 -10,12 15,0" fill="#1e293b"/>
                <text x="35" y="5" class="label">P-510</text>
            </g>

            <path class="pipe" d="M125,150 L220,150" />
            <path class="pipe" d="M320,150 L355,150" />
            <path class="pipe" d="M405,150 L520,150 L520,245" />
            <path class="pipe" d="M555,300 L655,300" />
            <path class="pipe" d="M520,355 L520,475" />
        </svg>
    </div>

    <script>
        const dataMap = {json_str};
        const box = window.parent.document.getElementById('info-box');

        function showPopup(el, id) {{
            const d = dataMap[id];
            const rect = el.getBoundingClientRect();
            box.style.display = 'block';
            box.style.left = (rect.left + window.pageXOffset + 50) + 'px';
            box.style.top = (rect.top + window.pageYOffset - 20) + 'px';
            box.innerHTML = `
                <div style="border-bottom:1px solid #eee; margin-bottom:8px; padding-bottom:4px">
                    <b style="color:#3b82f6; font-size:14px">${{id}}</b>
                </div>
                <div style="display:grid; gap:4px; font-size:12px; color:#475569">
                    <span>🌡️ <b>Temp:</b> ${{d.T}}</span>
                    <span>⏲️ <b>Pres:</b> ${{d.P}}</span>
                    <span>⚖️ <b>Flujo:</b> ${{d.F}}</span>
                </div>
            `;
        }}

        window.parent.document.addEventListener('click', (e) => {{
            if (!e.target.closest('.equipment')) box.style.display = 'none';
        }});
    </script>
    """
    st.components.v1.html(html_code, height=650)

# =================================================================
# INTERFAZ PRINCIPAL
# =================================================================
with st.sidebar:
    st.header("🎮 Parámetros")
    t_mosto = st.slider("Temp. Alimentación (°C)", 10, 60, 25)
    t_w220 = st.slider("Temp. Operación (°C)", 70, 100, 92)
    p_v100 = st.slider("Presión Flash (Pa)", 50000, 150000, 101325)
    st.divider()
    ia_tutor = st.toggle("Asistente IA", value=True)
    simular = st.button("🚀 Simular", use_container_width=True)

if simular:
    p = {'t_mosto': t_mosto, 't_w220': t_w220, 'p_v100': p_v100}
    sys, prod, chems, datos_js = ejecutar_simulacion_tecnica(p)
    
    st.subheader("🎯 Resultados Clave (Vapor)")
    cols = st.columns(4)
    pureza = (prod.imass['Ethanol']/prod.F_mass*100) if prod.F_mass > 0 else 0
    
    metrics = [
        ("Presión", f"{prod.P/101325:.2f} atm"),
        ("Temperatura", f"{prod.T-273.15:.1f} °C"),
        ("Flujo", f"{prod.F_mass:.1f} kg/h"),
        ("Pureza Etanol", f"{pureza:.1f} %")
    ]
    for i, (label, value) in enumerate(metrics):
        cols[i].markdown(f'<div class="metric-card"><div class="metric-label">{label}</div><div class="metric-value">{value}</div></div>', unsafe_allow_html=True)

    t1, t2, t3 = st.tabs(["📊 Balances", "📐 PFD Interactivo", "🤖 Gemini IA"])
    
    with t1:
        c_ids = [c.ID for c in chems]
        res = []
        for s in sys.streams:
            row = {"ID": s.ID, "T [°C]": f"{s.T-273.15:.1f}", "P [atm]": f"{s.P/101325:.2f}", "Total [kg/h]": f"{s.F_mass:.1f}"}
            for cid in c_ids: row[cid] = f"{s.imass[cid]:.1f}"
            res.append(row)
        st.dataframe(pd.DataFrame(res), use_container_width=True)
        
    with t2:
        st.info("🖱️ Haz clic en cualquier equipo del diagrama para ver sus parámetros en tiempo real.")
        render_full_interactive_diagram(datos_js)

    with t3:
        if ia_tutor and "GEMINI_API_KEY" in st.secrets:
            genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
            pregunta = st.text_input("Pregunta al asistente sobre el balance:")
            if pregunta:
                model = genai.GenerativeModel('gemini-2.5-pro')
                ctx = f"Flash a {p_v100}Pa, pureza {pureza:.1f}%. Analiza: "
                response = model.generate_content(ctx + pregunta)
                st.chat_message("assistant").write(response.text)
