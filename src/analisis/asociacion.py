"""Maquinaria del análisis de asociación MP2.5 ↔ urgencias respiratorias.

Vive aparte del notebook para que el notebook sea narrativa y no andamiaje, y
para que estas funciones se puedan probar sin ejecutar cuarenta celdas.

Asociación, nunca causalidad. Es un diseño ecológico observacional: la unidad es
ciudad-día y ninguna fila describe a una persona.

Decisiones que están fijadas aquí y no se eligen al vuelo
---------------------------------------------------------
* **Unidad ciudad-día.** El case-crossover es un diseño *temporal*: compara días
  dentro del mismo estrato. La mala clasificación espacial del promedio de
  ciudad penaliza un diseño espacial, no éste.
* **MP2.5 = media de las medias diarias por estación**, no media agrupada de
  horas: la agrupada pondera por cuántas horas reportó cada estación, que es un
  accidente de mantenimiento.
* **Poisson con efectos fijos de estrato ≡ Poisson condicional.** La Poisson es
  el caso donde el estimador de efectos fijos es consistente sin importar el
  tamaño del estrato, a diferencia del logit. Por eso no hace falta R.
* **Quasi-Poisson**, no errores de conglomerado: con tres ciudades no hay grupos
  suficientes para que el sándwich sea fiable.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.compute as pc
import pyarrow.dataset as ds
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.procesamiento.geografia import ciudad_de_codigo  # noqa: E402
from src.rutas import PROCESSED  # noqa: E402

SEMILLA = 20260829

# --- Causas (dim_causa) ---------------------------------------------------
CAUSAS_RESP = {10: "ira_alta", 3: "bronquitis", 4: "influenza",
               5: "neumonia", 11: "obstructiva", 6: "resp_otras"}
CAUSA_RESP_TOTAL = 2      # TOTAL CAUSA SISTEMA RESPIRATORIO (J00-J98)
CAUSA_TOTAL = 1           # TOTAL ATENCIONES DE URGENCIA
CAUSA_TRAUMA = 18         # control negativo 1: incluye caídas
CAUSA_TRANSITO = 19       # control negativo 2: mecanismo distinto al de caídas
# La 43 (quemaduras y exposición al humo) NO se usa como control negativo:
# en una ciudad con calefacción a leña responde de verdad al humo.

# --- Limpieza de temperatura (umbrales fijados por el equipo) --------------
TEMP_RANGO = (-25.0, 40.0)
TEMP_DESV_MAX = 10.0      # °C contra la mediana móvil
TEMP_VENTANA = 11         # horas, centrada

HORAS_MINIMAS_DIA = 18    # de 24; docs/calidad/cobertura_horaria_semanal.md
COBERTURA_PANEL = 95.0    # % de días que un establecimiento debe reportar

# Mismo recinto, renumerado el 2024-01-01. Verificado: cero días de solape entre
# ambos identificadores. Sin fusionarlos, el panel equilibrado descarta el
# establecimiento dos veces y Talcahuano pierde el 27 % de sus urgencias.
RENUMERADOS = {"201018": "19-912"}


# ==========================================================================
# Fase 0 — construcción del panel
# ==========================================================================
def establecimientos_del_estudio() -> pd.DataFrame:
    """Establecimientos de las tres ciudades, cruzando por CÓDIGO de comuna.

    Por nombre se perdería Coyhaique entera y sin error: el DEIS escribe
    «Coihaique» y el catálogo de aire «Coyhaique».
    """
    est = pq.read_table(PROCESSED / "dim_establecimiento").to_pandas()
    est["ciudad_id"] = est.comuna_codigo.map(ciudad_de_codigo)
    est = est[est.ciudad_id.notna()].copy()
    est["id_fusionado"] = est.establecimiento_id.replace(RENUMERADOS)
    return est


def leer_urgencias(causas: list[int]) -> pd.DataFrame:
    """Urgencias por establecimiento y día para las causas pedidas.

    Filtra en el lector (predicate pushdown), no después: de 66,3 millones de
    filas bajan a unos pocos millones sin pasar por memoria.
    """
    est = establecimientos_del_estudio()
    mapa_ciudad = dict(zip(est.establecimiento_id, est.ciudad_id, strict=True))
    mapa_fusion = dict(zip(est.establecimiento_id, est.id_fusionado, strict=True))

    d = ds.dataset(PROCESSED / "hecho_urgencia", format="parquet", partitioning="hive")
    t = d.to_table(
        columns=["establecimiento_id", "fecha", "causa_id", "total",
                 "menores_1", "de_1_a_4", "de_5_a_14", "de_15_a_64", "de_65_y_mas"],
        filter=(pc.field("establecimiento_id").isin(list(mapa_ciudad))
                & pc.field("causa_id").isin(causas)),
    ).to_pandas()
    t["ciudad_id"] = t.establecimiento_id.map(mapa_ciudad)
    t["id_fusionado"] = t.establecimiento_id.map(mapa_fusion)
    t["fecha"] = pd.to_datetime(t.fecha)
    return t


def panel_equilibrado(urg: pd.DataFrame, desde: str, hasta: str,
                      umbral: float = COBERTURA_PANEL) -> tuple[set, pd.DataFrame]:
    """Establecimientos que reportan al menos `umbral` % de los días.

    Restringir es preferible a un offset por número de reportantes: el offset
    asume proporcionalidad, esto elimina el problema en el origen. La cobertura
    se calcula sobre el identificador FUSIONADO, si no un recinto renumerado
    aparece como dos que reportan la mitad del tiempo cada uno.
    """
    v = urg[(urg.fecha >= desde) & (urg.fecha <= hasta)]
    base = v[v.causa_id == CAUSA_TOTAL]
    dias = v.fecha.nunique()
    cob = (base.groupby(["ciudad_id", "id_fusionado"]).fecha.nunique() / dias * 100)
    cob = cob.rename("cobertura_pct").reset_index()
    cob["retenido"] = cob.cobertura_pct >= umbral
    return set(cob.loc[cob.retenido, "id_fusionado"]), cob


def limpiar_temperatura(med: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Rango físico y desviación contra la mediana móvil.

    Reimplementado aquí, con los mismos umbrales que se usaron a mano, para que
    el notebook corra de punta a punta sin depender de un archivo limpiado
    fuera del repositorio.
    """
    t = med[med.parametro_id == "temperatura"].sort_values(
        ["estacion_id", "fecha", "hora"]).copy()
    n0 = len(t)
    fuera = ~t.valor.between(*TEMP_RANGO)
    t = t[~fuera]
    mediana = t.groupby("estacion_id").valor.transform(
        lambda s: s.rolling(TEMP_VENTANA, center=True, min_periods=6).median())
    desviado = (t.valor - mediana).abs() > TEMP_DESV_MAX
    t = t[~desviado]
    return t, {"horas_iniciales": n0,
               "fuera_de_rango": int(fuera.sum()),
               "desviacion_excesiva": int(desviado.sum()),
               "horas_finales": len(t)}


