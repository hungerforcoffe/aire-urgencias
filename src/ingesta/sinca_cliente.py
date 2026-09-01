"""Cliente de descarga de SINCA (MMA), sistema Airviro APUB.

SINCA es la unica fuente de aire para Chile en este proyecto. Este modulo aisla
el patron de peticion, que no esta documentado publicamente y se dedujo leyendo
el JavaScript de la pagina de consulta.

Patron descubierto
------------------
La pagina de consulta arma la descarga en la funcion Open(outtype):

    /cgi-bin/APUB-MMA/apub.tsindico2.cgi
        ?outtype=<tipo>
        &macro=./<REGION>/<ESTACION>/Cal/<PARAM>//<PARAM>.<res>.<agg>.ic
        &from=<AAMMDD>&to=<AAMMDD>
        &path=/usr/airviro/data/CONAMA/
        &lang=esp&rsrc=&macropath=

Detalles que rompen la descarga si se ignoran:

* `outtype=xcl` devuelve **CSV** (`application/csv`), pese al nombre. El valor
  `outtype=csv` devuelve un GIF vacio de 0 bytes con HTTP 200: un exito
  aparente que en realidad no trae datos. Nunca asumir que HTTP 200 = hay dato.
* Las barras del parametro `macro` deben ir **sin codificar**. Si se pasa por
  el argumento `params=` de requests, se convierten en %2F y el servidor
  responde el mismo GIF vacio. Por eso la URL se arma como texto.
* Las fechas van en formato AAMMDD (dos digitos de año), no AAAAMMDD.
* La respuesta viene en latin-1, con `;` como separador.

Columnas de la respuesta horaria
--------------------------------
    FECHA (YYMMDD);HORA (HHMM);Registros validados;Registros preliminares;Registros no validados;

Las tres columnas de registro son excluyentes: un dato aparece en una sola. Esa
separacion es la marca de validacion de SINCA y es informacion que no existe en
otras fuentes.
"""

from __future__ import annotations

import csv
import io
import logging
import time
from dataclasses import dataclass

import requests

# El modulo es una biblioteca, no un ejecutable: se limita a emitir por su
# logger y deja la configuracion de handlers a quien lo importe.
log = logging.getLogger("sinca")

BASE = "https://sinca.mma.gob.cl/cgi-bin/APUB-MMA/apub.tsindico2.cgi"
PATH_AIRVIRO = "/usr/airviro/data/CONAMA/"

# outtype=xcl devuelve CSV. No es una errata: ver docstring.
OUTTYPE_CSV = "xcl"

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"


class SincaVacio(Exception):
    """El servidor respondio 200 pero sin datos (GIF vacio o cuerpo sin filas)."""


class SincaBloqueado(Exception):
    """Respuesta compatible con bloqueo por IP/CGNAT, no con ausencia de dato."""


@dataclass(frozen=True)
class Serie:
    """Una serie horaria de una estacion-parametro, con marcas de validacion."""

    macro: str
    filas: list[dict]

    @property
    def validados(self) -> int:
        return sum(1 for f in self.filas if f["validado"] is not None)

    @property
    def preliminares(self) -> int:
        return sum(1 for f in self.filas if f["preliminar"] is not None)

    @property
    def no_validados(self) -> int:
        return sum(1 for f in self.filas if f["no_validado"] is not None)


def construir_macro(region: str, estacion: str, parametro: str,
                    resolucion: str = "horario", agregacion: str = "horario") -> str:
    """Arma el identificador de serie de Airviro.

    Ej.: ('RM', 'D14', 'PM25') -> './RM/D14/Cal/PM25//PM25.horario.horario.ic'
    El doble slash es parte del formato, no una errata.
    """
    return f"./{region}/{estacion}/Cal/{parametro}//{parametro}.{resolucion}.{agregacion}.ic"


def construir_url(macro: str, desde: str, hasta: str, outtype: str = OUTTYPE_CSV) -> str:
    """URL como texto: las barras de `macro` NO deben codificarse."""
    return (
        f"{BASE}?outtype={outtype}&macro={macro}"
        f"&from={desde}&to={hasta}&path={PATH_AIRVIRO}&lang=esp&rsrc=&macropath="
    )


REGION_LISTADO = "https://sinca.mma.gob.cl/index.php/region/index/id/{}"

# Codigos romanos de region tal como los usa la web de SINCA.
REGIONES = ["XV", "I", "II", "III", "IV", "V", "M", "VI", "VII", "XVI",
            "VIII", "IX", "XIV", "X", "XI", "XII"]


