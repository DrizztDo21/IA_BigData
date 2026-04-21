import os
import json
import shutil
import uuid
from datetime import datetime

PROJECTS_DIR = "./data/projects"

def get_projects() -> list[dict]:
    """Retorna una lista con la metadata de todos los proyectos creados."""
    if not os.path.exists(PROJECTS_DIR):
        return []
        
    projects = []
    for pid in os.listdir(PROJECTS_DIR):
        meta_path = os.path.join(PROJECTS_DIR, pid, "metadata.json")
        if os.path.exists(meta_path):
            with open(meta_path, "r", encoding="utf-8") as f:
                projects.append(json.load(f))
    return projects

def create_project(name: str) -> dict:
    """Instancia la estructura aislada para un nuevo contenedor RAG."""
    pid = str(uuid.uuid4())
    proj_dir = os.path.join(PROJECTS_DIR, pid)
    
    # Crear su propio directorio de base de datos Vectorial y de documentos nativos
    os.makedirs(os.path.join(proj_dir, "docs"), exist_ok=True)
    os.makedirs(os.path.join(proj_dir, "chroma_db"), exist_ok=True)
    
    metadata = {
        "id": pid,
        "name": name,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    
    with open(os.path.join(proj_dir, "metadata.json"), "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=4)
        
    return metadata

def delete_project(pid: str) -> bool:
    """Borra completamente y de manera recursiva el bloque de conocimiento RAG de disco.
    Fuerza el Garbage Collection y el cerrado del cliente nativo de Chroma para liberar el lock de Windows."""
    proj_dir = os.path.join(PROJECTS_DIR, pid)
    
    # 1. Intentar destruir los hilos/locks de sqlite abiertos por la instancia global de ChromaDB
    try:
        import gc
        import chromadb
        from langchain_chroma import Chroma
        
        db_path = os.path.join(proj_dir, "chroma_db")
        if os.path.exists(db_path):
            # Enganchar el cliente actual y cerrarlo por fuerza bruta
            v_store = Chroma(persist_directory=db_path)
            v_store._client.close()
            del v_store
            
        chromadb.api.client.SharedSystemClient.clear_system_cache()
        gc.collect()
    except Exception:
        pass

    if os.path.exists(proj_dir):
        shutil.rmtree(proj_dir, ignore_errors=True)
        return True
    return False

def clear_project_history(pid: str) -> bool:
    """Limpia el archivo físico JSON para borrar la memoria (LangChain lo leerá vacío)."""
    hist_file = os.path.join(PROJECTS_DIR, pid, "history.json")
    if os.path.exists(hist_file):
        os.remove(hist_file)
        return True
    return False

def get_project_files_directory(pid: str) -> str:
    """Obtiene la ruta física donde se guardan los archivos PDF/TXT subidos en ese ID."""
    return os.path.join(PROJECTS_DIR, pid, "docs")
