import streamlit as st

# Verificación de librerías
try:
    import biosteam as bst
    import thermosteam as tmo
    import pandas as pd
    import google.generativeai as genai
except ImportError as e:
    st.error(f"Error de librerías: {e}. Revisa tu requirements.txt.")
    st.stop()

# =================================================================
# CONFIGURACIÓN DE LA APP
# =================================================================
st.set_page_config(page_title="BioSteam Simulation Hub", layout="wide")

st.title("🧪 Simulador de Destilación de Etanol")
st.markdown("---")

# =================================================================
# LÓGICA DE BIOSTEAM
# =================================================================
def run_simulation(f_agua, f_etanol, temp_entrada):
    # CRÍTICO: Limpiar el flowsheet para evitar errores de ID duplicados
    bst.main_flowsheet.clear()
    
    # Definir compuestos
    chemicals = tmo.Chemicals(["Water", "Ethanol"])
    bst.settings.set_thermo(chemicals)

    # Alimentación
    mosto = bst.Stream("1_MOSTO", 
                       Water=f_agua, Ethanol=f_etanol, units="kg/hr",
                       T=temp_entrada + 273.15)
    
    vinazas_ret = bst.Stream("Vinazas_Retorno", Water=200, T=95+273.15)

    # Equipos de proceso
    P100 = bst.Pump("P100", ins=mosto, P=4*101325)
    
    W210 = bst.HXprocess("W210", 
                         ins=(P100-0, vinazas_ret), 
                         outs=("Mosto_Pre", "Drenaje"), 
                         phase0="l", phase1="l")
    W210.outs[0].T = 85 + 273.15

    W220 = bst.HXutility("W220", ins=W210-0, outs="Mezcla_Hot", T=92+273.15)
    V100 = bst.IsenthalpicValve("V100", ins=W220-0, outs="Mezcla_V", P=101325)
    
    # Unidad Flash (Adiabática)
    V1 = bst.Flash("V1", ins=V100-0, outs=("Vapor_Rico", "Vinazas_Fondo"), P=101325, Q=0)
    
    W310 = bst.HXutility("W310", ins=V1-0, outs="Destilado", T=25 + 273.15)
    P200 = bst.Pump("P200", ins=V1-1, outs=vinazas_ret, P=3*101325)

    # Crear Sistema
    sys = bst.System("etanol_sys", path=(P100, W210, W220, V100, V1, W310, P200))
    sys.simulate()
    return sys

# =================================================================
# INTERFAZ DE USUARIO
# =================================================================
with st.sidebar:
    st.header("🎮 Controles del Proceso")
    in_agua = st.number_input("Agua (kg/h)", 500, 1500, 900)
    in_etanol = st.number_input("Etanol (kg/h)", 10, 500, 100)
    in_temp = st.slider("Temp. Entrada (°C)", 15, 45, 25)
    
    st.markdown("---")
    btn_simular = st.button("🚀 Ejecutar Simulación", use_container_width=True)

if btn_simular:
    with st.spinner("Resolviendo balances termodinámicos..."):
        try:
            planta = run_simulation(in_agua, in_etanol, in_temp)
            st.success("Simulación finalizada")

            # 1. Diagrama de Flujo (DFP)
            st.subheader("📊 Diagrama de Flujo del Proceso")
            try:
                # Renderizado directo con Graphviz
                dot = planta.diagram(format='dot', display=False)
                st.graphviz_chart(dot)
            except:
                st.info("El diagrama no se pudo mostrar, pero los datos están listos abajo.")

            # 2. Tablas de Resultados
            col1, col2 = st.columns(2)
            
            with col1:
                st.write("**Balances de Materia**")
                # Extraer datos de corrientes de forma segura
                res_m = []
                for s in planta.streams:
                    if s.F_mass > 0.1:
                        res_m.append({
                            "Corriente": s.ID,
                            "Flujo (kg/h)": round(s.F_mass, 2),
                            "Temp (°C)": round(s.T - 273.15, 1),
                            "% ETOH": f"{(s.imass['Ethanol']/s.F_mass)*100:.1f}%" if s.F_mass > 0 else "0%"
                        })
                st.table(pd.DataFrame(res_m))

            with col2:
                st.write("**Balances de Energía**")
                # Extraer energía de forma segura
                res_e = []
                for u in planta.units:
                    # Sumatoria de servicios de calor
                    q_kw = sum([h.duty for h in u.heat_utilities]) / 3600
                    p_kw = u.power_utility.rate if u.power_utility else 0
                    if abs(q_kw) > 0.01 or p_kw > 0.01:
                        res_e.append({
                            "Equipo": u.ID,
                            "Calor (kW)": round(q_kw, 2),
                            "Potencia (kW)": round(p_kw, 2)
                        })
                st.table(pd.DataFrame(res_e))

            # 3. Integración con Gemini IA
            if "GEMINI_API_KEY" in st.secrets:
                st.divider()
                st.subheader("🤖 Consultoría IA (Tutor de Ingeniería)")
                try:
                    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
                    model = genai.GenerativeModel('gemini-1.5-flash')
                    
                    contexto = f"""
                    Como experto en termodinámica, analiza estos resultados:
                    MATERIA: {res_m}
                    ENERGÍA: {res_e}
                    Explica si la separación fue eficiente y sugiere una mejora.
                    """
                    response = model.generate_content(contexto)
                    st.info(response.text)
                except Exception as e:
                    st.error(f"Error IA: {e}")
            else:
                st.warning("⚠️ IA Desactivada: Registra tu GEMINI_API_KEY en los Secrets de Streamlit.")

        except Exception as ex:
            st.error(f"Error en la simulación: {ex}")
else:
    st.info("Ajusta los parámetros y presiona el botón para comenzar.")
