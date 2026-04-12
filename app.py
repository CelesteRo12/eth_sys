import streamlit as st
import biosteam as bst
import thermosteam as tmo
import pandas as pd
import google.generativeai as genai

# =================================================================
# 1. CONFIGURACIÓN DE PÁGINA Y ESTILOS
# =================================================================
st.set_page_config(page_title="Planta Etanol ISO v4.0", layout="wide")

st.markdown("""
    <style>
    .metric-box {
        background-color: #ffffff;
        padding: 20px;
        border-radius: 10px;
        border-left: 5px solid #28a745;
        box-shadow: 2px 2px 10px rgba(0,0,0,0.1);
        text-align: center;
        margin-bottom: 15px;
    }
    .metric-title { font-weight: bold; color: #555; font-size: 0.9em; text-transform: uppercase; }
    .metric-value { font-size: 1.5em; color: #111; font-weight: bold; margin-top: 5px; }
    </style>
""", unsafe_allow_html=True)

# =================================================================
# 2. LÓGICA DE SIMULACIÓN Y CÁLCULOS
# =================================================================
def simular_proceso_iso(p_elec, p_steam, p_water, p_mosto, p_etanol):
    # Reset del flowsheet
    bst.main_flowsheet.clear()
    
    # Termodinámica
    chemicals = tmo.Chemicals(["Water", "Ethanol"])
    bst.settings.set_thermo(chemicals)
    bst.settings.electricity_price = p_elec

    # Corrientes (Valores base de diseño)
    mosto = bst.Stream('Alimentacion', Water=900, Ethanol=100, units='kg/hr', T=25+273.15, price=p_mosto)
    reciclo = bst.Stream('Reciclo_Vinaza', Water=200, T=95+273.15)

    # Unidades de Proceso
    P100 = bst.Pump('P100', ins=mosto, P=4*101325)
    W210 = bst.HXprocess('W210', ins=(P100-0, reciclo), outs=('S1', 'S2'), phase0='l', phase1='l')
    W210.outs[0].T = 85 + 273.15
    W220 = bst.HXutility('W220', ins=W210-0, outs='S3', T=92+273.15) # Vapor usado aquí
    V100 = bst.IsenthalpicValve('V100', ins=W220-0, outs='S4', P=101325)
    V1 = bst.Flash('V1', ins=V100-0, outs=('Vapor', 'Vinazas'), P=101325, Q=0)
    W310 = bst.HXutility('W310', ins=V1-0, outs='Producto_Final', T=25+273.15) # Agua enfriamiento
    P200 = bst.Pump('P200', ins=V1-1, outs=reciclo, P=3*101325)

    # Simulación
    sys = bst.System('sys_etanol', path=(P100, W210, W220, V100, V1, W310, P200))
    sys.simulate()
    
    # --- CÁLCULOS ECONÓMICOS ---
    inv_capital = 250000 
    horas_año = 8000
    
    # Costos operativos
    costo_vapor = (W220.heat_utilities[0].duty / 2000) * p_steam * horas_año # Aprox. simplificada
    costo_agua = abs(W310.heat_utilities[0].duty / 500) * p_water * horas_año
    costo_elec = sum([u.power_utility.cost for u in sys.units]) * horas_año
    costo_materia = mosto.F_mass * p_mosto * horas_año
    
    op_cost_total = costo_vapor + costo_agua + costo_elec + costo_materia
    ingresos = W310.F_mass * p_etanol * horas_año
    flujo_caja = ingresos - op_cost_total
    
    # Indicadores
    costo_real_unitario = op_cost_total / (W310.F_mass * horas_año) if W310.F_mass > 0 else 0
    roi = (flujo_caja / inv_capital) * 100
    pb = inv_capital / flujo_caja if flujo_caja > 0 else float('inf')
    npv = sum([flujo_caja / (1.1**i) for i in range(1, 11)]) - inv_capital

    return sys, W310, npv, pb, roi, costo_real_unitario

# =================================================================
# 3. INTERFAZ DE USUARIO (SIDEBAR)
# =================================================================
with st.sidebar:
    st.header("💰 Precios de Mercado")
    val_p_elec = st.slider("Luz (USD/kWh)", 0.05, 0.50, 0.12)
    val_p_steam = st.slider("Vapor (USD/ton)", 10.0, 100.0, 35.0)
    val_p_water = st.slider("Agua (USD/m3)", 0.1, 5.0, 0.8)
    val_p_mosto = st.slider("Mosto (USD/kg)", 0.01, 0.5, 0.06)
    val_p_etanol = st.slider("Etanol (Venta) (USD/kg)", 0.5, 3.0, 1.2)
    
    st.divider()
    tutor_activo = st.toggle("🎓 Habilitar Tutor IA")
    ejecutar = st.button("🚀 EJECUTAR PLANTA", use_container_width=True)

