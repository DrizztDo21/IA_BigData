# RAG Enterprise Multi-Project - Aplicación Web Local Avanzada

Sistema RAG con Agente Conversacional basado en una arquitectura **Enterprise Project-Based**, utilizando modelos Open Source a través de LM Studio.

Este sistema es una **plataforma matricial multi-proyecto** que permite gestionar espacios de trabajo (Sandboxes) totalmente aislados. Cada proyecto cuenta con sus propios documentos indexados on-the-fly (`en caliente`), una base de datos vectorial (ChromaDB) exclusiva, y su propio historial conversacional persistido directamente en el disco duro.

---

## 📂 Arquitectura del Proyecto (Aislamiento de Entornos)

El código está organizado bajo un esquema profesional regido por APIs modernas RESTful:
- **`app/main.py`**: El backend central en FastAPI que expone la arquitectura para controlar la creación, eliminación, históricos y conversaciones bajo llamadas lógicas tipo `/projects/{id}`.
- **`app/core/rag_chain.py`** y **`app/core/agent.py`**: El núcleo lógico sobre LangChain. Aquí se han programado las memorias persistentes en disco (`FileChatMessageHistory`) e instanciaciones de *tools* exclusivas. Se implementa una potente arquitectura LCEL **History-Aware Retriever Pipeline**: este sistema analiza autónomamente el historial de chat inyectado para detectar preguntas de seguimiento cortas (ej: "¿Cuánto pesa?"), reformulándolas en consultas enriquecidas e independientes (Standalone Queries) antes de bucear en la base de datos vectorial ChromaDB. Esto mitiga por completo problemas de "Amnesia de Contexto" con modelos Open Source. Además implementa un **Patrón de Herramienta Parametrizada con Índice Dinámico**, por el cual el Agente deduce iterativamente qué archivos existen en el proyeto e inyecta dinámicamente sus identificadores usando el operador `$contains` de los kwargs del buscador ChromaDB para evitar la *Contaminación Cruzada de Contexto* (Context Mixing) cuando múltiples directivas difieren en varios de sus manuales.
- **`app/services/`**: Un bloque de operaciones para manipular el sistema de carpetas y vectorización (controlador y particionador de colecciones ChromaDB aisladas).
- **`frontend/app_ui.py`**: La interfaz visual en Streamlit. Cuenta con formularios dinámicos de creación, visualizador de memoria inyectada desde el disco local y manejo de historiales de forma persistente.
- **`data/projects/`**: La matriz de almacenamiento del sistema. Todo UUID posee una subcarpeta física propia y totalmente aislada.
- **`.env`**: Archivo de variables de entorno globales donde se aloja la URL de acceso a LM Studio y el delimitador de tokens para autocompactación del historial (`MEMORY_TOKEN_LIMIT`).

---

## 🛠️ Requisitos e Instalación

Para la gestión de dependencias y despliegues virtualizados se utiliza **uv**.

```bash
# Sincronizar e instalar las dependencias automáticamente usando uv
uv sync
```

### 1. Configurar el Motor Inteligente (LM Studio)
Este RAG Enterprise está diseñado para ejecutarse de forma 100% local, garantizando la total privacidad de los datos:
1. Abrir **LM Studio** y cargar el modelo local deseado.
2. Ir al panel de **Local Server** (<=>).
3. Hacer clic en el botón verde superior **"Start Server"** verificando que usa el puerto por defecto `1234`. La IP local ahora rige y emula la API del LLM para Langchain en modo local.

---

## 🚀 Cómo Iniciar la Ejecución

Al ser una arquitectura orientada a web de doble servicio cliente/servidor, se deben arrancar los dos nodos en **terminales separadas**.

### Paso 1: Levantar el Backend (FastAPI)
Abrir una consola en la raíz de la aplicación y arrancar el backend mediante `uv`:
```bash
uv run uvicorn app.main:app --port 8000
```
*Se enrutará de inmediato localhost:8000. Desde este instante, Uvicorn escucha las peticiones y maneja el AgentExecutor en LangChain para el proyecto que opere.*

### Paso 2: Invocar la Máquina Visual (Streamlit)
Abrir **una segunda pestaña de consola** para iniciar la interfaz visual:
```bash
uv run streamlit run frontend/app_ui.py
```
*A partir de este instante se puede acceder al panel web. La barra lateral izquierda (Sidebar) permite gestionar y alternar entre los distintos proyectos independientes.*

---

## ⚠️ Limitaciones Detectadas

- **Rendimiento del modelo local:** al ejecutarse en CPU (o GPU limitada), la latencia de cada respuesta es de varios segundos. En preguntas complejas donde el agente invoca la herramienta varias veces, la espera puede superar los 30 segundos.
- **Sensibilidad del prompt:** los modelos locales de 8B parámetros son muy sensibles a la formulación del prompt. Se iteró entre estrategias Zero-Shot (reglas) y Few-Shot (ejemplos) porque el modelo se sobrecargaba con instrucciones largas y alucinaba herramientas inexistentes. La estrategia Few-Shot resultó más estable, pero requiere adaptar los ejemplos cada vez que cambian los documentos de la empresa, lo que limita la utilidad real del diseño multi-proyecto.
- **Límites del razonamiento matemático:** en ocasiones el modelo local comete errores aritméticos al encadenar varias operaciones (ej: calcular días devengados + bonificaciones por antigüedad - días consumidos).
- **Búsqueda multi-documento limitada:** aunque el agente puede realizar varias búsquedas secuenciales cambiando de archivo, no siempre lo hace espontáneamente.

---

## 🔮 Mejoras Futuras

- **Streaming de respuestas** token a token con Server-Sent Events.
- **Re-ranking** con un modelo cross-encoder para mejorar la relevancia de los fragmentos tras la recuperación.
- **Evaluación automatizada** con un benchmark tipo RAGAS para comparar configuraciones objetivamente.
- **Autenticación y roles** para restringir el acceso a proyectos por usuario.
- **Soporte para más formatos:** Word (.docx), Excel (.xlsx), PowerPoint (.pptx).
- **Sistemas multi-agente** (router/supervisor) para gestionar tareas complejas invocando agentes especializados.
