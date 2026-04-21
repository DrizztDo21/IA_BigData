import os
import streamlit as st
import requests

st.set_page_config(page_title="RAG Multi-Project AI", page_icon="🤖", layout="wide")
API_URL = os.getenv("API_URL", "http://127.0.0.1:8000")

def get_status():
    try:
        r = requests.get(f"{API_URL}/status", timeout=5)
        return r.json().get("status") if r.status_code == 200 else "offline"
    except Exception as e:
        print(f"Error fetching status: {e}")
        return "offline"

def get_projects():
    try:
        r = requests.get(f"{API_URL}/projects", timeout=5)
        return r.json().get("projects", []) if r.status_code == 200 else []
    except Exception as e:
        print(f"Error fetching projects: {e}")
        return []

# =====================================================================
# SIDEBAR (Control Aislado de Proyectos)
# =====================================================================
st.sidebar.title("🗄️ Panel de Proyectos RAG")

status = get_status()
if status == "online":
    st.sidebar.markdown("🟢 **Motor Local LLM:** `ONLINE`")
else:
    st.sidebar.markdown("🔴 **Motor Local LLM:** `OFFLINE`")

st.sidebar.divider()

# Sección de Crear Proyecto Múltiple
st.sidebar.subheader("➕ Nuevo Proyecto")
with st.sidebar.form("new_project_form", clear_on_submit=True):
    new_name = st.text_input("Nombre del Sandbox")
    submitted = st.form_submit_button("Inicializar Proyecto")
    if submitted and new_name:
        res = requests.post(f"{API_URL}/projects", json={"name": new_name})
        if res.status_code == 200:
            st.toast("Bloque creado en disco.")
        else:
            st.error("Fallo al crear proyecto.")

# Tracker de Projecto Activo
projects = get_projects()
project_options = {p["name"]: p["id"] for p in projects}

active_project_id = None
if project_options:
    st.sidebar.subheader("🗂️ Entornos de Trabajo")
    selected_name = st.sidebar.selectbox("Selecciona un núcleo activo:", list(project_options.keys()))
    active_project_id = project_options[selected_name]
else:
    st.sidebar.info("Crea tu primer proyecto para empezar a chatear.")

# Herramientas del Proyecto Activo
if active_project_id:
    st.sidebar.divider()
    st.sidebar.subheader("🚀 Gestionar Conocimiento")
    
    # Fuentes Actuales
    st.sidebar.markdown("**Archivos Indexados:**")
    files_req = requests.get(f"{API_URL}/projects/{active_project_id}/files")
    if files_req.status_code == 200:
        docs = files_req.json().get("files", [])
        if docs:
            for d in docs: st.sidebar.caption(f"📄 {d}")
        else:
            st.sidebar.caption("Sin documentos.")
            
    # Subida de archivo
    uploaded_file = st.sidebar.file_uploader("Indexar archivo nuevo", type=["pdf", "txt"], key="uploader")
    if st.sidebar.button("Subir Fichero"):
        if uploaded_file:
            with st.spinner("Fragmentando y vectorizando dinámicamente..."):
                files = {"file": (uploaded_file.name, uploaded_file.getvalue(), uploaded_file.type)}
                r = requests.post(f"{API_URL}/projects/{active_project_id}/upload", files=files)
                if r.status_code == 200:
                    st.toast(f"Indexado OK: {r.json()['chunks']} segmentos aprendidos.")
                    st.rerun()
                else:
                    st.sidebar.error("Error al vectorizar.")
        else:
            st.sidebar.warning("No hay fichero.")

    # Acciones Destructivas
    st.sidebar.divider()
    col1, col2 = st.sidebar.columns(2)
    if col1.button("🧹 Limpiar Chat", use_container_width=True):
        requests.post(f"{API_URL}/projects/{active_project_id}/clear")
        st.rerun()
    if col2.button("🗑️ Eliminar Proyecto", use_container_width=True):
        requests.delete(f"{API_URL}/projects/{active_project_id}")
        st.rerun()

# =====================================================================
# VENTANA CENTRAL DE CHAT
# =====================================================================
st.header(f"🧠 Agente RAG Local ({selected_name if active_project_id else 'Sin proyecto activo'})")

if not active_project_id:
    st.info("← Usa el panel lateral para seleccionar o dotar de vida a un nuevo entorno de proyecto aislable.")
else:
    # Obtener el Historial Persistido del Disco (Traducido de LangChain BaseMessage)
    # Recordatorio Técnico: History devuelto es un array de diccionarios tipo 
    # {"type": "human"/"ai", "data": {"content": "..."}} provisto por FileChatMessageHistory
    hist_req = requests.get(f"{API_URL}/projects/{active_project_id}/history")
    chat_history = hist_req.json().get("history", []) if hist_req.status_code == 200 else []

    # Pintar las burbujas atadas estricatamente a la memoria en duro
    for msg in chat_history:
        role = "user" if msg.get("type", "") == "human" else "assistant"
        content = msg.get("data", {}).get("content", "")
        with st.chat_message(role):
            st.markdown(content)
            
    # Manejar input vivo
    user_input = st.chat_input("Dispara tu consulta (Recuerda que conozco las herramientas del Agente)...")
    if user_input:
        # Optimistic UI update 
        with st.chat_message("user"):
            st.markdown(user_input)
            
        with st.chat_message("assistant"):
            with st.spinner("Pensando..."):
                try:
                    payload = {"message": user_input}
                    res = requests.post(f"{API_URL}/projects/{active_project_id}/chat", json=payload, timeout=90)
                    if res.status_code == 200:
                        st.markdown(res.json().get("response", ""))
                    else:
                        st.error("Fallo de la llamada de sistema general")
                except:
                    st.error("¿Uvicorn o LM Studio están muertos?")
        # Realizamos rerun para fetchear el estado formal desde el disco duro de Langchain
        st.rerun()
