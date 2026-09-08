/* Análisis semanal: series de tiempo, espacial y proyección. Requiere comun.js.

   Es el segundo cuerpo de análisis del proyecto, hecho por otra persona y con
   otro diseño: la unidad es ciudad-semana. Los números salen de
   `semanal_nt.json`, que escribe `src/sitio/exportar_semanal.py` leyendo las
   salidas guardadas de los notebooks. Acá no se calcula nada.

   Sus figuras se insertan en los capítulos que ya abrió el HTML, junto a las del
   modelo diario: el lector recorre el argumento, no a los autores.

   Sobre Granger. El test se llama «de causalidad» por convención estadística y
   mide otra cosa: si el pasado de una serie mejora la predicción de otra. Eso es
   precedencia temporal predictiva, y así se nombra acá. No es una sutileza de
   redacción, es la regla 1 del proyecto. */

(async function () {
  const $ = s => document.querySelector(s);

  let d;
  try { d = await AU.cargar("semanal_nt"); }
  catch (e) { console.warn("análisis semanal no disponible:", e); return; }
  // Estas figuras van en contenedores propios dentro de los mismos capítulos.
  // No se comparte contenedor con los otros scripts a propósito: #s-trampa lo
  // repinta analisis.js cada vez que se mueve un control, y cualquier cosa
  // añadida ahí desaparecería al primer cambio de ciudad.

  // Escribir en un contenedor que no existe tumbaba el script entero y con el
  // las figuras siguientes. Se falla en silencio y se avisa por consola.
  const pon = (sel, html) => {
    const el = document.querySelector(sel);
    if (el) el.innerHTML = html; else console.warn("falta el contenedor", sel);
  };

  const NOMBRE = { coyhaique: "Coyhaique", santiago: "Santiago", talcahuano: "Talcahuano" };
  const ORDEN = ["coyhaique", "santiago", "talcahuano"];
  const SEM = '<span class="fuente">Análisis semanal · series de tiempo</span>';
  const ALFA = 0.05;
  const MONO = 'font-family="JetBrains Mono,ui-monospace,monospace"';

  /* ================= barras horizontales =================
     Para lo que no es una estimación con intervalo: correlaciones,
     coeficientes, kilómetros. El cero queda dentro del gráfico y la barra crece
     hacia el lado que le toca. */
  function barras(filas, { w = 700, izq = 170, alto = 26, dec = 2 } = {}) {
    const der = 52, arriba = 8, eje = 26;
    const h = arriba + filas.length * alto + eje;
    const lo = Math.min(0, ...filas.map(f => f.v));
    const hi = Math.max(0, ...filas.map(f => f.v));
    const aire = Math.max((hi - lo) * 0.08, 1e-6);
    const x = AU.escala(lo - (lo < 0 ? aire : 0), hi + aire, izq, w - der);
    const x0 = x(0);

    const grilla = AU.marcas(lo, hi).map(v =>
      `<line x1="${x(v).toFixed(1)}" y1="${arriba}" x2="${x(v).toFixed(1)}"
        y2="${arriba + filas.length * alto}" style="stroke:var(--fig-rejilla)"
        stroke-width="1"/>
      <text x="${x(v).toFixed(1)}" y="${h - 10}" text-anchor="middle" ${MONO}
        font-size="9" style="fill:var(--fig-tinta-3)"
        >${AU.num(v, v % 1 ? dec : 0)}</text>`).join("");

    const cuerpo = filas.map((f, i) => {
      const y = arriba + i * alto + 4;
      const a = Math.min(x0, x(f.v)), b = Math.max(x0, x(f.v));
      const col = f.color || "var(--fig-s1)";
      return `<text x="${izq - 10}" y="${y + alto / 2 - 1}" text-anchor="end"
          font-size="11" style="fill:var(--fig-tinta)">${f.nom}</text>
        <rect x="${a.toFixed(1)}" y="${y}" width="${Math.max(b - a, 1).toFixed(1)}"
          height="${alto - 10}" style="fill:${col}" opacity="${f.tenue ? .35 : .9}"/>
        <text x="${(b + 6).toFixed(1)}" y="${y + alto / 2 - 1}" ${MONO} font-size="9"
          style="fill:var(--fig-tinta-2)">${AU.num(f.v, dec)}</text>`;
    }).join("");

    return `<svg viewBox="0 0 ${w} ${h}" role="img" aria-label="Comparación por categoría">
      ${grilla}
      <line x1="${x0.toFixed(1)}" y1="${arriba}" x2="${x0.toFixed(1)}"
        y2="${arriba + filas.length * alto}" style="stroke:var(--fig-tinta)"
        stroke-width="1"/>
      ${cuerpo}</svg>`;
  }

  /* Barras apiladas al 100 %: el reparto de importancia, donde lo que importa es
     la proporción y no la magnitud. */
  function apiladas(filas, claves) {
    const izq = 100, alto = 32, w = 700, der = 14, arriba = 6;
    const h = arriba + filas.length * alto + 4;
    const ancho = w - izq - der;
    const cuerpo = filas.map((f, i) => {
      const y = arriba + i * alto + 5;
      let acum = 0;
      const trozos = claves.map(k => {
        const px = f[k.campo] / 100 * ancho;
        const x = izq + acum;
        acum += px;
        return `<rect x="${x.toFixed(1)}" y="${y}" width="${Math.max(px, 0).toFixed(1)}"
            height="${alto - 14}" style="fill:${k.color}" opacity=".9"
            ><title>${f.nom} — ${k.nom}: ${AU.num(f[k.campo], 1)} %</title></rect>
          ${px > 34 ? `<text x="${(x + px / 2).toFixed(1)}" y="${y + (alto - 14) / 2 + 3.5}"
            text-anchor="middle" ${MONO} font-size="9.5" style="fill:#fff"
            >${AU.num(f[k.campo], 1)}</text>` : ""}`;
      }).join("");
      return `<text x="${izq - 10}" y="${y + (alto - 14) / 2 + 3.5}" text-anchor="end"
        font-size="11" style="fill:var(--fig-tinta)">${f.nom}</text>${trozos}`;
    }).join("");
    return `<svg viewBox="0 0 ${w} ${h}" role="img"
      aria-label="Reparto de la importancia entre bloques de variables">${cuerpo}</svg>`;
  }

  /* ================= capítulo 3: la trampa, a escala semanal ================= */
  const granger = d.granger;
  const sig = granger.filter(f => f.p_valor < ALFA);
  const lags = [...new Set(granger.map(f => f.lag_semanas))].sort((a, b) => a - b);
  const multi = ORDEN.map(c => d.multivariado.find(f => f.ciudad_id === c));

  const tablaGranger = `<table>
    <thead><tr><th>Ciudad</th>${lags.map(l => `<th>${l}</th>`).join("")}</tr></thead>
    <tbody>${ORDEN.map(c => `<tr><td>${NOMBRE[c]}</td>${lags.map(l => {
      const f = granger.find(g => g.ciudad_id === c && g.lag_semanas === l);
      const s = f && f.p_valor < ALFA;
      return `<td${s ? ' style="color:var(--fig-alerta);font-weight:600"' : ""}
        >${f ? AU.num(f.p_valor, 4) : "—"}</td>`;
    }).join("")}</tr>`).join("")}</tbody></table>`;

  pon("#s-trampa-nt", `
    ${SEM}
    <div class="fig-par">
      ${AU.figura("Coeficiente del MP2.5 sobre la tasa semanal, crudo y ajustado.",
        barras(multi.flatMap(f => [
          { nom: NOMBRE[f.ciudad_id] + " · crudo", v: f.coef_crudo, color: "var(--fig-s2)" },
          { nom: "con clima e inercia", v: f.coef_clima_ar1, color: "var(--fig-s1)",
            tenue: f.p_clima_ar1 >= ALFA },
        ]), { w: 430, izq: 150 }), {
        pie: "Las barras pálidas ya no se distinguen del cero. Ajuste: temperatura, " +
             "humedad e inercia AR(1) de la propia serie.",
      })}
      ${AU.figura("Precedencia temporal de Granger: valores p por rezago en semanas.",
        tablaGranger, {
        pie: `¿El MP2.5 de semanas anteriores mejora la predicción de las urgencias, más ` +
             `allá de lo que ya predice su propio pasado? En rojo, p < ${AU.num(ALFA, 2)}.`,
      })}
    </div>
    <p>El mismo desplome, medido de otra forma y por otra persona: el coeficiente crudo de
      Santiago pasa de ${AU.num(multi[1].coef_crudo, 2)} a ${AU.num(multi[1].coef_clima_ar1, 2)}
      al controlar clima e inercia. Y de las ${granger.length} pruebas de precedencia, solo
      ${sig.length} quedan bajo el umbral: <b>las ${sig.length} en Coyhaique</b>, la ciudad
      donde el humo llega en pulsos aislados dentro de un valle sin ventilación.</p>
    <p>En Coyhaique el coeficiente ajustado sigue siendo distinto de cero pero
      <b>cambia de signo</b> (${AU.num(multi[0].coef_clima_ar1, 2)},
      p = ${AU.num(multi[0].p_clima_ar1, 4)}). Su autor no lo interpreta; a esta resolución
      conviene leerlo como señal de que el modelo semanal está mal especificado, no como un
      hallazgo.</p>`);

  /* ================= capítulo 5: dónde ================= */
  const dist = ORDEN.map(c => d.distancias.find(f => f.ciudad_id === c));
  const viento = d.talcahuano_viento.filter(f => f.escenario.startsWith("Viento oeste"));

  pon("#s-donde-nt", `
    ${SEM}
    <div class="fig-par">
      ${AU.figura("Distancia media de cada establecimiento a su estación SINCA.",
        barras(dist.map(f => ({
          nom: NOMBRE[f.ciudad_id] + ` (${f.establecimientos})`, v: f.km_media,
        })), { w: 430, izq: 140, dec: 2 }), {
        pie: "Entre paréntesis, establecimientos georreferenciados. Distancia geodésica " +
             "(Haversine) al monitor más cercano.",
      })}
      ${AU.figura(`Hospital Las Higueras: correlación con dos estaciones, ` +
        `${viento[0] ? viento[0].n_dias : "—"} días de viento del oeste.`,
        barras(viento.map(f => ({
          nom: f.escenario.replace("Viento oeste, ", ""), v: f.r,
          color: f.escenario.includes("San Vicente") ? "var(--fig-s2)" : "var(--fig-s1)",
        })), { w: 430, izq: 150, dec: 4 }), {
        pie: "Correlaciones simples, sin ajuste por clima ni estacionalidad: comparan dos " +
             "estaciones entre sí, no estiman asociación.",
      })}
    </div>
    <p>En Coyhaique y Talcahuano la estación mide el aire del barrio del hospital. En
      Santiago la media sube a ${AU.num(dist[1].km_media, 1)} km y el más lejano queda a
      ${AU.num(dist[1].km_max, 1)}; aun así ${dist[1].n_alta} de los
      ${dist[1].establecimientos} caen dentro de 5 km. <b>La exposición de Santiago es la
      peor medida de las tres</b>, y eso empuja sus estimaciones hacia el cero.</p>
    <p>En Talcahuano, la estación de <b>San Vicente está cuatro veces más lejos</b> que
      Inpesca y aun así correlaciona más con las urgencias del hospital cuando el viento
      sopla desde la bahía industrial. Asignar la estación más cercana no siempre asigna el
      aire que se respira.</p>`);

  /* ================= anexo: proyección ================= */
  const imp = ORDEN.map(c => d.importancias.find(f => f.ciudad_id === c));
  const BLOQUES = [
    { campo: "inercia", nom: "Inercia de las consultas", color: "var(--fig-s1)" },
    { campo: "clima", nom: "Clima y calendario", color: "var(--fig-s3)" },
    { campo: "mp25", nom: "MP2.5", color: "var(--fig-s2)" },
  ];
  // A modelo fijo: comparar el mejor de B contra el mejor de C mezclaría
  // algoritmos y mediría la diferencia entre ellos, no el aporte del MP2.5.
  const aporte = ORDEN.map(c => {
    const de = cfg => d.ablacion.filter(f => f.ciudad_id === c
      && f.configuracion.startsWith(cfg));
    const b = de("B"), cc = de("C");
    const pares = b.map(x => {
      const y = cc.find(z => z.modelo === x.modelo);
      return y ? { modelo: x.modelo, delta: y.r2 - x.r2, base: x.r2 } : null;
    }).filter(Boolean);
    return { ciudad_id: c, ...pares.reduce((a, b2) => a.delta > b2.delta ? a : b2) };
  });
  const sem = ORDEN.map(c => d.semaforo.find(f => f.ciudad_id === c));

  pon("#s-anexo", `
    ${SEM}
    ${AU.figura("Reparto de la importancia de las variables en el modelo de proyección.",
      apiladas(imp.map(f => ({ ...f, nom: NOMBRE[f.ciudad_id] })), BLOQUES), {
      clave: BLOQUES,
      pie: "Suma 100 % por ciudad. Modelo de proyección de la tasa de urgencias a t+1.",
    })}
    <p>La demanda de la semana que viene la explica, sobre todo, <b>la demanda de esta
      semana</b>. El MP2.5 se queda con una franja pequeña, y su orden entre ciudades repite
      el de todo lo demás: ${ORDEN.slice().sort((a, b) =>
        imp.find(f => f.ciudad_id === b).mp25 - imp.find(f => f.ciudad_id === a).mp25)
        .map(c => `${NOMBRE[c]} ${AU.num(imp.find(f => f.ciudad_id === c).mp25, 1)} %`)
        .join(", ")}.</p>

    <div class="fig-par">
      ${AU.figura("Ganancia en R² al añadir el MP2.5, a algoritmo fijo.",
        barras(aporte.map(f => ({
          nom: NOMBRE[f.ciudad_id], v: f.delta,
          color: f.delta > 0 ? "var(--fig-s2)" : "var(--fig-tinta-3)",
        })), { w: 430, izq: 110, dec: 3 }), {
        pie: "Se compara el mismo algoritmo con y sin MP2.5: el mejor modelo cambia de " +
             "familia entre configuraciones, y comparar los mejores mediría otra cosa.",
      })}
      ${AU.figura("Detección de semanas de alta demanda, prueba ciega 2024.",
        `<table><thead><tr><th>Ciudad</th><th>Sobre P75</th><th>Detect.</th>
          <th>Sensib.</th><th>Precis.</th></tr></thead>
        <tbody>${sem.map(f => `<tr><td>${NOMBRE[f.ciudad_id]}</td>
          <td>${f.semanas_saturacion}</td><td>${f.semanas_detectadas}</td>
          <td>${AU.num(f.recall, 1)} %</td><td>${AU.num(f.precision, 1)} %</td>
          </tr>`).join("")}</tbody></table>`, {
        pie: "Umbrales por percentil local de cada ciudad, calibrados sobre 2022–2023.",
      })}
    </div>
    <p>En el mejor caso —Coyhaique— el R² sube ${AU.num(aporte[0].delta, 3)} desde
      ${AU.num(aporte[0].base, 3)}. <b>El MP2.5 no es lo que permite anticipar la
      demanda</b>: eso lo hace la inercia epidemiológica. Sobre un solo año de prueba y tres
      ciudades esto <b>no es un sistema validado</b>, y Talcahuano, con
      ${sem[2].semanas_saturacion} semanas sobre el umbral en todo el año, no tiene casos
      suficientes para que su cifra signifique algo.</p>`);
})();
