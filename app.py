import streamlit as st
import biosteam as bst
import thermosteam as tmo
import pandas as pd
import google.generativeai as genai

# =================================================================
# 1. CONFIGURACIÓN DE PÁGINA
# =================================================================
st.set_page_config(page_title="Planta Etanol ISO v4.0", layout="wide")

st.markdown("""
    <style>
    .metric-box {
        background-color: #f8f9fa;
        padding: 15px;
        border-radius: 8px;
        border-top: 4px solid #28a745;
        text-align: center;
        box-shadow: 2px 2px 5px rgba(0,0,0,0.05);
        margin-bottom: 10px;
    }
    .metric-title { font-weight: bold; color: #444; font-size: 0.85em; }
    .metric-value { font-size: 1.25em; color: #000; font-weight: bold; }
    </style>
""", unsafe_allow_html=True)

# =================================================================
# 2. LÓGICA DE SIMULACIÓN (Cálculos Puros)
# =================================================================
def simular_proceso_iso(t_feed, t_out_w220, p_flash, p_elec, p_steam, p_water, p_mosto, p_etanol):
    # Reset del flowsheet para evitar duplicidad de equipos
    bst.main_flowsheet.clear()
    
    # Termodinámica
    chemicals = tmo.Chemicals(["Water", "Ethanol"])
    bst.settings.set_thermo(chemicals)

    # Precios (vía configuración de BioSTEAM)
    bst.settings.electricity_price = p_elec
    
    # 2.1 Definición de Corrientes
    mosto = bst.Stream('Alimentacion', Water=900, Ethanol=100, units='kg/hr', T=t_feed+273.15, price=p_mosto)
    reciclo = bst.Stream('Reciclo_Vinaza', Water=200, T=95+273.15)

    # 2.2 Unidades de Proceso
    P100 = bst.Pump('P100', ins=mosto, P=4*101325)
    W210 = bst.HXprocess('W210', ins=(P100-0, reciclo), outs=('S1', 'S2'), phase0='l', phase1='l')
    W210.outs[0].T = 85 + 273.15
    W220 = bst.HXutility('W220', ins=W210-0, outs='S3', T=t_out_w220+273.15)
    V100 = bst.IsenthalpicValve('V100', ins=W220-0, outs='S4', P=p_flash*101325)
    V1 = bst.Flash('V1', ins=V100-0, outs=('Vapor', 'Vinazas'), P=p_flash*101325, Q=0)
    W310 = bst.HXutility('W310', ins=V1-0, outs='Producto_Final', T=25+273.15)
    P200 = bst.Pump('P200', ins=V1-1, outs=reciclo, P=3*101325)

    # 2.3 Simulación del Sistema
    sys = bst.System('sys_etanol', path=(P100, W210, W220, V100, V1, W310, P200))
    sys.simulate()
    
    # --- CÁLCULOS FINANCIEROS ---
    inv_capital = 200000 
    horas_año = 8000
    
    # Costos operativos (Suma de utilidades y materias primas)
    costo_utilidades = sum([u.utility_cost for u in sys.units]) * horas_año
    costo_materia = mosto.F_mass * p_mosto * horas_año
    ingresos = W310.F_mass * p_etanol * horas_año
    
    flujo_caja = ingresos - costo_utilidades - costo_materia
    
    roi = (flujo_caja / inv_capital) * 100
    pb = inv_capital / flujo_caja if flujo_caja > 0 else 0
    npv = sum([flujo_caja / (1.1**i) for i in range(1, 11)]) - inv_capital

    return sys, W310, npv, pb, roi, flujo_caja

# =================================================================
# 3. INTERFAZ DE USUARIO (Captura de datos)
# =================================================================
with st.sidebar:
    st.header("⚙️ Parámetros Planta ISO")
    
    with st.expander("🌡️ Variables de Operación", expanded=True):
        val_t_feed = st.slider("T Alimentación Mosto (°C)", 10.0, 50.0, 25.0)
        val_t_w220 = st.slider("T Salida W220 (°C)", 70.0, 110.0, 92.0)
        val_p_flash = st.slider("P Separador V100 (atm)", 0.2, 2.0, 1.0)
        
    with st.expander("💰 Precios de Mercado", expanded=True):
        val_p_elec = st.slider("Precio Luz (USD/kWh)", 0.05, 0.5, 0.12)
        val_p_steam = st.slider("Precio Vapor (USD/ton)", 10.0, 60.0, 30.0)
        val_p_water = st.slider("Precio Agua (USD/m3)", 0.1, 5.0, 0.8)
        val_p_mosto = st.slider("Precio Mosto (USD/kg)", 0.01, 0.4, 0.06)
        val_p_etanol = st.slider("Precio Etanol (USD/kg)", 0.5, 3.0, 1.3)

    st.divider()
    tutor_activo = st.toggle("🎓 Modo Tutor IA")
    ejecutar = st.button("🚀 ACTUALIZAR PROCESO", use_container_width=True)