@dataclass(frozen=True)
class EstacionSinca:
    """Una estacion del catalogo, con la comuna que declara la propia web."""

    region: str          # codigo de macropath, ej. 'RVIII'
    codigo: str          # ej. '802'
    nombre: str
    comuna: str | None
    ficha_id: str | None
    parametros: tuple[str, ...]

    def macro(self, parametro: str = "PM25", resolucion: str = "horario",
              agregacion: str = "horario") -> str:
        return construir_macro(self.region, self.codigo, parametro, resolucion, agregacion)


def catalogo_region(region_romana: str, sesion: requests.Session | None = None
                    ) -> list[EstacionSinca]:
    """Lista las estaciones de una region con su comuna y parametros medidos.

    La comuna no hay que inferirla de coordenadas: la web de SINCA la declara en
    un `<div class="comuna">` junto al nombre de la estacion. Esa es la
    asignacion oficial y es la que se usa para agrupar por ciudad.
    """
    import html as _html
    import re

    s = sesion or requests.Session()
    s.headers.setdefault("User-Agent", UA)
    r = s.get(REGION_LISTADO.format(region_romana), timeout=60)
    r.raise_for_status()
    crudo = _html.unescape(r.text)

    # Se parsea FILA a FILA. Emparejar por nombre de estacion no sirve: hay
    # nombres que se repiten o difieren entre el <th> y el parametro `header`
    # del enlace, y eso asignaria estaciones a la comuna equivocada.
    filas = re.split(r"<tr[^>]*>", crudo)
    out = []
    for fila in filas:
        m_est = re.search(
            r'<a href="/index\.php/estacion/index/id/(\d+)">([^<]+)</a>'
            r'\s*<div class="comuna">([^<]*)</div>',
            fila,
        )
        if not m_est:
            continue
        ficha, nombre, comuna = m_est.group(1), m_est.group(2).strip(), m_est.group(3).strip()

        macros = re.findall(
            r"macropath=\./([A-Z0-9]+)/([A-Z0-9]+)/Cal/([A-Z0-9]+)", fila)
        if not macros:
            continue
        reg = macros[0][0]
        cod = macros[0][1]
        # Dentro de una fila todos los enlaces apuntan a la misma estacion.
        distintos = {(a, b) for a, b, _ in macros}
        if len(distintos) > 1:
            log.warning("fila con codigos mezclados en %s: %s", region_romana, distintos)
        out.append(EstacionSinca(
            region=reg, codigo=cod, nombre=nombre, comuna=comuna or None,
            ficha_id=ficha, parametros=tuple(sorted({p for _, _, p in macros})),
        ))
    return sorted(out, key=lambda e: (e.region, e.codigo))


def _num(s: str) -> float | None:
    s = (s or "").strip()
    if not s:
        return None
    try:
        return float(s.replace(",", "."))
    except ValueError:
        return None


def descargar(macro: str, desde: str, hasta: str, sesion: requests.Session | None = None,
              reintentos: int = 3, espera: float = 2.0) -> bytes:
    """Descarga crudo. Devuelve los bytes tal cual llegan, sin decodificar.

    Distingue vacio de bloqueado: un GIF de 0 bytes es "no hay dato publicado
    para esa combinacion", mientras que 403/timeout apunta a la IP.
    """
    s = sesion or requests.Session()
    s.headers.setdefault("User-Agent", UA)
    url = construir_url(macro, desde, hasta)

    ultimo = None
    for intento in range(1, reintentos + 1):
        try:
            r = s.get(url, timeout=60)
        except requests.exceptions.Timeout as e:
            ultimo = e
            time.sleep(espera * intento)
            continue
        if r.status_code == 403:
            raise SincaBloqueado(
                f"HTTP 403 en {macro} {desde}-{hasta}. Probable bloqueo por IP "
                f"(el proyecto corre tras CGNAT), no ausencia de dato."
            )
        if r.status_code != 200:
            ultimo = RuntimeError(f"HTTP {r.status_code}")
            time.sleep(espera * intento)
            continue
        ct = r.headers.get("content-type", "")
        if not r.content or ct.startswith("image/"):
            raise SincaVacio(
                f"Respuesta sin datos para {macro} {desde}-{hasta} "
                f"(HTTP 200, content-type={ct!r}, {len(r.content)} bytes). "
                f"El recurso existe pero no hay serie publicada."
            )
        return r.content
    raise SincaBloqueado(f"Sin respuesta util tras {reintentos} intentos: {ultimo}")


