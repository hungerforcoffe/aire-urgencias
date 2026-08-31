"""Qué comunas forman cada ciudad, y a qué ciudad pertenece una estación.

Vive aparte porque lo usan los dos lados del modelo: `estaciones.py` para
decidir la ciudad de cada estación de SINCA, y `ciudades.py` para construir
`dim_ciudad` y comprobar que ambos lados describan el mismo territorio.

La pertenencia se decide por **código de comuna**, no por cercanía ni por
región. Es la misma definición que usa el lado de la salud (`COMUNAS_CIUDAD` en
`src/ingesta/reconocer_deis.py`), de modo que el numerador y el denominador del
estudio hablen del mismo sitio.

Una estación cuya comuna no está en ninguna de las tres listas **no pertenece a
ninguna ciudad**: `ciudad_de` devuelve `None`. No se le asigna la ciudad más
cercana. Ver `docs/calidad/definicion_ciudades.md`.
"""

from __future__ import annotations

import re
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.ingesta.reconocer_deis import COMUNAS_CIUDAD  # noqa: E402

# Codigo de comuna del INE, solo para las comunas donde hay estacion de SINCA.
# No es un catalogo nacional: es lo justo para cruzar el lado del aire (que trae
# nombre de comuna) con el del DEIS (que trae codigo).
COD_COMUNA = {
    "santiago": 13101, "cerrillos": 13102, "cerro navia": 13103,
    "el bosque": 13105, "independencia": 13108, "la florida": 13110,
    "las condes": 13114, "pudahuel": 13124, "quilicura": 13125,
    "puente alto": 13201, "talagante": 13601,
    "talcahuano": 8110, "hualpen": 8112,
    "coyhaique": 11101,
}

CIUDADES = {
    "santiago": {
        "nombre": "Santiago",
        "region_codigo": 13,
        "region": "Metropolitana de Santiago",
        "comunas": COMUNAS_CIUDAD["Santiago"],
        "pct_lena_casen": 3.6,
    },
    "talcahuano": {
        "nombre": "Talcahuano",
        "region_codigo": 8,
        "region": "del Biobío",
        "comunas": COMUNAS_CIUDAD["Talcahuano"],
        "pct_lena_casen": 63.5,
    },
    "coyhaique": {
        "nombre": "Coyhaique",
        "region_codigo": 11,
        "region": "Aysén del General Carlos Ibáñez del Campo",
        "comunas": COMUNAS_CIUDAD["Coyhaique"],
        "pct_lena_casen": 82.5,
    },
}

# Estaciones que quedan fuera del alcance por decision del equipo, con el motivo.
# Estar aqui no las borra de dim_estacion: las deja con ciudad_id nulo, que es lo
# que impide que entren en un promedio por descuido.
FUERA_DE_ALCANCE = {
    "talagante": {
        # A qué ciudad se le habría asignado con un criterio de cercanía. Se
        # guarda para poder contarla y nombrarla en dim_ciudad, no para incluirla.
        "habria_sido": "santiago",
        "motivo": (
            "Comuna 13601, fuera de las 34 que definen Santiago. Está a 35,7 km del "
            "centro, más del doble que la siguiente más lejana, con terreno agrícola "
            "de por medio: es otra localidad y su MP2.5 mediría otra cosa. "
            "Decisión del equipo, 2026-08-26."
        ),
    },
}


def normalizar_nombre(s: str) -> str:
    """Clave de cruce: sin acentos, sin mayúsculas, sin puntuación.

    Hace falta porque los dos lados escriben lo mismo de formas distintas:
    «Estacion Coyhaique» sin tilde en el nombre de archivo y «Estación Coyhaique»
    con tilde en el catálogo, «Estación Consultorio San Vicente» en uno y
    «Estación Consultorio - San Vicente» en el otro. Cruzando literalmente
    coinciden 16 de 20; normalizando, las 20.

    No se normaliza más de lo necesario. Quitar «Consultorio», por ejemplo,
    haría colisionar la estación 241 con la 91 («San Vicente, Bomberos»), que
    está a 210 m y es otra estación.
    """
    s = unicodedata.normalize("NFKD", s.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"\(acreditada\)", " ", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return " ".join(s.split())


# Codigo de comuna -> ciudad del estudio. Se arma una vez a partir de CIUDADES,
# de modo que no exista una segunda lista de comunas que pueda desincronizarse.
_POR_CODIGO = {cod: cid for cid, d in CIUDADES.items() for cod in d["comunas"]}


def ciudad_de_codigo(codigo: int | None) -> str | None:
    """Ciudad del estudio a la que pertenece un código de comuna del INE.

    **Este es el cruce que corresponde al lado de la salud.** El DEIS trae el
    código de comuna, y el código no se escribe de dos maneras: Coyhaique es
    11101 en las dos fuentes, aunque el DEIS lo deletree «Coihaique» y SINCA
    «Coyhaique». Cruzar por nombre pierde esa comuna entera sin lanzar error.

    La otra razón para preferirlo: cubre las 34 comunas de Santiago, no solo
    las 11 que tienen estación de aire. Sobre `dim_establecimiento`, el cruce
    por código encuentra 122 establecimientos en Santiago y el cruce por nombre
    encuentra 46 — y los dos resultados parecen igual de razonables al mirarlos.
    """
    return _POR_CODIGO.get(codigo) if codigo is not None else None


def ciudad_de(comuna: str) -> str | None:
    """Ciudad del estudio a la que pertenece una comuna, **por nombre**.

    Es el cruce del **lado del aire**: el catálogo de SINCA identifica la comuna
    de cada estación por nombre y no por código, así que aquí no hay alternativa.
    Se apoya en `COD_COMUNA`, que solo conoce las comunas donde hay estación.

    Para cualquier tabla que traiga `comuna_codigo` —todo el lado de la salud—
    usar `ciudad_de_codigo`. Esta función devolvería `None` en comunas reales
    del estudio simplemente porque no tienen estación de aire, y ese `None` no
    se distingue de un «fuera de alcance» legítimo.

    Devolver None es deliberado y es lo que hace segura la tabla: una consulta
    que filtre por `ciudad_id = 'santiago'` y se olvide de todo lo demás excluye
    sola las estaciones fuera de alcance. Si en cambio se les asignara la ciudad
    más cercana, el descuido las incluiría.
    """
    clave = normalizar_nombre(comuna)
    if not clave or clave in FUERA_DE_ALCANCE:
        return None
    cod = COD_COMUNA.get(clave)
    if cod is None:
        return None
    for ciudad_id, datos in CIUDADES.items():
        if cod in datos["comunas"]:
            return ciudad_id
    return None


def motivo_exclusion(comuna: str) -> str:
    """Por qué una comuna quedó fuera. Cadena vacía si está dentro."""
    entrada = FUERA_DE_ALCANCE.get(normalizar_nombre(comuna))
    return entrada["motivo"] if entrada else ""


def habria_sido(comuna: str) -> str | None:
    """Ciudad a la que un criterio de cercanía habría asignado esta comuna."""
    entrada = FUERA_DE_ALCANCE.get(normalizar_nombre(comuna))
    return entrada["habria_sido"] if entrada else None
