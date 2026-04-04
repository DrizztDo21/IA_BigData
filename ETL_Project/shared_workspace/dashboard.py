import streamlit as st
from cassandra.cluster import Cluster
import networkx as nx
from pyvis.network import Network
import streamlit.components.v1 as components
import pandas as pd
import time
import os

st.set_page_config(page_title="SOC Ecommerce - Lambda", layout="wide")
st.title("🛡️ Centro de Control E-commerce (Arquitectura Lambda)")

# --- CONEXIONES ---
@st.cache_resource
def init_connection():
    cluster = Cluster(['cassandra-db'], port=9042)
    return cluster.connect('ecommerce')

session = init_connection()

# --- PESTAÑAS ---
tab_batch, tab_realtime = st.tabs(["📚 Cierre Diario (Batch Layer)", "⚡ Tiempo Real (Speed Layer)"])

# ==========================================
# PESTAÑA 1: BATCH LAYER (Cierre Nocturno)
# ==========================================
with tab_batch:
    st.header("Resumen del Cierre Nocturno (Hive / HDFS)")
    csv_path = "/opt/workspace/resumen_batch.csv"
    
    if os.path.exists(csv_path):
        df_batch = pd.read_csv(csv_path)
        st.success("Datos sincronizados con el último cierre de Airflow.")
        
        col_b1, col_b2 = st.columns([1, 2])
        with col_b1:
            st.dataframe(df_batch, use_container_width=True, hide_index=True)
        with col_b2:
            st.bar_chart(df_batch.set_index("card_country"))
    else:
        st.info("Esperando a que Airflow ejecute el cierre nocturno...")

    st.markdown("---")
    st.subheader("🕸️ Topología de la Red de Fraude")
    csv_grafos = "/opt/workspace/nodos_calientes.csv"
    
    if os.path.exists(csv_grafos):
        df_grafos = pd.read_csv(csv_grafos)
        
        tipo_nodo = st.radio("Filtrar por tipo de nodo:", ["TODOS", "IP", "USUARIO", "PAIS"], horizontal=True)
        
        if tipo_nodo != "TODOS":
            df_filtered = df_grafos[df_grafos['tipo'] == tipo_nodo]
        else:
            df_filtered = df_grafos

        col_g1, col_g2 = st.columns([1, 1])
        
        with col_g1:
            st.write(f"**Nodos con mayor centralidad ({tipo_nodo})**")
            def color_nodos(val):
                color = '#ff4b4b' if val == 'PAIS' else '#0068c9' if val == 'USUARIO' else '#ffaa00'
                return f'color: {color}; font-weight: bold'
            
            st.dataframe(df_filtered.style.map(color_nodos, subset=['tipo']), use_container_width=True, hide_index=True)

        with col_g2:
            st.write("**Gráfico de Conexiones Totales (Degrees)**")
            st.bar_chart(df_filtered.set_index("id")["degree"])
            
    st.markdown("---")
    st.subheader("🛡️ Triage Automático de Comunidades (Fraud Rings)")

    try:
        df_comunidades = pd.read_csv("/opt/workspace/redes_detectadas.csv")

        def clasificar_amenaza(miembros):
            lista_nodos = [nodo.strip() for nodo in str(miembros).upper().split(",")]
            miembros_str = str(miembros).upper()
            
            # Si hay usuarios etiquetados como fraude o nuestra IP de botnet conocida
            if "FRAUD_" in miembros_str or "222.15." in miembros_str:
                return "🔴 CRÍTICO: Red Criminal"
                
            # Si vemos una plaga de invitados (Scraping o Credential Stuffing)
            elif "GUEST_" in miembros_str:
                return "🟠 ALTO: Botnet / Scraper"
                
            # Si es un grupo enorme pero solo unido por el país, y sin fraude
            elif any(pais in lista_nodos for pais in ["ES", "FR", "IT", "DE", "US", "UK", "CN", "RU"]):
                return "🟢 SEGURO: Geografía Legítima"
                
            # Grupos pequeñitos (routers domésticos, oficinas)
            else:
                return "🟡 INFO: IP Doméstica Compartida"

        # Aplicamos la regla a la columna
        df_comunidades['Nivel_Amenaza'] = df_comunidades['miembros'].apply(clasificar_amenaza)

        col_f1, col_f2 = st.columns(2)
        with col_f1:
            # Por defecto, ocultamos lo seguro y lo informativo
            mostrar_seguros = st.checkbox("Mostrar tráfico seguro y doméstico", value=False)

        if not mostrar_seguros:
            df_filtrado = df_comunidades[df_comunidades['Nivel_Amenaza'].str.contains("🔴|🟠")]
        else:
            df_filtrado = df_comunidades

        st.write(f"Mostrando **{len(df_filtrado)}** comunidades de interés:")
        
        # Reordenamos las columnas para que la amenaza salga la primera
        df_mostrar = df_filtrado[['Nivel_Amenaza', 'component', 'num_entidades', 'miembros']]
        df_mostrar.columns = ['Severidad', 'ID Comunidad', 'Nº Nodos', 'Entidades Implicadas']
        
        st.dataframe(df_mostrar, use_container_width=True, hide_index=True)

    except Exception as e:
        st.warning("Aún no hay datos de comunidades detectadas. Ejecuta el proceso Batch.")
        st.error(f"Detalle técnico: {e}")
    

    st.markdown("---")
    st.subheader("🕸️ Análisis Forense Interactivo")

    # Filtramos solo las comunidades peligrosas para no saturar el selector
    comunidades_peligrosas = df_comunidades[df_comunidades['Nivel_Amenaza'].str.contains("🔴|🟠|🟢")]

    if not comunidades_peligrosas.empty:
        opciones = comunidades_peligrosas['component'].astype(str) + " - " + comunidades_peligrosas['Nivel_Amenaza']
        seleccion = st.selectbox("Selecciona una red criminal para analizar su topología:", opciones.tolist())
        
        id_seleccionado = int(seleccion.split(" - ")[0])
        
        miembros_str = df_comunidades[df_comunidades['component'] == id_seleccionado]['miembros'].values[0]
        lista_nodos = [nodo.strip() for nodo in miembros_str.split(',')]
        
        # --- CREACIÓN DEL GRAFO INTERACTIVO ---
        net = Network(height='500px', width='100%', bgcolor='#0e1117', font_color='white', directed=False)
        
        ips = []
        usuarios = []
        paises = []
        
        for nodo in lista_nodos:
            if "." in nodo: # Es una IP
                ips.append(nodo)
                net.add_node(nodo, label=nodo, color='#ffaa00', shape='diamond', size=25, title="IP Atacante")
            elif len(nodo) == 2 and nodo.isupper(): # Es un País
                paises.append(nodo)
                net.add_node(nodo, label=nodo, color='#ff4b4b', shape='hexagon', size=35, title="País Afectado")
            else: # Es un Usuario
                usuarios.append(nodo)
                net.add_node(nodo, label=nodo, color='#0068c9', shape='dot', size=20, title="Usuario Vulnerado")
                
        # Dibujamos las conexiones heurísticas (IPs -> Usuarios -> Países)
        for ip in ips:
            for user in usuarios:
                # Líneas rojas punteadas para los ataques
                net.add_edge(ip, user, color='red', dashes=True)
                
        for user in usuarios:
            for pais in paises:
                # Líneas azules sólidas para las compras
                net.add_edge(user, pais, color='#0068c9')
                
        # Físicas para que los nodos flotenr y no se amontonen
        net.repulsion(node_distance=150, spring_length=100)
        
        # Guardamos el grafo como archivo HTML temporal y lo incrustamos
        path_html = '/tmp/grafo_forense.html'
        net.save_graph(path_html)
        
        with open(path_html, 'r', encoding='utf-8') as f:
            html_code = f.read()
            
        st.components.v1.html(html_code, height=520)

    else:
        st.success("No se han detectado amenazas activas de alto riesgo en este momento.")