def viento_vectorial(med: pd.DataFrame) -> pd.DataFrame:
    """Media vectorial diaria del viento a partir de velocidad y dirección.

    Promediar grados es un error: la media aritmética de 350° y 10° da 180°, el
    sur, cuando ambos son norte. Se descompone en componentes y se promedian
    esas. `u` es la componente oeste-este y `v` la sur-norte; el módulo del
    vector resultante mide además cuán persistente fue la dirección — un valor
    bajo con velocidad alta significa viento que giró, y por tanto poca
    ventilación efectiva.
    """
    vel = med[med.parametro_id == "vel_viento"][["estacion_id", "fecha", "hora", "valor"]]
    dire = med[med.parametro_id == "dir_viento"][["estacion_id", "fecha", "hora", "valor"]]
    j = vel.merge(dire, on=["estacion_id", "fecha", "hora"], suffixes=("_vel", "_dir"))
    if j.empty:
        return pd.DataFrame(columns=["estacion_id", "fecha", "viento_u", "viento_v",
                                     "viento_vel", "viento_persistencia"])
    rad = np.deg2rad(j.valor_dir)
    j = j.assign(u=-j.valor_vel * np.sin(rad), v=-j.valor_vel * np.cos(rad))
    g = j.groupby(["estacion_id", "fecha"]).agg(
        viento_u=("u", "mean"), viento_v=("v", "mean"),
        viento_vel=("valor_vel", "mean"), horas=("u", "size")).reset_index()
    g = g[g.horas >= HORAS_MINIMAS_DIA]
    modulo = np.hypot(g.viento_u, g.viento_v)
    g["viento_persistencia"] = np.where(g.viento_vel > 0, modulo / g.viento_vel, np.nan)
    return g.drop(columns="horas")


