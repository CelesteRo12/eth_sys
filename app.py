import streamlit as st

# Verificación de librerías
try:
    import biosteam as bst
    import thermosteam as tmo
    import pandas as pd
    import google.generativeai as genai
except ImportError as e:
    st.error(f"Error de librerías: {e}")
    st.info("Revisa que tu archivo requirements.txt solo tenga 'biosteam' sin versión fija.")
    st.stop()

# =================================================================
# CONFIGURACIÓN DE LA INTERFAZ
# =================================================================
st.set_page_config(page_title="BioSteam Expert App", layout="wide")

st.title("⚗️ Simulador de Bioprocesos Interactivo")
st.markdown("---")

# =================================================================
# NÚCLEO DE LA SIMULACIÓN
# =================================================================
def ejecutar_modelo(flujo_h2o, flujo_etoh, temperatura_c):
    # Paso 1: Reset del Flowsheet (Evita IDs duplicados en Streamlit)
    bst.main_flowsheet.clear()
    
    # Paso 2: Configuración Termodinámica
    chemicals = tmo.Chemicals(["Water", "Ethanol"])
    bst.settings.set_thermo(chemicals)

    # Paso 3: Definición de Corrientes
    mosto = bst.Stream("1_MOSTO", 
                       Water=flujo_h2o, 
                       Ethanol=flujo_etoh, 
                       units="kg/hr", 
                       T=temperatura_c + 273.15)
    
    vinazas_rec = bst.Stream("Reciclo_Vinazas", Water=200, T=95+273.15)

    # Paso 4: Arquitectura de Equipos
    P100 = bst.Pump("P100", ins=mosto, P=4*101325)
    
    W210 = bst.HXprocess("W210", 
                         ins=(P100-0, vinazas_rec), 
                         outs=("Mosto_Pre", "Drenaje"), 
                         phase0="l", phase1="l")
    W210.outs[0].T = 85 + 273.15

    W220 = bst.HXutility("W220", ins=W210-0, outs="Mezcla_Hot", T=92+273.15)
    V100 = bst.IsenthalpicValve("V100", ins=W220-0, outs="Mezcla_V", P=101325)
    
    # Separador Flash Adiabático
    V1 = bst.Flash("V1", ins=V100-0, outs=("Vapor_Etanol", "Vinazas_Fondo"), P=101325, Q=0)
    
    W310 = bst.HXutility("W310", ins=V1-0, outs="Destilado_Final", T=25 + 273.15)
    P200 = bst.Pump("P200", ins=V1-1, outs=vinazas_rec, P=3*101325)

    # Paso 5: Simulación del Sistema
    sys = bst.System("etanol_sys", path=(P100, W210, W220, V100, V1, W310, P200))
    sys.simulate()
    return sys

# =================================================================
# INTERFAZ DE USUARIO (SIDEBAR)
# =================================================================
with st.sidebar:
    st.header("⚙️ Ajustes de Operación")
    h2o = st.slider("Agua en alimentación (kg/h)", 500, 1500, 900)
    etoh = st.slider("Etanol en alimentación (kg/h)", 10, 400, 100)
    t_in = st.number_input("Temperatura Entrada (°C)", 10, 50, 25)
    
    st.markdown("---")
    simular = st.button("🚀 Iniciar Simulación", use_container_width=True)

# =================================================================
# RESULTADOS
# =================================================================
if simular:
    with st.spinner("Calculando balances termodinámicos..."):
        try:
            planta = ejecutar_modelo(h2o, etoh, t_in)
            st.success("¡Simulación finalizada con éxito!")

            # 1. Visualización del Diagrama
            st.subheader("📊 Diagrama de Flujo de Proceso")
            dot_code = planta.diagram(format='dot', display=False)
            st.graphviz_chart(dot_code)

            # 2. Tablas de Balance
            col1, col2 = st.columns(2)
            
            with col1:
                st.write("**Balance de Materia**")
                # Extraemos datos de corrientes con flujo
                df_m = pd.DataFrame([
                    {"Corriente": s.ID, "Flujo (kg/h)": round(s.F_mass, 2), "T (°C)": round(s.T-273.15, 1)}
                    for s in planta.streams if s.F_mass > 0.1
                ])
                st.dataframe(df_m, hide_index=True, use_container_width=True)

            with col2:
                st.write("**Balance de Energía**")
                # Cálculo robusto de energía térmica y eléctrica
                datos_e = []
                for u in planta.units:
                    q_kw = sum([h.duty for h in u.heat_utilities]) / 3600
                    p_kw = u.power_utility.rate if u.power_utility else 0
                    if abs(q_kw) > 0.01 or p_kw > 0.01:
                        datos_e.append({"Equipo": u.ID, "Calor (kW)": round(q_kw, 2), "Potencia (kW)": round(p_kw, 2)})
                
                st.dataframe(pd.DataFrame(datos_e), hide_index=True, use_container_width=True)

            # 3. Integración con Gemini IA
            if "GEMINI_API_KEY" in st.secrets:
                st.markdown("---")
                st.subheader("🤖 Consultoría IA (Gemini)")
                try:
                    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
                    model = genai.GenerativeModel('gemini-1.5-flash')
                    
                    # Preparamos el contexto para la IA
                    prompt = f"""
                    Actúa como un Ingeniero Químico experto. Analiza estos datos:
                    MATERIAL: {df_m.to_dict()}
                    ENERGÍA: {datos_e}
                    Resume en 3 puntos: 
                    1. ¿Es eficiente la separación de etanol?
                    2. ¿Qué equipo consume más energía?
                    3. Una sugerencia para bajar costos operativos.
                    """
                    respuesta = model.generate_content(prompt)
                    st.info(respuesta.text)
                except Exception as e:
                    st.error(f"Error al conectar con la IA: {e}")
            
        except Exception as ex:
            st.error(f"Error crítico en la simulación: {ex}")
else:
    st.info("⬅️ Ajusta los parámetros en el panel izquierdo y haz clic en 'Simular'.")
