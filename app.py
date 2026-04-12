import streamlit as st
import biosteam as bst
import thermosteam as tmo
import pandas as pd
import google.generativeai as genai

# =================================================================
# CONFIGURACIÓN Y ESTILOS
# =================================================================
st.set_page_config(page_title="Planta Etanol ISO v4.0", layout="wide")

st.markdown("""
    <style>
    .metric-box {
        background-color: #f1f3f5;
        padding: 20px;
        border-radius: 10px;
        border-left: 5px solid #007bff;
        text-align: center;
        margin-bottom: 10px;
    }
    .metric-title { font-size: 0.9em; color: #666; font-weight: bold; }
    .metric-value { font-size: 1.4em; color: #111; font-weight: bold; }
    </style>
""", unsafe_allow_html=True)

# =================================================================
# LÓGICA DE SIMULACIÓN
# =================================================================
def ejecutar_simulacion(t_feed, t_out_w220, p_flash, p_elec, p_steam, p_water, p_mosto, p_etanol):
    # Reiniciar flowsheet
    bst.main_flowsheet.clear()
    chemicals = tmo.Chemicals(["Water", "Ethanol"])
    bst.settings.set_thermo(chemicals)
    
    # Precios de utilidades
    bst.settings.electricity_price = p_elec
    
    # 1. Corrientes
    mosto = bst.Stream('Alimentacion', Water=900, Ethanol=100, units='kg/hr', T=t_feed+273.15, price=p_mosto)
    vinaza_rec = bst.Stream('Reciclo', Water=200, T=95+273.15)

    # 2. Unidades
    P100 = bst.Pump('P100', ins=mosto, P=4*101325)
    W210 = bst.HXprocess('W210', ins=(P100-0, vinaza_rec), outs=('S1', 'S2'), phase0='l', phase1='l')
    W210.outs[0].T = 85 + 273.15 # Calor recuperado
    
    W220 = bst.HXutility('W220', ins=W210-0, outs='S3', T=t_out_w220+273.15)
    V100 = bst.IsenthalpicValve('V100', ins=W220-0, outs='S4', P=p_flash*101325)
    V1 = bst.Flash('V1', ins=V100-0, outs=('Vapor', 'Vinazas'), P=p_flash*101325, Q=0)
    W310 = bst.HXutility('W310', ins=V1-0, outs='Producto_Final', T=25+273.15)
    P200 = bst.Pump('P200', ins=V1-1, outs=vinaza_rec, P=3*101325)

    # 3. Sistema y Simulación
    sys = bst.System('sys_etanol', path=(P100, W210, W220, V100, V1, W310, P200))
    sys.simulate()

    # --- CÁLCULOS FINANCIEROS ---
    capitale_inv = 250000 
    horas_anuales = 8000
    
    costo_op_anual = (sys.utility_cost + (mosto.F_mass * p_mosto)) * horas_anuales
    ingreso_anual = W310.F_mass * p_etanol * horas_anuales
    flujo_caja = ingreso_anual - costo_op_anual
    
    # Indicadores
    costo_real_unitario = costo_op_anual / (W310.F_mass * horas_anuales) if W310.F_mass > 0 else 0
    sugerido = costo_real_unitario * 1.30 # Margen 30%
    roi = (flujo_caja / capitale_inv) * 100
    pb = capitale_inv / flujo_caja if flujo_caja > 0 else float('inf')
    npv = sum([flujo_caja / (1.1**i) for i in range(1, 11)]) - capitale_inv

    return sys, W310, costo_real_unitario, sugerido, npv, pb, roi

# =================================================================
# INTERFAZ (SLIDERS Y CONTROLES)
# =================================================================
with st.sidebar:
    st.header("⚙️ Parámetros de Control")
    
    with st.expander("🌡️ Temperaturas y Presión", expanded=True):
        val_t_feed = st.slider("T Mosto Alimentación (°C)", 10.0, 50.0, 25.0)
        val_t_w220 = st.slider("T Salida Intercambiador W220 (°C)", 70.0, 110.0, 92.0)
        val_p_flash = st.slider("Presión Separador (atm)", 0.1, 2.0, 1.0)

    with st.expander("💰 Precios de Insumos", expanded=True):
        val_p_elec = st.slider("Precio Electricidad (USD/kWh)", 0.05, 0.5, 0.12)
        val_p_steam = st.slider("Precio Vapor (USD/ton)", 10.0, 100.0, 35.0)
        val_p_water = st.slider("Precio Agua (USD/m3)", 0.1, 5.0, 1.0)
        val_p_mosto = st.slider("Precio Mosto (USD/kg)", 0.01, 0.5, 0.08)
        val_p_etanol = st.slider("Precio Venta Etanol (USD/kg)", 0.5, 4.0, 1.5)

    st.divider()
    modo_tutor = st.toggle("🎓 Habilitar Modo Tutor IA")
    btn_ejecutar = st.button("🚀 ACTUALIZAR PLANTA", use_container_width=True)

