import streamlit as st

# Intentar importar librerías y mostrar error amigable si fallan las dependencias
try:
    import biosteam as bst
    import thermosteam as tmo
    import pandas as pd
    import google.generativeai as genai
except ModuleNotFoundError as e:
    st.error(f"Falta una librería: {e}. Asegúrate de que el archivo requirements.txt esté en GitHub.")
    st.stop()

# =================================================================
# CONFIGURACIÓN DE PÁGINA
# =================================================================
st.set_page_config(page_title="BioSteam Web App", layout="wide")

st.title("🧪 Simulador Bioquímico de Etanol")
st.markdown("---")

# =================================================================
# LÓGICA DE SIMULACIÓN (Encapsulada para evitar ID duplicados)
# =================================================================
def run_biosteam_sim(flow_water, flow_ethanol, t_in_celsius):
    # Paso vital: Limpiar memoria de BIOSTEAM
    bst.main_flowsheet.clear()
    
    # Configuración de compuestos
    chemicals = tmo.Chemicals(["Water", "Ethanol"])
    bst.settings.set_thermo(chemicals)

    # Corrientes
    mosto = bst.Stream("mosto", Water=flow_water, Ethanol=flow_ethanol, 
                       units="kg/hr", T=t_in_celsius + 273.15)
    
    vinazas_retorno = bst.Stream("vinazas_retorno", Water=200, T=95+273.15)

    # Equipos
    P100 = bst.Pump("P100", ins=mosto, P=4*101325)
    W210 = bst.HXprocess("W210", ins=(P100-0, vinazas_retorno), 
                         outs=("mosto_pre","drenaje"), phase0="l", phase1="l")
    W210.outs[0].T = 85 + 273.15
    
    W220 = bst.HXutility("W220", ins=W210-0, outs="mezcla", T=92+273.15)
    V100 = bst.IsenthalpicValve("V100", ins=W220-0, outs="mezcla_bifasica", P=101325)
    V1 = bst.Flash("V1", ins=V100-0, outs=("vapor", "vinazas"), P=101325, Q=0)
    W310 = bst.HXutility("W310", ins=V1-0, outs="producto", T=25+273.15)
    P200 = bst.Pump("P200", ins=V1-1, outs=vinazas_retorno, P=3*101325)

    # Crear y simular sistema
    sys = bst.System("etanol_sys", path=(P100, W210, W220, V100, V1, W310, P200))
    sys.simulate()
    return sys

# =================================================================
# INTERFAZ DE USUARIO
# =================================================================
st.sidebar.header("⚙️ Parámetros de Simulación")
f_w = st.sidebar.slider("Agua (kg/h)", 500, 1500, 900)
f_e = st.sidebar.slider("Etanol (kg/h)", 10, 300, 100)
temp = st.sidebar.slider("Temperatura (°C)", 15, 45, 25)

if st.sidebar.button("🚀 Ejecutar Simulación"):
    with st.spinner("Procesando balances termodinámicos..."):
        try:
            planta = run_biosteam_sim(f_w, f_e, temp)
            st.success("Simulación finalizada")

            # Mostrar Diagrama de Flujo
            st.subheader("📊 Diagrama de Proceso")
            dot_data = planta.diagram(format='dot', display=False)
            st.graphviz_chart(dot_data)

            # Extraer Datos para tablas
            st.subheader("📋 Resultados del Balance")
            col1, col2 = st.columns(2)

            # Generar datos de corrientes
            materia = []
            for s in planta.streams:
                if s.F_mass > 0:
                    materia.append({"ID": s.ID, "Masa (kg/h)": round(s.F_mass, 2), "T (C)": round(s.T-273.15, 1)})
            
            # Generar datos de energía (Uso de heat_utilities para evitar errores de duty)
            energia = []
            for u in planta.units:
                q = sum([hu.duty for hu in u.heat_utilities]) / 3600
                if abs(q) > 0.1:
                    energia.append({"Equipo": u.ID, "Calor (kW)": round(q, 2)})

            with col1:
                st.write("**Materia:**")
                st.dataframe(pd.DataFrame(materia))
            with col2:
                st.write("**Energía:**")
                st.dataframe(pd.DataFrame(energia))

            # --- SECCIÓN DE IA ---
            st.markdown("---")
            if "GEMINI_API_KEY" in st.secrets:
                st.subheader("🤖 Análisis del Tutor IA")
                genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
                model = genai.GenerativeModel('gemini-1.5-flash')
                
                res_str = f"Materia: {materia}, Energía: {energia}"
                prompt = f"Analiza estos datos de simulación química y dame 3 consejos de optimización: {res_str}"
                
                response = model.generate_content(prompt)
                st.info(response.text)
            else:
                st.warning("⚠️ IA desactivada: Agrega GEMINI_API_KEY en los Secrets de Streamlit.")

        except Exception as ex:
            st.error(f"Hubo un error en los cálculos: {ex}")
else:
    st.info("Configura los valores a la izquierda y presiona el botón para iniciar.")
