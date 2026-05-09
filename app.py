import streamlit as st
import biosteam as bst
import thermosteam as tmo
import pandas as pd
import google.generativeai as genai

# =================================================================
# 1. CONFIGURACIÓN DE PÁGINA Y ESTILO
# =================================================================
st.set_page_config(page_title="Planta Etanol ISO-Pro", layout="wide")

st.markdown("""
    <style>
    .metric-card {
        background-color: #ffffff;
        padding: 15px;
        border-radius: 10px;
        border-top: 4px solid #10b981;
        text-align: center;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        margin-bottom: 10px;
    }
    .metric-label { font-size: 0.8rem; color: #666; font-weight: bold; }
    .metric-value { font-size: 1.1rem; color: #111; font-weight: bold; }
    </style>
""", unsafe_allow_html=True)

# =================================================================
# 2. MOTOR DE CÁLCULO (Optimizado con BioSTEAM TEA)
# =================================================================
def ejecutar_simulacion(t_feed, p_v100, p_luz, p_vap, p_h2o, p_mosto, p_etanol):
    # Limpieza y configuración
    bst.main_flowsheet.clear()
    chemicals = tmo.Chemicals(["Water", "Ethanol"])
    tmo.settings.set_thermo(chemicals)
    
    # Precios de servicios (utilities)
    bst.settings.electricity_price = p_luz
    
    # Definición de Corrientes
    feed = bst.Stream('mosto', Water=900, Ethanol=100, units='kg/hr', T=t_feed+273.15, price=p_mosto)
    
    # Diseño de Proceso
    P1 = bst.Pump('P100', ins=feed, P=3*101325)
    W1 = bst.HXutility('W220', ins=P1-0, outs='S1', T=365.15)
    V1_valv = bst.IsenthalpicValve('V100_v', ins=W1-0, outs='S2', P=p_v100*101325)
    F1 = bst.Flash('V100', ins=V1_valv-0, outs=('Vapor', 'Liquido'), P=p_v100*101325, Q=0)
    
    # Definir el producto y su precio de venta
    W2 = bst.HXutility('W310', ins=F1-0, outs='Etanol_Destilado', T=298.15)
    W2.outs[0].price = p_etanol 
    
    P2 = bst.Pump('P200', ins=F1-1, outs='reciclo', P=101325)

    # Crear Sistema
    sys = bst.System('sys_etanol', path=(P1, W1, V1_valv, F1, W2, P2))
    sys.simulate()

    # --- ANÁLISIS ECONÓMICO (TEA) Basado en los documentos ---
    # Implementamos los parámetros del archivo "TEA (1).html"
    tea = bst.TEA(
        system=sys,
        IRR=0.15, # Tasa interna de retorno deseada (15%)
        duration=(2026, 2046), # 20 años de vida útil
        depreciation='MACRS7', # Método de depreciación estándar
        income_tax=0.30, # 30% de impuestos
        operating_days=330, # Días de operación anual
        lang_factor=4.0, # Factor de instalación para plantas de fluidos
        construction_schedule=(0.5, 0.5), # 2 años de construcción
        startup_VOCfrac=0.5,
        startup_FOCfrac=0.5,
        startup_salesfrac=0.5,
        WC_over_FCI=0.05 # 5% de capital de trabajo
    )

    # Cálculo de métricas finales
    npv = tea.NPV
    # El payback y ROI se calculan internamente tras resolver el flujo de caja
    try:
        sales = tea.sales
        costs = tea.VOC + tea.FOC
        net_earnings = sales - costs
        roi = (net_earnings / tea.TCI) * 100 if tea.TCI > 0 else 0
    except:
        roi = 0

    return sys, W2, tea, npv, roi

