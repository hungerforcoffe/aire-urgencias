"""Trabajo de Spark: lleva las tablas del proyecto al grano fino del análisis.

Produce dos salidas, ninguna agregada por ciudad:

  * `urgencias_establecimiento_dia` — urgencias respiratorias por establecimiento
    y día, con el desglose de los dos extremos etarios.
  * `aire_estacion_dia` — MP2.5 por estación y día, sin promediar entre estaciones.

**No promedia por ciudad a propósito.** Entre estaciones de Santiago, en la misma
semana de invierno, hay diferencias de hasta 61 µg/m³; promediarlas aquí dejaría
esa variación fuera del alcance del análisis para siempre. El promedio, el radio y
la ponderación son decisiones de análisis y pertenecen a la consulta.

Asociación, nunca causalidad. Es un estudio ecológico observacional.

Se corre con spark-submit, no como módulo del repositorio: la VM usa su propio
intérprete y no tiene instalado el paquete `src`. Por eso no importa nada de
`src/` y lee las comunas de cada ciudad desde `dim_ciudad`, que ya viaja con los
datos — una sola definición de qué es Santiago, no dos.

Uso
---
    spark-submit --master yarn --deploy-mode client \
        --driver-memory 1g --executor-memory 2g --num-executors 2 \
        spark_grano_fino.py hdfs:///user/$USER/aire/processed hdfs:///user/$USER/aire/trabajo
"""

import sys

from pyspark.sql import SparkSession
from pyspark.sql import functions as F

# Las seis causas respiratorias se leen de dim_causa, no se escriben aquí.
# Un identificador copiado a mano es un identificador que se desactualiza.
HORAS_MINIMAS_DIA = 18  # de 24. Ver docs/calidad/cobertura_horaria_semanal.md


def ciudades_por_comuna(spark, base):
    """Tabla comuna_codigo -> ciudad_id, derivada de dim_ciudad.

    `dim_ciudad.comunas` es una cadena con los códigos separados por coma. Se
    explota en filas para poder cruzar. La ventaja de sacarlo de ahí y no de una
    lista escrita en este archivo es que existe una sola definición de qué
    comunas forman cada ciudad, y vive junto a los datos.
    """
    dim = spark.read.parquet(f"{base}/dim_ciudad")
    return (dim
            .select("ciudad_id",
                    F.explode(F.split("comunas", ",")).alias("cod"))
            .select("ciudad_id",
                    F.trim(F.col("cod")).cast("bigint").alias("comuna_codigo")))


def main(base, salida):
    spark = (SparkSession.builder
             .appName("aire-urgencias-grano-fino")
             .config("spark.sql.session.timeZone", "America/Santiago")
             # El resultado es chico: 200 particiones de shuffle solo generarían
             # 200 archivos casi vacíos y mucho overhead en un cluster de un nodo.
             .config("spark.sql.shuffle.partitions", "16")
             .getOrCreate())
    spark.sparkContext.setLogLevel("WARN")
    print(f"Spark {spark.version} · master {spark.sparkContext.master}")

    urg = spark.read.parquet(f"{base}/hecho_urgencia")
    med = spark.read.parquet(f"{base}/hecho_medicion")
    est = spark.read.parquet(f"{base}/dim_establecimiento")
    cau = spark.read.parquet(f"{base}/dim_causa")

    # --- establecimientos de las tres ciudades, cruzando por CODIGO de comuna ---
    # Por nombre se perdería Coyhaique entera y sin lanzar error: el DEIS escribe
    # «Coihaique» y el catálogo de aire «Coyhaique». El código es 11101 en ambos.
    comunas = ciudades_por_comuna(spark, base)
    est_ciudad = (est.join(F.broadcast(comunas), "comuna_codigo")
                     .select("establecimiento_id", "nombre", "comuna", "ciudad_id"))
    n_est = est_ciudad.count()
    print(f"establecimientos en las tres ciudades: {n_est}")
    est_ciudad.groupBy("ciudad_id").count().orderBy("ciudad_id").show()

    # --- urgencias respiratorias por establecimiento y dia ---
    resp = [f.causa_id for f in
            cau.filter("es_respiratoria_detalle").select("causa_id").collect()]
    print(f"causas respiratorias de detalle: {sorted(resp)}")

    urg_dia = (urg
               .filter(F.col("causa_id").isin(resp))
               .join(F.broadcast(est_ciudad), "establecimiento_id")
               .groupBy("ciudad_id", "establecimiento_id", "fecha")
               .agg(F.sum("total").alias("urg_resp"),
                    F.sum("menores_1").alias("urg_menores_1"),
                    F.sum("de_65_y_mas").alias("urg_65_y_mas")))

    # --- MP2.5 por estacion y dia, sin promediar entre estaciones ---
    aire_dia = (med
                .filter(F.col("parametro_id") == "mp25")
                .groupBy("ciudad_id", "estacion_id", "fecha")
                .agg(F.avg("valor").alias("mp25"),
                     F.max("valor").alias("mp25_max_hora"),
                     F.count("valor").alias("horas"))
                .filter(F.col("horas") >= HORAS_MINIMAS_DIA))

    # --- escritura ---
    # coalesce(1) porque el resultado son decenas de miles de filas, no millones:
    # un archivo se descarga y se abre en pandas sin ceremonia. No se haría esto
    # con una salida grande, donde partir el archivo es justamente la gracia.
    (urg_dia.coalesce(1).write.mode("overwrite")
     .parquet(f"{salida}/urgencias_establecimiento_dia"))
    (aire_dia.coalesce(1).write.mode("overwrite")
     .parquet(f"{salida}/aire_estacion_dia"))

    n_urg = urg_dia.count()
    n_aire = aire_dia.count()
    print(f"\nurgencias establecimiento x día : {n_urg:,} filas")
    print(f"aire estación x día            : {n_aire:,} filas")

    # Control: ninguna de las dos salidas puede venir vacía. Un trabajo que
    # escribe cero filas y termina con exito es un fallo que parece un exito.
    if n_urg == 0 or n_aire == 0:
        raise SystemExit("Una de las salidas quedó vacía. Revisar el cruce.")
    if n_est == 0:
        raise SystemExit("Ningún establecimiento cruzó con las tres ciudades.")

    print(f"\nescrito en {salida}")
    spark.stop()


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(f"uso: {sys.argv[0]} <base_processed> <salida>")
    main(sys.argv[1], sys.argv[2])
