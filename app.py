import streamlit as st

# Verificación de entorno e importaciones
try:
    import biosteam as bst
    import thermosteam as tmo
    import pandas as pd
    import google.generativeai as genai
except ImportError as e:
    st.error(f"Error en librerías: {e}. Revisa tu requirements.txt.")
    st.stop()

# =================================================================
# CONFIGURACIÓN DE PÁGINA
# =================================================================
st.set_page_config(page_title="BioSteam Simulation Hub", layout="wide")

st.title("⚗️ Simulador Químico Profesional")
st.markdown("---")

# =================================================================
# FUNCIÓN DE SIMULACIÓN BIOSTEAM
# =================================================================
def simular_proceso(flujo_agua, flujo_etanol, temp_c):
    # Limpiar flowsheet para evitar conflictos de ID en reruns de Streamlit
    bst.main_flowsheet.clear()
    
    # Configuración Termodinámica
    chemicals = tmo.Chemicals(["Water", "Ethanol"])
    bst.settings.set_thermo(chemicals)

    # Corrientes
    mosto = bst.Stream("1_MOSTO", Water=flujo_agua, Ethanol=flujo_etanol, units="kg/hr", T=temp_c + 273.15)
    vinazas_ret = bst.Stream("Retorno", Water=200, T=95+273.15)

    # Equipos
    P100 = bst.Pump("P100", ins=mosto, P=4*101325)
    W210 = bst.HXprocess("W210", ins=(P100-0, vinazas_ret), outs=("Pre", "Drain"), phase0="l", phase1="l")
    W210.outs[0].T = 85 + 273.15
    W220 = bst.HXutility("W220", ins=W210-0, outs="Hot", T=92+273.15)
    V100 = bst.IsenthalpicValve("V100", ins=W220-0, outs="Mix", P=101325)
    
    # Flash Adiabático
    V1 = bst.Flash("V1", ins=V100-0, outs=("Vapor", "Líquido"), P=101325, Q=0)
    
    W310 = bst.HXutility("W310", ins=V1-0, outs="Producto", T=25 + 273.15)
    P200 = bst.Pump("P200", ins=V1-1, outs=vinazas_ret, P=3*101325)

    # Sistema
    sys = bst.System("etanol_sys", path=(P100, W210, W220, V100, V1, W310, P200))
    sys.simulate()
    return sys

# =================================================================
# INTERFAZ DE USUARIO
# =================================================================
with st.sidebar:
    st.header("⚙️ Configuración")
    agua = st.number_input("Agua (kg/h)", 500, 1500, 900)
    etanol = st.number_input("Etanol (kg/h)", 10, 500, 100)
    temp = st.slider("Temperatura (°C)", 10, 50, 25)
    st.markdown("---")
    ejecutar = st.button("🚀 Simular Proceso", use_container_width=True)

if ejecutar:
    with st.spinner("Ejecutando cálculos termodinámicos..."):
        try:
            planta = simular_proceso(agua, etanol, temp)
            st.success("Simulación finalizada exitosamente.")

            # 1. Diagrama de Flujo (Graphviz - No usa Altair)
            st.subheader("📊 Esquema del Proceso")
            try:
                dot_source = planta.diagram(format='dot', display=False)
                st.graphviz_chart(dot_source)
            except:
                st.warning("Diagrama no disponible en este momento.")

            # 2. Tablas de Resultados (st.table es ANTI-ERRORES de Altair)
            st.subheader("📋 Balances Finales")
            col1, col2 = st.columns(2)
            
            with col1:
                st.write("**Materia**")
                res_m = []
                for s in planta.streams:
                    if s.F_mass > 0.1:
                        res_m.append({
                            "Corriente": s.ID,
                            "kg/h": round(s.F_mass, 1),
                            "T (°C)": round(s.T - 273.15, 1)
                        })
                # Usamos st.table para evitar conflictos con el motor de Altair/VegaLite
                st.table(pd.DataFrame(res_m))

            with col2:
                st.write("**Energía**")
                res_e = []
                for u in planta.units:
                    q_kw = sum([h.duty for h in u.heat_utilities]) / 3600
                    p_kw = u.power_utility.rate if u.power_utility else 0
                    if abs(q_kw) > 0.01 or p_kw > 0.01:
                        res_e.append({
                            "Equipo": u.ID,
                            "Calor (kW)": round(q_kw, 2),
                            "Potencia (kW)": round(p_kw, 2)
                        })
                st.table(pd.DataFrame(res_e))

            # 3. Tutor IA (Gemini)
            if "GEMINI_API_KEY" in st.secrets:
                st.divider()
                st.subheader("🤖 Análisis del Tutor IA")
                try:
                    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
                    model = genai.GenerativeModel('gemini-2.5-pro')
                    
                    prompt = f"""
                    Como experto en ingeniería de procesos, analiza estos datos:
                    MATERIA: {res_m}
                    ENERGÍA: {res_e}
                    Resume en 3 puntos la eficiencia del proceso y da una recomendación técnica.
                    """
                    response = model.generate_content(prompt)
                    st.info(response.text)
                except Exception as e:
                    st.error(f"Error en IA: {e}")
            else:
                st.warning("IA: Registra tu GEMINI_API_KEY en los Secrets de Streamlit para el análisis.")

        except Exception as ex:
            st.error(f"Error técnico: {ex}")
else:
    st.info("Ajusta los parámetros y presiona 'Simular Proceso'.")
