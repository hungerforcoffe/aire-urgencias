"""Rutas del proyecto, resueltas desde la ubicación de este archivo.

Ninguna ruta absoluta queda escrita en el código: todo se deriva de la raíz del
repositorio, de modo que el proyecto funciona igual en el equipo de cualquier
integrante y dentro de la VM de Hadoop.

Uso:
    from src.rutas import RAW, INTERIM, PROCESSED

    destino = RAW / "sinca" / "sinca_mp25_2018-2024.csv"
"""

from pathlib import Path

# src/rutas.py -> src/ -> raíz del repositorio
RAIZ = Path(__file__).resolve().parent.parent

DATA = RAIZ / "data"
RAW = DATA / "raw"
INTERIM = DATA / "interim"
PROCESSED = DATA / "processed"

DOCS = RAIZ / "docs"
RECONOCIMIENTO = DOCS / "reconocimiento"
CALIDAD = DOCS / "calidad"

LOGS = RAIZ / "logs"
NOTEBOOKS = RAIZ / "notebooks"


def asegurar(*rutas: Path) -> None:
    """Crea los directorios indicados si no existen.

    Pensado para las rutas de escritura (interim, processed, logs). No se usa
    sobre `RAW`: la zona cruda se puebla solo desde los scripts de ingesta y sus
    archivos son inmutables.
    """
    for ruta in rutas:
        ruta.mkdir(parents=True, exist_ok=True)
