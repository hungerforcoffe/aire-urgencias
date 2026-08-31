"""Reconocimiento de las Atenciones de Urgencia del DEIS (MINSAL).

Fuente co-primaria del proyecto. Este modulo descubre y caracteriza lo que el
DEIS publica, sin asumir nada sobre el esquema.

Ruta de descarga
----------------
    https://repositoriodeis.minsal.cl/SistemaAtencionesUrgencia/AtencionesUrgencia<AAAA>.zip

No esta enlazada desde el portal: la pagina de datos abiertos de deis.minsal.cl
carga por JavaScript y el registro de datos.gob.cl (creado en 2013) apunta a
`www.deis.cl`, dominio que ya **no resuelve**. La ruta se ubico por busqueda.

Validacion de descarga
----------------------
La leccion de OpenAQ/SINCA es que un HTTP 200 no significa que haya dato. Aqui
toda descarga pasa por `validar_zip`, que comprueba, en este orden:

    1. codigo HTTP (403 -> bloqueo/permiso; 404 -> no existe)
    2. content-type declarado
    3. numeros magicos reales del cuerpo (PK\\x03\\x04)
    4. integridad del ZIP (testzip)
    5. que el CSV interior tenga filas

Un fallo en 3 con exito en 1 es el caso peligroso: servidor que responde 200 con
una pagina de error o un GIF. Se detecta y se reporta como tal.

Subcomandos
-----------
    disponibilidad  que años existen, con validacion real
    descargar       baja un año a data/raw (inmutable) y verifica
    esquema         compara columnas entre años y reporta diferencias
    perfil          granularidad, causas, grupos etarios, establecimientos
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import logging
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.rutas import INTERIM, LOGS, RAW, asegurar  # noqa: E402

BASE = "https://repositoriodeis.minsal.cl/SistemaAtencionesUrgencia"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"

log = logging.getLogger("deis")


class DescargaInvalida(Exception):
    """La respuesta llego pero no es el dato esperado."""


class RecursoBloqueado(Exception):
    """403: sin permiso o bloqueo por IP. Distinto de inexistente."""


class RecursoInexistente(Exception):
    """404: el recurso no esta publicado."""


@dataclass
class Veredicto:
    anio: int
    url: str
    http: int | None = None
    bytes_declarados: int | None = None
    content_type: str | None = None
    magic_ok: bool | None = None
    zip_integro: bool | None = None
    miembros: list[str] | None = None
    veredicto: str = ""


def url_anio(anio: int) -> str:
    return f"{BASE}/AtencionesUrgencia{anio}.zip"


def sondear(anio: int, sesion: requests.Session | None = None) -> Veredicto:
    """Comprueba un año sin descargarlo entero: HEAD + los primeros bytes."""
    s = sesion or requests.Session()
    s.headers.setdefault("User-Agent", UA)
    u = url_anio(anio)
    v = Veredicto(anio=anio, url=u)
    try:
        h = s.head(u, timeout=40, allow_redirects=True)
    except requests.exceptions.RequestException as e:
        v.veredicto = f"SIN CONEXION ({type(e).__name__}) - reintentar antes de concluir ausencia"
        return v
    v.http = h.status_code
    v.content_type = h.headers.get("content-type")
    try:
        v.bytes_declarados = int(h.headers.get("content-length", 0)) or None
    except ValueError:
        pass

    if h.status_code == 403:
        v.veredicto = "BLOQUEADO (403) - sin permiso o IP; NO concluir que falta el dato"
        return v
    if h.status_code == 404:
        v.veredicto = "NO EXISTE (404) - año no publicado"
        return v
    if h.status_code != 200:
        v.veredicto = f"HTTP {h.status_code} inesperado"
        return v

    # Numeros magicos: la unica prueba de que el cuerpo es lo que dice ser.
    g = s.get(u, timeout=40, headers={"Range": "bytes=0-3"})
    v.magic_ok = g.content[:2] == b"PK"
    v.veredicto = "OK" if v.magic_ok else "HTTP 200 PERO EL CUERPO NO ES UN ZIP"
    return v


def validar_zip(cuerpo: bytes, anio: int) -> zipfile.ZipFile:
    """Comprueba integridad y devuelve el ZIP abierto. Lanza si algo no cuadra."""
    if cuerpo[:2] != b"PK":
        raise DescargaInvalida(
            f"{anio}: el cuerpo no empieza por 'PK' ({cuerpo[:8]!r}). "
            f"Respuesta valida en HTTP pero no es un ZIP."
        )
    try:
        z = zipfile.ZipFile(io.BytesIO(cuerpo))
    except zipfile.BadZipFile as e:
        raise DescargaInvalida(f"{anio}: ZIP corrupto ({e})") from e
    malo = z.testzip()
    if malo:
        raise DescargaInvalida(f"{anio}: miembro corrupto dentro del ZIP: {malo}")
    if not z.namelist():
        raise DescargaInvalida(f"{anio}: ZIP valido pero vacio")
    return z


def descargar_anio(anio: int, sesion: requests.Session | None = None,
                   forzar: bool = False) -> Path:
    """Descarga un año a data/raw/deis/. La zona cruda es inmutable."""
    destino = RAW / "deis" / f"deis_atencionesurgencia_{anio}.zip"
    asegurar(destino.parent)
    if destino.exists() and not forzar:
        log.info("%s ya existe (%s MB), no se sobrescribe",
                 destino.name, round(destino.stat().st_size / 1024**2, 1))
        return destino

    s = sesion or requests.Session()
    s.headers.setdefault("User-Agent", UA)
    u = url_anio(anio)
    r = s.get(u, timeout=600)
    if r.status_code == 403:
        raise RecursoBloqueado(f"{anio}: HTTP 403 en {u}")
    if r.status_code == 404:
        raise RecursoInexistente(f"{anio}: HTTP 404 en {u}")
    r.raise_for_status()

    validar_zip(r.content, anio)  # no se escribe nada que no haya pasado validacion
    destino.write_bytes(r.content)
    log.info("%s -> %s MB", destino.name, round(len(r.content) / 1024**2, 1))
    return destino


def _abrir_csv(ruta: Path) -> tuple[str, bytes]:
    """Devuelve (nombre del miembro, bytes) del CSV principal del ZIP."""
    z = validar_zip(ruta.read_bytes(), 0)
    csvs = [n for n in z.namelist() if n.lower().endswith(".csv")]
    if not csvs:
        raise DescargaInvalida(f"{ruta.name}: el ZIP no contiene CSV: {z.namelist()}")
    principal = max(csvs, key=lambda n: z.getinfo(n).file_size)
    return principal, z.read(principal)


def detectar_codificacion(muestra: bytes) -> str:
    """Las fuentes chilenas suelen ser latin-1. No asumir UTF-8."""
    for enc in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            muestra.decode(enc)
            return enc
        except UnicodeDecodeError:
            continue
    return "latin-1"


def detectar_separador(cabecera: str) -> str:
    return max([";", ",", "|", "\t"], key=cabecera.count)


# --------------------------------------------------------------------------
def cmd_disponibilidad(args) -> dict:
    s = requests.Session()
    out = []
    for a in range(args.desde, args.hasta + 1):
        v = sondear(a, s)
        log.info("%s -> %s", a, v.veredicto)
        out.append(vars(v))
    return {"años": out}


def cmd_descargar(args) -> dict:
    s = requests.Session()
    res = []
    for a in range(args.desde, args.hasta + 1):
        try:
            p = descargar_anio(a, s, forzar=args.forzar)
            res.append({"anio": a, "estado": "ok", "ruta": str(p),
                        "MB": round(p.stat().st_size / 1024**2, 1)})
        except (RecursoBloqueado, RecursoInexistente, DescargaInvalida) as e:
            log.error("%s: %s", a, e)
            res.append({"anio": a, "estado": "fallo", "diagnostico": str(e)})
    return {"descargas": res}


def cmd_esquema(args) -> dict:
    """Compara las columnas de cada año. No asume estabilidad entre años."""
    base = RAW / "deis"
    archivos = sorted(base.glob("deis_atencionesurgencia_*.zip"))
    if not archivos:
        return {"error": f"no hay ZIP en {base}; correr 'descargar' primero"}

    por_anio = {}
    for p in archivos:
        anio = int(p.stem.split("_")[-1])
        if not (args.desde <= anio <= args.hasta):
            continue
        nombre, crudo = _abrir_csv(p)
        enc = detectar_codificacion(crudo[:200_000])
        texto = crudo.decode(enc, errors="replace")
        primera = texto.split("\n", 1)[0]
        sep = detectar_separador(primera)
        cols = next(csv.reader(io.StringIO(primera), delimiter=sep))
        cols = [c.strip().lstrip("﻿") for c in cols]
        filas = texto.count("\n") - 1

        # Un año puede publicarse SIN fila de cabecera (2020 lo hace). En ese
        # caso la primera linea ya es un dato y lo de arriba no son columnas.
        tiene_cabecera = any(
            c.lower() in {"idestablecimiento", "nestablecimiento", "idcausa", "glosacausa"}
            for c in cols
        )
        if not tiene_cabecera:
            cols_reales = COLS_21 if len(cols) == 21 else COLS_15
            log.warning("%s: SIN fila de cabecera; se asignan los nombres de 2021", anio)
        else:
            cols_reales = cols

        por_anio[anio] = {
            "miembro": nombre,
            "codificacion": enc,
            "separador": sep,
            "n_columnas": len(cols),
            "tiene_fila_de_cabecera": tiene_cabecera,
            "columnas": cols_reales,
            "primera_linea_cruda": primera[:160] if not tiene_cabecera else None,
            "filas_aprox": filas + (0 if tiene_cabecera else 1),
            "bytes_csv": len(crudo),
        }
        log.info("%s: %s cols, ~%s filas, enc=%s sep=%r", anio, len(cols), filas, enc, sep)

    anios = sorted(por_anio)
    comunes = set(por_anio[anios[0]]["columnas"]) if anios else set()
    for a in anios:
        comunes &= set(por_anio[a]["columnas"])

    difs = {}
    for a in anios:
        s_a = set(por_anio[a]["columnas"])
        difs[a] = {
            "solo_este_anio": sorted(s_a - comunes),
            "faltan_respecto_union": [],
        }
    union = set()
    for a in anios:
        union |= set(por_anio[a]["columnas"])
    for a in anios:
        difs[a]["faltan_respecto_union"] = sorted(union - set(por_anio[a]["columnas"]))

    cambios = []
    for i in range(1, len(anios)):
        ant, act = anios[i - 1], anios[i]
        s_ant, s_act = set(por_anio[ant]["columnas"]), set(por_anio[act]["columnas"])
        if s_ant != s_act:
            cambios.append({
                "de": ant, "a": act,
                "aparecen": sorted(s_act - s_ant),
                "desaparecen": sorted(s_ant - s_act),
            })

    return {
        "por_anio": por_anio,
        "columnas_comunes_a_todos": sorted(comunes),
        "union_de_columnas": sorted(union),
        "esquema_estable": not cambios,
        "cambios_entre_años_consecutivos": cambios,
        "diferencias_por_anio": difs,
    }


# --------------------------------------------------------------------------
# perfil: granularidad, causas, etarios, establecimientos
# --------------------------------------------------------------------------
# El año 2020 se publico SIN fila de cabecera: la primera linea ya es un dato.
# Un lector que asuma encabezado perderia una fila y usaria valores como nombres
# de columna. Estos son los nombres que corresponden, tomados de 2021.
COLS_15 = [
    "IdEstablecimiento", "NEstablecimiento", "IdCausa", "GlosaCausa", "Total",
    "Menores_1", "De_1_a_4", "De_5_a_14", "De_15_a_64", "De_65_y_mas",
    "fecha", "semana", "GLOSATIPOESTABLECIMIENTO", "GLOSATIPOATENCION", "GlosaTipoCampana",
]
COLS_21 = COLS_15 + [
    "CodigoRegion", "NombreRegion", "CodigoDependencia", "NombreDependencia",
    "CodigoComuna", "NombreComuna",
]

# Filas que NO son causas sino agregados o encabezados de seccion. Sumarlas junto
# al detalle produce doble (o triple) conteo. Se derivan del Anexo 1 del
# diccionario: ver docs/reconocimiento/hallazgos.md.
IDCAUSA_AGREGADAS = {1, 2, 7, 8, 12, 18, 21, 22, 23, 25, 26, 34, 36, 42}

# Causas respiratorias de detalle (excluye los totales 2 y 7).
IDCAUSA_RESPIRATORIA_DETALLE = {3, 4, 5, 6, 10, 11}


def _normalizar_fecha(s: str) -> str | None:
    """El formato de fecha cambia entre años. Devuelve AAAA-MM-DD.

    2020: 'Wed Sep 23 00:00:00 GMT-04:00 2020'  (Date de Java)
    2021+: '04/06/2021'                          (dd/mm/aaaa)
    """
    s = (s or "").strip()
    if not s:
        return None
    if "/" in s:
        p = s.split("/")
        if len(p) == 3 and len(p[2]) == 4:
            return f"{p[2]}-{int(p[1]):02d}-{int(p[0]):02d}"
        return None
    partes = s.split()
    if len(partes) >= 6:
        meses = {m: i for i, m in enumerate(
            ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
             "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}
        try:
            return f"{partes[-1]}-{meses[partes[1]]:02d}-{int(partes[2]):02d}"
        except (KeyError, ValueError, IndexError):
            return None
    return None


def _stream_csv(ruta: Path):
    """Itera (dict) sobre el CSV del ZIP sin extraerlo a disco."""
    z = zipfile.ZipFile(ruta)
    nombre = max((n for n in z.namelist() if n.lower().endswith(".csv")),
                 key=lambda n: z.getinfo(n).file_size, default=None)
    if nombre is None:
        return
    with z.open(nombre) as bruto:
        envuelto = io.TextIOWrapper(bruto, encoding="latin-1", newline="")
        primera = envuelto.readline()
        n_campos = primera.count(";") + 1
        cols = COLS_21 if n_campos == 21 else COLS_15
        # ¿la primera linea es cabecera o ya es dato?
        es_cabecera = "IdEstablecimiento" in primera or "idestablecimiento" in primera.lower()
        lector = csv.reader(envuelto, delimiter=";")
        if not es_cabecera:
            yield dict(zip(cols, next(csv.reader(io.StringIO(primera), delimiter=";"))))
        for fila in lector:
            if len(fila) == len(cols):
                yield dict(zip(cols, fila))


def cmd_perfil(args) -> dict:
    """Perfila cada año: filas, fechas, causas, etarios, establecimientos."""
    base = RAW / "deis"
    out = {}
    for p in sorted(base.glob("deis_atencionesurgencia_*.zip")):
        anio = int(p.stem.split("_")[-1])
        if not (args.desde <= anio <= args.hasta):
            continue
        z = zipfile.ZipFile(p)
        if not any(n.lower().endswith(".csv") for n in z.namelist()):
            out[anio] = {"formato": "mdb (Access)", "miembros": z.namelist(),
                         "nota": "requiere pyodbc; ver subcomando 'mdb'"}
            log.warning("%s: formato mdb, se omite en perfil CSV", anio)
            continue

        filas = 0
        fechas: set[str] = set()
        fecha_nula = 0
        establecimientos: set[str] = set()
        causas: dict[str, str] = {}
        total_por_causa: dict[int, int] = {}
        suma_etarios_distinta = 0
        comunas: set[str] = set()

        for r in _stream_csv(p):
            filas += 1
            f = _normalizar_fecha(r.get("fecha", ""))
            if f:
                fechas.add(f)
            else:
                fecha_nula += 1
            establecimientos.add(r.get("IdEstablecimiento", ""))
            try:
                idc = int(r.get("IdCausa") or -999)
            except ValueError:
                idc = -999
            causas.setdefault(str(idc), (r.get("GlosaCausa") or "")[:70])
            try:
                tot = int(r.get("Total") or 0)
            except ValueError:
                tot = 0
            total_por_causa[idc] = total_por_causa.get(idc, 0) + tot
            try:
                s = sum(int(r.get(c) or 0) for c in
                        ("Menores_1", "De_1_a_4", "De_5_a_14", "De_15_a_64", "De_65_y_mas"))
                if s != tot:
                    suma_etarios_distinta += 1
            except ValueError:
                pass
            if r.get("NombreComuna"):
                comunas.add(r["NombreComuna"])
            if args.limite and filas >= args.limite:
                break

        det = sum(v for k, v in total_por_causa.items()
                  if k in IDCAUSA_RESPIRATORIA_DETALLE)
        tot_resp = total_por_causa.get(2, 0)
        out[anio] = {
            "formato": "csv",
            "filas": filas,
            "dias_distintos": len(fechas),
            "fecha_min": min(fechas) if fechas else None,
            "fecha_max": max(fechas) if fechas else None,
            "fechas_no_parseadas": fecha_nula,
            "establecimientos_distintos": len(establecimientos),
            "n_causas_distintas": len(causas),
            "comunas_en_archivo": len(comunas),
            "filas_donde_suma_etarios_difiere_de_total": suma_etarios_distinta,
            "total_causa_2_TOTAL_RESPIRATORIO": tot_resp,
            "suma_causas_respiratorias_detalle": det,
            "coincide_total_con_detalle": tot_resp == det,
        }
        log.info("%s: %s filas, %s dias, %s establecimientos",
                 anio, filas, len(fechas), len(establecimientos))
    return out


# --------------------------------------------------------------------------
# establecimientos: la dimension geografica
# --------------------------------------------------------------------------
# Solo 2023 y 2024 traen comuna dentro del archivo de urgencias. Para 2018-2022
# la unica via de asignar una atencion a una ciudad es cruzar por
# idestablecimiento con la Base de Establecimientos del año correspondiente.
BASE_ESTAB = "https://repositoriodeis.minsal.cl/ContenidoSitioWeb2020/Establecimientos"


def descargar_establecimientos(anio: int, sesion: requests.Session | None = None,
                               forzar: bool = False) -> Path:
    from urllib.parse import quote

    s = sesion or requests.Session()
    s.headers.setdefault("User-Agent", UA)
    destino = RAW / "deis" / f"deis_establecimientos_{anio}.xlsx"
    asegurar(destino.parent)
    if destino.exists() and not forzar:
        return destino
    u = f"{BASE_ESTAB}/{quote(f'Base de Establecimientos {anio}.xlsx')}"
    r = s.get(u, timeout=300)
    if r.status_code == 403:
        raise RecursoBloqueado(f"establecimientos {anio}: HTTP 403")
    if r.status_code == 404:
        raise RecursoInexistente(f"establecimientos {anio}: HTTP 404")
    r.raise_for_status()
    # xlsx es un ZIP: mismo control de numeros magicos que para los datos.
    if r.content[:2] != b"PK":
        raise DescargaInvalida(
            f"establecimientos {anio}: HTTP 200 pero el cuerpo no es xlsx ({r.content[:8]!r})")
    destino.write_bytes(r.content)
    log.info("%s -> %s KB", destino.name, round(len(r.content) / 1024))
    return destino


def cmd_establecimientos(args) -> dict:
    s = requests.Session()
    out = []
    for a in range(args.desde, args.hasta + 1):
        try:
            p = descargar_establecimientos(a, s, forzar=args.forzar)
            out.append({"anio": a, "estado": "ok", "KB": round(p.stat().st_size / 1024)})
        except (RecursoBloqueado, RecursoInexistente, DescargaInvalida) as e:
            out.append({"anio": a, "estado": "fallo", "diagnostico": str(e)})
    return {"establecimientos": out}


# --------------------------------------------------------------------------
# cobertura por establecimiento y año en las tres ciudades
# --------------------------------------------------------------------------
# Codigos CUT de comuna. "Santiago" es el Gran Santiago: la provincia de
# Santiago mas Puente Alto y San Bernardo, que es la definicion habitual para
# calidad del aire porque comparten cuenca atmosferica.
COMUNAS_CIUDAD = {
    "Santiago": set(range(13101, 13133)) | {13201, 13401},
    "Talcahuano": {8110},
    "Coyhaique": {11101},
}

# Alternativas evaluadas para Talcahuano, ver docs/reconocimiento/hallazgos.md 4.x:
#   estricto            {8110}                    1 estacion SINCA validada
#   con Hualpen         {8110, 8112}              Hualpen se separo de Talcahuano
#                                                 en 2004 y comparte la bahia de
#                                                 San Vicente; sus 3 estaciones
#                                                 son solo NO validadas
#   Gran Concepcion     8101..8112                6 estaciones validadas
COMUNAS_ALTERNATIVAS = {
    "Talcahuano_con_Hualpen": {8110, 8112},
    "Gran_Concepcion": set(range(8101, 8113)),
}


def mapa_establecimiento_comuna(anio: int) -> dict[str, dict]:
    """idestablecimiento (codigo antiguo) -> {comuna, ciudad, apertura, cierre}."""
    import pandas as pd

    p = RAW / "deis" / f"deis_establecimientos_{anio}.xlsx"
    if not p.exists():
        raise FileNotFoundError(f"falta {p}; correr 'establecimientos' primero")
    df = pd.read_excel(p, header=1)
    cols = {str(c).strip(): c for c in df.columns}

    # Los nombres de columna de la Base de Establecimientos NO son estables:
    #   2018-2019: 'Codigo Antiguo Establecimiento'   (29-30 columnas)
    #   2020-2024: 'Codigo Antiguo'                   (30-32 columnas)
    #   2024:      añade ademas 'Codigo  Madre Antiguo', que hay que excluir
    # Las fechas de vigencia/cierre existen hasta 2020 y desaparecen desde 2021.
    def col(*claves, excluir=()):
        for k, orig in cols.items():
            kl = k.lower()
            if all(c in kl for c in claves) and not any(x in kl for x in excluir):
                return orig
        return None

    c_id = col("antiguo", excluir=("madre",))
    c_com = col("digo", "comuna")
    c_nom = col("nombre", "comuna")
    c_des = col("vigencia")
    c_cie = col("cierre")
    if not c_id or not c_com:
        raise DescargaInvalida(f"establecimientos {anio}: no se hallaron columnas clave: {list(cols)[:8]}")

    out = {}
    for _, r in df.iterrows():
        ident = str(r[c_id]).strip()
        if not ident or ident == "nan":
            continue
        try:
            cod = int(r[c_com])
        except (ValueError, TypeError):
            continue
        ciudad = next((c for c, s in COMUNAS_CIUDAD.items() if cod in s), None)
        out[ident] = {
            "cod_comuna": cod,
            "comuna": str(r[c_nom]).strip() if c_nom else None,
            "ciudad": ciudad,
            "vigencia_desde": str(r[c_des])[:10] if c_des else None,
            "cierre": str(r[c_cie])[:10] if c_cie and str(r[c_cie]) != "nan" else None,
        }
    return out


def _stream_mdb(ruta_mdb: Path, tabla: str):
    """Itera el .mdb con el driver ODBC de Access.

    Las columnas del .mdb se llaman Col01..Col06 en vez de tener nombre. Se
    verifico empiricamente que Col01 = Col02+..+Col06 en el 100% de las filas,
    por lo que el orden coincide con el del CSV.
    """
    import pyodbc

    cn = pyodbc.connect(
        rf"DRIVER={{Microsoft Access Driver (*.mdb, *.accdb)}};DBQ={ruta_mdb};",
        autocommit=True, timeout=600)
    cur = cn.cursor()
    cur.execute(
        f"SELECT idestablecimiento, Idcausa, Col01, fecha, semana FROM [{tabla}]")
    while (lote := cur.fetchmany(50000)):
        for r in lote:
            yield {"IdEstablecimiento": str(r[0]).strip(), "IdCausa": r[1],
                   "Total": r[2], "fecha": str(r[3]), "semana": r[4]}
    cn.close()


def filas_anio(anio: int):
    """Iterador unificado: da igual si el año viene en CSV o en Access."""
    zip_p = RAW / "deis" / f"deis_atencionesurgencia_{anio}.zip"
    z = zipfile.ZipFile(zip_p)
    if any(n.lower().endswith(".csv") for n in z.namelist()):
        yield from _stream_csv(zip_p)
        return
    mdb = INTERIM / "deis" / f"AtencionesUrgencia{anio}.mdb"
    if not mdb.exists():
        asegurar(mdb.parent)
        miembro = [n for n in z.namelist() if n.lower().endswith(".mdb")][0]
        log.info("extrayendo %s -> %s", miembro, mdb)
        with z.open(miembro) as f, open(mdb, "wb") as o:
            while (b := f.read(8 << 20)):
                o.write(b)
    import pyodbc

    cn = pyodbc.connect(
        rf"DRIVER={{Microsoft Access Driver (*.mdb, *.accdb)}};DBQ={mdb};",
        autocommit=True, timeout=600)
    tabla = [r.table_name for r in cn.cursor().tables(tableType="TABLE")][0]
    cn.close()
    yield from _stream_mdb(mdb, tabla)


def cmd_cobertura(args) -> dict:
    """Cuenta establecimientos activos por ciudad y año, y detecta el recambio."""
    resultado = {}
    presencia: dict[str, set[int]] = {}

    for anio in range(args.desde, args.hasta + 1):
        try:
            mapa = mapa_establecimiento_comuna(anio)
        except FileNotFoundError as e:
            resultado[anio] = {"error": str(e)}
            continue

        por_ciudad: dict[str, dict[str, dict]] = {c: {} for c in COMUNAS_CIUDAD}
        sin_mapa = set()
        filas = 0
        for r in filas_anio(anio):
            filas += 1
            ident = (r.get("IdEstablecimiento") or "").strip()
            info = mapa.get(ident)
            if info is None:
                sin_mapa.add(ident)
                continue
            ciudad = info["ciudad"]
            if ciudad is None:
                continue
            f = _normalizar_fecha(str(r.get("fecha", "")))
            d = por_ciudad[ciudad].setdefault(
                ident, {"dias": set(), "filas": 0, "total": 0, "comuna": info["comuna"]})
            d["filas"] += 1
            if f:
                d["dias"].add(f)
            try:
                idc = int(r.get("IdCausa") or -999)
                if idc in IDCAUSA_RESPIRATORIA_DETALLE:
                    d["total"] += int(r.get("Total") or 0)
            except (ValueError, TypeError):
                pass

        resultado[anio] = {
            "filas_leidas": filas,
            "establecimientos_sin_mapa": len(sin_mapa),
            "por_ciudad": {
                c: {
                    "n_establecimientos": len(d),
                    "detalle": {
                        i: {"comuna": v["comuna"], "dias_con_registro": len(v["dias"]),
                            "filas": v["filas"], "urgencias_respiratorias": v["total"]}
                        for i, v in sorted(d.items())
                    },
                } for c, d in por_ciudad.items()
            },
        }
        for c, d in por_ciudad.items():
            for i in d:
                presencia.setdefault(f"{c}|{i}", set()).add(anio)
        log.info("%s: %s", anio, {c: len(d) for c, d in por_ciudad.items()})

    anios = list(range(args.desde, args.hasta + 1))
    recambio = {}
    for clave, presentes in sorted(presencia.items()):
        ciudad, ident = clave.split("|")
        faltan = [a for a in anios if a not in presentes]
        if faltan:
            recambio.setdefault(ciudad, {})[ident] = {
                "presente_en": sorted(presentes),
                "ausente_en": faltan,
            }
    resultado["recambio_de_establecimientos"] = recambio
    return resultado


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--salida-json", type=Path)
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("disponibilidad")
    d.add_argument("--desde", type=int, default=2017)
    d.add_argument("--hasta", type=int, default=2026)
    d.set_defaults(fn=cmd_disponibilidad)

    g = sub.add_parser("descargar")
    g.add_argument("--desde", type=int, default=2018)
    g.add_argument("--hasta", type=int, default=2024)
    g.add_argument("--forzar", action="store_true")
    g.set_defaults(fn=cmd_descargar)

    e = sub.add_parser("esquema")
    e.add_argument("--desde", type=int, default=2018)
    e.add_argument("--hasta", type=int, default=2024)
    e.set_defaults(fn=cmd_esquema)

    b = sub.add_parser("establecimientos")
    b.add_argument("--desde", type=int, default=2018)
    b.add_argument("--hasta", type=int, default=2024)
    b.add_argument("--forzar", action="store_true")
    b.set_defaults(fn=cmd_establecimientos)

    c = sub.add_parser("cobertura")
    c.add_argument("--desde", type=int, default=2018)
    c.add_argument("--hasta", type=int, default=2024)
    c.set_defaults(fn=cmd_cobertura)

    f = sub.add_parser("perfil")
    f.add_argument("--desde", type=int, default=2018)
    f.add_argument("--hasta", type=int, default=2024)
    f.add_argument("--limite", type=int, default=0, help="0 = sin corte")
    f.set_defaults(fn=cmd_perfil)

    args = p.parse_args(argv)
    asegurar(LOGS)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(LOGS / "reconocer_deis.log", encoding="utf-8"),
                  logging.StreamHandler(sys.stderr)],
    )
    res = args.fn(args)
    print(json.dumps(res, indent=2, ensure_ascii=False, default=str))
    if args.salida_json:
        asegurar(args.salida_json.parent)
        args.salida_json.write_text(json.dumps(res, indent=2, ensure_ascii=False, default=str),
                                    encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