def panel_ciudad_dia(desde: str = "2018-01-01", hasta: str = "2026-08-22") -> pd.DataFrame:
    """Panel ciudad-día con exposición, meteorología y desenlaces.

    Una fila por ciudad y día del calendario, incluidas las que no tienen dato:
    si la fila desapareciera, el hueco sería invisible.
    """
    med = pq.read_table(
        PROCESSED / "hecho_medicion",
        columns=["estacion_id", "ciudad_id", "fecha", "hora", "parametro_id", "valor"],
    ).to_pandas()
    med["fecha"] = pd.to_datetime(med.fecha)
    med = med[(med.fecha >= desde) & (med.fecha <= hasta)]

    limpia, informe_temp = limpiar_temperatura(med)
    otros = med[med.parametro_id != "temperatura"]
    med = pd.concat([otros, limpia], ignore_index=True)

    # --- exposicion y meteorologia escalares: estacion-dia -> ciudad-dia ---
    partes = {}
    for par, nombre in [("mp25", "mp25"), ("temperatura", "temp"), ("humedad", "humedad")]:
        d = med[med.parametro_id == par]
        ed = d.groupby(["ciudad_id", "estacion_id", "fecha"]).valor.agg(
            media="mean", minimo="min", maximo="max", horas="count")
        ed = ed[ed.horas >= HORAS_MINIMAS_DIA]
        cd = ed.groupby(level=["ciudad_id", "fecha"]).agg(
            **{nombre: ("media", "mean"),
               f"{nombre}_min": ("minimo", "min"),
               f"{nombre}_max": ("maximo", "max"),
               f"{nombre}_estaciones": ("media", "size")})
        partes[par] = cd

    aire = partes["mp25"].join(partes["temperatura"], how="outer").join(
        partes["humedad"], how="outer").reset_index()

    vien = viento_vectorial(med)
    if not vien.empty:
        est_ciudad = pq.read_table(PROCESSED / "dim_estacion").to_pandas()
        vien = vien.merge(est_ciudad[["estacion_id", "ciudad_id"]], on="estacion_id")
        vien = vien[vien.ciudad_id.notna()].groupby(["ciudad_id", "fecha"])[
            ["viento_u", "viento_v", "viento_vel", "viento_persistencia"]].mean().reset_index()
        aire = aire.merge(vien, on=["ciudad_id", "fecha"], how="left")

    # --- desenlaces ---
    causas = [CAUSA_TOTAL, CAUSA_RESP_TOTAL, CAUSA_TRAUMA, CAUSA_TRANSITO, *CAUSAS_RESP]
    urg = leer_urgencias(causas)
    urg = urg[(urg.fecha >= desde) & (urg.fecha <= hasta)]

    tie = pq.read_table(PROCESSED / "dim_tiempo").to_pandas()
    tie["fecha"] = pd.to_datetime(tie.fecha)
    tie = tie[(tie.fecha >= desde) & (tie.fecha <= hasta)]

    idx = pd.MultiIndex.from_product(
        [sorted(urg.ciudad_id.unique()), sorted(tie.fecha)], names=["ciudad_id", "fecha"])
    panel = pd.DataFrame(index=idx).reset_index()
    panel = panel.merge(aire, on=["ciudad_id", "fecha"], how="left")
    panel = panel.merge(
        tie[["fecha", "anio", "mes", "dia_semana", "nombre_dia", "anio_epi", "semana_epi",
             "semana_id", "estacion_anio", "es_invierno", "periodo_pandemia"]],
        on="fecha", how="left")
    panel.attrs["informe_temperatura"] = informe_temp
    panel.attrs["urgencias_crudas"] = urg
    return panel


