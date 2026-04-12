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
#====================================================================
#MÓDULO DE EVALUACIÓN TÉCNICA Y ECONÓMICA
#====================================================================

#Objetivos
#1. Leer los tamaños de los equipos (Ingeniería de Detalle).
#2. Calcular cuánto cuesta la planta (CAPEX) usando el Factor de Lang
#3. Calcular cuánto cuesta operar la planta (OPEX).
#4. Determinar si el negocio es rentable (ROI y Payback)

print("\n>>>> INICIANDO MÓDULO DE ANÁLISIS INTEGRAL....")
#====================================================================
#PASO 0: VERIFICAMOS LA SIMULACIÓN
#====================================================================
#El costo de los equipos es función del tamaño
#Por ejemplo,
#- No puedes cotizar un tanque si no sabes su volumen
#- No puedes cotizar un intercambiador de calor si no sabes su área de transferencia

try:
  eth_sys.simulate()
except:
  pass #Si ya estaba simulado

#=====================================================================
#PASO 0.5: REPORTE DE INGENIERÍA DE DETALLE (PARÁMETROS DE DISEÑO)
#=====================================================================
#Aquí respondemos ¿Qué tan grandes son los equipos?
#Biosteam una vez que realiza los balances de materia y energía, hace el cálculo
#de los parámetros de diseño y los guarda en un objeto "design_results"

print("\n" + "="*60)
print(" Reporte de ingeniería de detalle (dimensionamiento)")
print("\n" + "="*60)

for equipo in eth_sys.units:
  #Usamos hasattr para preguntar ¿Este equipo tiene resultados de diseño?
  if hasattr(equipo, "design_results") and equipo.design_results:
    print(f"\n Equipo: {equipo.ID} ({equipo.__class__.__name__})")

    #BUCLE FOR: Recorreemos cada parámetro calculado (área, potencia, etc)
    for parametro, valor in equipo.design_results.items():
      val_str = f"{valor:,.2f}" if isinstance(valor, float) else str(valor)

      #Biosteam calcula en unidades americanas por defecto para el diseño
      unidad=""
      definicion=""

      if "Area" in parametro:
        unidad ="ft2"
        definicion="Área de transferencia de calor"
      elif "Power" in parametro or "duty" in parametro:
        unidad="HP"
        definicion="Potencia del motor"
      elif "Volume" in parametro:
        unidad="ft3"
        definicion="Volumen o capacidad del tanque"
      elif "Pressure" in parametro:
        unidad="psi"
        definicion="Caída de presión/Delta P"
      elif "Material" in parametro:
        unidad="" #El material es texto, no tiene unidad numérica
        definicion="(Material de Construcción-Afecta el costo)"

      #IMPRESIÓN FORMATEADA
      print(f"        {parametro:<25}: {val_str} {unidad:<5} {definicion}")

#====================================================================
#PASO 1: VARIABLES DE MERCADO (INPUTS EXTERNOS)
#====================================================================
#Son variables externas.  El ingeniero de diseño NO tiene control
#sobre ellas, las dicta el mercado internacional o los proveedores locales

precio_luz = 0.085 #$/kWh (Tarifa Industrial media -CFE)
precio_vapor = 0.025 #$/MJ (Costo por generar vapor: Gas natural + Agua)
precio_agua = 0.0005 #$/MJ (Costo de bombeo y químicos de torre de enfriamiento)
precio_mosto = 0.0005 #$/kg  (Costo de materia prima)
precio_etanol = 100.2 #$/kg (Precio de venta-Determina los ingresos)

#======================================================================
#PASO 2: CÁLCULO DE INVERSIÓN DE CAPITAL (CAPEX)
#======================================================================
#CAPEX (Capital Expenditures)
#Es la inversión inicial. El dinero que necesitas tener en el banco ANTES
#de empezar a producir la primera gota de mosto concentrado.

print("\n" + "="*60)
print(" Análisis de inversión (CAPEX)")
print("="*60)

costo_equipos=0.0

print("\n--A. COSTO DE COMPRA DE EQUIPOS (PRECIO FOB)---")
#Costo FOB (Free On Board)
#Es el costo de la máquina "puesta en la fábrica del vendedor"
#NO INCLUYE: Flete, Grúas, Instalación, tubería.....

#¿Cómo calcula el software?-->Formula de Williams
#Usa la "Ley de potencia" (Economy of scale):
#Costo=Costo_base*(Capacidad/Capacidad_base)^0.6
#Donde la potencia es un exponente que puede varía entre 0.3 y 1
for unidad in eth_sys.units:
  #Filtro
  if hasattr(unidad, "purchase_cost") and unidad.purchase_cost is not None:
    precio_individual = unidad.purchase_cost
    print(f"{unidad.ID:<10}: ${precio_individual:,.0f}")
    costo_equipos += precio_individual

#=========================================================================
#EL FACTOR DE LANG (HANS LANG, 1950)
#=========================================================================
#El factor de lang estima los "Costos de Planta instalada" (ISBL)
#Multiplicamos el costo de los equipos FOB por un factor.

#Desgloce del factor (Típico 4 para fluidos):
# +1.0: Equipos (lo que viene en el FOB)
# +0.4: Tuberías (Es muy caro)
# +0.35: Instrumentación y Control (Sensores, EP, EF, etc.)
# +0.1: Electrico (Subestaciones, Cables)
# +0.2: Obra civil (edificios, concreto)
# +0.3: Ingeniería y Supervisión
# +0.65: Contingencias y Costos de construcción
# =4.0 (Total aproximado)

