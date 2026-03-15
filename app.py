import streamlit as st

# Verificación de librerías al inicio
try:
    import biosteam as bst
    import thermosteam as tmo
    import pandas as pd
    import google.generativeai as genai
except ImportError as e:
    st.error(f"Error de instalación: {e}. Revisa que 'packages.txt' y 'requirements.txt' estén en GitHub.")
    st.stop()

# Configuración de la interfaz
st.set_page_config(page_title="Simulador BioStream", layout="wide")

st.title("🧪 Simulador Industrial de Etanol")
st.markdown("---")

# --- Lógica de Simulación ---
def ejecutar_planta(agua, etanol, temp_ent):
    # Limpieza total del sistema previo
    bst.main_flowsheet.clear()
    
    # Termodinámica
    chemicals = tmo.Chemicals(["Water", "Ethanol"])
    bst.settings.set_thermo(chemicals)

    # Corrientes dinámicas
    mosto = bst.Stream("1-MOSTO", Water=agua, Ethanol=etanol, units="kg/hr", T=temp_ent + 273.15)
    vinazas_retorno = bst.Stream("Vinazas-Retorno", Water=200, T=95+273.15)

    # Diseño de equipos
    P100 = bst.Pump("P100", ins=mosto, P=4*101325)
    
    W210 = bst.HXprocess("W210", 
                         ins=(P100-0, vinazas_retorno), 
                         outs=("3-Mosto-Pre", "Drenaje"), 
                         phase0="l", phase1="l")
    W210.outs[0].T = 85 + 273.15

    W220 = bst.HXutility("W220", ins=W210-0, outs="Mezcla", T=92+273.15)
    V100 = bst.IsenthalpicValve("V100", ins=W220-0, outs="Mezcla-Bifasica", P=101325)
    
    # Flash: Adiabático (Q=0)
    V1 = bst.Flash("V1", ins=V100-0, outs=("Vapor", "Vinazas"), P=101325, Q=0)
    
    W310 = bst.HXutility("W310", ins=V1-0, outs="Producto-Final", T=25 + 273.15)
    P200 = bst.Pump("P200", ins=V1-1, outs=vinazas_retorno, P=3*101325)

    # Crear sistema y simular
    sys = bst.System("etanol_sys", path=(P100, W210, W220, V100, V1, W310, P200))
    sys.simulate()
    return sys

# --- Interfaz Lateral ---
st.sidebar.header("Parámetros de Proceso")
f_w = st.sidebar.slider("Flujo Agua (kg/h)", 500, 1500, 900)
f_e = st.sidebar.slider("Flujo Etanol (kg/h)", 10, 300, 100)
t_i = st.sidebar.slider("Temp. Entrada (°C)", 15, 40, 25)

if st.sidebar.button("Simular Ahora"):
    with st.spinner("Simulando balances..."):
        try:
            planta = ejecutar_planta(f_w, f_e, t_i)
            st.success("✅ Simulación Convergida")

            # 1. Diagrama de Flujo (DFP)
            st.subheader("Esquema del Proceso")
            dot = planta.diagram(format='dot', display=False)
            st.graphviz_chart(dot)

            # 2. Resultados en Tablas
            st.subheader("Resultados de la Operación")
            c1, c2 = st.columns(2)
            
            # Datos de corrientes
            datos_m = [{"Corriente": s.ID, "kg/h": round(s.F_mass, 1), "T(°C)": round(s.T-273.15, 1)} 
                       for s in planta.streams if s.F_mass > 0]
            
            # Datos de energía (Método seguro)
            datos_e = []
            for u in planta.units:
                duty = sum([hu.duty for hu in u.heat_utilities]) / 3600
                pwr = u.power_utility.rate if u.power_utility else 0
                if abs(duty) > 0.01 or pwr > 0.01:
                    datos_e.append({"Equipo": u.ID, "Calor (kW)": round(duty, 2), "Potencia (kW)": round(pwr, 2)})

            with c1:
                st.write("**Balances de Materia**")
                st.table(pd.DataFrame(datos_m))
            with c2:
                st.write("**Consumo Energético**")
                st.table(pd.DataFrame(datos_e))

            # 3. Tutor IA (Gemini)
            st.divider()
            if "GEMINI_API_KEY" in st.secrets:
                st.subheader("🤖 Análisis del Profesor IA")
                genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
                model = genai.GenerativeModel('gemini-1.5-flash')
                
                contexto = f"Resultados simulación: Materia {datos_m}, Energía {datos_e}. Explica qué pasa en el flash."
                response = model.generate_content(contexto)
                st.info(response.text)
            else:
                st.warning("IA: Configura GEMINI_API_KEY en Secrets.")

        except Exception as err:
            st.error(f"Error técnico: {err}")
else:
    st.info("Ajusta los parámetros y presiona 'Simular Ahora'.")