def parsear(crudo: bytes, macro: str = "") -> Serie:
    """Parsea la respuesta horaria conservando las tres marcas de validacion."""
    texto = crudo.decode("latin-1")
    lector = csv.reader(io.StringIO(texto), delimiter=";")
    encabezado = next(lector, None)
    if not encabezado:
        raise SincaVacio("respuesta sin encabezado")

    filas = []
    for fila in lector:
        if len(fila) < 3 or not fila[0].strip():
            continue
        aa, mm, dd = fila[0][:2], fila[0][2:4], fila[0][4:6]
        hora = fila[1].strip().zfill(4) if len(fila) > 1 else ""
        filas.append({
            "fecha": f"20{aa}-{mm}-{dd}",
            "hora": f"{hora[:2]}:{hora[2:]}" if len(hora) == 4 else None,
            "validado": _num(fila[2]) if len(fila) > 2 else None,
            "preliminar": _num(fila[3]) if len(fila) > 3 else None,
            "no_validado": _num(fila[4]) if len(fila) > 4 else None,
        })
    return Serie(macro=macro, filas=filas)


# ---------------------------------------------------------------------------
# Coordenadas de la ficha de estacion
# ---------------------------------------------------------------------------

FICHA = "https://sinca.mma.gob.cl/index.php/estacion/index/id/{}"

# Chile continental mas islas oceanicas. No es un adorno: sirve para rechazar
# una coordenada que se leyo mal antes de que llegue al mapa. Nueva Libertad ya
# aparecio una vez en Argentina por un huso UTM equivocado
# (docs/calidad/correccion_coordenadas.md); la reja existe por eso.
CAJA_CHILE = {"lat_min": -56.0, "lat_max": -17.3, "lon_min": -110.0, "lon_max": -66.0}


def coordenadas_estacion(ficha_id: str, sesion: requests.Session | None = None
                         ) -> tuple[float, float] | None:
    """Latitud y longitud declaradas en la ficha de la estacion.

    La ficha no publica las coordenadas como texto ni en una tabla: las pasa al
    mapa incrustado en la propia pagina, en una llamada
    `new google.maps.LatLng(lat, lon)`. Se leen de ahi porque es el unico sitio
    donde SINCA las expone; el resto de la ficha habla de la estacion en prosa.

    Devuelve None si la ficha no trae mapa o si el par cae fuera de Chile. Un
    None es un dato ausente y se registra como tal: no se inventa una posicion
    ni se reutiliza la de la comuna.
    """
    import re

    s = sesion or requests.Session()
    s.headers.setdefault("User-Agent", UA)
    r = s.get(FICHA.format(ficha_id), timeout=60)
    r.raise_for_status()

    m = re.search(r"google\.maps\.LatLng\(\s*(-?\d+\.\d+)\s*,\s*(-?\d+\.\d+)\s*\)", r.text)
    if not m:
        log.warning("ficha %s sin coordenadas en el mapa incrustado", ficha_id)
        return None

    lat, lon = float(m.group(1)), float(m.group(2))
    c = CAJA_CHILE
    if not (c["lat_min"] <= lat <= c["lat_max"] and c["lon_min"] <= lon <= c["lon_max"]):
        log.warning("ficha %s: coordenada fuera de Chile (%.5f, %.5f); se descarta",
                    ficha_id, lat, lon)
        return None
    return lat, lon


def catalogo_nacional(sesion: requests.Session | None = None, pausa: float = 0.4,
                      solo_parametro: str | None = None) -> list[dict]:
    """Las estaciones de las 16 regiones, con comuna, parametros y coordenadas.

    Es el catalogo completo de la red, no el de las tres ciudades del estudio.
    Con `solo_parametro="PM25"` se queda con las que miden ese contaminante.

    Una region que falle no aborta el recorrido: se registra y se sigue, porque
    perder las 15 restantes por una caida puntual seria peor que quedarse con un
    catalogo incompleto y declarado como tal.
    """
    s = sesion or requests.Session()
    s.headers.setdefault("User-Agent", UA)

    out: list[dict] = []
    for romana in REGIONES:
        try:
            estaciones = catalogo_region(romana, s)
        except Exception as e:  # noqa: BLE001 — se registra y se continua
            log.error("region %s: no se pudo listar (%s: %s)", romana, type(e).__name__, e)
            continue
        for e in estaciones:
            if solo_parametro and solo_parametro not in e.parametros:
                continue
            coord = coordenadas_estacion(e.ficha_id, s) if e.ficha_id else None
            out.append({
                "region_romana": romana,
                "region_macro": e.region,
                "codigo": e.codigo,
                "ficha_id": e.ficha_id,
                "nombre": e.nombre,
                "comuna": e.comuna,
                "parametros": list(e.parametros),
                "lat": coord[0] if coord else None,
                "lon": coord[1] if coord else None,
            })
            if pausa:
                time.sleep(pausa)
        log.info("region %s: %d estaciones", romana, len(estaciones))
    return out