# =================================================================
# 3. INTERFAZ (SIDEBAR)
# =================================================================
with st.sidebar:
    st.header("⚙️ Variables de Proceso")
    s_tf = st.slider("Temp. Mosto (°C)", 15.0, 50.0, 25.0)
    s_pv = st.slider("Presión Flash V100 (atm)", 0.2, 1.8, 0.8)
    
    st.divider()
    st.header("💵 Mercado")
    s_pl = st.slider("Luz (USD/kWh)", 0.05, 0.45, 0.12)
    s_pm = st.slider("Costo Mosto (USD/kg)", 0.01, 0.35, 0.05)
    s_pe = st.slider("Venta Etanol (USD/kg)", 0.5, 3.0, 1.8)
    
    st.divider()
    tutor_on = st.toggle("🎓 Habilitar Tutor IA")
    btn = st.button("🚀 SIMULAR PROCESO", use_container_width=True)

# =================================================================
# 4. DASHBOARD DE RESULTADOS
# =================================================================
if btn:
    sys, prod, tea, vpn, roi = ejecutar_simulacion(s_tf, s_pv, s_pl, 25.0, 0.6, s_pm, s_pe)

    # 4.1 Indicadores de Corriente
    st.subheader("📦 Resultados de la Destilación")
    c1, c2, c3, c4 = st.columns(4)
    pureza = (prod.imass['Ethanol']/prod.F_mass)*100 if prod.F_mass > 0 else 0
    
    with c1: st.markdown(f"<div class='metric-card'><div class='metric-label'>Flujo Producto</div><div class='metric-value'>{prod.F_mass:.1f} kg/h</div></div>", unsafe_allow_html=True)
    with c2: st.markdown(f"<div class='metric-card'><div class='metric-label'>Pureza Etanol</div><div class='metric-value'>{pureza:.1f} %</div></div>", unsafe_allow_html=True)
    with c3: st.markdown(f"<div class='metric-card'><div class='metric-label'>Inversión (TCI)</div><div class='metric-value'>USD {tea.TCI/1e3:.1f}k</div></div>", unsafe_allow_html=True)
    with c4: st.markdown(f"<div class='metric-card'><div class='metric-label'>Costo Operativo</div><div class='metric-value'>USD {tea.AOC/1e3:.1f}k/año</div></div>", unsafe_allow_html=True)

    # 4.2 Indicadores Económicos Reales
    st.divider()
    f1, f2, f3 = st.columns(3)
    f1.metric("VPN (Valor Presente Neto)", f"{vpn/1000:.1f}k USD", delta=None if vpn > 0 else "No rentable")
    f2.metric("ROI Estimado", f"{roi:.2f} %")
    f3.metric("MPSP (Precio Mínimo)", f"USD {tea.solve_price(prod):.2f}/kg")

    # 4.3 Balances
    st.divider()
    t1, t2 = st.tabs(["📊 Balance de Materia", "⚡ Consumo Energético"])
    with t1:
        df_materia = pd.DataFrame([{"Corriente": s.ID, "Flujo (kg/h)": s.F_mass, "Etanol %": (s.imass['Ethanol']/s.F_mass*100 if s.F_mass>0 else 0)} for s in sys.streams])
        st.dataframe(df_materia, use_container_width=True)
    with t2:
        df_energia = pd.DataFrame([{"Equipo": u.ID, "Carga (kW)": sum([h.duty for h in u.heat_utilities])/3600} for u in sys.units])
        st.dataframe(df_energia, use_container_width=True)

    # 4.4 Tutor IA
    if tutor_on:
        st.divider()
        st.subheader("💬 Consulta al Tutor del Dr. Arzola")
        if "GEMINI_API_KEY" in st.secrets:
            genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
            model = genai.GenerativeModel('gemini-2.5-pro')
            # Contexto enriquecido con los datos de la simulación
            ctx = f"Simulación Etanol: VPN={vpn}, Pureza={pureza}%, ROI={roi}%. El usuario pregunta: "
            
            if prompt := st.chat_input("¿Qué significa que mi VPN sea negativo?"):
                res = model.generate_content(ctx + prompt)
                st.info(res.text)
        else:
            st.warning("Configura tu GEMINI_API_KEY en los secretos para usar el tutor.")
else:
    st.info("Ajuste los parámetros y presione el botón para iniciar el análisis tecno-económico.")
