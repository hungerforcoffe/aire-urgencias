"""Normaliza la vigilancia de virus respiratorios del ISP para el catálogo.

Qué es esta fuente
------------------
Los informes semanales de circulación de virus respiratorios del Instituto de
Salud Pública, 2018-2026. Es el **control del confusor** que faltaba: las
urgencias respiratorias suben en invierno tanto por el humo como por la
circulación de virus, y sin esta variable el modelo le atribuye al MP2.5 parte
de lo que hizo el VRS.

La extracción desde los PDF la hizo otra integrante del equipo. Acá llega ya
tabulada; este módulo solo recorta y valida antes de que entre al catálogo.

Qué se saca, y por qué
----------------------
El archivo de origen trae 36 columnas, de las cuales 14 son de la extracción y
no del fenómeno: URL del informe, ruta del PDF en disco, tamaño en bytes,
estado de descarga, y los chequeos internos que hizo el extractor.

Dos razones para no publicarlas:

1. `ruta_pdf` trae una ruta absoluta de un Google Drive personal. La regla del
   proyecto es que no hay rutas absolutas en el código ni en los datos, y menos
   en una tabla que consulta todo el equipo.
2. `codetecciones_reportadas` y `discrepancia_total_agentes` venían como
   `object` de pandas aunque su contenido es booleano puro. Glue infiere el
   tipo leyendo el Parquet: una columna así se cataloga como texto y después
   `WHERE discrepancia = true` no filtra nada.

**Se conservan `estado_fuente` y `panel_version`**, que no son fontanería:

* `estado_fuente` dice por qué una semana está en nulo — hay 10 informes
  catalogados que el ISP no publica y 4 semanas sin informe. Sin esa columna un
  nulo de cobertura y un nulo de «no existe» son indistinguibles.
* `panel_version` es la razón de ser de `actividad_viral_clasica_100`. El panel
  del ISP cambió tres veces en el período —6, 7 y 9 agentes— y esa variable
  existe para mantener comparables los mismos seis virus de punta a punta.

Lo que se pierde al recortar queda escrito en `docs/calidad/isp_virus.md`,
incluida la inconsistencia que el extractor detectó en el informe de 2024-SE47.

Dos tablas, dos consumidores
----------------------------
`isp_virus_semana` se une a `analitico_ciudad_semana` por `semana_id`;
`isp_virus_dia` es la misma serie repetida por día, que es lo que necesita el
case-crossover de `src/analisis/asociacion.py`, que desplaza rezagos por día y
estratifica por día de la semana.

Uso
---
    python -m src.procesamiento.isp_virus construir
    python -m src.procesamiento.isp_virus verificar
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.procesamiento.tiempo import semana_mmwr  # noqa: E402
from src.rutas import LOGS, PROCESSED, RAW, asegurar  # noqa: E402

log = logging.getLogger("isp-virus")

ORIGEN = RAW / "isp"
FUENTE_SEMANAL = ORIGEN / "isp_vigilancia_viral_semanal_2018_2026.parquet"
FUENTE_DIARIA = ORIGEN / "isp_vigilancia_viral_diaria_2018_2026.parquet"

SALIDA_SEMANA = PROCESSED / "isp_virus_semana"
SALIDA_DIA = PROCESSED / "isp_virus_dia"

# Las 14 que no viajan al catálogo. Ver el docstring: ocho son la fontanería de
# la descarga y seis son chequeos internos del extractor.
FUERA = [
    "url_publicada", "url_pdf", "archivo", "estado_descarga", "ruta_pdf",
    "archivo_pdf", "bytes", "archivo_extraido",
    "codetecciones_reportadas", "n_agentes_panel", "suma_agentes_panel",
    "diferencia_total_agentes", "discrepancia_total_agentes", "observacion_fuente",
]

# Mínimos por debajo de los cuales no se publica. Son el orden de magnitud de lo
# medido, no un «> 0»: una tabla con tres semanas pasaría un chequeo de vacío y
# dejaría el modelo ajustando por una serie que casi no existe.
MIN_SEMANAS = 400
MIN_CON_DATO = 400
SEMANAS_ESPERADAS = 452


class Rechazada(Exception):
    """Lo que llegó no es publicable."""


def recortar(d: pd.DataFrame, cual: str) -> pd.DataFrame:
    """Saca las columnas de extracción y agrega la clave de semana del proyecto.

    `semana_id` no viene en el origen y se construye acá: es como `dim_tiempo` y
    `analitico_ciudad_semana` nombran una semana, así que con ella el cruce es
    una sola clave en vez de dos columnas.
    """
    sobran = [c for c in FUERA if c in d.columns]
    faltan = [c for c in FUERA if c not in d.columns]
    if faltan:
        # Que una columna a borrar no exista no es inocuo: significa que el
        # archivo de origen cambió de forma y el recorte ya no describe lo que
        # está pasando. Se avisa, no se ignora.
        log.warning("%s: estas columnas ya no estaban en el origen: %s", cual, faltan)
    fuera = d.drop(columns=sobran)
    fuera.insert(2, "semana_id",
                 fuera.anio_epi.astype(str) + "-W" + fuera.semana_epi.astype(str).str.zfill(2))
    return fuera


def validar(d: pd.DataFrame, cual: str, filas_esperadas: int) -> None:
    """Regla 5: la tabla no es buena hasta que lo demuestra."""
    if len(d) != filas_esperadas:
        raise Rechazada(f"{cual}: {len(d)} filas, se esperaban {filas_esperadas}")
    if len(d) < MIN_SEMANAS:
        raise Rechazada(f"{cual}: solo {len(d)} filas")

    con = d.actividad_viral_clasica_100.notna().sum()
    if con < MIN_CON_DATO:
        raise Rechazada(f"{cual}: solo {con} filas con actividad viral")

    # Glue infiere los tipos leyendo el Parquet. Una columna `object` se cataloga
    # como texto y rompe cualquier comparación numérica o booleana en Athena.
    objeto = [c for c in d.columns if d[c].dtype == object]
    if objeto:
        raise Rechazada(f"{cual}: columnas de tipo object que Athena leería como "
                        f"texto: {objeto}")

    quedan = [c for c in FUERA if c in d.columns]
    if quedan:
        raise Rechazada(f"{cual}: sobrevivieron columnas que debían salir: {quedan}")

    # La semana MMWR es la que usa el DEIS, y es la que hace que el cruce
    # apunte a la semana correcta. Se comprueba contra la del proyecto, no se
    # confía en la del origen.
    mal = [(r.anio_epi, r.semana_epi)
           for r in d.drop_duplicates("semana_id").itertuples()
           if semana_mmwr(r.fecha_inicio_semana.date()) != (r.anio_epi, r.semana_epi)]
    if mal:
        raise Rechazada(f"{cual}: {len(mal)} semanas que no son MMWR, p. ej. {mal[:3]}")


def cmd_construir(args) -> int:
    for ruta in (FUENTE_SEMANAL, FUENTE_DIARIA):
        if not ruta.exists():
            raise SystemExit(
                f"Falta {ruta}.\n"
                f"  Los dos Parquet del ISP van en {ORIGEN}, que es la zona cruda "
                f"de esta fuente.")

    sem = recortar(pd.read_parquet(FUENTE_SEMANAL), "semanal")
    dia = recortar(pd.read_parquet(FUENTE_DIARIA), "diaria")

    validar(sem, "semanal", SEMANAS_ESPERADAS)
    validar(dia, "diaria", SEMANAS_ESPERADAS * 7)

    # Cada tabla en su carpeta, con un solo Parquet dentro: es la forma que ya
    # tienen dim_tiempo y analitico_ciudad_semana, y la que catalogo.py espera
    # para descubrirlas bajo processed/.
    for d, destino in ((sem, SALIDA_SEMANA), (dia, SALIDA_DIA)):
        asegurar(destino)
        d.to_parquet(destino / f"{destino.name}.parquet", index=False)

    print(f"  {SALIDA_SEMANA.name:<18} {len(sem):>5} filas x {len(sem.columns)} columnas")
    print(f"  {SALIDA_DIA.name:<18} {len(dia):>5} filas x {len(dia.columns)} columnas")
    print(f"  columnas retiradas : {len(FUERA)}")
    print(f"  semanas con dato   : {int(sem.actividad_viral_clasica_100.notna().sum())}"
          f" de {len(sem)}")
    print("  por que faltan     : "
          + ", ".join(f"{k}={v}" for k, v in sem.estado_fuente.value_counts().items()))
    print("  paneles del ISP    : "
          + ", ".join(f"{k}={v}" for k, v in sem.panel_version.value_counts().items()))
    print(f"\n  columnas publicadas: {', '.join(sem.columns)}")
    return 0


def cmd_verificar(args) -> int:
    problemas = []
    for destino, filas in ((SALIDA_SEMANA, SEMANAS_ESPERADAS),
                           (SALIDA_DIA, SEMANAS_ESPERADAS * 7)):
        ruta = destino / f"{destino.name}.parquet"
        if not ruta.exists():
            print(f"  falta {ruta}; corre primero `construir`")
            return 1
        d = pd.read_parquet(ruta)
        try:
            validar(d, destino.name, filas)
            print(f"  {destino.name:<18} {len(d):>5} filas x {len(d.columns)} col   ok")
        except Rechazada as e:
            problemas.append(str(e))
            print(f"  {destino.name:<18} {e}")

    # El cruce contra el panel del análisis, que es para lo que existe la tabla.
    panel = PROCESSED / "analitico_ciudad_semana" / "analitico_ciudad_semana.parquet"
    if panel.exists():
        p = pd.read_parquet(panel, columns=["semana_id"])
        i = pd.read_parquet(SALIDA_SEMANA / f"{SALIDA_SEMANA.name}.parquet",
                            columns=["semana_id", "actividad_viral_clasica_100"])
        falta = set(p.semana_id) - set(i.semana_id)
        sin = set(p.semana_id) - set(i[i.actividad_viral_clasica_100.notna()].semana_id)
        print(f"  semanas del panel sin fila en el ISP : {len(falta) or 'ninguna'}")
        print(f"  semanas del panel que quedan en nulo : {len(sin)}"
              f"  ({100 * len(sin) / p.semana_id.nunique():.1f} % de las semanas)")
        if falta:
            problemas.append(f"{len(falta)} semanas del panel sin fila en el ISP")

    if problemas:
        print(f"\n  {len(problemas)} problema(s)")
        return 1
    print("  todo consistente")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0],
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("construir").set_defaults(fn=cmd_construir)
    sub.add_parser("verificar").set_defaults(fn=cmd_verificar)
    args = p.parse_args(argv)
    asegurar(LOGS)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(LOGS / "isp_virus.log", encoding="utf-8")])
    try:
        return args.fn(args)
    except Rechazada as e:
        log.error("no se publica: %s", e)
        print(f"  ABORTADO - {e}\n  Las tablas anteriores quedan intactas.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