# ==================================================
# PESTAÑA 2: SPEED LAYER (Detección en Tiempo Real)
# ==================================================
if 'tx_vistas' not in st.session_state:
    st.session_state.tx_vistas = set()
    st.session_state.df_ultimos_ataques = pd.DataFrame()

with tab_realtime:

    if 'tabla_ventanas_existe' not in st.session_state:
        st.session_state.tabla_ventanas_existe = True

    future_alertas = session.execute_async("SELECT * FROM alertas_fraude")
    future_ventanas = None
    if st.session_state.tabla_ventanas_existe:
        try:
            future_ventanas = session.execute_async("SELECT window_start, total_visitas FROM metricas_ventanas LIMIT 100")
        except Exception:
            st.session_state.tabla_ventanas_existe = False

    rows = future_alertas.result()
    df = pd.DataFrame(list(rows))
    
    if not df.empty:
        df_bloqueados = df[df['status'] == 'BLOQUEADO']

        nuevos = df_bloqueados[~df_bloqueados['tx_id'].isin(st.session_state.tx_vistas)]

        if not nuevos.empty:
            st.session_state.tx_vistas.update(nuevos['tx_id'].tolist())
            st.session_state.df_ultimos_ataques = pd.concat([nuevos, st.session_state.df_ultimos_ataques]).head(8)
        
        col1, col2, col3 = st.columns(3)
        col1.metric("Transacciones Analizadas", len(df))
        col2.metric("Ataques Bloqueados", len(df_bloqueados))
        col3.metric("Dinero Salvado (€)", f"{df_bloqueados['amount'].sum():.2f}")
        
        st.markdown("---")
        
        col_chart, col_table = st.columns([1, 1])
        with col_chart:
            st.subheader("🌍 Origen del Fraude")
            if not df_bloqueados.empty:
                st.bar_chart(df_bloqueados['card_country'].value_counts(), color="#ff4b4b")
        
        with col_table:
            st.subheader("🕵️ Últimos Ataques")
            if not st.session_state.df_ultimos_ataques.empty:
                st.dataframe(
                    st.session_state.df_ultimos_ataques[['user_id', 'amount', 'card_country', 'status']], 
                    use_container_width=True, 
                    hide_index=True
                )
                
        st.markdown("---")
        st.subheader("⏱️ Carga del Servidor (Ventanas de 1 minuto)")
        if st.session_state.tabla_ventanas_existe and future_ventanas is not None:
            try:
                rows_ventanas = future_ventanas.result()
                df_ventanas = pd.DataFrame(list(rows_ventanas))
                if not df_ventanas.empty:
                    df_ventanas = df_ventanas.sort_values(by="window_start", ascending=True)
                    st.line_chart(df_ventanas.set_index("window_start")["total_visitas"], color="#11ff4b")
                else:
                    st.info("Recopilando eventos para completar la primera ventana de 1 minuto...")
            except Exception:
                st.session_state.tabla_ventanas_existe = False
                st.info("La tabla de ventanas de 1 minuto aún no se ha inicializado en Cassandra.")
        else:
            st.info("La tabla de ventanas de 1 minuto aún no se ha inicializado en Cassandra.")
    else:
        st.warning("Esperando datos en streaming desde Spark...")

time.sleep(2)
st.rerun()