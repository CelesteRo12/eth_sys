import streamlit as st

# --- Control de dependencias al inicio ---
try:
    import biosteam as bst
    import thermosteam as tmo
    import pandas as pd
    import google.generativeai as genai
except ImportError as e:
    st.error(f"❌ Error de dependencias: {e}")
    st.info("Asegúrate de tener 'packages.txt' y 'requirements.txt' correctamente en GitHub.")
    st.stop()

# =================================================================
# CONFIGURACIÓN DE LA APP
# =================================================================
st.set_page_config(page_title="Simulador Químico AI", layout="wide")

st.title("🧪 Planta de Etanol Interactiva")
st.markdown("---")

# =================================================================
# LÓGICA DE SIMULACIÓN (Encapsulada)
# =================================================================
def correr_simulacion(flow_agua, flow_etanol, temp_c):
    # 1. LIMPIEZA TOTAL: Evita el error de "Duplicate ID" en Streamlit
    bst.main_flowsheet.clear()
    
    # 2. TERMODINÁMICA
    chemicals = tmo.Chemicals(["Water", "Ethanol"])
    bst.settings.set_thermo(chemicals)

    # 3. CORRIENTES DINÁMICAS
    mosto = bst.Stream("1-MOSTO", Water=flow_agua, Ethanol=flow_etanol, 
                       units="kg/hr", T=temp_c + 273.15)
    
    vinazas_retorno = bst.Stream("Vinazas-Retorno", Water=200, T=95+273.15)

    # 4. EQUIPOS
    P100 = bst.Pump("P100", ins=mosto, P=4*101325)
    
    W210 = bst.HXprocess("W210", 
                         ins=(P100-0, vinazas_retorno), 
                         outs=("3-Precalentado", "Drenaje"), 
                         phase0="l", phase1="l")
    W210.outs[0].T = 85 + 273.15

    W220 = bst.HXutility("W220", ins=W210-0, outs="Mezcla", T=92+273.15)
    V100 = bst.IsenthalpicValve("V100", ins=W220-0, outs="Mezcla-Válvula", P=101325)
    
    # Flash: Definido como adiabático (Q=0)
    V1 = bst.Flash("V1", ins=V100-0, outs=("Vapor-Rico", "Vinazas-Fondo"), P=101325, Q=0)
    
    W310 = bst.HXutility("W310", ins=V1-0, outs="Etanol-Destilado", T=25 + 273.15)
    P200 = bst.Pump("P200", ins=V1-1, outs=vinazas_retorno, P=3*101325)

    # 5. SISTEMA
    sys = bst.System("etanol_sys", path=(P100, W210, W220, V100, V1, W310, P200))
    sys.simulate()
    return sys

# =================================================================
# INTERFAZ Y CONTROLES
# =================================================================
with st.sidebar:
    st.header("⚙️ Parámetros")
    f_w = st.number_input("Agua (kg/h)", 500, 2000, 900)
    f_e = st.number_input("Etanol (kg/h)", 10, 500, 100)
    t_in = st.slider("Temperatura (°C)", 10, 50, 25)
    boton = st.button("🚀 Ejecutar Simulación", use_container_width=True)

if boton:
    with st.spinner("Calculando balances de masa y energía..."):
        try:
            # Ejecución
            planta = correr_simulacion(f_w, f_e, t_in)
            st.success("¡Simulación completada!")

            # Visualización del Diagrama (Seguro para Web)
            st.subheader("📊 Diagrama de Flujo (DFP)")
            dot_data = planta.diagram(format='dot', display=False)
            st.graphviz_chart(dot_data)

            # Tablas de Resultados
            col1, col2 = st.columns(2)
            
            # Procesar Materia
            mat_res = [{"Stream": s.ID, "Flujo (kg/h)": round(s.F_mass, 2), "T (°C)": round(s.T-273.15, 1)} 
                       for s in planta.streams if s.F_mass > 0]
            
            # Procesar Energía (Evitando error de duty en Flash)
            en_res = []
            for u in planta.units:
                # Sumamos todos los heat_utilities del equipo
                calor = sum([hu.duty for hu in u.heat_utilities]) / 3600 # kJ/h a kW
                pwr = u.power_utility.rate if u.power_utility else 0
                if abs(calor) > 0.01 or pwr > 0.01:
                    en_res.append({"Equipo": u.ID, "Calor (kW)": round(calor, 2), "Potencia (kW)": round(pwr, 2)})

            with col1:
                st.write("**Balance de Materia**")
                st.dataframe(pd.DataFrame(mat_res), use_container_width=True)
            
            with col2:
                st.write("**Balance de Energía**")
                st.dataframe(pd.DataFrame(en_res), use_container_width=True)

            # --- SECCIÓN DE IA ---
            st.divider()
            if "GEMINI_API_KEY" in st.secrets:
                st.subheader("🤖 Consultoría con Tutor IA")
                try:
                    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
                    model = genai.GenerativeModel('gemini-1.5-flash')
                    
                    prompt = f"""
                    Eres un tutor de Ingeniería Química. Analiza estos resultados:
                    Materia: {mat_res}
                    Energía: {en_res}
                    Explica si la separación fue efectiva y sugiere un cambio técnico.
                    """
                    response = model.generate_content(prompt)
                    st.info(response.text)
                except Exception as e:
                    st.error(f"Error IA: {e}")
            else:
                st.warning("IA: No se encontró la GEMINI_API_KEY en los Secrets de Streamlit.")

        except Exception as ex:
            st.error(f"Error en la simulación: {ex}")
else:
    st.info("Modifica los valores en la barra lateral y presiona 'Ejecutar'.")
