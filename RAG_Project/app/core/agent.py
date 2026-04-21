import os
import datetime
from langchain_classic.agents import create_openai_tools_agent, AgentExecutor
from langchain_core.tools import tool
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_classic.memory import ConversationSummaryBufferMemory
from langchain_community.chat_message_histories import FileChatMessageHistory


# Funciones arquitectónicas de nuestro RAG global
from app.core.rag_chain import get_llm, get_rag_chain

# Construimos una instancia global del LLM ya que es apátrida (Stateless)
llm = get_llm()

# Configuramos autocompactación interactiva para evadir Memory OOM local
MEMORY_LIMIT = int(os.getenv("MEMORY_TOKEN_LIMIT", 3000))

# Caché de agentes en memoria
agent_executors_cache = {}

def build_project_agent(project_id: str) -> AgentExecutor:
    """
    Patrón Factory: Fábrica dinámica encarga de construir una identidad del LLM, 
    sus Tools especializadas (con clausura léxica atadas a su project_id) y su Memoria.
    Aseguramos Isolation total (Cero Data Leakage entre proyectos).
    """
    
    hist_file = f"./data/projects/{project_id}/history.json"
    chat_memory = FileChatMessageHistory(file_path=hist_file)
    
    docs_dir = f"./data/projects/{project_id}/docs"
    archivos = os.listdir(docs_dir) if os.path.exists(docs_dir) else []
    lista_archivos_str = ", ".join(archivos) if archivos else "Ninguno"

    @tool(return_direct=True)
    def consultar_documentos(consulta: str, archivo_filtro: str = None) -> str:
        """Útil para buscar información en los documentos manuales, PDFs y TXTs de la empresa.
        Usa esta herramienta SIEMPRE que el usuario te pregunte por temas internos del proyecto, 
        teorías, resúmenes de archivos, o si desconoces una respuesta de negocio.
        Recibe un string principal con la pregunta a buscar en 'consulta'.
        Parámetro 'archivo_filtro' (OPCIONAL): Si el contexto te indica a qué documento concreto se refiere la duda, pásale su nombre de archivo exacto para purgar ruido."""
        try:
            # Reclama el motor RAG puramente construido para el bloque vectorial del ID respectivo
            cadena_rag = get_rag_chain(project_id, archivo_filtro)
            
            # Usar API LCEL: Le pasamos 'input' (la consulta) y 'chat_history' extraído de FileChatMessageHistory
            resultado = cadena_rag.invoke({
                "input": consulta,
                "chat_history": chat_memory.messages
            })
            
            respuesta_texto = resultado.get("answer", "")
            documentos = resultado.get("context", [])
            
            fuentes_unicas = set()
            for doc in documentos:
                # Extraemos metadata, soportando TXTs sin página o fallos
                source = doc.metadata.get("source", "Documento desconocido")
                # Extraemos filename puro si es una ruta
                filename = os.path.basename(source) 
                page = doc.metadata.get("page", None)
                
                if page is not None:
                    fuentes_unicas.add(f"- {filename} (Pág. {page})")
                else:
                    fuentes_unicas.add(f"- {filename}")
                    
            if fuentes_unicas:
                footer_fuentes = "\n\n📚 **Fuentes consultadas:**\n" + "\n".join(sorted(list(fuentes_unicas)))
                respuesta_texto += footer_fuentes
                
            return respuesta_texto
        except FileNotFoundError:
            return "Aún no tengo conocimientos sobre ese tema u otros en general ya que no existen archivos en mi base RAG. Pide que suban fuentes (documentos)."
        except Exception as e:
            return f"Error en indexador interno: {e}"

    @tool()
    def obtener_fecha_actual(dummy: str = "") -> str:
        """Útil para obtener la fecha y la hora actual del sistema. Usa si el usuario pregunta '¿qué día es hoy?'."""
        return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    @tool()
    def calcular_estadisticas_texto(texto: str) -> str:
        """Útil para calcular estadísticas o tamaño (caracteres o palabras) de un texto proporcionado explícitamente."""
        palabras = len(texto.split())
        caracteres = len(texto)
        return f"El fragmento tiene {palabras} palabras y {caracteres} caracteres (incluyendo espacios)."

    tools = [consultar_documentos, obtener_fecha_actual, calcular_estadisticas_texto]

    prompt = ChatPromptTemplate.from_messages([
        ("system", "ERES UN AGENTE EXTRACTOR. SIGUE ESTRICTAMENTE ESTOS EJEMPLOS PARA USAR TUS HERRAMIENTAS:\n"
                   "\n"
                   "EJEMPLO 1 (Términos y acciones exactas):\n"
                   "- Pregunta: 'Me he comprado una silla ergonómica de 300€ para casa, ¿cuánto me devuelven?'\n"
                   "- Pensamiento: Debo extraer las palabras exactas del usuario. No usaré sinónimos.\n"
                   "- Acción: consultar_documentos(consulta='silla ergonómica', archivo_filtro='Politica teletrabajo.txt')\n"
                   "\n"
                   "EJEMPLO 2 (Infracciones literales):\n"
                   "- Pregunta: 'Un empleado ha simulado su presencia moviendo el ratón. ¿Qué sanción tiene?'\n"
                   "- Pensamiento: No debo traducir 'simulado' a palabras como 'engaño' o 'fraude'. Usaré los términos literales del usuario.\n"
                   "- Acción: consultar_documentos(consulta='simulado presencia ratón', archivo_filtro='Politica teletrabajo.txt')\n"
                   "\n"
                   "EJEMPLO 3 (Matemáticas paso a paso):\n"
                   "- Pregunta: 'Entré el 1 de julio y estamos en diciembre. ¿Cuántos días he devengado?'\n"
                   "- Pensamiento: Son 6 meses trabajados. Debo buscar la regla de devengo mensual.\n"
                   "- Acción: consultar_documentos(consulta='devengo de vacaciones por mes', archivo_filtro='Politica vacaciones.txt')\n"
                   "- Regla encontrada: '2.08 días por mes'.\n"
                   "- Respuesta Final: Multiplicando 6 meses x 2.08 días, te corresponden 12.48 días.\n"
                   "\n"
                   "PROHIBICIONES ABSOLUTAS:\n"
                   "1. NUNCA inventes herramientas. Usa SOLAMENTE las herramientas proporcionadas.\n"
                   "2. NUNCA inventes reglas, tablas o bonos. Si no encuentras el texto, di que no lo sabes.\n"
                   "3. COPIA Y PEGA: Al rellenar el parámetro 'consulta', DEBES usar las palabras exactas de la pregunta del usuario. TIENES PROHIBIDO usar palabras como 'fraude', 'engaño' o 'devolución' si el usuario no las ha escrito explícitamente.\n"
                   "4. Si recuperas info, DEBES anexar intacta la sección '📚 Fuentes consultadas' al final de tu mensaje.\n"
                   "5. Si el usuario pregunta por un documento específico, DEBES usar el parámetro 'archivo_filtro' para acotar la búsqueda.\n"
                   "6. APLICACIÓN DE NORMAS GENERALES: Si encuentras una norma o sanción general (ej. 'fraccionamiento de facturas'), DEBES aplicarla a los casos específicos del usuario (ej. 'facturas de hotel', 'facturas de restaurante'). No ignores una regla solo porque no mencione el sub-tipo exacto."
                   "\n"
                   f"ARCHIVOS DISPONIBLES EN ESTE PROYECTO: {lista_archivos_str}\n"),
        MessagesPlaceholder(variable_name="chat_history"),
        ("human", "{input}"),
        MessagesPlaceholder(variable_name="agent_scratchpad"),
    ])

    agent = create_openai_tools_agent(llm, tools, prompt)


    memory = ConversationSummaryBufferMemory(
        llm=llm,
        max_token_limit=MEMORY_LIMIT,
        chat_memory=chat_memory,  # Persiste directo al SSD mediante la envoltura FileChatMessageHistory
        memory_key="chat_history",
        return_messages=True
    )

    executor = AgentExecutor(
        agent=agent,
        tools=tools,
        memory=memory,
        max_iterations=10,
        verbose=True,
        handle_parsing_errors=True
    )
    
    return executor

def ask_agent(project_id: str, query: str) -> str:
    """Invoca al Agente en el entorno del Proyecto, cacheando la instancia para evitar relanzamientos"""
    if project_id not in agent_executors_cache:
        agent_executors_cache[project_id] = build_project_agent(project_id)
        
    executor = agent_executors_cache[project_id]

    try:
        respuesta = executor.invoke({"input": query})
        return respuesta['output']
    except Exception as e:
        return f"Error catastrófico local al llamar a LM Studio RAG: {e}"

def invalidate_agent_cache(project_id: str):
    """Destruye el agente cacheado si el historial es borrado o se manipula la estructura desde el cliente."""
    if project_id in agent_executors_cache:
        del agent_executors_cache[project_id]