# =================================================================
# DASHBOARD DE RESULTADOS
# =================================================================
if btn_ejecutar:
    sys, prod, c_real, c_sug, npv, pb, roi = ejecutar_simulacion(
        val_t_feed, val_t_w220, val_p_flash, val_p_elec, val_p_steam, val_p_water, val_p_mosto, val_p_etanol
    )

    # 1. Recuadros de Producto Final
    st.subheader("📦 Propiedades Corriente de Producto")
    c1, c2, c3, c4 = st.columns(4)
    with c1: st.markdown(f"<div class='metric-box'><div class='metric-title'>Presión</div><div class='metric-value'>{prod.P/101325:.2f} atm</div></div>", unsafe_allow_html=True)
    with c2: st.markdown(f"<div class='metric-box'><div class='metric-title'>Temperatura</div><div class='metric-value'>{prod.T-273.15:.1f} °C</div></div>", unsafe_allow_html=True)
    with c3: st.markdown(f"<div class='metric-box'><div class='metric-title'>Flujo Masico</div><div class='metric-value'>{prod.F_mass:.1f} kg/h</div></div>", unsafe_allow_html=True)
    pureza = (prod.imass['Ethanol']/prod.F_mass)*100 if prod.F_mass > 0 else 0
    with c4: st.markdown(f"<div class='metric-box'><div class='metric-title'>Composición Etanol</div><div class='metric-value'>{pureza:.1f}%</div></div>", unsafe_allow_html=True)

    # 2. Indicadores Financieros
    st.divider()
    st.subheader("📊 Análisis Económico")
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Costo Real", f"${c_real:.3f}/kg")
    m2.metric("Venta Sugerida", f"${c_sug:.2f}/kg")
    m3.metric("NPV (10 años)", f"${npv/1000:.1f}k")
    m4.metric("Payback", f"{pb:.1f} años")
    m5.metric("ROI Anual", f"{roi:.1f}%")

    # 3. Tablas de Balance
    st.divider()
    t1, t2 = st.tabs(["Balance de Materia", "Balance de Energía"])
    with t1:
        df_m = pd.DataFrame([{"Corriente": s.ID, "Flujo (kg/h)": round(s.F_mass, 2), "T (°C)": round(s.T-273.15, 1)} for s in sys.streams if s.F_mass > 0])
        st.table(df_m)
    with t2:
        df_e = pd.DataFrame([{"Equipo": u.ID, "Carga Térmica (kW)": round(sum([h.duty for h in u.heat_utilities])/3600, 2)} for u in sys.units])
        st.table(df_e)

    # 4. Tutor con IA Contextual
    if modo_tutor:
        st.divider()
        st.subheader("💬 Ventana de Contexto: Tutor IA")
        if "chat_history" not in st.session_state: st.session_state.chat_history = []

        # Mostrar historial
        for msg in st.session_state.chat_history:
            with st.chat_message(msg["role"]): st.markdown(msg["content"])

        if prompt := st.chat_input("Pregúntame sobre el ROI o la eficiencia térmica..."):
            st.session_state.chat_history.append({"role": "user", "content": prompt})
            with st.chat_message("user"): st.markdown(prompt)

            if "GEMINI_API_KEY" in st.secrets:
                genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
                model = genai.GenerativeModel('gemini-2.5-pro')
                
                # Contexto enriquecido para la IA
                contexto_ia = f"""
                Eres un tutor de ingeniería química. Datos actuales:
                - ROI: {roi:.1f}%, NPV: {npv:.1f}.
                - Pureza Etanol: {pureza:.1f}%.
                - Presión Flash: {val_p_flash} atm.
                - Costo producción: {c_real} USD/kg.
                Responde de forma concisa y técnica a: {prompt}
                """
                response = model.generate_content(contexto_ia)
                st.session_state.chat_history.append({"role": "assistant", "content": response.text})
                with st.chat_message("assistant"): st.markdown(response.text)
            else:
                st.warning("IA: Configura GEMINI_API_KEY en Secrets.")

else:
    st.info("👈 Configura los parámetros en el panel lateral y presiona 'ACTUALIZAR PLANTA' para ver los resultados.")
