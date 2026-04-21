import os
from dotenv import load_dotenv
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_core.prompts import PromptTemplate, ChatPromptTemplate, MessagesPlaceholder
from langchain_classic.chains import RetrievalQA
from langchain_openai import ChatOpenAI
from langchain_classic.chains import create_history_aware_retriever, create_retrieval_chain
from langchain_classic.chains.combine_documents import create_stuff_documents_chain

load_dotenv()

LM_STUDIO_API_URL = os.getenv("LM_STUDIO_API_URL", "http://127.0.0.1:1234/v1")
LM_STUDIO_API_KEY = os.getenv("LM_STUDIO_API_KEY", "lm-studio")

def get_llm():
    return ChatOpenAI(
        base_url=LM_STUDIO_API_URL,
        api_key=LM_STUDIO_API_KEY, 
        model="local-model",
        temperature=0.0
    )



def get_rag_chain(project_id: str, archivo_filtro: str = None): # -> Return type is LCEL Runnable
    """
    Carga el vectorstore desde disco y construye un motor RAG sensible al contexto (History-Aware Retriever).
    Mantiene el foco de seguimiento usando el historial de chat del proyecto.
    Si provee archivo_filtro, confina la búsqueda dinámica a document chunks de ese archivo.
    """
    db_path = f"./data/projects/{project_id}/chroma_db"
    
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"El proyecto {project_id} no ha generado indexación vectorial local RAG. Por favor, sube un documento para arrancar su matriz.")

    # Se sustituyó el modelo all-MiniLM-L6-v2 por su variante multilingüe ya que el original presentaba 
    # deficiencias en la búsqueda semántica en español, mejorando drásticamente el recall del retriever
    embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
    vectorstore = Chroma(persist_directory=db_path, embedding_function=embeddings)
    
    # 0. Filtro de metadatos por documento específico (Anti Context-Mixing)
    # ChromaDB NO soporta $contains en metadata, solo $eq. El campo 'source' almacena la ruta
    # completa tal como la generó el ingest pipeline (os.path.join), así que la reconstruimos.
    search_kwargs = {"k": 5, "fetch_k": 10}
    if archivo_filtro:
        source_path = os.path.join("./data/projects", project_id, "docs", archivo_filtro)
        search_kwargs["filter"] = {"source": source_path}
        
    # Se sustituyó el retriever simple por MMR (Maximal Marginal Relevance) para mejorar la diversidad de los documentos recuperados
    retriever = vectorstore.as_retriever(
        search_type="mmr", 
        search_kwargs=search_kwargs
    )

    llm = get_llm()

    # 1. Prompt de Contextualización: Autocorreción y Standalone Formatting
    contextualize_q_system_prompt = """Dada una conversación y una pregunta reciente del usuario 
                                        que podría referirse a información previa en el historial de chat, escribe una 
                                        pregunta independiente (Standalone Query) que pueda entenderse por sí sola sin 
                                        necesidad de leer la conversación anterior. NO respondas a la pregunta, solo 
                                        reformúlala si es necesario, o devuélvela tal cual."""
    
    contextualize_q_prompt = ChatPromptTemplate.from_messages([
        ("system", contextualize_q_system_prompt),
        MessagesPlaceholder("chat_history"),
        ("human", "{input}"),
    ])
    
    history_aware_retriever = create_history_aware_retriever(
        llm, retriever, contextualize_q_prompt
    )

    # 2. Prompt del Q&A QA Chain (Few-Shot: el modelo aprende por imitación)
    qa_system_prompt = """Responde SOLO con datos del contexto. SIGUE estos ejemplos:

EJEMPLO A:
- Pregunta del usuario: "Llevo 7 años, ¿cuántos días extra me tocan?"
- Contexto contiene: "3-5 años: +1 día, 5-10 años: +3 días, >10 años: +5 días"
- RESPUESTA CORRECTA: "Con 7 años de antigüedad, te encuentras en el tramo de 5 a 10 años, por lo que te corresponden +3 días laborables extra."
- RESPUESTA INCORRECTA: copiar la tabla entera y decir "dime cuántos años llevas".

EJEMPLO B:
- Pregunta del usuario: "¿Cuánto es el límite de alojamiento?"
- Contexto contiene: "Nacional: 120€/noche. Internacional: 180€/noche."
- RESPUESTA CORRECTA: "El límite es de 120€/noche en viajes nacionales y 180€/noche en internacionales."
- RESPUESTA INCORRECTA: mencionar solo uno de los dos valores.

EJEMPLO C:
- Pregunta del usuario: "¿Qué opinas de Bitcoin?"
- Contexto: no contiene nada sobre Bitcoin.
- RESPUESTA CORRECTA: "No tengo información sobre ese tema en los documentos disponibles."
- RESPUESTA INCORRECTA: inventar datos o pedir más contexto.

REGLAS:
1. Si el usuario ya te da un dato (ej: "7 años", "300€"), ÚSALO. No le pidas que te lo repita.
2. Incluye TODOS los valores relevantes del contexto, no solo el primero.
3. Si no hay información, di "No tengo información sobre ese tema en los documentos disponibles." y nada más.

Contexto:
{context}"""

    qa_prompt = ChatPromptTemplate.from_messages([
        ("system", qa_system_prompt),
        MessagesPlaceholder("chat_history"),
        ("human", "{input}"),
    ])
    
    question_answer_chain = create_stuff_documents_chain(llm, qa_prompt)
    
    # 3. Ensamblaje final de la tubería RAG
    rag_chain = create_retrieval_chain(history_aware_retriever, question_answer_chain)
    
    return rag_chain
