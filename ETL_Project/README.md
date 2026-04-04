# 🚀 Sentinel: End-to-End Big Data Pipeline & Analytics Platform
> Arquitectura Lambda distribuida para la ingesta, procesamiento y análisis interactivo de datos masivos de e-commerce.

![Python](https://img.shields.io/badge/Python-3.12-blue?style=for-the-badge&logo=python)
![FastAPI](https://img.shields.io/badge/FastAPI-Simulator-009688?style=for-the-badge&logo=fastapi)
![Apache Spark](https://img.shields.io/badge/Apache_Spark-3.1-E25A1C?style=for-the-badge&logo=apachespark)
![Apache Kafka](https://img.shields.io/badge/Apache_Kafka-Streaming-231F20?style=for-the-badge&logo=apachekafka)
![Docker](https://img.shields.io/badge/Docker_Compose-Containerized-2496ED?style=for-the-badge&logo=docker)

Este proyecto implementa una plataforma Big Data completa desde cero. Abarca desde la generación sintética de telemetría de usuarios mediante una API construida a medida, hasta el despliegue de un clúster distribuido en Docker capaz de soportar procesamiento analítico en tiempo real (Streaming) y por lotes (Batch).

---

## 🏗️ Arquitectura del Sistema (Lambda Architecture)

El core del proyecto es una **Arquitectura Lambda** totalmente dockerizada, diseñada para resolver el problema de procesar tanto el "ahora" (latencia en milisegundos) como el "histórico" (grandes volúmenes) sobre la misma infraestructura de datos.

**Flujo de Datos:**
* **Generación:** Un simulador en *FastAPI* genera eventos transaccionales y de navegación.
* **Ingesta:**  *Apache NiFi* este se encarga de conectar con la API del simulador, persistir los crudos en *HDFS* enviar los datos filtrados a colas de *Apache Kafka*.
* **Speed Layer:** *Spark Streaming* consume de Kafka, procesa al vuelo y guarda métricas de baja latencia en *Apache Cassandra*.
* **Batch Layer:** *Apache NiFi* persiste los datos en *HDFS*. Tareas programadas con *Apache Airflow* lanzan *Spark Batch* para extraer relaciones complejas (GraphFrames) y guardar el histórico en *Apache Hive* y volúmenes compartidos.
* **Serving:** Un SOC Dashboard en *Streamlit* consume tanto de Cassandra (Live) como de Hive/HDFS (Histórico) para ofrecer una vista unificada.

---

## 🚀 Componentes Principales del Pipeline

### 1. 🎲 Generador de Datos (FastAPI)
Para alimentar el clúster con datos realistas, se desarrolló un simulador asíncrono con **FastAPI**. Este componente inyecta continuamente JSONs con tres patrones de comportamiento configurables:
* **Tráfico de Navegación:** Visitas, tiempos de sesión, páginas vistas.
* **Transacciones:** Eventos de pago simulando pasarelas de e-commerce.
* **Actividad Anómala:** Inyección controlada de picos de tráfico, scrapers y botnets rotatorias para poner a prueba los sistemas analíticos.

### 2. ⚡ Speed Layer (Real-Time Analytics)
* **Ingesta:** Los eventos generados por la API son publicados en tópicos de **Apache Kafka**.
* **Procesamiento:** Micro-batching con **Spark Streaming** para calcular métricas agregadas al vuelo.
* **Serving DB:** Almacenamiento optimizado para lecturas rápidas en **Apache Cassandra**, alimentando las gráficas en vivo del sistema.

### 3. 🧠 Batch Layer (Data Lake & Machine Learning)
* **Ingesta y Enrutamiento:** **Apache NiFi** captura los eventos de la API y los almacena organizados temporalmente en el Data Lake (**HDFS**).
* **Data Warehouse:** Trabajos pesados de limpieza y estructuración mediante **Spark Batch**, persistiendo tablas optimizadas en **Apache Hive**.
* **Graph Analytics:** Uso de `GraphFrames` (modelo de programación Pregel) para trazar redes tripartitas complejas (IPs-Usuarios-Países) y detectar comunidades a través de todo el histórico de datos.
* **Orquestación:** **Apache Airflow** gestiona las dependencias y lanza los procesos de "Cierre Diario".

### 4. 📊 Data Serving (Streamlit Dashboard)
Interfaz analítica interactiva que unifica ambos mundos (Streaming y Batch), mostrando KPIs de negocio, métricas de latencia, y visualizaciones de grafos generadas dinámicamente con `PyVis` y `NetworkX`.

---

## 🛠️ Stack Tecnológico

| Capa | Tecnologías Utilizadas |
| :--- | :--- |
| **Generación de Datos** | FastAPI |
| **Ingesta & Mensajería** | Apache Kafka, Apache NiFi |
| **Procesamiento Distribuido** | Apache Spark (Streaming & Batch), GraphFrames |
| **Almacenamiento (DWH / Data Lake)** | Hadoop (HDFS), Apache Hive, Apache Cassandra |
| **Orquestación & Gestión** | Apache Airflow, YARN ResourceManager |
| **Visualización** | Streamlit, Pandas, PyVis, NetworkX |
| **Infraestructura** | Docker, Docker Compose |

---

## ⚙️ Optimización de Infraestructura (YARN & Docker)

Desplegar una arquitectura Lambda completa en un entorno local dockerizado requiere técnicas avanzadas de DataOps para evitar cuellos de botella:
* **Tuning de YARN:** Modificación de `capacity-scheduler.xml` para permitir al `ApplicationMaster` de Spark consumir el 100% de los recursos de la cola, evitando deadlocks en clústeres reducidos.
* **Data Locality:** Desactivación de esperas locales (`spark.locality.wait="0s"`) para forzar el despliegue inmediato de *Executors* en nodos disponibles.
* **Gestión de Memoria:** Parametrización fina de la JVM y Spark (`--executor-memory`, `--driver-memory`) para permitir la concurrencia de trabajos de Streaming 24/7 y procesos Batch pesados sobre los mismos nodos de procesamiento.