# `src/analisis/` — el modelo y el trabajo de Spark

Etapa 4.

## El modelo de asociación

[`asociacion.py`](asociacion.py) es la maquinaria; el cuaderno
[`notebooks/analisis_mp25_urgencias.ipynb`](../../notebooks/) es la narrativa.

- **Diseño:** case-crossover estratificado por tiempo, con Poisson condicional
  sobre conteos diarios. Cada ciudad se compara consigo misma dentro del mismo
  año, mes y día de la semana.
- **Ajuste:** temperatura (spline natural), humedad y circulación viral.
- **Exposición:** MP2.5 diario de ciudad, como media de las medias por estación.
- **Controles negativos:** traumatismos y accidentes de tránsito, desenlaces que la
  exposición no puede provocar. Quemaduras quedó fuera a propósito: en una ciudad
  que se calienta con leña responde de verdad al humo.

Las decisiones de diseño están fijadas en el docstring del módulo, no se eligen al
vuelo. Los resultados y su lectura están en el
[informe](../../docs/informe/INFORME.md).

## El trabajo de Spark

[`spark_grano_fino.py`](spark_grano_fino.py) corre **fuera** del repositorio, en la
VM de Hadoop y sobre HDFS, con su propio intérprete:

```bash
spark-submit --master yarn --deploy-mode client \
    --driver-memory 1g --executor-memory 2g --num-executors 2 \
    src/analisis/spark_grano_fino.py \
    hdfs:///user/$USER/aire/processed hdfs:///user/$USER/aire/trabajo
```

Baja las tablas al grano estación-día y establecimiento-día **sin promediar por
ciudad**: entre estaciones de Santiago, en la misma semana, hay diferencias de hasta
61 µg/m³, y promediar ahí perdería esa variación para siempre. La misma cadena está
replicada en PySpark sobre Colab en `notebooks/`.

## Los otros dos módulos

`graficos_reporte.py` y `generar_pdf.py` arman el informe de la **etapa de
reconocimiento**. Sus cifras están escritas a mano a propósito —vienen de los
hallazgos documentados— y no se recalculan.
