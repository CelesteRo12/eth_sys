import streamlit as st
import biosteam as bst
import thermosteam as tmo
import pandas as pd
import google.generativeai as genai

# =================================================================
# 1. CONFIGURACIÓN DE LA PÁGINA Y ESTILOS
# =================================================================
st.set_page_config(page_title="BioProcesos Interactivos", layout="wide")

st.title("Simulador de Recuperación de Etanol")
st.markdown("""
Esta aplicación simula un proceso de separación de etanol/agua utilizando **BIOSTEAM** y proporciona análisis técnico mediante **IA (Gemini)**.
""")

# =================================================================
# 2. LÓGICA DE LA SIMULACIÓN (ENCAPSULADA)
# =================================================================
def ejecutar_simulacion(f_agua, f_etanol, t_entrada, p_flash):
    """
    Encapsula la lógica de BIOSTEAM. 
    Limpia el flowsheet en cada ejecución para evitar errores de ID duplicados.
    """
    # IMPORTANTE: Limpiar el flowsheet global antes de crear nuevos equipos
    bst.main_flowsheet.clear() 
    
    # Definición de compuestos y termodinámica
    chemicals = tmo.Chemicals(["Water", "Ethanol"])
    bst.settings.set_thermo(chemicals)

    # Corrientes de entrada con parámetros dinámicos
    mosto = bst.Stream("1_MOSTO", 
                       Water=f_agua, Ethanol=f_etanol, units="kg/hr",
                       T=t_entrada + 273.15, P=101325)

    vinazas_retorno = bst.Stream("Vinazas_Retorno", 
                                 Water=200, Ethanol=0, units="kg/hr",
                                 T=95 + 273.15, P=300000)

    # Unidades de Proceso
    P100 = bst.Pump("P100", ins=mosto, P=4*101325)
    
    W210 = bst.HXprocess("W210", 
                         ins=(P100-0, vinazas_retorno), 
                         outs=("3_Mosto_Pre", "Drenaje"), 
                         phase0="l", phase1="l")
    W210.outs[0].T = 85 + 273.15

    W220 = bst.HXutility("W220", ins=W210-0, outs="Mezcla", T=92+273.15)
    
    V100 = bst.IsenthalpicValve("V100", ins=W220-0, outs="Mezcla_Bifasica", P=p_flash * 101325)

    # Tanque Flash: Q=0 asegura balance adiabático
    V1 = bst.Flash("V1", ins=V100-0, outs=("Vapor_Caliente", "Vinazas"), P=p_flash * 101325, Q=0)

    W310 = bst.HXutility("W310", ins=V1-0, outs="Producto_Final", T=25 + 273.15)

    P200 = bst.Pump("P200", ins=V1-1, outs=vinazas_retorno, P=3*101325)

    # Crear Sistema y Simular
    eth_sys = bst.System("planta_etanol", path=(P100, W210, W220, V100, V1, W310, P200))
    
    try:
        eth_sys.simulate()
        return eth_sys, None
    except Exception as e:
        return None, str(e)

# =================================================================
# 3. GENERACIÓN DE REPORTES (MANEJO DE ERRORES DE ENERGÍA)
# =================================================================
def generar_tablas(sistema):
    # Tabla de Materia
    datos_mat = []
    for s in sistema.streams:
        if s.F_mass > 0.01:
            datos_mat.append({
                "ID": s.ID,
                "T (°C)": round(s.T - 273.15, 2),
                "P (bar)": round(s.P / 1e5, 2),
                "Flujo (kg/h)": round(s.F_mass, 2),
                "% Etanol": f"{(s.imass['Ethanol']/s.F_mass)*100:.1f}%" if s.F_mass > 0 else "0%"
            })
    df_mat = pd.DataFrame(datos_mat)

    # Tabla de Energía (Uso de heat_utilities para evitar errores de .duty)
    datos_en = []
    for u in sistema.units:
        # Sumar todos los servicios de calor del equipo
        duty_total = sum([hu.duty for hu in u.heat_utilities]) / 3600 # kW
        pwr = u.power_utility.rate if u.power_utility else 0
        
        if abs(duty_total) > 0.01 or pwr > 0.01:
            datos_en.append({
                "Equipo": u.ID,
                "Calor (kW)": round(duty_total, 2),
                "Potencia (kW)": round(pwr, 2)
            })
    df_en = pd.DataFrame(datos_en)
    
    return df_mat, df_en

# =================================================================
# 4. INTERFAZ DE USUARIO (SIDEBAR)
# =================================================================
st.sidebar.header("Parámetros de Operación")
f_agua = st.sidebar.number_input("Flujo Agua (kg/h)", 500, 2000, 900)
f_etanol = st.sidebar.number_input("Flujo Etanol (kg/h)", 10, 500, 100)
t_in = st.sidebar.slider("Temperatura Entrada (°C)", 10, 50, 25)
p_flash = st.sidebar.slider("Presión en Flash (atm)", 0.1, 2.0, 1.0)

# =================================================================
# 5. EJECUCIÓN Y VISUALIZACIÓN
# =================================================================
if st.sidebar.button("Simular Proceso"):
    with st.spinner("Calculando balances..."):
        sistema, error = ejecutar_simulacion(f_agua, f_etanol, t_in, p_flash)
        
        if error:
            st.error(f"Error en la simulación: {error}")
        else:
            st.success("¡Simulación completada con éxito!")
            
            # Mostrar Diagrama (Renderizado directo en Web)
            st.subheader("Diagrama de Flujo de Proceso (DFP)")
            try:
                # Obtenemos el objeto graphviz y lo pasamos a streamlit
                dot = sistema.diagram(format='dot', display=False)
                st.graphviz_chart(dot)
            except Exception as e:
                st.warning(f"No se pudo renderizar el diagrama: {e}")

            # Mostrar Tablas
            col1, col2 = st.columns(2)
            df_m, df_e = generar_tablas(sistema)
            
            with col1:
                st.write("**Balance de Materia**")
                st.dataframe(df_m, use_container_width=True)
            
            with col2:
                st.write("**Balance de Energía**")
                st.dataframe(df_e, use_container_width=True)

            # --- INTEGRACIÓN CON GEMINI IA ---
            st.divider()
            st.subheader("🤖 Consultar al Tutor de Ingeniería Química")
            
            if "GEMINI_API_KEY" in st.secrets:
                try:
                    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
                    model = genai.GenerativeModel('gemini-2.5-pro')
                    
                    prompt = f"""
                    Actúa como un profesor experto en termodinámica. 
                    Analiza estos datos de una simulación de separación de etanol:
                    MATERIAL: {df_m.to_json()}
                    ENERGÍA: {df_e.to_json()}
                    
                    1. Explica brevemente si la separación es eficiente según la concentración de la corriente 'Vapor_Caliente'.
                    2. Comenta sobre el consumo energético de las unidades.
                    3. Sugiere una mejora técnica.
                    Mantenlo técnico pero pedagógico.
                    """
                    
                    if st.button("Generar Análisis de IA"):
                        response = model.generate_content(prompt)
                        st.info(response.text)
                except Exception as e:
                    st.error(f"Error al conectar con Gemini: {e}")
            else:
                st.warning("Configura tu GEMINI_API_KEY en los Secrets de Streamlit para activar el tutor.")
else:
    st.info("Ajusta los parámetros en la barra lateral y presiona 'Simular Proceso'.")
