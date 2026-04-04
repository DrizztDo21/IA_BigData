from pyspark.sql import SparkSession
from pyspark.sql.functions import col, from_json, when, broadcast
from pyspark.sql.types import StructType, StringType, DoubleType, BooleanType, IntegerType

# 1. Inicializamos Spark
spark = SparkSession.builder \
    .appName("Deteccion_Fraude_Ecommerce") \
    .config("spark.cassandra.connection.host", "cassandra-db") \
    .config("spark.cassandra.connection.port", "9042") \
    .getOrCreate()

spark.sparkContext.setLogLevel("WARN")

# ==========================================
# 2. ESQUEMAS DE DATOS
# ==========================================
esquema_pagos = StructType() \
    .add("tx_id", StringType()) \
    .add("user_id", StringType()) \
    .add("amount", DoubleType()) \
    .add("currency", StringType()) \
    .add("card_country", StringType()) \
    .add("method", StringType()) \
    .add("flag_ataque", BooleanType())

esquema_visitas = StructType() \
    .add("timestamp", StringType()) \
    .add("user_id", StringType()) \
    .add("ip", StringType()) \
    .add("session_duration", IntegerType()) \
    .add("pages_visited", IntegerType()) \
    .add("is_bot", BooleanType()) \
    .add("flag_ataque", BooleanType())

# ==========================================
# 3. STREAMING 1: PROCESAMIENTO DE PAGOS
# ==========================================
df_kafka_pagos = spark.readStream \
    .format("kafka") \
    .option("kafka.bootstrap.servers", "kafka-broker:9092") \
    .option("subscribe", "datos_pagos") \
    .option("failOnDataLoss", "false") \
    .option("startingOffsets", "latest") \
    .load()

df_pagos = df_kafka_pagos.select(from_json(col("value").cast("string"), esquema_pagos).alias("data")).select("data.*")

df_pagos_evaluado = df_pagos \
    .withColumn("score_fraude", 
                when(col("amount") > 1000, 50).otherwise(0) + 
                when(col("card_country").isin(["RU", "CN"]), 50).otherwise(0) +
                when(col("method") == "Crypto", 20).otherwise(0)) \
    .withColumn("status", 
                when(col("score_fraude") >= 100, "BLOQUEADO")
                .when(col("score_fraude") >= 50, "SOSPECHOSO")
                .otherwise("OK"))

# Guardamos los pagos en cassandra
stream_pagos = df_pagos_evaluado.select("tx_id", "user_id", "amount", "card_country", "score_fraude", "status") \
    .writeStream \
    .outputMode("append") \
    .format("org.apache.spark.sql.cassandra") \
    .option("keyspace", "ecommerce") \
    .option("table", "alertas_fraude") \
    .option("checkpointLocation", "/tmp/checkpoints_pagos") \
    .start()

# ==========================================
# 4. STREAMING 2: PROCESAMIENTO DE VISITAS
# ==========================================


try:
    df_blacklist = spark.read.csv("file:///opt/workspace/blacklist_ips.csv", header=True)
    print("✅ Lista negra de IPs cargada en memoria para Broadcast.")
except Exception as e:
    print("⚠️ Aviso: No se encontró blacklist_ips.csv, se usará flujo sin enriquecer.")
    # Creamos un dataframe vacío con el mismo esquema por si falla el archivo
    df_blacklist = spark.createDataFrame([], StructType().add("ip", StringType()).add("riesgo_historico", StringType()))

df_kafka_visitas = spark.readStream \
    .format("kafka") \
    .option("kafka.bootstrap.servers", "kafka-broker:9092") \
    .option("subscribe", "datos_visitas") \
    .option("failOnDataLoss", "false") \
    .option("startingOffsets", "latest") \
    .load()

df_visitas = df_kafka_visitas.select(from_json(col("value").cast("string"), esquema_visitas).alias("data")).select("data.*")


# Cruzamos el streaming de visitas con la lista negra usando broadcast
df_visitas_enriquecidas = df_visitas.join(
    broadcast(df_blacklist), 
    on="ip", 
    how="left"
)

df_bots = df_visitas_enriquecidas.filter(
    (col("is_bot") == True) | (col("riesgo_historico").isNotNull())
)

# Guardamos el tráfico bot en cassandra
stream_visitas = df_bots.select("user_id", "ip", "pages_visited", "timestamp", "riesgo_historico") \
    .writeStream \
    .outputMode("append") \
    .format("org.apache.spark.sql.cassandra") \
    .option("keyspace", "ecommerce") \
    .option("table", "trafico_bot") \
    .option("checkpointLocation", "/tmp/checkpoints_visitas") \
    .start()

print("Motores de Visitas y Pagos INICIADOS...")
spark.streams.awaitAnyTermination()