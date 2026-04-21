from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings

def ingest_file(file_path: str, project_id: str):
    """
    Toma un archivo físico y lo incorpora ÚNICAMENTE al VectorStore aislado
    del proyecto especificado por su UUID.
    """
    if file_path.endswith(".pdf"):
        loader = PyPDFLoader(file_path)
    elif file_path.endswith(".txt"):
        loader = TextLoader(file_path, encoding="utf-8")
    else:
        raise ValueError("Formato no soportado.")
        
    documentos = loader.load()
    if not documentos:
        raise ValueError("Archivo vacío.")

    splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
    chunks = splitter.split_documents(documentos)

    # Se sustituyó el modelo all-MiniLM-L6-v2 por su variante multilingüe ya que el original presentaba 
    # deficiencias en la búsqueda semántica en español, mejorando drásticamente el recall del retriever
    embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")

    # Inyección dinámica hacia el bloque de vectorización confinado en /data/projects/{id}/chroma_db
    project_db_path = f"./data/projects/{project_id}/chroma_db"
    db = Chroma(persist_directory=project_db_path, embedding_function=embeddings)
    db.add_documents(chunks)
    
    return len(chunks)
