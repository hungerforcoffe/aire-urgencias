#!/usr/bin/env bash
# Qué hay realmente en la VM antes de intentar correr nada.
#
# El proyecto tiene una regla: los lectores detectan, no suponen. Vale igual para
# el entorno. Suponer una versión de Java o un gestor de recursos que no está es
# la forma más rápida de perder una tarde.
#
# Uso:  bash diagnostico_vm.sh

echo "=============================================="
echo " SISTEMA"
echo "=============================================="
echo "-- memoria --"
free -h 2>/dev/null || echo "  (sin free)"
echo "-- núcleos --"
nproc 2>/dev/null || echo "  (sin nproc)"
echo "-- disco --"
df -h / 2>/dev/null | tail -n +1

echo
echo "=============================================="
echo " JAVA"
echo "=============================================="
java -version 2>&1 || echo "  java NO está en el PATH"
echo "JAVA_HOME = ${JAVA_HOME:-(sin definir)}"

echo
echo "=============================================="
echo " HADOOP"
echo "=============================================="
if command -v hadoop > /dev/null 2>&1; then
  hadoop version 2>&1 | head -3
  echo "HADOOP_HOME     = ${HADOOP_HOME:-(sin definir)}"
  echo "HADOOP_CONF_DIR = ${HADOOP_CONF_DIR:-(sin definir)}"
else
  echo "  hadoop NO está en el PATH"
fi

echo
echo "-- demonios corriendo (jps) --"
if command -v jps > /dev/null 2>&1; then
  jps
  echo
  echo "  NameNode + DataNode         -> HDFS arriba"
  echo "  ResourceManager + NodeManager -> YARN arriba"
  echo "  si falta alguno, arrancar con start-dfs.sh y start-yarn.sh"
else
  echo "  jps no disponible; probando con ps"
  ps -ef | grep -E "NameNode|DataNode|ResourceManager|NodeManager" | grep -v grep
fi

echo
echo "-- HDFS responde? --"
hdfs dfs -ls / 2>&1 | head -10 || echo "  HDFS no responde"

echo
echo "=============================================="
echo " SPARK"
echo "=============================================="
if command -v spark-submit > /dev/null 2>&1; then
  spark-submit --version 2>&1 | grep -E "version|Scala|Branch" | head -5
  echo "SPARK_HOME = ${SPARK_HOME:-(sin definir)}"
  echo
  echo "-- Python que usará Spark --"
  echo "PYSPARK_PYTHON        = ${PYSPARK_PYTHON:-(sin definir, usará 'python3')}"
  echo "PYSPARK_DRIVER_PYTHON = ${PYSPARK_DRIVER_PYTHON:-(sin definir)}"
  python3 --version 2>&1 || echo "  python3 NO está"
else
  echo "  spark-submit NO está en el PATH"
  echo "  buscando instalaciones de Spark..."
  ls -d /opt/spark* /usr/local/spark* /usr/lib/spark* 2>/dev/null || echo "  ninguna encontrada"
fi

echo
echo "=============================================="
echo " QUÉ REPORTAR"
echo "=============================================="
echo "  1. versión de Java"
echo "  2. versión de Hadoop y de Spark"
echo "  3. qué demonios salieron en jps"
echo "  4. memoria total y núcleos"
echo
echo "Spark 3.x necesita Java 8, 11 o 17. Spark 4.x necesita Java 17 o 21."
echo "Si la versión de Java no calza con la de Spark, la sesión no arranca."