def agregar_desenlaces(panel: pd.DataFrame, urg: pd.DataFrame,
                       retenidos: set | None = None) -> pd.DataFrame:
    """Suma las urgencias al panel. Si se pasa `retenidos`, usa el panel equilibrado."""
    u = urg if retenidos is None else urg[urg.id_fusionado.isin(retenidos)]
    salida = panel.copy()
    columnas = {CAUSA_TOTAL: "urg_totales", CAUSA_RESP_TOTAL: "resp",
                CAUSA_TRAUMA: "trauma", CAUSA_TRANSITO: "transito", **CAUSAS_RESP}
    for cid, nombre in columnas.items():
        g = (u[u.causa_id == cid].groupby(["ciudad_id", "fecha"]).total.sum()
             .rename(nombre).reset_index())
        salida = salida.merge(g, on=["ciudad_id", "fecha"], how="left")
        salida[nombre] = salida[nombre].fillna(0).astype("int64")
    n_est = (u[u.causa_id == CAUSA_TOTAL].groupby(["ciudad_id", "fecha"])
             .id_fusionado.nunique().rename("n_establecimientos").reset_index())
    return salida.merge(n_est, on=["ciudad_id", "fecha"], how="left")


def proxy_viral(panel: pd.DataFrame, columna: str = "resp",
                suavizado: int = 7) -> pd.Series:
    """Proxy de temporada viral: la serie de las OTRAS ciudades, suavizada.

    La epidemia de VRS es nacional y sincrónica; el MP2.5 es local y con
    calendarios distintos (Coyhaique tiene su peak respiratorio en octubre y
    Santiago en invierno). Eso permite usar una ciudad para informar a otra.

    **No es limpio y hay que decirlo:** el MP2.5 correlaciona r≈0,5 entre
    ciudades, así que el proxy arrastra algo de exposición y sesga hacia el
    nulo. El suavizado de 7 días lo mitiga —la epidemia es lenta y los picos de
    contaminación son rápidos— pero no lo elimina. Es un ajuste **conservador**:
    si el coeficiente sobrevive es evidencia fuerte; si no sobrevive, el
    resultado es ambiguo entre confusión viral y sobreajuste.
    """
    tasa = panel.pivot_table(index="fecha", columns="ciudad_id", values=columna)
    z = (tasa - tasa.mean()) / tasa.std()
    z = z.rolling(suavizado, center=True, min_periods=suavizado // 2).mean()
    salida = pd.Series(index=panel.index, dtype=float)
    for ciudad in z.columns:
        otras = z.drop(columns=ciudad).mean(axis=1)
        sel = panel.ciudad_id == ciudad
        salida.loc[sel] = panel.loc[sel, "fecha"].map(otras).to_numpy()
    return salida


# ==========================================================================
# Fase 3 — lag distribuido con restricción polinómica
# ==========================================================================
def matriz_lags(x: pd.Series, L: int) -> np.ndarray:
    """Matriz n×(L+1) con la exposición rezagada 0..L días."""
    return np.column_stack([x.shift(k).to_numpy() for k in range(L + 1)])


def almon(datos, desenlace: str, exposicion: str = "mp25", L: int = 7,
          grado: int = 3, ajustes: tuple[str, ...] = ("temp",), gl_temp: int = 4):
    """Lag distribuido de Almon dentro del case-crossover.

    Por qué no lags sueltos ni medias móviles sueltas: la exposición está
    autocorrelada (el MP2.5 de hoy se parece al de ayer), así que ocho términos
    separados se reparten el mismo efecto y **ninguno queda ajustado por los
    demás**. Con la restricción polinómica β_l = Σ_j α_j·l^j se estiman
    mutuamente ajustados y con cuatro parámetros en vez de ocho.

    Probado contra una estructura conocida con exposición autocorrelada:
    recupera 7 de 8 coeficientes dentro del IC95.

    Devuelve beta por rezago y su error estándar por método delta.
    """
    from patsy import dmatrix

    d = datos.sort_values(["ciudad_id", "fecha"]).copy()
    for k in range(L + 1):
        d[f"_lag{k}"] = d.groupby("ciudad_id", observed=True)[exposicion].shift(k)
    d["estrato"] = _clave_estrato(d)

    cols = [f"_lag{k}" for k in range(L + 1)]
    extras = _extras(d, ajustes)
    d = d.dropna(subset=[desenlace, *cols, *extras] + (["temp"] if "temp" in ajustes else []))
    if d.empty:
        return None

    X_lags = d[cols].to_numpy()
    P = np.column_stack([np.arange(L + 1) ** j for j in range(grado + 1)])
    bloques = [X_lags @ P]
    if "temp" in ajustes:
        bloques.append(np.asarray(dmatrix(f"cr(temp, df={gl_temp})-1", d,
                                          return_type="dataframe")))
    if extras:
        bloques.append(d[extras].to_numpy())
    X = np.column_stack(bloques)

    r = poisson_condicional(d[desenlace], X, d.estrato)
    if r is None:
        return None
    alpha = r["beta"][:grado + 1]
    # Covarianza de alpha reescalada por la sobredispersion, igual que los EE.
    cov = np.diag(r["se"][:grado + 1] ** 2)
    beta = P @ alpha
    se = np.sqrt(np.einsum("ij,jk,ik->i", P, cov, P))
    return {"lag": np.arange(L + 1), "beta": beta, "se": se,
            "rr10": np.exp(10 * beta),
            "ic_inf": np.exp(10 * (beta - 1.96 * se)),
            "ic_sup": np.exp(10 * (beta + 1.96 * se)),
            "n": r["n"], "escala": r["escala"], "convergio": r["convergio"]}


# ==========================================================================
# Poisson condicional
# ==========================================================================
def poisson_condicional(y, X, estrato, max_iter: int = 200):
    """Poisson condicional exacto: los estratos se eliminan, no se estiman.

    Por qué hace falta y no basta con `C(estrato)`
    ----------------------------------------------
    Con desenlaces densos (respiratorias, traumatismos) los efectos fijos y el
    condicional dan el mismo coeficiente, y la versión con dummies es más cómoda.
    Con desenlaces **escasos** no: los estratos de 2 a 5 días con muchos ceros
    empujan su efecto fijo hacia −infinito, los valores ajustados caen a cero y
    la IRLS muere con «invalid value in weights». Le pasa a accidentes de
    tránsito en Coyhaique, que son 0,7 casos al día con 69 % de días en cero.

    El condicional no tiene ese problema porque los parámetros de estrato
    desaparecen del todo. Condicionando en el total de cada estrato, los conteos
    siguen una multinomial:

        p_si = exp(x_si·β) / Σ_j exp(x_sj·β)

    y la log-verosimilitud es Σ_s Σ_i y_si·(x_si·β − logΣ_j exp(x_sj·β)),
    estable con logsumexp. Es el mismo estimador que `gnm::gnm(eliminate=)` en R.

    Devuelve (beta, errores estándar, escala de sobredispersión, n usados).
    """
    from scipy.optimize import minimize

    y = np.asarray(y, dtype=float)
    X = np.asarray(X, dtype=float)
    cod, _ = pd.factorize(pd.Series(estrato))
    n_est = cod.max() + 1

    # Un estrato sin casos no aporta informacion sobre el riesgo relativo, y uno
    # con una sola observacion tampoco da contraste. El condicional los excluye
    # por construccion; aqui se hace explicito.
    totales = np.bincount(cod, weights=y, minlength=n_est)
    tamanos = np.bincount(cod, minlength=n_est)
    util = (totales[cod] > 0) & (tamanos[cod] > 1)
    y, X, cod = y[util], X[util], pd.factorize(pd.Series(cod[util]))[0]
    n_est = cod.max() + 1 if len(cod) else 0
    if len(y) == 0 or n_est == 0:
        return None
    totales = np.bincount(cod, weights=y, minlength=n_est)

    def partes(beta):
        eta = X @ beta
        # logsumexp por estrato, sin construir matrices densas de estratos
        maximos = np.full(n_est, -np.inf)
        np.maximum.at(maximos, cod, eta)
        expo = np.exp(eta - maximos[cod])
        sumas = np.bincount(cod, weights=expo, minlength=n_est)
        lse = maximos + np.log(sumas)
        p = expo / sumas[cod]
        return eta, lse, p

    def neg_ll(beta):
        eta, lse, _ = partes(beta)
        return -float(np.sum(y * (eta - lse[cod])))

    def grad(beta):
        _, _, p = partes(beta)
        mu = totales[cod] * p
        return -(X * (y - mu)[:, None]).sum(axis=0)

    # BFGS con gradiente analitico. `gtol` relajado a 1e-6 a proposito: con la
    # exposicion en escala de cientos y los splines en escala 1, un umbral de
    # 1e-8 nunca se alcanza y la bandera `success` sale False estando convergido.
    # La convergencia se juzga por la norma del gradiente, no por la bandera.
    # (L-BFGS-B se descarto: para antes de tiempo con |grad|~9 y devuelve otro
    # coeficiente. Newton-CG da lo mismo que BFGS.)
    res = minimize(neg_ll, np.zeros(X.shape[1]), jac=grad, method="BFGS",
                   options={"maxiter": max_iter, "gtol": 1e-6})
    beta = res.x
    norma_grad = float(np.linalg.norm(grad(beta)))
    _, _, p = partes(beta)
    mu = totales[cod] * p

    # Hessiana observada: Σ_s N_s (Σ_i p x x' − (Σ_i p x)(Σ_i p x)')
    k = X.shape[1]
    H = np.zeros((k, k))
    for s in range(n_est):
        m = cod == s
        Xs, ps = X[m], p[m]
        media = ps @ Xs
        H += totales[s] * ((Xs * ps[:, None]).T @ Xs - np.outer(media, media))
    cov = np.linalg.pinv(H)
    gl = max(len(y) - n_est - k, 1)
    escala = float(np.sum((y - mu) ** 2 / np.maximum(mu, 1e-9)) / gl)  # quasi-Poisson
    se = np.sqrt(np.diag(cov) * escala)

    # Convergencia en unidades adimensionales. La norma del gradiente crece con
    # el numero de casos —traumatismos tiene millones y respiratorias tambien—
    # asi que un umbral absoluto declara no convergido algo que si lo esta. El
    # criterio correcto es cuanto se movería beta con un paso de Newton mas,
    # medido en errores estandar: si es menos del 1 %, ya llego.
    paso = cov @ grad(beta)
    paso_en_se = float(np.max(np.abs(paso) / np.maximum(se, 1e-12)))
    return {"beta": beta, "se": se, "escala": escala, "n": len(y),
            "n_estratos": n_est, "norma_gradiente": norma_grad,
            "paso_restante_en_se": paso_en_se,
            "convergio": paso_en_se < 0.01,
            "casos": float(y.sum()), "residuos": y - mu, "ajustado": mu}


# ==========================================================================
# Fase 4 — case-crossover
# ==========================================================================
def _extras(d: pd.DataFrame, ajustes) -> list[str]:
    """Columnas de ajuste, validadas contra el DataFrame.

    `temp` se trata aparte porque entra como spline, no como columna cruda.
    Cualquier otro nombre se toma como columna y **tiene que existir**: si se
    ignorara en silencio, pedir un ajuste que no está daría exactamente el mismo
    resultado que no pedirlo, y el modelo sin ajustar pasaría por ajustado.
    """
    faltan = [a for a in ajustes if a != "temp" and a not in d.columns]
    if faltan:
        raise KeyError(f"ajustes que no existen en los datos: {faltan}. "
                       f"Disponibles: {sorted(d.columns)}")
    return [a for a in ajustes if a != "temp"]


def _clave_estrato(d: pd.DataFrame) -> pd.Series:
    """Estrato del case-crossover: ciudad × año × mes × día de la semana.

    Absorbe tendencia, estacionalidad y patrón semanal sin estimarlos: solo se
    comparan días del mismo mes, del mismo año, de la misma ciudad y del mismo
    día de la semana.
    """
    return (d.ciudad_id.astype(str) + "_" + d.anio.astype(str) + "_"
            + d.mes.astype(str).str.zfill(2) + "_" + d.dia_semana.astype(str))


def case_crossover(datos: pd.DataFrame, desenlace: str, exposicion: str = "mp25_ma03",
                   ajustes: tuple[str, ...] = (), gl_temp: int = 4,
                   por_ciudad: bool = False, etiqueta: str = ""):
    """Case-crossover estratificado por tiempo, vía Poisson condicional exacto.

    Se usa el condicional y no efectos fijos con dummies porque con desenlaces
    escasos —accidentes de tránsito en Coyhaique, 0,7 casos/día— los efectos
    fijos hacen que la IRLS falle. En desenlaces densos ambos coinciden a la
    quinta cifra; está comprobado en el notebook.

    Devuelve el RR por cada 10 µg/m³ con IC95 y escala de sobredispersión.
    """
    from patsy import dmatrix

    d = datos.copy()
    d["estrato"] = _clave_estrato(d)
    extras = _extras(d, ajustes)
    necesarias = [desenlace, exposicion, *extras] + (["temp"] if "temp" in ajustes else [])
    d = d.dropna(subset=[c for c in necesarias if c in d.columns])
    if d.empty or d[desenlace].sum() == 0:
        return None

    bloques = [d[[exposicion]].to_numpy()]
    if "temp" in ajustes:
        bloques.append(np.asarray(dmatrix(f"cr(temp, df={gl_temp})-1", d,
                                          return_type="dataframe")))
    if extras:
        bloques.append(d[extras].to_numpy())
    X = np.column_stack(bloques)

    r = poisson_condicional(d[desenlace], X, d.estrato)
    if r is None:
        return None
    b, se = float(r["beta"][0]), float(r["se"][0])
    salida = {"etiqueta": etiqueta, "desenlace": desenlace, "exposicion": exposicion,
              "n_dias": r["n"], "n_estratos": r["n_estratos"], "casos": int(r["casos"]),
              "rr10": float(np.exp(10 * b)),
              "ic_inf": float(np.exp(10 * (b - 1.96 * se))),
              "ic_sup": float(np.exp(10 * (b + 1.96 * se))),
              "escala": r["escala"], "convergio": r["convergio"],
              "residuos": r["residuos"], "beta": b, "se": se}
    if por_ciudad:
        salida["por_ciudad"] = {
            c: case_crossover(g, desenlace, exposicion, ajustes, gl_temp, etiqueta=c)
            for c, g in datos.groupby("ciudad_id")}
    return salida


def tabla_resultados(filas: list[dict], etiquetas: list[str] | None = None) -> pd.DataFrame:
    """Resultados en una tabla legible, sin el objeto del modelo."""
    r = pd.DataFrame([{k: v for k, v in f.items()
                       if k not in ("modelo", "por_ciudad", "residuos")}
                      for f in filas if f is not None])
    if etiquetas is not None:
        r.insert(0, "especificacion", etiquetas[:len(r)])
    r["significativo"] = (r.ic_inf > 1) | (r.ic_sup < 1)
    return r
