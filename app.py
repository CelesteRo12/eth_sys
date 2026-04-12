import streamlit as st
import biosteam as bst
import thermosteam as tmo
import pandas as pd
import google.generativeai as genai

# =================================================================
# 1. CONFIGURACIÓN DE PÁGINA
# =================================================================
st.set_page_config(page_title="Simulador Etanol ISO v5.1", layout="wide")

# =================================================================
# 2. LÓGICA DE SIMULACIÓN (BioSTEAM)
# =================================================================
def ejecutar_simulacion(f_agua, f_etanol, t_feed, p_elec, p_mosto, p_etanol_v):
    # Reset del flowsheet para evitar IDs duplicados al re-ejecutar
    bst.main_flowsheet.clear()
    
    # Termodinámica
    chemicals = tmo.Chemicals(["Water", "Ethanol"])
    bst.settings.set_thermo(chemicals)
    bst.settings.electricity_price = p_elec
    
    # Corrientes
    mosto = bst.Stream('Alimentacion', Water=f_agua, Ethanol=f_etanol, units='kg/hr', T=t_feed+273.15, price=p_mosto)
    reciclo = bst.Stream('Reciclo_Vinaza', Water=200, T=95+273.15)

    # Equipos (Configuración del PFD)
    P100 = bst.Pump('P100', ins=mosto, P=4*101325)
    W210 = bst.HXprocess('W210', ins=(P100-0, reciclo), outs=('S1', 'S2'), phase0='l', phase1='l')
    W210.outs[0].T = 85 + 273.15
    W220 = bst.HXutility('W220', ins=W210-0, outs='S3', T=92+273.15)
    V100 = bst.IsenthalpicValve('V100', ins=W220-0, outs='S4', P=101325)
    V1 = bst.Flash('V1', ins=V100-0, outs=('Vapor', 'Vinazas'), P=101325, Q=0)
    W310 = bst.HXutility('W310', ins=V1-0, outs='Producto_Final', T=25+273.15)
    P200 = bst.Pump('P200', ins=V1-1, outs=reciclo, P=3*101325)

    # Crear Sistema y Simular
    sys = bst.System('sys_etanol', path=(P100, W210, W220, V100, V1, W310, P200))
    sys.simulate()
    
    # Cálculo Económico
    ingresos = W310.F_mass * p_etanol_v
    # Suma de costos de operación (Utilidades + Materia Prima)
    costos_op = sys.get_utility_cost() + (mosto.F_mass * p_mosto)
    margen = ingresos - costos_op

    return sys, W310, margen

# =================================================================
# 3. INTERFAZ DE USUARIO (Sidebar)
# =================================================================
with st.sidebar:
    st.header("⚙️ Parámetros de Planta")
    
    with st.expander("🌡️ Operación", expanded=True):
        f_agua = st.slider("Agua en Mosto (kg/h)", 500, 1500, 900)
        f_etanol = st.slider("Etanol en Mosto (kg/h)", 10, 500, 100)
        t_feed = st.slider("T Alimentación (°C)", 10, 50, 25)
    
    with st.expander("💰 Precios", expanded=True):
        p_elec = st.slider("Precio Luz (USD/kWh)", 0.05, 0.50, 0.12)
        p_mosto = st.slider("Costo Mosto (USD/kg)", 0.01, 0.40, 0.06)
        p_etanol_v = st.slider("Venta Etanol (USD/kg)", 0.5, 3.0, 1.5)

    st.divider()
    tutor_ia = st.toggle("🎓 Habilitar Tutor IA")
    btn_simular = st.button("🚀 EJECUTAR PLANTA", use_container_width=True)

# =================================================================
# 4. RESULTADOS
# =================================================================
if btn_simular:
    try:
        sys, prod, margen = ejecutar_simulacion(f_agua, f_etanol, t_feed, p_elec, p_mosto, p_etanol_v)
        
        # Métricas principales
        c1, c2, c3 = st.columns(3)
        c1.metric("Producción", f"{prod.F_mass:.2f} kg/h")
        pureza = (prod.imass['Ethanol']/prod.F_mass)*100 if prod.F_mass > 0 else 0
        c2.metric("Pureza Etanol", f"{pureza:.1f} %")
        c3.metric("Margen Neto", f"{margen:.2f} USD/h")

        st.divider()
        col_left, col_right = st.columns(2)

        with col_left:
            st.subheader("📋 Balance de Materia")
            # Filtrar corrientes con flujo significativo
            data_m = [{"Corriente": s.ID, "Masa (kg/h)": round(s.F_mass, 2)} for s in sys.streams if s.F_mass > 0.001]
            st.table(pd.DataFrame(data_m))

        with col_right:
            st.subheader("⚡ Balance de Energía")
            res_e = []
            for u in sys.units:
                # CORRECCIÓN DEL ERROR: Usar u.heat_utilities en lugar de intentar llamar a la clase
                q_total = sum([h.duty for h in u.heat_utilities]) / 3600 # Convertir a kW
                if abs(q_total) > 0.001 or u.power_utility.rate > 0:
                    res_e.append({
                        "Unidad": u.ID,
                        "Carga Calor (kW)": round(q_total, 2),
                        "Costo (USD/h)": round(u.utility_cost, 3)
                    })
            st.table(pd.DataFrame(res_e))
            
        # Guardar para el tutor
        st.session_state.res_actual = f"Margen: {margen}, Pureza: {pureza}%"

    except Exception as e:
        st.error(f"Error en la simulación: {e}")

# =================================================================
# 5. TUTOR IA (Chat)
# =================================================================
if tutor_ia:
    st.divider()
    st.subheader("💬 Consultoría con IA")
    
    if "messages" not in st.session_state:
        st.session_state.messages = []

    for m in st.session_state.messages:
        with st.chat_message(m["role"]): st.markdown(m["content"])

    if prompt := st.chat_input("¿Por qué el margen es negativo?"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"): st.markdown(prompt)

        if "GEMINI_API_KEY" in st.secrets:
            genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
            model = genai.GenerativeModel('gemini-2.5-pro')
            contexto = f"Simulación planta etanol. Resultados: {st.session_state.get('res_actual')}. Pregunta: {prompt}"
            response = model.generate_content(contexto)
            
            with st.chat_message("assistant"): st.markdown(response.text)
            st.session_state.messages.append({"role": "assistant", "content": response.text})
        else:
            st.warning("Configura tu API Key en los secretos de Streamlit.")