# =================================================================
# 4. CUERPO PRINCIPAL (RESULTADOS)
# =================================================================
st.title("⚗️ Dashboard de Simulación de Etanol")

if ejecutar:
    sys, prod, npv, pb, roi, c_real = simular_proceso_iso(
        val_p_elec, val_p_steam, val_p_water, val_p_mosto, val_p_etanol
    )

    # 4.1 Recuadros de Corriente de Producto
    st.subheader("📦 Propiedades del Producto Final")
    c1, c2, c3, c4 = st.columns(4)
    with c1: st.markdown(f"<div class='metric-box'><div class='metric-title'>Presión</div><div class='metric-value'>{prod.P/101325:.2f} atm</div></div>", unsafe_allow_html=True)
    with c2: st.markdown(f"<div class='metric-box'><div class='metric-title'>Temperatura</div><div class='metric-value'>{prod.T-273.15:.1f} °C</div></div>", unsafe_allow_html=True)
    with c3: st.markdown(f"<div class='metric-box'><div class='metric-title'>Flujo Másico</div><div class='metric-value'>{prod.F_mass:.1f} kg/h</div></div>", unsafe_allow_html=True)
    pureza = (prod.imass['Ethanol']/prod.F_mass)*100 if prod.F_mass > 0 else 0
    with c4: st.markdown(f"<div class='metric-box'><div class='metric-title'>Pureza Etanol</div><div class='metric-value'>{pureza:.1f} %</div></div>", unsafe_allow_html=True)

    # 4.2 Indicadores Financieros
    st.divider()
    st.subheader("📉 Análisis de Rentabilidad")
    f1, f2, f3, f4, f5 = st.columns(5)
    f1.metric("Costo Producción", f"{c_real:.3f} $/kg")
    f2.metric("Sugerido Venta", f"{c_real*1.3:.2f} $/kg", "Margin 30%")
    f3.metric("NPV (10 años)", f"{npv/1000:.1f}k USD")
    f4.metric("Payback", f"{pb:.1f} años")
    f5.metric("ROI Anual", f"{roi:.1f} %")

    # 4.3 Tablas de Balances
    st.divider()
    b1, b2 = st.tabs(["📊 Balance de Materia", "⚡ Balance de Energía"])
    with b1:
        df_m = pd.DataFrame([{"Corriente": s.ID, "Flujo (kg/h)": round(s.F_mass, 2), "Etanol (%)": round(s.imass['Ethanol']/s.F_mass*100, 1) if s.F_mass>0 else 0} for s in sys.streams if s.F_mass > 0])
        st.table(df_m)
    with b2:
        df_e = pd.DataFrame([{"Equipo": u.ID, "Carga Térmica (kW)": round(sum([h.duty for h in u.heat_utilities])/3600, 2), "Potencia (kW)": round(u.power_utility.rate, 2)} for u in sys.units])
        st.table(df_e)

    # 4.4 Tutor IA (Ventana de Contexto)
    if tutor_activo:
        st.divider()
        st.subheader("💬 Consultoría con Tutor IA")
        
        if "chat_history" not in st.session_state:
            st.session_state.chat_history = []

        # Mostrar chat previo
        for msg in st.session_state.chat_history:
            with st.chat_message(msg["role"]): st.write(msg["content"])

        if prompt := st.chat_input("Pregunta al tutor (ej. ¿Por qué el ROI es negativo?)"):
            st.session_state.chat_history.append({"role": "user", "content": prompt})
            with st.chat_message("user"): st.write(prompt)

            if "GEMINI_API_KEY" in st.secrets:
                genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
                model = genai.GenerativeModel('gemini-2.5-pro')
                
                contexto = f"Simulación planta etanol. Costo prod: {c_real}. ROI: {roi}%. Pureza: {pureza}%. Usuario pregunta: {prompt}"
                response = model.generate_content(contexto)
                
                respuesta_ia = response.text
                with st.chat_message("assistant"): st.write(respuesta_ia)
                st.session_state.chat_history.append({"role": "assistant", "content": respuesta_ia})
            else:
                st.error("Por favor, configura GEMINI_API_KEY en los secretos de Streamlit.")

else:
    st.info("Ajuste los costos en el panel lateral y presione 'Ejecutar Planta' para ver el análisis.")
