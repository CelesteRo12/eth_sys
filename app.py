import streamlit as st
import biosteam as bst
import thermosteam as tmo
import pandas as pd
import google.generativeai as genai

# =================================================================
# 1. CONFIGURACIÓN DE PÁGINA
# =================================================================
st.set_page_config(page_title="Planta Etanol ISO v5.3", layout="wide")

# =================================================================
# 2. LÓGICA DE SIMULACIÓN (BioSTEAM) - VERSIÓN BLINDADA
# =================================================================
def simular_proceso_blindado(f_agua, f_etanol, t_feed, p_elec, p_mosto, p_etanol_v):
    # Paso 1: Limpieza absoluta del entorno
    bst.main_flowsheet.clear()
    
    # Paso 2: Termodinámica
    chemicals = tmo.Chemicals(["Water", "Ethanol"])
    bst.settings.set_thermo(chemicals)
    bst.settings.electricity_price = p_elec
    
    # Paso 3: Definición de Corrientes
    # Usamos nombres claros para evitar conflictos con clases
    stream_alimentacion = bst.Stream('Alim', Water=f_agua, Ethanol=f_etanol, units='kg/hr', T=t_feed+273.15, price=p_mosto)
    stream_reciclo = bst.Stream('Rec', Water=200, T=368.15)

    # Paso 4: Equipos (Nombres de variables únicos)
    equipo_bomba_1 = bst.Pump('P1', ins=stream_alimentacion, P=4*101325)
    
    equipo_hx_proceso = bst.HXprocess('W1', 
                                     ins=(equipo_bomba_1-0, stream_reciclo), 
                                     outs=('S1', 'S2'), 
                                     phase0='l', phase1='l')
    equipo_hx_proceso.outs[0].T = 358.15 # 85 C
    
    equipo_hx_utilidad = bst.HXutility('W2', ins=equipo_hx_proceso-0, outs='S3', T=365.15) # 92 C
    
    equipo_valvula = bst.IsenthalpicValve('V1', ins=equipo_hx_utilidad-0, outs='S4', P=101325)
    
    equipo_flash = bst.Flash('F1', ins=equipo_valvula-0, outs=('Vap', 'Liq'), P=101325, Q=0)
    
    equipo_condensador = bst.HXutility('W3', ins=equipo_flash-0, outs='Prod', T=298.15)
    
    equipo_bomba_2 = bst.Pump('P2', ins=equipo_flash-1, outs=stream_reciclo, P=3*101325)

    # Paso 5: Creación del Sistema
    sistema_iso = bst.System('etanol_iso', path=(equipo_bomba_1, equipo_hx_proceso, equipo_hx_utilidad, equipo_valvula, equipo_flash, equipo_condensador, equipo_bomba_2))
    
    # Simulación
    sistema_iso.simulate()
    
    # Cálculos económicos
    ingresos_h = equipo_condensador.outs[0].F_mass * p_etanol_v
    costos_utilidades_h = sistema_iso.get_utility_cost()
    costo_materia_h = stream_alimentacion.F_mass * p_mosto
    margen_h = ingresos_h - costos_utilidades_h - costo_materia_h

    return sistema_iso, equipo_condensador.outs[0], margen_h

# =================================================================
# 3. INTERFAZ (Sidebar)
# =================================================================
with st.sidebar:
    st.header("⚙️ Configuración")
    f_agua = st.slider("Agua (kg/h)", 500, 1500, 900)
    f_etanol = st.slider("Etanol (kg/h)", 10, 500, 100)
    t_feed = st.slider("T Entrada (°C)", 10, 50, 25)
    
    st.subheader("💰 Precios")
    p_elec = st.slider("Luz (USD/kWh)", 0.05, 0.5, 0.12)
    p_mosto = st.slider("Mosto (USD/kg)", 0.01, 0.4, 0.06)
    p_etanol_v = st.slider("Etanol (USD/kg)", 0.5, 3.0, 1.5)
    
    st.divider()
    tutor_ia = st.toggle("🎓 Modo Tutor IA")
    btn = st.button("🚀 ACTUALIZAR", use_container_width=True)

# =================================================================
# 4. DASHBOARD
# =================================================================
if btn:
    try:
        sys, prod, margen = simular_proceso_blindado(f_agua, f_etanol, t_feed, p_elec, p_mosto, p_etanol_v)
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Producción", f"{prod.F_mass:.1f} kg/h")
        pureza = (prod.imass['Ethanol']/prod.F_mass)*100 if prod.F_mass > 0 else 0
        c2.metric("Pureza", f"{pureza:.1f} %")
        c3.metric("Margen", f"{margen:.2f} USD/h")

        st.divider()
        t1, t2 = st.tabs(["Materia", "Energía"])
        
        with t1:
            st.table(pd.DataFrame([{"ID": s.ID, "kg/h": round(s.F_mass, 1)} for s in sys.streams if s.F_mass > 0.1]))
            
        with t2:
            # EXTRACCIÓN SEGURA DE ENERGÍA
            data_e = []
            for u in sys.units:
                # Aquí evitamos el error usando el atributo nativo heat_utilities
                # de forma protegida
                hu_list = getattr(u, 'heat_utilities', [])
                q_kw = sum([h.duty for h in hu_list]) / 3600
                if abs(q_kw) > 0.001 or u.power_utility.rate > 0:
                    data_e.append({
                        "Unidad": u.ID,
                        "Calor (kW)": round(q_kw, 2),
                        "Costo (USD/h)": round(u.utility_cost, 3)
                    })
            st.table(pd.DataFrame(data_e))
            
        st.session_state.contexto = f"Planta operando con margen de {margen:.2f} USD/h y pureza de {pureza:.1f}%."

    except Exception as e:
        st.error(f"Error detectado: {e}")

# =================================================================
# 5. VENTANA DE CHAT (Tutor)
# =================================================================
if tutor_ia:
    st.divider()
    st.subheader("💬 Ventana de Contexto: Tutor IA")
    
    if "chat_history" not in st.session_state: st.session_state.chat_history = []
    
    for m in st.session_state.chat_history:
        with st.chat_message(m["role"]): st.markdown(m["content"])

    if p := st.chat_input("Dime cómo mejorar la pureza..."):
        st.session_state.chat_history.append({"role": "user", "content": p})
        with st.chat_message("user"): st.markdown(p)
        
        if "GEMINI_API_KEY" in st.secrets:
            genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
            model = genai.GenerativeModel('gemini-2.5-pro')
            res = model.generate_content(f"Datos: {st.session_state.get('contexto')}. Pregunta: {p}")
            with st.chat_message("assistant"): st.markdown(res.text)
            st.session_state.chat_history.append({"role": "assistant", "content": res.text})
        else:
            st.warning("Falta la API KEY en los Secrets.")
