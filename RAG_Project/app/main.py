import os
import shutil
import requests
import json
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from pydantic import BaseModel
from typing import List
from dotenv import load_dotenv

from app.core.agent import ask_agent, invalidate_agent_cache
from app.services.ingest_service import ingest_file
from app.services.project_service import (
    get_projects, create_project, delete_project, 
    clear_project_history, get_project_files_directory
)

load_dotenv()

app = FastAPI(title="RAG Enterprise Multi-Project API", version="2.0.0")

class ProjectCreateRequest(BaseModel):
    name: str

class ChatRequest(BaseModel):
    message: str

@app.get("/status")
def get_status():
    """Comprueba si el servidor local de LM Studio está encendido."""
    try:
        LM_STUDIO_API_URL = os.getenv("LM_STUDIO_API_URL", "http://localhost:1234/v1")
        response = requests.get(f"{LM_STUDIO_API_URL}/models", timeout=3)
        if response.status_code == 200:
            return {"status": "online"}
    except Exception as e:
        print("Status check error:", e)
        pass
    return {"status": "offline"}

@app.get("/projects")
def list_projects_endpoint():
    """Retorna la jerarquía matricial de proyectos encontrados en el FS."""
    return {"projects": get_projects()}

@app.post("/projects")
def create_project_endpoint(req: ProjectCreateRequest):
    """Instancia un subsistema independiente aislado RAG."""
    return create_project(req.name)

@app.delete("/projects/{project_id}")
def delete_project_endpoint(project_id: str):
    """Purga todo el conocimiento vectorial, histórico y base del sistema de archivos."""
    invalidate_agent_cache(project_id)
    if delete_project(project_id):
        return {"status": "eliminado"}
    raise HTTPException(status_code=404, detail="Proyecto inexistente")

@app.post("/projects/{project_id}/upload")
async def upload_document_endpoint(project_id: str, file: UploadFile = File(...)):
    """Sube un documento y fragmenta el RAG aislado sobre la marcha."""
    if not (file.filename.endswith(".pdf") or file.filename.endswith(".txt")):
        raise HTTPException(status_code=400, detail="Solo se soportan PDF o TXT.")
        
    docs_dir = get_project_files_directory(project_id)
    if not os.path.exists(docs_dir):
        raise HTTPException(status_code=404, detail="Proyecto fuera de línea o inexistente.")
        
    file_path = os.path.join(docs_dir, file.filename)
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    try:
        chunks_count = ingest_file(file_path, project_id)
    except Exception as e:
        os.remove(file_path)
        raise HTTPException(status_code=500, detail=f"Error indexación vector store: {e}")
        
    # Rompemos la caché para instanciar la memoria Lógica de la Base de nuevo
    invalidate_agent_cache(project_id)
    return {"status": "ok", "filename": file.filename, "chunks": chunks_count}

@app.get("/projects/{project_id}/files")
def get_project_files_endpoint(project_id: str):
    """Visor de sistema físico documental atado al subsistema."""
    docs_dir = get_project_files_directory(project_id)
    if not os.path.exists(docs_dir):
        return {"files": []}
    return {"files": os.listdir(docs_dir)}

@app.get("/projects/{project_id}/history")
def get_chat_history_endpoint(project_id: str):
    """Carga nativa del hilo conversacional físico alojado interactuando contra memoria de LangChain."""
    hist_file = f"./data/projects/{project_id}/history.json"
    if not os.path.exists(hist_file):
         return {"history": []}
    try:
         with open(hist_file, "r", encoding="utf-8") as f:
             return {"history": json.load(f)}
    except:
         return {"history": []}

@app.post("/projects/{project_id}/clear")
def clear_history_endpoint(project_id: str):
    """Vacia el history dict para purgar temporalmente en memoria a corto y largo."""
    clear_project_history(project_id)
    invalidate_agent_cache(project_id)
    return {"status": "limpiado"}

@app.post("/projects/{project_id}/chat")
def post_chat_endpoint(project_id: str, req: ChatRequest):
    """Puerta enrutadora hacia el LM y cadena de herramientas."""
    respuesta = ask_agent(project_id, req.message)
    return {"response": respuesta}
