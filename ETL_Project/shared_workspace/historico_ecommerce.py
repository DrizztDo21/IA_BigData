from pyspark.sql import SparkSession
from pyspark.sql.functions import col, to_timestamp, lit, desc, regexp_replace, from_json, count, desc, upper, collect_list, concat_ws, row_number
from pyspark.sql.window import Window
from pyspark.sql.types import StructType, StringType, IntegerType, BooleanType
from graphframes import GraphFrame

# 1. Iniciamos Spark con soporte para Hive
spark = SparkSession.builder \
    .appName("Cierre_Caja_Ecommerce") \
    .enableHiveSupport() \
    .getOrCreate()

spark.sparkContext.setLogLevel("WARN")

print("--- INICIANDO CIERRE BATCH DE E-COMMERCE ---")

# 2. Leemos TODOS los pagos crudos que NiFi ha dejado en HDFS
try:
    df_raw = spark.read.json("hdfs://namenode:9000/datos/pagos/*")
    total_registros = df_raw.count()
    print(f"✅ Se han cargado {total_registros} transacciones de HDFS.")
except Exception as e:
    print("Error leyendo de HDFS. Verifica que NiFi esté escribiendo correctamente y que la ruta sea correcta.")
    raise e

# 3. Pequeña limpieza (castear tipos de datos para Hive)
df_limpio = df_raw \
    .withColumn("amount", col("amount").cast("double")) \
    .filter(col("tx_id").isNotNull()).cache() # Quitamos posibles registros corruptos y cacheamos porque lo usaremos varias veces

# 4. Guardamos en el almacén de Hive
print("Persistiendo en Hive (tabla: historial_pagos)...")
df_limpio.write.mode("overwrite").saveAsTable("historial_pagos")

print("----PROCESO BATCH COMPLETADO CON ÉXITO----")

print("Generando vista agregada para el Dashboard (Serving Layer)...")
try:
    # Agrupamos por país para ver el volumen de negocio
    resumen_df = df_limpio.groupBy("card_country") \
        .count() \
        .withColumnRenamed("count", "total_transacciones") \
        .orderBy("total_transacciones", ascending=False)
    
    # Lo convertimos a Pandas y lo guardamos como CSV en la carpeta compartida
    resumen_df.toPandas().to_csv("/opt/workspace/resumen_batch.csv", index=False)
    print("Resumen Batch exportado a CSV para el Dashboard.")
except Exception as e:
    print(f"Error exportando el CSV: {e}")


print("--- INICIANDO CIERRE BATCH DE VISITAS ---")

# 1. Definimos el esquema esperado del JSON
esquema_visitas = StructType() \
    .add("timestamp", StringType()) \
    .add("user_id", StringType()) \
    .add("ip", StringType()) \
    .add("session_duration", IntegerType()) \
    .add("pages_visited", IntegerType()) \
    .add("is_bot", BooleanType()) \
    .add("flag_ataque", BooleanType())

try:
    # 2. Leemos como texto plano (para que Spark no intente parsear el JSON todavía)
    df_raw_text = spark.read.text("hdfs://namenode:9000/datos/visitas/*")
    total_visitas = df_raw_text.count()
    print(f"✅ Se han cargado {total_visitas} registros de visitas de HDFS.")
    
    # 3. Limpiamos el prefijo "data: " y parseamos el JSON dinámicamente
    df_parsed = df_raw_text \
        .withColumn("clean_json", regexp_replace(col("value"), "^data: ", "")) \
        .select(from_json(col("clean_json"), esquema_visitas).alias("data")) \
        .select("data.*")

    # 4. Filtramos nulos y cacheamos (Optimización)
    df_visitas_limpio = df_parsed.filter(col("ip").isNotNull()).cache()

    print("Persistiendo en Hive (tabla: historial_visitas)...")
    df_visitas_limpio.write.mode("overwrite").saveAsTable("historial_visitas")

    # 5. ANÁLISIS BATCH: Bots Lentos
    df_abuso_recursos = df_visitas_limpio.groupBy("ip") \
        .agg(
            {"pages_visited": "sum", "session_duration": "sum", "user_id": "count"}
        ) \
        .withColumnRenamed("sum(pages_visited)", "total_paginas_dia") \
        .withColumnRenamed("sum(session_duration)", "tiempo_total_segundos") \
        .withColumnRenamed("count(user_id)", "total_sesiones_dia") \
        .orderBy("total_paginas_dia", ascending=False)
    
    top_scrapers = df_abuso_recursos.limit(10)
    top_scrapers.toPandas().to_csv("/opt/workspace/top_scrapers_batch.csv", index=False)
    print("Reporte de Scrapers exportado a CSV para el Dashboard.")

except Exception as e:
    print(f"ERROR CRÍTICO procesando visitas: {e}")
    raise e # Detenemos el proceso aquí porque las visitas son clave para el análisis de grafos


print("--- INICIANDO ANÁLISIS DE GRAFOS (FRAUD RINGS) ---")

usuarios_pagos = df_limpio.select(col("user_id").alias("id"))
usuarios_visitas = df_visitas_limpio.select(col("user_id").alias("id"))

usuarios = usuarios_pagos.union(usuarios_visitas).withColumn("tipo", lit("usuario")).distinct()
paises = df_limpio.select(col("card_country").alias("id")).withColumn("tipo", lit("pais")).distinct()
ips = df_visitas_limpio.select(col("ip").alias("id")).withColumn("tipo", lit("ip")).distinct()

vertices = usuarios.unionByName(paises).unionByName(ips)

# 2. Crear Aristas (Edges)
# Aristas 1: El usuario X compra en el País Y
edges_pagos = df_limpio.select(
    col("user_id").alias("src"), 
    col("card_country").alias("dst"),
    lit("pago").alias("relacion")
)

# Aristas 2: La IP Z fue usada por el Usuario X
edges_visitas = df_visitas_limpio.select(
    col("ip").alias("src"), 
    col("user_id").alias("dst"),
    lit("visita").alias("relacion")
).distinct()

edges = edges_pagos.unionByName(edges_visitas)

grafo_fraude = GraphFrame(vertices, edges)

print("Calculando centralidad de la red...")

centralidad = grafo_fraude.degrees

ventana_por_tipo = Window.partitionBy(upper(col("tipo"))).orderBy(desc("degree"))

nodos_calientes = centralidad.join(grafo_fraude.vertices, "id") \
    .withColumn("tipo", upper(col("tipo"))) \
    .withColumn("ranking", row_number().over(ventana_por_tipo)) \
    .where(col("ranking") <= 15) \
    .drop("ranking")

nodos_calientes.toPandas().to_csv("/opt/workspace/nodos_calientes.csv", index=False)

print("Detectando comunidades...")
spark.sparkContext.setCheckpointDir("hdfs://namenode:9000/tmp/checkpoints_grafos")

# para vaciar la RAM y evitar que explote por OOM
comunidades = grafo_fraude.connectedComponents(checkpointInterval=2)

redes_agrupadas = comunidades.groupBy("component") \
    .agg(
        count("id").alias("num_entidades"),
        collect_list("id").alias("miembros_lista")
    ) \
    .filter(col("num_entidades") > 2) \
    .orderBy(desc("num_entidades"))

# Convertimos la lista de array a texto separado por comas para que Streamlit lo lea fácil
resumen_comunidades = redes_agrupadas.withColumn("miembros", concat_ws(", ", col("miembros_lista"))) \
    .drop("miembros_lista")

resumen_comunidades.toPandas().to_csv("/opt/workspace/redes_detectadas.csv", index=False)

print("✅ Análisis de grafos tripartitos completado y exportado.")