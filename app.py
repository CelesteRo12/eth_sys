import streamlit as st
import biosteam as bst
import thermosteam as tmo
import pandas as pd
import google.generativeai as genai

# =================================================================
# 1. CONFIGURACIÓN DE PÁGINA
# =================================================================
st.set_page_config(page_title="Planta Etanol ISO v5.2", layout="wide")

# Estilo para las métricas
st.markdown("""
    <style>
    [data-testid="stMetricValue"] { font-size: 1.8rem; color: #2E7D32; }
    .stTable { font-size: 0.9rem; }
    </style>
""", unsafe_allow_html=True)

# =================================================================
# 2. LÓGICA DE SIMULACIÓN (BioSTEAM)
# =================================================================
def simular_planta(f_agua, f_etanol, t_feed, p_elec, p_steam, p_water, p_mosto, p_etanol_v):
    # Limpieza total del flowsheet para evitar errores de ID duplicados
    bst.main_flowsheet.clear()
    
    # Configuración Termodinámica
    chemicals = tmo.Chemicals(["Water", "Ethanol"])
    bst.settings.set_thermo(chemicals)
    
    # CONFIGURACIÓN DE PRECIOS GLOBALES
    bst.settings.electricity_price = p_elec
    
    # Definición de Corrientes
    mosto = bst.Stream('Alimentacion', Water=f_agua, Ethanol=f_etanol, units='kg/hr', T=t_feed+273.15, price=p_mosto)
    reciclo = bst.Stream('Reciclo_Vinaza', Water=200, T=95+273.15)

    # Equipos de Proceso
    P100 = bst.Pump('P100', ins=mosto, P=4*101325)
    W210 = bst.HXprocess('W210', ins=(P100-0, reciclo), outs=('S1', 'S2'), phase0='l', phase1='l')
    W210.outs[0].T = 85 + 273.15
    
    # Intercambiador con utilidad (Vapor)
    W220 = bst.HXutility('W220', ins=W210-0, outs='S3', T=92+273.15)
    
    V100 = bst.IsenthalpicValve('V100', ins=W220-0, outs='S4', P=101325)
    V1 = bst.Flash('V1', ins=V100-0, outs=('Vapor', 'Vinazas'), P=101325, Q=0)
    
    # Condensador final
    W310 = bst.HXutility('W310', ins=V1-0, outs='Producto_Final', T=25+273.15)
    P200 = bst.Pump('P200', ins=V1-1, outs=reciclo, P=3*101325)

    # Simulación del Sistema
    sys = bst.System('sys_etanol', path=(P100, W210, W220, V100, V1, W310, P200))
    sys.simulate()
    
    # Cálculos económicos
    ingresos = W310.F_mass * p_etanol_v
    costos_utilidades = sys.get_utility_cost()
    costo_materia_prima = mosto.F_mass * p_mosto
    margen = ingresos - costos_utilidades - costo_materia_prima

    return sys, W310, margen, costos_utilidades

# =================================================================
# 3. INTERFAZ (Sidebar con Sliders)
# =================================================================
with st.sidebar:
    st.header("⚙️ Parámetros del Proceso")
    
    with st.expander("🌡️ Alimentación", expanded=True):
        f_agua = st.slider("Agua (kg/h)", 500, 1500, 900)
        f_etanol = st.slider("Etanol (kg/h)", 10, 500, 100)
        t_feed = st.slider("T Entrada (°C)", 10, 50, 25)
    
    with st.expander("💰 Precios (OPEX)", expanded=True):
        p_elec = st.slider("Electricidad (USD/kWh)", 0.05, 0.50, 0.12)
        p_steam = st.slider("Vapor (USD/ton)", 10.0, 60.0, 30.0)
        p_water = st.slider("Agua (USD/m3)", 0.1, 5.0, 0.8)
        p_mosto = st.slider("Mosto (USD/kg)", 0.01, 0.40, 0.06)
        p_etanol_v = st.slider("Venta Etanol (USD/kg)", 0.5, 3.0, 1.5)

    st.divider()
    tutor_ia = st.toggle("🎓 Activar Tutor IA")
    ejecutar = st.button("🚀 SIMULAR AHORA", use_container_width=True)

# =================================================================
# 4. DASHBOARD DE RESULTADOS
# =================================================================
if ejecutar:
    try:
        sys, prod, margen, c_util = simular_planta(f_agua, f_etanol, t_feed, p_elec, p_steam, p_water, p_mosto, p_etanol_v)
        
        # Fila de métricas
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Flujo Etanol", f"{prod.F_mass:.1f} kg/h")
        pureza = (prod.imass['Ethanol']/prod.F_mass)*100 if prod.F_mass > 0 else 0
        m2.metric("Pureza", f"{pureza:.1f} %")
        m3.metric("Costo Utilidades", f"{c_util:.2f} USD/h")
        m4.metric("Margen Neto", f"{margen:.2f} USD/h", delta=f"{margen:.2f}")

        # Balances en Tablas
        st.divider()
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("📋 Balance de Materia")
            df_m = pd.DataFrame([
                {"ID": s.ID, "Flujo (kg/h)": round(s.F_mass, 2), "T (°C)": round(s.T-273.15, 1)} 
                for s in sys.streams if s.F_mass > 0.1
            ])
            st.table(df_m)

        with col2:
            st.subheader("⚡ Balance de Energía")
            # SOLUCIÓN AL ERROR: Acceso correcto a heat_utilities
            df_e = []
            for u in sys.units:
                # Sumamos el duty de todas las utilidades de calor del equipo
                q_kw = sum([h.duty for h in u.heat_utilities]) / 3600
                p_kw = u.power_utility.rate if u.power_utility else 0
                
                if abs(q_kw) > 0.001 or p_kw > 0.001:
                    df_e.append({
                        "Unidad": u.ID,
                        "Q (kW)": round(q_kw, 2),
                        "Potencia (kW)": round(p_kw, 2),
                        "Costo (USD/h)": round(u.utility_cost, 3)
                    })
            st.table(pd.DataFrame(df_e))
        
        # Guardar contexto para la IA
        st.session_state.contexto_planta = f"Resultados: Margen {margen:.2f} USD/h, Pureza {pureza:.1f}%, Producción {prod.F_mass:.1f} kg/h."

    except Exception as e:
        st.error(f"Error en simulación: {e}")

# =================================================================
# 5. TUTOR IA (Ventana de Chat)
# =================================================================
if tutor_ia:
    st.divider()
    st.subheader("💬 Consultoría Técnica con IA")
    
    if "messages" not in st.session_state:
        st.session_state.messages = []

    # Mostrar historial del chat
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    if prompt := st.chat_input("Pregúntale al tutor sobre el proceso..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        # Respuesta de Gemini
        if "GEMINI_API_KEY" in st.secrets:
            try:
                genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
                model = genai.GenerativeModel('gemini-1.5-flash')
                
                # Enviamos el contexto de la simulación a la IA
                data_planta = st.session_state.get('contexto_planta', 'Aún no hay datos de simulación.')
                input_ia = f"Contexto Planta: {data_planta}. Usuario pregunta: {prompt}"
                
                response = model.generate_content(input_ia)
                
                with st.chat_message("assistant"):
                    st.markdown(response.text)
                st.session_state.messages.append({"role": "assistant", "content": response.text})
            except Exception as ex:
                st.error(f"Error IA: {ex}")
        else:
            st.info("💡 Para hablar con el tutor, añade tu GEMINI_API_KEY en los Secrets de Streamlit.")