factor_de_lang=4.0
inversion_total = costo_equipos*factor_de_lang

print(f" SUMA DE EQUIPOS (FOB) ${costo_equipos:,.2f}")
print(f" FACTO DE LANG (Instalación): x {factor_de_lang:,.2f}")
print(f" INVERSIÓN TOTAL ESTIMADA: ${inversion_total:,.2f} USD")

#==========================================================================
#PASO 3. CÁLCULO DE OPERACIÓN (OPEX)
#==========================================================================
#Definición: OPEX (Operating Expenditures)
#Es el costo de "mantener las luces encendidas". Se gasta hora tras hora.
#Incluye: Costos variables (Materia prima, Energía-servicios auxiliares) y Fijo (Mano de obra)

print("\n" + "="*60)
print(" ANÁLISIS OPERATIVO (OPEX Y FLUJO DE CAJA)")
print("\n" + "="*60)

#A. COSTO DE MATERIA PRIMA (VARIABLE)
#Flujo (kg/h)*Precio ($/kg)
gasto_mosto=mosto.F_mass*precio_mosto

#B. COSTO DE SERVICIOS (ENERGÍA)
#Suma manual del consumo de cada equipo de forma invidual
consumo_luz_kw = 0.0
consumo_calor_mj = 0.0
consumo_frio_mj = 0.0

for u in eth_sys.units:
  #1. Electricidad (Motores)
  if u.power_utility:
    consumo_luz_kw += u.power_utility.rate
  #2. Calor y frío (Intercambiadores)
  for hu in u.heat_utilities:
    #El duty en Biosteam suele estar en kJ/h
    #Lo convertimos entonces en MJ/h dividiendo entre 1000
    duty_mj=hu.duty/1000

    if duty_mj >0:
      consumo_calor_mj += duty_mj  #(+)Vapor (Calentamiento)
    elif duty_mj < 0:
      consumo_frio_mj += abs(duty_mj) #(-) Agua (Enfriamiento)

#Convertimos energía física en dinero ($)
costo_luz = consumo_luz_kw*precio_luz
costo_calor = consumo_calor_mj*precio_vapor
costo_frio = consumo_frio_mj*precio_agua
total_servicios = costo_luz + costo_calor + costo_frio

#C. VENTAS (INGRESOS BRUTOS)
ventas_etanol = W310.outs[0].F_mass*precio_etanol

#===================================================================
#PASO 4. RESULTADOS E INDICADORES DE RENTABILIDAD
#===================================================================
#Balance de caja por hora
ganancia_hora = ventas_etanol - (gasto_mosto + total_servicios)

print(f"      (-) Materia Prima:               ${gasto_mosto:,.4f}/h")
print(f"      (-) Electricidad:                ${costo_luz:,.4f}/h")
print(f"      (-) Vapor (Calentamiento)        ${costo_calor:,.4f}/h")
print(f"      (-) Agua (Enfriamiento)          ${costo_frio:,.4f}/h")
print(f"      ------------------------------------------------------")
print(f"       TOTAL GASTO (Salidas)           ${gasto_mosto + total_servicios:,.4f}/h")
print(f"\n    (+) VENTAS (Entradas)            ${ventas_etanol:,.4f}/h")
print(f"      ------------------------------------------------------")

#LÓGICA DE DIAGNÓSTICO FINAL
if ganancia_hora > 0:
  print(f" >>>>>FLUJO NETO:               ${ganancia_hora:,.4f}/h  (✅Ganancia)")
  #-----CÁLCULO DE ROI (RETORNO DE INVERSIÓN)---------
  #Definición: ROI (Return of Investment)
  #Fórmula: (Ganancial Anual/Inversión Total)*100
  #Nos dice el % de la inversión  que recuperaremos cada año

  #SUPUESTO: Año operativo de 330 días (7920 h).
  #Los restantes 35 días son para mantenimiento o limpieza
  horas_anuales= 7920
  ganancia_anual = horas_anuales*ganancia_hora

  if inversion_total > 0:
    roi = (ganancia_anual/inversion_total)*100

    #DEFINICIÓN: PAYBACK PERIOD (TIEMPO DE RECUPERACIÓN)
    #Años necesarios para que la suma de ganancia iguale a la inversión inicial
    tiempo_recuperacion = 100/roi

    print(f"\n     >>>>📊INDICADORES FINANCIEROS CLAVE:")
    print(f"           1. Ganancia Anual:          ${ganancia_anual:,.4f}/año")
    print(f"           2. ROI:                      {roi:,.1} % Anual")
    print(f"           3. Payback:                  {tiempo_recuperacion:,.4f} años")

    #Semáforo de inversión
    if roi > 25:
      print("                VEREDICTO: 🟢 EXCELENTE (Alta rentabilidad)")
    elif roi >10:
      print("                VEREDICTO: 🟡 ACEPTABLE (Rentabilidad estándar)")
    else:
      print("                VEREDICTO: 🔴 BAJO (Es mejor meter el dinero al banco)")
  else:
    print("   ☢ Error: Inversión es cero. Revise el costo de equipos")
else:
  print(f"   >>>>FLUJO NETO:          ${ganancia_hora:,.4f}/h (💔 PÉRDIDA)")
  print(f"       El proceso quema dinero. Posibles causas:")
  print(f"       1. Ineficiencia energética (estamos gastando demasiado vapor)")
  print(f"       2. Margen bruto negativo (Mosto es muy caro o etanol muy barato)")
    

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
