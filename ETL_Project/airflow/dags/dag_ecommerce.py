from airflow import DAG
from airflow.providers.apache.spark.operators.spark_submit import SparkSubmitOperator
from airflow.operators.python import PythonOperator
from airflow.operators.empty import EmptyOperator
from airflow.exceptions import AirflowSkipException
from datetime import datetime, timedelta
import requests

# ==========================================
# 1. SISTEMA DE ALERTAS (CALLBACKS)
# ==========================================
def notificar_fallo_soc(context):
    """Simula el envío de una alerta crítica (ej. Slack/Teams) si algo rompe."""
    tarea_fallida = context.get('task_instance').task_id
    print(f"🚨 [ALERTA CRÍTICA SOC] - La tarea '{tarea_fallida}' ha fallado tras agotar los reintentos.")
    print("Por favor, revise los logs de YARN o el estado del NameNode.")

def notificar_exito_cierre(context):
    """Se ejecuta solo si todo el DAG termina sin errores."""
    print("✅ [INFO SOC] - Cierre nocturno finalizado. Datos en Hive y grafos actualizados.")

# ==========================================
# CONFIGURACIÓN BASE Y REINTENTOS
# ==========================================
default_args = {
    'owner': 'data_engineer',
    'depends_on_past': False,
    'start_date': datetime(2026, 4, 1),
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 3,
    'retry_delay': timedelta(minutes=2),
    'on_failure_callback': notificar_fallo_soc
}

# ==========================================
# 2. FUNCIONES DE INTERACCIÓN CON HDFS
# ==========================================
def comprobar_nuevos_datos():
    """SENSOR: Dependencia clara. Verifica si hay crudos antes de lanzar Spark."""
    url = "http://namenode:9870/webhdfs/v1/datos/pagos?op=LISTSTATUS"
    print(f"Comprobando NameNode: {url}")
    
    respuesta = requests.get(url)
    if respuesta.status_code == 200:
        archivos = respuesta.json().get("FileStatuses", {}).get("FileStatus", [])
        if len(archivos) == 0:
            # Si no hay archivos, detenemos el DAG aquí mismo como un "Skip" exitoso
            raise AirflowSkipException("No hay transacciones nuevas en HDFS. Se omite la ejecución.")
        print(f"OK. Se encontraron {len(archivos)} bloques de datos listos para procesar.")
    elif respuesta.status_code == 404:
        raise AirflowSkipException("El directorio HDFS aún no existe. Se omite la ejecución.")
    else:
        raise Exception(f"Error NameNode: {respuesta.status_code}")
    
def limpiar_hdfs_api():
    """Limpieza post-procesamiento de crudos (Pagos y Visitas)."""
    directorios = ["/datos/pagos", "/datos/visitas"]
    
    for directorio in directorios:
        url = f"http://namenode:9870/webhdfs/v1{directorio}?op=DELETE&recursive=true"
        respuesta = requests.delete(url)
        
        if respuesta.status_code == 200:
            print(f"🧹 Carpeta {directorio} purgada correctamente tras el cierre.")
        else:
            print(f"⚠️ Aviso al purgar {directorio}: {respuesta.text}")
            # No lanzamos Exception aquí para intentar borrar ambas carpetas aunque una falle

# ==========================================
# 3. DEFINICIÓN DEL DAG
# ==========================================
with DAG(
    'cierre_diario_ecommerce',
    default_args=default_args,
    description='Pipeline Batch con reintentos, dependencias y alertas.',
    schedule_interval='@daily',
    catchup=False,
    tags=['ecommerce', 'batch', 'hive', 'grafos'],
    on_success_callback=notificar_exito_cierre
) as dag:

    # Nodo 1: Sensor de Dependencias
    sensor_hdfs = PythonOperator(
        task_id='verificar_datos_hdfs',
        python_callable=comprobar_nuevos_datos
    )

    # Nodo 2: Procesamiento Pesado en Spark
    tarea_spark_batch = SparkSubmitOperator(
        task_id='procesar_hive_y_grafos',
        application='/opt/workspace/historico_ecommerce.py',
        conn_id='spark_default', 
        packages='graphframes:graphframes:0.8.2-spark3.1-s_2.12', 
        
        num_executors=1,       
        executor_cores=1,
        
        # --- DIETA ESTRICTA PARA FORZAR LA ENTRADA ---
        executor_memory='512m',  
        driver_memory='512m',    
        conf={
            "spark.hadoop.fs.defaultFS": "hdfs://namenode:9000",
            "spark.sql.warehouse.dir": "hdfs://namenode:9000/user/hive/warehouse",
            "spark.yarn.am.memory": "512m",
            
            "spark.sql.adaptive.enabled": "false",
            "spark.sql.shuffle.partitions": "4",
            "spark.sql.autoBroadcastJoinThreshold": "-1",
            "spark.locality.wait": "0s",
            
            # --- PROHIBIMOS A SPARK HACER COSAS RARAS CON LOS RECURSOS ---
            "spark.dynamicAllocation.enabled": "false" 
        },
        verbose=True
    )

    # Nodo 3: Purga de datos procesados
    tarea_limpiar_hdfs = PythonOperator(
        task_id='purga_crudos_hdfs',
        python_callable=limpiar_hdfs_api
    )

    # Nodo 4: Fin de ejecución exitosa
    fin_proceso = PythonOperator(
        task_id='cierre_completado',
        python_callable=lambda: print("Cierre Batch de E-commerce finalizado con éxito. Hive actualizado y grafos listos.")
    )

    # ==========================================
    # 4. ORQUESTACIÓN (Flujo del DAG)
    # ==========================================
    sensor_hdfs >> tarea_spark_batch >> tarea_limpiar_hdfs >> fin_proceso