# =================================================================
# 4. DASHBOARD DE RESULTADOS
# =================================================================
if ejecutar:
    # Llamada a la función pasándole los VALORES de los sliders, no los sliders mismos
    sys, prod, npv, pb, roi, neto = simular_proceso_iso(
        val_t_feed, val_t_w220, val_p_flash, val_p_elec, val_p_steam, val_p_water, val_p_mosto, val_p_etanol
    )

    # 4.1 Métricas de Producto (Recuadros)
    st.subheader("📦 Propiedades de la Corriente Final")
    r1, r2, r3, r4 = st.columns(4)
    with r1: st.markdown(f"<div class='metric-box'><div class='metric-title'>Presión</div><div class='metric-value'>{prod.P/101325:.2f} atm</div></div>", unsafe_allow_html=True)
    with r2: st.markdown(f"<div class='metric-box'><div class='metric-title'>Temperatura</div><div class='metric-value'>{prod.T-273.15:.1f} °C</div></div>", unsafe_allow_html=True)
    with r3: st.markdown(f"<div class='metric-box'><div class='metric-title'>Flujo Total</div><div class='metric-value'>{prod.F_mass:.1f} kg/h</div></div>", unsafe_allow_html=True)
    pureza = (prod.imass['Ethanol']/prod.F_mass)*100 if prod.F_mass > 0 else 0
    with r4: st.markdown(f"<div class='metric-box'><div class='metric-title'>Comp. Etanol</div><div class='metric-value'>{pureza:.1f} %</div></div>", unsafe_allow_html=True)

    # 4.2 Indicadores Financieros
    st.divider()
    st.subheader("📉 Indicadores de Rentabilidad (TEA)")
    f1, f2, f3, f4 = st.columns(4)
    f1.metric("Costo Producción", f"{(1 - (neto/(prod.F_mass*val_p_etanol*8000)))*val_p_etanol:.3f} USD/kg")
    f2.metric("NPV (10a)", f"{npv/1000:.1f}k USD")
    f3.metric("Payback Period", f"{pb:.1f} años")
    f4.metric("ROI Anual", f"{roi:.1f} %")

    # 4.3 Tablas
    st.divider()
    b1, b2 = st.tabs(["Balance de Masa", "Balance de Energía"])
    with b1:
        st.table(pd.DataFrame([{"ID": s.ID, "kg/h": round(s.F_mass, 1), "T(C)": round(s.T-273.15, 1)} for s in sys.streams if s.F_mass > 0.1]))
    with b2:
        st.table(pd.DataFrame([{"Unidad": u.ID, "Carga (kW)": round(sum([h.duty for h in u.heat_utilities])/3600, 2)} for u in sys.units]))

    # 4.4 Descargas ISO
    st.divider()
    st.subheader("📂 Documentación ISO (AutoCAD Plant 3D)")
    d1, d2 = st.columns(2)
    d1.download_button("📥 Diagrama de Bloques ISO", data="PDF_BIN", file_name="Bloques_Etanol_ISO.pdf", use_container_width=True)
    d2.download_button("📥 PFD ISO 14617", data="PDF_BIN", file_name="PFD_Etanol_ISO.pdf", use_container_width=True)

    # 4.5 Tutor IA
    if tutor_activo:
        st.divider()
        st.subheader("💬 Consultoría Técnica con IA")
        if "chat_log" not in st.session_state: st.session_state.chat_log = []
        for m in st.session_state.chat_log:
            with st.chat_message(m["role"]): st.markdown(m["content"])

        if preg := st.chat_input("Explícame por qué el ROI es bajo..."):
            st.session_state.chat_log.append({"role": "user", "content": preg})
            with st.chat_message("user"): st.markdown(preg)
            
            if "GEMINI_API_KEY" in st.secrets:
                genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
                model = genai.GenerativeModel('gemini-2.5-pro')
                ctx = f"Planta Etanol. ROI: {roi:.1f}%. Pureza: {pureza:.1f}%. Pregunta: {preg}"
                res = model.generate_content(ctx)
                with st.chat_message("assistant"): st.markdown(res.text)
                st.session_state.chat_log.append({"role": "assistant", "content": res.text})
            else:
                st.error("Falta API Key en Secrets.")

else:
    st.info("👈 Use el panel lateral para ajustar la planta y presione el botón para calcular.")
