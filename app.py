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
    .metric-card-econ {
        background-color: #ffffff;
        padding: 20px;
        border-radius: 15px;
        border-left: 5px solid #10b981;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
        margin-bottom: 10px;
    }
    .metric-value { font-size: 24px; font-weight: bold; color: #1e293b; }
    .metric-label { font-size: 14px; color: #64748b; text-transform: uppercase; }
    
    #info-box {
        position: absolute;
        background: rgba(255, 255, 255, 0.98);
        border: 2px solid #3b82f6;
        border-radius: 10px;
        padding: 12px;
        display: none;
        z-index: 1000;
        box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1);
        pointer-events: none;
        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        min-width: 180px;
    }
    </style>
    <div id="info-box"></div>
""", unsafe_allow_html=True)

# =================================================================
# LÓGICA DE SIMULACIÓN TÉCNICA Y ECONÓMICA (BIOSTEAM)
# =================================================================
def ejecutar_simulacion_tecnica(params):
    # 1. Reiniciar Flowsheet
    bst.main_flowsheet.clear()
    
    # 2. Configuración Termodinámica
    chems = Chemicals(['Water', 'Ethanol'])
    settings.set_thermo(chems)
    
    # 3. Creación de Corrientes
    mosto = Stream('mosto', Water=900, Ethanol=100, units='kg/hr', 
                    T=params['t_mosto'] + 273.15)
    
    # 4. Diseño de Equipos
    P100 = bst.Pump('P100', ins=mosto, P=4*101325)
    V210 = bst.HXutility('V210', ins=P100-0, T=params['t_w220'] + 273.15)
    W310 = bst.HXutility('W310', ins=V210-0, T=params['t_w220'] + 5 + 273.15)
    R410 = bst.Flash('R410', ins=W310-0, outs=('vapor_prod', 'liquido_residuo'), 
                      P=params['p_v100'], Q=0)
    V510 = bst.HXutility('V510', ins=R410-0, T=40 + 273.15, V=0)
    P510 = bst.Pump('P510', ins=V510-0, P=101325)
    
    # Simular Sistema
    sys = bst.System('sys_proceso', path=(P100, V210, W310, R410, V510, P510))
    sys.simulate()
    
    # 5. Diccionario de Datos para JavaScript (PFD)
    datos_equipos = {
        "P-100": {"T": f"{P100.outs[0].T-273.15:.1f} °C", "P": f"{P100.outs[0].P/101325:.2f} atm", "F": f"{P100.outs[0].F_mass:.1f} kg/h"},
        "V-210": {"T": f"{V210.outs[0].T-273.15:.1f} °C", "P": f"{V210.outs[0].P/101325:.2f} atm", "F": f"{V210.outs[0].F_mass:.1f} kg/h"},
        "W-310": {"T": f"{W310.outs[0].T-273.15:.1f} °C", "P": f"{W310.outs[0].P/101325:.2f} atm", "F": f"{W310.outs[0].F_mass:.1f} kg/h"},
        "R-410": {"T": f"{R410.outs[0].T-273.15:.1f} °C", "P": f"{R410.outs[0].P/101325:.2f} atm", "F": f"{R410.outs[0].F_mass:.1f} kg/h (V)"},
        "V-510": {"T": f"{V510.outs[0].T-273.15:.1f} °C", "P": f"{V510.outs[0].P/101325:.2f} atm", "F": f"{V510.outs[0].F_mass:.1f} kg/h"},
        "P-510": {"T": f"{P510.outs[0].T-273.15:.1f} °C", "P": f"{P510.outs[0].P/101325:.2f} atm", "F": f"{P510.outs[0].F_mass:.1f} kg/h"}
    }
    
    # =================================================================
    # EVALUACIÓN ECONÓMICA EN TIEMPO REAL
    # =================================================================
    prod = R410.outs[0]
    pureza = (prod.imass['Ethanol'] / prod.F_mass * 100) if prod.F_mass > 0 else 0
    
    # Materias primas y productos masicos
    costo_mosto_total = mosto.F_mass * params['p_costo_mosto']
    ingreso_etanol_total = prod.imass['Ethanol'] * params['p_precio_etanol']
    
    # Servicios auxiliares (Energía y Calor)
    costo_electricidad_total = 0.0
    costo_calentamiento_total = 0.0 # Vapor
    costo_enfriamiento_total = 0.0  # Agua de enfriamiento
    
    for u in sys.units:
        # Potencia eléctrica (kW) -> convertimos a costo por hora
        if hasattr(u, 'power') and u.power > 0:
            costo_electricidad_total += u.power * params['p_costo_luz']
            
        # Cargas térmicas (kJ/h)
        if hasattr(u, 'heat_utilities') and u.heat_utilities:
            for hu in u.heat_utilities:
                if hu.duty > 0: # Requiere calentamiento (Vapor)
                    # Convertir kJ a toneladas de vapor aproximadas o usar factor directo por MJ
                    costo_calentamiento_total += (hu.duty / 1000) * params['p_costo_vapor']
                elif hu.duty < 0: # Requiere enfriamiento (Agua)
                    costo_enfriamiento_total += (abs(hu.duty) / 1000) * params['p_costo_agua']

    costos_operativos = costo_mosto_total + costo_electricidad_total + costo_calentamiento_total + costo_enfriamiento_total
    utilidad_neta = ingreso_etanol_total - costos_operativos

    # Preparar resúmenes para la UI y la IA
    resumen_materia = ""
    for s in sys.streams:
        resumen_materia += f"- Corriente '{s.ID}': T = {s.T-273.15:.1f}°C, P = {s.P/101325:.2f}atm, Flujo Total = {s.F_mass:.1f}kg/h (Agua: {s.imass['Water']:.1f}kg/h, Etanol: {s.imass['Ethanol']:.1f}kg/h)\n"
    
    resumen_energia = ""
    for u in sys.units:
        q_neto = sum(hu.duty for hu in u.heat_utilities) if u.heat_utilities else 0.0
        p_elec = u.power if hasattr(u, 'power') else 0.0
        resumen_energia += f"- Equipo '{u.ID}' ({type(u).__name__}): Calor Neto Q = {q_neto:,.1f} kJ/h, Potencia = {p_elec:.4f} kW\n"

    resultados_estaticos = {
        "presion": f"{prod.P/101325:.2f} atm",
        "temperatura": f"{prod.T-273.15:.1f} °C",
        "flujo_vapor": f"{prod.F_mass:.1f} kg/h",
        "pureza": f"{pureza:.1f} %",
        "ingresos": f"${ingreso_etanol_total:,.2f} USD/h",
        "costos": f"${costos_operativos:,.2f} USD/h",
        "utilidad": f"${utilidad_neta:,.2f} USD/h",
        "utilidad_raw": utilidad_neta,
        "resumen_materia": resumen_materia,
        "resumen_energia": resumen_energia,
        "datos_materia_df": [{"Corriente": s.ID, "T [°C]": f"{s.T-273.15:.1f}", "P [atm]": f"{s.P/101325:.2f}", "Total [kg/h]": round(s.F_mass, 2), "Water": round(s.imass['Water'], 2), "Ethanol": round(s.imass['Ethanol'], 2)} for s in sys.streams],
        "datos_energia_df": [{"Equipo": u.ID, "Tipo": type(u).__name__, "Calor Neto (Q) [kJ/h]": f"{(sum(hu.duty for hu in u.heat_utilities) if u.heat_utilities else 0.0):,.2f}", "Potencia Eléctrica [kW]": f"{(u.power if hasattr(u, 'power') else 0.0):.4f}"} for u in sys.units],
        "desglose_economico": {
            "Costo Mosto": costo_mosto_total,
            "Costo Electricidad": costo_electricidad_total,
            "Costo Vapor (Calentamiento)": costo_calentamiento_total,
            "Costo Agua (Enfriamiento)": costo_enfriamiento_total,
            "Ingreso Etanol": ingreso_etanol_total
        }
    }
    
    return resultados_estaticos, datos_equipos

# =================================================================
# COMPONENTE INTERACTIVO (SVG + JS)
# =================================================================
def render_interactive_diagram(datos_json):
    svg_html = f"""
    <div id="svg-container" style="background: #f8fafc; border-radius: 15px; padding: 20px;">
        <svg viewBox="0 0 800 600" width="100%" height="100%" id="process-svg">
          <style>
            .equipment {{ fill: #f0f8ff; stroke: #000080; stroke-width: 2; cursor: pointer; transition: all 0.3s; }}
            .equipment:hover {{ fill: #3b82f6; stroke-width: 3; filter: brightness(1.1); }}
            .pipe {{ fill: none; stroke: #64748b; stroke-width: 3; }}
            .label {{ font-family: 'Arial'; font-size: 14px; font-weight: bold; fill: #1e293b; pointer-events: none; }}
          </style>

          <path class="pipe" d="M 50 150 L 125 150" /> <path class="pipe" d="M 175 150 L 250 150" /> <path class="pipe" d="M 350 150 L 375 150 L 375 250 L 325 250" /> <path class="pipe" d="M 300 275 L 300 350 L 375 350" /> <path class="pipe" d="M 425 350 L 525 350" /> <path class="pipe" d="M 400 430 L 400 480" /> <path class="pipe" d="M 575 350 L 650 350" /> 
          <g id="P-100" class="equipment" onclick="showPopup(this, 'P-100')" transform="translate(150, 150)">
            <circle cx="0" cy="0" r="25" />
            <polygon points="-10,-10 -10,10 15,0" fill="#000080"/>
            <text x="35" y="5" class="label">P-100</text>
          </g>

          <g id="V-210" class="equipment" onclick="showPopup(this, 'V-210')" transform="translate(250, 130)">
            <rect x="0" y="0" width="100" height="40" rx="20" />
            <line x1="10" y1="10" x2="90" y2="10" stroke="#000080" />
            <line x1="10" y1="30" x2="90" y2="30" stroke="#000080" />
            <text x="10" y="-10" class="label">V-210</text>
          </g>

          <g id="W-310" class="equipment" onclick="showPopup(this, 'W-310')" transform="translate(300, 250)">
            <circle cx="0" cy="0" r="25" />
            <path d="M -15 -15 L 15 15 M -15 15 L 15 -15" stroke="#000080" stroke-width="2"/>
            <text x="30" y="5" class="label">W-310</text>
          </g>

          <g id="R-410" class="equipment" onclick="showPopup(this, 'R-410')" transform="translate(400, 350)">
            <rect x="-25" y="-40" width="50" height="80" rx="10" />
            <text x="35" y="0" class="label">R-410</text>
          </g>

          <g id="V-510" class="equipment" onclick="showPopup(this, 'V-510')" transform="translate(550, 350)">
            <circle cx="0" cy="0" r="25" />
            <path d="M -15 -15 L 15 15 M -15 15 L 15 -15" stroke="#000080" stroke-width="2"/>
            <text x="30" y="5" class="label">V-510</text>
          </g>

          <g id="P-510" class="equipment" onclick="showPopup(this, 'P-510')" transform="translate(400, 500)">
            <circle cx="0" cy="0" r="20" />
            <polygon points="-8,-8 -8,8 12,0" fill="#000080"/>
            <text x="25" y="5" class="label">P-510</text>
          </g>
        </svg>
    </div>

    <script>
        const simData = {json.dumps(datos_json)};
        const box = window.parent.document.getElementById('info-box');

        function showPopup(el, id) {{
            const data = simData[id];
            const rect = el.getBoundingClientRect();
            
            box.style.display = 'block';
            box.style.left = (rect.left + window.scrollX + 50) + 'px';
            box.style.top = (rect.top + window.scrollY - 20) + 'px';
            
            box.innerHTML = `
                <div style="border-bottom:1px solid #eee; margin-bottom:8px; padding-bottom:4px;">
                    <b style="color:#3b82f6; font-size:14px;">${{id}}</b>
                </div>
                <div style="line-height:1.6;">
                    🌡️ <b>Temp:</b> ${{data.T}}<br>
                    🌀 <b>Pres:</b> ${{data.P}}<br>
                    ⚖️ <b>Flujo:</b> ${{data.F}}
                </div>
            `;
        }}

        window.parent.document.addEventListener('click', (e) => {{
            if (!e.target.closest('.equipment')) box.style.display = 'none';
        }});
    </script>
    """
    st.components.v1.html(svg_html, height=600)

# =================================================================
# INTERFAZ DE USUARIO PRINCIPAL (BARRA LATERAL)
# =================================================================
with st.sidebar:
    st.header("⚙️ Parámetros Operativos")
    with st.expander("🌡️ Condiciones de Entrada", expanded=True):
        t_mosto = st.slider("Temp. Alimentación (°C)", 10, 60, 25)
        t_w220 = st.slider("Temp. Intercambiador (°C)", 70, 100, 92)
        p_v100 = st.slider("Presión Flash (Pa)", 50000, 150000, 101325)
        
    st.header("💰 Costos y Mercado")
    with st.expander("💸 Precios de Insumos y Servicios", expanded=True):
        p_costo_luz = st.slider("Precio de la Luz ($/kWh)", 0.05, 0.50, 0.12, step=0.01)
        p_costo_vapor = st.slider("Precio del Vapor ($/MJ)", 0.01, 0.10, 0.03, step=0.005)
        p_costo_agua = st.slider("Precio del Agua ($/MJ)", 0.005, 0.05, 0.01, step=0.005)
        p_costo_mosto = st.slider("Precio del Mosto ($/kg)", 0.10, 2.00, 0.40, step=0.05)
        p_precio_etanol = st.slider("Precio del Etanol Puro ($/kg)", 1.00, 5.00, 2.50, step=0.10)
    
    st.divider()
    ia_tutor = st.toggle("Asistente IA con Gemini", value=True)
    simular = st.button("🚀 Iniciar Simulación", use_container_width=True)

# Capturar clics y almacenar todo en st.session_state
if simular:
    params = {
        't_mosto': t_mosto, 't_w220': t_w220, 'p_v100': p_v100,
        'p_costo_luz': p_costo_luz, 'p_costo_vapor': p_costo_vapor,
        'p_costo_agua': p_costo_agua, 'p_costo_mosto': p_costo_mosto,
        'p_precio_etanol': p_precio_etanol
    }
    res_estaticos, json_equipos = ejecutar_simulacion_tecnica(params)
    st.session_state.resultados = res_estaticos
    st.session_state.json_equipos = json_equipos

# =================================================================
# RENDERIZADO ESTABLE DESDE EL SESSION_STATE
# =================================================================
if "resultados" in st.session_state:
    res = st.session_state.resultados
    
    # --- FILA DE MÉTRICAS TÉCNICAS ---
    st.subheader("🎯 Resultados Técnicos (Destilado)")
    c1, c2, c3, c4 = st.columns(4)
    with c1: st.markdown(f'<div class="metric-card"><div class="metric-label">Presión</div><div class="metric-value">{res["presion"]}</div></div>', unsafe_allow_html=True)
    with c2: st.markdown(f'<div class="metric-card"><div class="metric-label">Temperatura</div><div class="metric-value">{res["temperatura"]}</div></div>', unsafe_allow_html=True)
    with c3: st.markdown(f'<div class="metric-card"><div class="metric-label">Flujo Vapor</div><div class="metric-value">{res["flujo_vapor"]}</div></div>', unsafe_allow_html=True)
    with c4: st.markdown(f'<div class="metric-card"><div class="metric-label">Pureza Etanol</div><div class="metric-value">{res["pureza"]}</div></div>', unsafe_allow_html=True)

    # --- FILA DE MÉTRICAS ECONÓMICAS ---
    st.subheader("📈 Rendimiento Financiero del Proceso")
    ec1, ec2, ec3 = st.columns(3)
    with ec1: st.markdown(f'<div class="metric-card-econ"><div class="metric-label">Ingresos estimados</div><div class="metric-value" style="color:#059669;">{res["ingresos"]}</div></div>', unsafe_allow_html=True)
    with ec2: st.markdown(f'<div class="metric-card-econ"><div class="metric-label">Costos Operativos totales</div><div class="metric-value" style="color:#dc2626;">{res["costos"]}</div></div>', unsafe_allow_html=True)
    
    # Dar color dinámico a la utilidad (Rojo si hay pérdidas, verde si hay ganancias)
    color_utilidad = "#059669" if res["utilidad_raw"] >= 0 else "#dc2626"
    with ec3: st.markdown(f'<div class="metric-card-econ" style="border-left-color:{color_utilidad};"><div class="metric-label">Utilidad Neta</div><div class="metric-value" style="color:{color_utilidad};">{res["utilidad"]}</div></div>', unsafe_allow_html=True)

    # Pestañas principales de los Datos e Instrumentación
    tab1, tab2 = st.tabs(["📊 Balances de Materia, Energía y Costos", "📐 Diagrama Interactivo (PFD)"])
    
    with tab1:
        st.write("### ⚖️ Balance de Materia (Corrientes)")
        st.dataframe(pd.DataFrame(res["datos_materia_df"]), use_container_width=True, hide_index=True)
        
        st.divider()
        st.write("### ⚡ Balance de Energía (Equipos)")
        st.dataframe(pd.DataFrame(res["datos_energia_df"]), use_container_width=True, hide_index=True)
        
        st.divider()
        st.write("### 💸 Desglose de Costos por Hora ($ USD/h)")
        df_costos = pd.DataFrame([{"Concepto": k, "Valor ($ USD/h)": f"${v:,.2f}"} for k, v in res["desglose_economico"].items()])
        st.dataframe(df_costos, use_container_width=True, hide_index=True)
    
    with tab2:
        st.info("💡 **Interacción:** Haz clic sobre cualquier equipo del diagrama para ver sus datos técnicos en tiempo real.")
        render_interactive_diagram(st.session_state.json_equipos)

    # =================================================================
    # PANEL DE CONTEXTO / VENTANA DE CHAT PERSISTENTE CON STREAMING
    # =================================================================
    st.divider()
    if ia_tutor:
        st.subheader("🤖 Tutoría Técnico-Económica en Tiempo Real")
        
        if "GEMINI_API_KEY" in st.secrets:
            genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
            
            instrucciones_sistema = (
                "Eres un tutor de Inteligencia Artificial experto en Ingeniería de Procesos Químicos y Análisis Económico de Plantas. "
                "Tu labor es entablar una conversación en lenguaje natural con el estudiante. "
                "Es obligatorio que expliques detalladamente los fenómenos físicos, químicos, termodinámicos y viabilidades financieras "
                "del proceso usando estrictamente los valores numéricos calculados por la simulación (técnicos y de costos) que se te proveen en el contexto. "
                "Debes justificar tus respuestas usando balances de masa, costos operativos, ingresos por producto y relaciones de rentabilidad."
            )
            
            contexto_simulacion = f"""
            [VALORES CALCULADOS POR LA SIMULACIÓN ACTUAL DE LA APLICACIÓN]
            **Balances de Materia (Corrientes):**
            {res["resumen_materia"]}
            
            **Balances de Energía (Equipos):**
            {res["resumen_energia"]}
            
            **Resultados Financieros de Operación:**
            - Ingresos Totales por Venta de Etanol: {res["ingresos"]}
            - Costos Totales de Operación (Materia prima + Servicios Auxiliares): {res["costos"]}
            - Utilidad Bruta del Sistema: {res["utilidad"]}
            - Desglose de flujo de efectivo detallado: {json.dumps(res["desglose_economico"])}
            
            **Resultados de Desempeño Técnico Clave:**
            - Pureza de Etanol en el Destilado (Domo R410): {res["pureza"]}
            - Temperatura de equilibrio en el Flash: {res["temperatura"]}
            """
            
            if "chat_history" not in st.session_state:
                st.session_state.chat_history = []
            
            for message in st.session_state.chat_history:
                with st.chat_message(message["role"]):
                    st.write(message["content"])
            
            if pregunta := st.chat_input("Pregúntale al tutor (ej. ¿El proceso es rentable con estos precios de servicios auxiliares?):"):
                with st.chat_message("user"):
                    st.write(pregunta)
                st.session_state.chat_history.append({"role": "user", "content": pregunta})
                
                model = genai.GenerativeModel(
                    model_name='gemini-2.5-pro',
                    system_instruction=instrucciones_sistema
                )
                
                prompt_final = f"{contexto_simulacion}\n\nPregunta del Estudiante:\n{pregunta}"
                
                with st.chat_message("assistant"):
                    def generar_stream():
                        response_stream = model.generate_content(prompt_final, stream=True)
                        for chunk in response_stream:
                            yield chunk.text
                    
                    respuesta_completa = st.write_stream(generar_stream())
                
                st.session_state.chat_history.append({"role": "assistant", "content": respuesta_completa})
                st.rerun()
        else:
            st.error("Error: Por favor configura la variable 'GEMINI_API_KEY' en el panel de Secrets de Streamlit.")
else:
    st.info("👋 ¡Bienvenido! Por favor, configura los parámetros operativos y los costos de mercado en la barra lateral izquierda y haz clic en '🚀 Iniciar Simulación'.")
