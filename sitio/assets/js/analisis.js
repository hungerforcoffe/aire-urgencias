/* Análisis semanal: MP2.5 y urgencias respiratorias. Requiere comun.js.

   El punto delicado de esta página es la confusión estacional. En invierno sube
   el MP2.5 (calefacción a leña, capa de inversión térmica) y suben las urgencias
   respiratorias (circulación viral, frío). Correlacionar las dos series en bruto
   mide sobre todo que ambas conocen el calendario.

   Por eso todo se muestra dos veces: en bruto y en anomalía —restando a cada
   semana el promedio histórico de esa misma semana del año en esa ciudad—. La
   segunda pregunta es la que interesa: cuando una semana trae MÁS MP2.5 que lo
   normal para esa fecha, ¿trae también más urgencias que lo normal?

   Ni siquiera esa versión establece causalidad. Es un estudio ecológico
   observacional: describe asociación entre agregados de ciudad, no exposición
   ni desenlace de ninguna persona. */

(async function () {
  const $ = s => document.querySelector(s);

  let meta, semanal, ciudades;
  try { [meta, semanal, ciudades] = await AU.cargar("meta", "semanal", "ciudades"); }
  catch (e) { AU.fallo("#paneles", e); return; }

  // El rezago se calcula recorriendo el arreglo, así que el orden es parte del
  // cálculo, no de la presentación. El exportador ya ordena; esto lo garantiza
  // aunque alguien edite la consulta y se le olvide el ORDER BY.
  semanal.sort((a, b) => a.ciudad_id.localeCompare(b.ciudad_id) ||
                         a.semana_id.localeCompare(b.semana_id));

  const NOMBRE = new Map(ciudades.map(c => [c.id, c.nombre]));
  let ciudad = "santiago", rezago = 1, modo = "anomalia";

  /* ================= estadística ================= */
  const media = a => a.reduce((s, x) => s + x, 0) / a.length;
  function pearson(x, y) {
    const n = x.length;
    if (n < 8) return null;
    const mx = media(x), my = media(y);
    let sxy = 0, sxx = 0, syy = 0;
    for (let i = 0; i < n; i++) {
      const dx = x[i] - mx, dy = y[i] - my;
      sxy += dx * dy; sxx += dx * dx; syy += dy * dy;
    }
    return (sxx === 0 || syy === 0) ? null : sxy / Math.sqrt(sxx * syy);
  }
  // Intervalo de confianza al 95% por transformación de Fisher. Se muestra
  // porque un r sin incertidumbre invita a leer diferencias que no existen.
  function ic95(r, n) {
    if (r === null || n < 10) return null;
    const z = 0.5 * Math.log((1 + r) / (1 - r)), s = 1 / Math.sqrt(n - 3);
    const lo = Math.tanh(z - 1.96 * s), hi = Math.tanh(z + 1.96 * s);
    return [lo, hi];
  }

  /* Anomalía: a cada semana se le resta el promedio histórico de esa misma
     semana epidemiológica en esa ciudad. Es el descontado estacional más
     simple que existe y no necesita suponer forma de la curva. */
  function conAnomalias(filas) {
    const clim = new Map();
    for (const f of filas) {
      const k = f.semana_epi;
      if (!clim.has(k)) clim.set(k, { mp: [], tasa: [], temp: [] });
      const c = clim.get(k);
      if (f.mp25_media !== null) c.mp.push(f.mp25_media);
      if (f.tasa_resp_100k !== null) c.tasa.push(f.tasa_resp_100k);
      if (f.temp_media !== null) c.temp.push(f.temp_media);
    }
    const prom = new Map();
    for (const [k, c] of clim) prom.set(k, {
      mp: c.mp.length ? media(c.mp) : null,
      tasa: c.tasa.length ? media(c.tasa) : null,
      temp: c.temp.length ? media(c.temp) : null,
    });
    return filas.map(f => {
      const p = prom.get(f.semana_epi) || {};
      return Object.assign({}, f, {
        mp_anom: (f.mp25_media !== null && p.mp !== null) ? f.mp25_media - p.mp : null,
        tasa_anom: (f.tasa_resp_100k !== null && p.tasa !== null) ? f.tasa_resp_100k - p.tasa : null,
        temp_anom: (f.temp_media !== null && p.temp !== null) ? f.temp_media - p.temp : null,
      });
    });
  }

  const climatologia = filas => {
    const m = new Map();
    for (const f of filas) {
      if (!m.has(f.semana_epi)) m.set(f.semana_epi, { mp: [], tasa: [] });
      const c = m.get(f.semana_epi);
      if (f.mp25_media !== null) c.mp.push(f.mp25_media);
      if (f.tasa_resp_100k !== null) c.tasa.push(f.tasa_resp_100k);
    }
    return [...m.entries()].sort((a, b) => a[0] - b[0]).map(([k, c]) => ({
      semana: k,
      mp: c.mp.length ? media(c.mp) : null,
      tasa: c.tasa.length ? media(c.tasa) : null,
    }));
  };

  /* El rezago se toma de las columnas ya calculadas en la tabla analítica
     (`mp25_media_lag1`, `lag2`), no recorriendo el arreglo: así el desfase
     respeta los huecos de semanas sin cobertura en vez de correr el índice. */
  function paresRezago(filas, k, anomalia) {
    const col = k === 0 ? "mp25_media" : (k === 1 ? "mp25_media_lag1" : "mp25_media_lag2");
    if (!anomalia) {
      const x = [], y = [], meta = [];
      for (const f of filas) if (f[col] !== null && f.tasa_resp_100k !== null && f.cobertura_ok) {
        x.push(f[col]); y.push(f.tasa_resp_100k); meta.push(f);
      }
      return { x, y, meta };
    }
    // Para la versión en anomalía hay que descontar también el MP2.5 rezagado,
    // usando la climatología de la semana de la que viene ese valor.
    const porSemana = new Map(filas.map(f => [f.semana_id, f]));
    const idx = new Map(filas.map((f, i) => [f.semana_id, i]));
    const x = [], y = [], meta = [];
    for (const f of filas) {
      if (f.tasa_anom === null || !f.cobertura_ok) continue;
      const i = idx.get(f.semana_id);
      const orig = k === 0 ? f : filas[i - k];
      if (!orig || orig.mp_anom === null) continue;
      // Solo vale si la semana de origen es realmente k semanas antes.
      if (k > 0 && f[col] === null) continue;
      x.push(orig.mp_anom); y.push(f.tasa_anom); meta.push(f);
    }
    return { x, y, meta };
  }

  /* ================= dibujo ================= */
  const P = { l: 46, r: 14, t: 12, b: 26 };
  function ejes(w, h, xt, yt, ylab) {
    const L = AU.css("--linea"), I3 = AU.css("--tinta-3");
    const M = 'font-family="IBM Plex Mono,monospace" font-size="9"';
    let g = `<line x1="${P.l}" y1="${h - P.b}" x2="${w - P.r}" y2="${h - P.b}" stroke="${L}"/>`;
    for (const t of yt) g += `<line x1="${P.l}" y1="${t.y.toFixed(1)}" x2="${w - P.r}"
      y2="${t.y.toFixed(1)}" stroke="${L}"/>
      <text x="${P.l - 5}" y="${(t.y + 3).toFixed(1)}" text-anchor="end" ${M}
        fill="${t.color || I3}">${t.t}</text>`;
    for (const t of xt) g += `<text x="${t.x.toFixed(1)}" y="${h - P.b + 13}"
      text-anchor="middle" ${M} fill="${I3}">${t.t}</text>`;
    if (ylab) g += `<text x="10" y="${(P.t + 8)}" ${M} fill="${I3}">${ylab}</text>`;
    return g;
  }
  const escala = (v0, v1, p0, p1) => v => p0 + (v - v0) / (v1 - v0 || 1) * (p1 - p0);
  const bonito = m => { const p = Math.pow(10, Math.floor(Math.log10(m)));
    return Math.ceil(m / p) * p; };

  function serieDoble(filas) {
    const w = 700, h = 250;
    const mps = filas.map(f => f.mp25_media).filter(v => v !== null);
    const tas = filas.map(f => f.tasa_resp_100k).filter(v => v !== null);
    if (!mps.length) return '<p class="aviso">Sin datos para esta ciudad.</p>';
    const maxMp = bonito(Math.max(...mps)), maxTa = bonito(Math.max(...tas));
    const X = escala(0, filas.length - 1, P.l, w - P.r);
    const Ymp = escala(0, maxMp, h - P.b, P.t), Yta = escala(0, maxTa, h - P.b, P.t);
    // Dos magnitudes distintas sobre un mismo marco: el MP2.5 va en tinta
    // neutra —es la serie medida— y las urgencias en el naranja de señal, que
    // es el único color de interfaz de todo el sitio.
    const AC = AU.css("--tinta"), E4 = AU.css("--senal");

    let bandas = "";
    filas.forEach((f, i) => {
      if (f.es_invierno) bandas += `<rect x="${(X(i) - (X(1) - X(0)) / 2).toFixed(1)}" y="${P.t}"
        width="${(X(1) - X(0)).toFixed(2)}" height="${h - P.b - P.t}"
        fill="${AU.css("--senal-suave")}"/>`;
    });
    const linea = (campo, Y, color) => {
      let d = "", run = [];
      const cerrar = () => { if (run.length > 1) d += `<polyline points="${run.join(" ")}"
        fill="none" stroke="${color}" stroke-width="1.5" stroke-linejoin="round"/>`; run = []; };
      filas.forEach((f, i) => f[campo] === null ? cerrar()
        : run.push(X(i).toFixed(1) + "," + Y(f[campo]).toFixed(1)));
      cerrar(); return d;
    };
    const xt = [];
    filas.forEach((f, i) => { if (f.semana_epi === 1 || (i === 0 && filas.length > 20))
      xt.push({ x: X(i), t: String(f.anio_epi).slice(2) }); });
    const yt = [0, .5, 1].map(f => ({ y: Ymp(maxMp * f), t: (maxMp * f).toFixed(0), color: AC }));

    return `<svg class="grafico" viewBox="0 0 ${w} ${h}" role="img"
      aria-label="MP2.5 y tasa de urgencias respiratorias por semana">
      ${bandas}${ejes(w, h, xt, yt, "µg/m³")}
      ${linea("tasa_resp_100k", Yta, E4)}${linea("mp25_media", Ymp, AC)}
      <text x="${w - P.r}" y="${P.t + 8}" text-anchor="end"
        font-family="IBM Plex Mono,monospace" font-size="9" fill="${E4}">
        tasa /100k · máx ${maxTa.toFixed(0)}</text></svg>`;
  }

  function graficoClima(filas) {
    const w = 340, h = 210, c = climatologia(filas);
    if (!c.length) return "";
    const maxMp = bonito(Math.max(...c.map(x => x.mp || 0)));
    const maxTa = bonito(Math.max(...c.map(x => x.tasa || 0)));
    const X = escala(1, 53, P.l, w - P.r);
    const Ymp = escala(0, maxMp, h - P.b, P.t), Yta = escala(0, maxTa, h - P.b, P.t);
    const AC = AU.css("--tinta"), E4 = AU.css("--senal");
    const traza = (campo, Y, color) => `<polyline points="${c.filter(x => x[campo] !== null)
      .map(x => X(x.semana).toFixed(1) + "," + Y(x[campo]).toFixed(1)).join(" ")}"
      fill="none" stroke="${color}" stroke-width="2" stroke-linejoin="round"/>`;
    const inv = `<rect x="${X(18).toFixed(1)}" y="${P.t}" width="${(X(35) - X(18)).toFixed(1)}"
      height="${h - P.b - P.t}" fill="${AU.css("--senal-suave")}"/>`;
    const xt = [1, 13, 26, 39, 52].map(s => ({ x: X(s), t: "S" + s }));
    const yt = [0, .5, 1].map(f => ({ y: Ymp(maxMp * f), t: (maxMp * f).toFixed(0), color: AC }));
    return `<svg class="grafico" viewBox="0 0 ${w} ${h}" role="img"
      aria-label="Promedio por semana del año">${inv}${ejes(w, h, xt, yt, "µg/m³")}
      ${traza("tasa", Yta, E4)}${traza("mp", Ymp, AC)}</svg>`;
  }

  function dispersion(par, anomalia) {
    const w = 340, h = 210;
    if (par.x.length < 8) return '<p class="aviso">Muy pocas semanas para graficar.</p>';
    const x0 = Math.min(...par.x), x1 = Math.max(...par.x);
    const y0 = Math.min(...par.y), y1 = Math.max(...par.y);
    const X = escala(x0, x1, P.l, w - P.r), Y = escala(y0, y1, h - P.b, P.t);
    const pts = par.x.map((v, i) => {
      const f = par.meta[i];
      return `<circle cx="${X(v).toFixed(1)}" cy="${Y(par.y[i]).toFixed(1)}" r="2.3"
        fill="${f.es_invierno ? AU.css("--senal") : AU.css("--tinta-3")}" fill-opacity=".55"/>`;
    }).join("");
    // Recta de mínimos cuadrados, como resumen visual de la nube. No es un
    // modelo ajustado: no controla temperatura, pandemia ni circulación viral.
    const mx = media(par.x), my = media(par.y);
    let sxy = 0, sxx = 0;
    for (let i = 0; i < par.x.length; i++) { sxy += (par.x[i] - mx) * (par.y[i] - my);
      sxx += (par.x[i] - mx) ** 2; }
    const b = sxx ? sxy / sxx : 0, a = my - b * mx;
    const recta = `<line x1="${X(x0).toFixed(1)}" y1="${Y(a + b * x0).toFixed(1)}"
      x2="${X(x1).toFixed(1)}" y2="${Y(a + b * x1).toFixed(1)}"
      stroke="${AU.css("--tinta-2")}" stroke-width="1.5" stroke-dasharray="5 3"/>`;
    const xt = [x0, (x0 + x1) / 2, x1].map(v => ({ x: X(v), t: v.toFixed(0) }));
    const yt = [y0, (y0 + y1) / 2, y1].map(v => ({ y: Y(v), t: v.toFixed(0) }));
    return `<svg class="grafico" viewBox="0 0 ${w} ${h}" role="img"
      aria-label="Dispersión entre MP2.5 y tasa de urgencias">
      ${ejes(w, h, xt, yt, anomalia ? "anomalía tasa" : "tasa /100k")}${pts}${recta}
      <text x="${w - P.r}" y="${h - P.b + 13}" text-anchor="end"
        font-family="IBM Plex Mono,monospace" font-size="9" fill="${AU.css("--tinta-3")}">
        ${anomalia ? "anomalía MP2.5 (µg/m³)" : "MP2.5 (µg/m³)"}</text></svg>`;
  }

  function graficoRezagos(filas) {
    const w = 340, h = 210;
    const barras = [0, 1, 2].map(k => ({
      k,
      bruto: pearson(...(p => [p.x, p.y])(paresRezago(filas, k, false))),
      anom: pearson(...(p => [p.x, p.y])(paresRezago(filas, k, true))),
    }));
    const todos = barras.flatMap(b => [b.bruto, b.anom]).filter(v => v !== null);
    const lim = Math.max(.35, ...todos.map(Math.abs));
    const Y = escala(-lim, lim, h - P.b, P.t);
    const anchoG = (w - P.l - P.r) / 3, aB = anchoG * 0.32;
    const AC = AU.css("--senal"), I2 = AU.css("--tinta-2");
    let g = `<line x1="${P.l}" y1="${Y(0).toFixed(1)}" x2="${w - P.r}" y2="${Y(0).toFixed(1)}"
      stroke="${AU.css("--linea-2")}"/>`;
    barras.forEach((b, i) => {
      const cx = P.l + anchoG * (i + .5);
      [[b.bruto, -aB * 1.05, I2], [b.anom, aB * 0.05, AC]].forEach(([v, dx, col]) => {
        if (v === null) return;
        const y = Y(v), y0 = Y(0);
        g += `<rect x="${(cx + dx).toFixed(1)}" y="${Math.min(y, y0).toFixed(1)}"
          width="${aB.toFixed(1)}" height="${Math.abs(y - y0).toFixed(1)}" fill="${col}"
          fill-opacity=".85"/>
          <text x="${(cx + dx + aB / 2).toFixed(1)}" y="${(v >= 0 ? y - 4 : y + 11).toFixed(1)}"
          text-anchor="middle" font-family="IBM Plex Mono,monospace" font-size="9"
          fill="${col}">${v.toFixed(2)}</text>`;
      });
      g += `<text x="${cx.toFixed(1)}" y="${h - P.b + 14}" text-anchor="middle"
        font-family="IBM Plex Mono,monospace" font-size="9" fill="${AU.css("--tinta-3")}">
        ${b.k === 0 ? "misma sem." : b.k + " sem. antes"}</text>`;
    });
    [-lim, 0, lim].forEach(v => { g += `<text x="${P.l - 5}" y="${(Y(v) + 3).toFixed(1)}"
      text-anchor="end" font-family="IBM Plex Mono,monospace" font-size="9"
      fill="${AU.css("--tinta-3")}">${v.toFixed(2)}</text>`; });
    return `<svg class="grafico" viewBox="0 0 ${w} ${h}" role="img"
      aria-label="Correlación por rezago, en bruto y en anomalía">${g}</svg>`;
  }

  /* ================= render ================= */
  function pintar() {
    const base = semanal.filter(f => f.ciudad_id === ciudad);
    const filas = conAnomalias(base);
    const anomalia = modo === "anomalia";
    const par = paresRezago(filas, rezago, anomalia);
    const r = pearson(par.x, par.y), ic = ic95(r, par.x.length);

    // Las dos versiones se calculan siempre, aunque solo una se grafique: los
    // indicadores de arriba muestran las dos juntas, que es donde se ve el
    // salto entre "parece asociación" y "era el calendario".
    const parBruto = paresRezago(filas, rezago, false);
    const rBruto = pearson(parBruto.x, parBruto.y);
    const parAnom = paresRezago(filas, rezago, true);
    const rAnom = pearson(parAnom.x, parAnom.y);
    const icAnom = ic95(rAnom, parAnom.x.length);

    const tempPar = { x: [], y: [] };
    for (const f of filas) if (f.temp_media !== null && f.tasa_resp_100k !== null) {
      tempPar.x.push(f.temp_media); tempPar.y.push(f.tasa_resp_100k);
    }
    const rTemp = pearson(tempPar.x, tempPar.y);
    const nom = NOMBRE.get(ciudad);

    $("#indicadores").innerHTML = `
      <div><div class="k">Semanas</div><div class="v">${AU.miles(base.length)}</div>
        <div class="d">${base[0] ? base[0].semana_id : "—"} a
          ${base.length ? base[base.length - 1].semana_id : "—"}</div></div>
      <div><div class="k">r · en bruto</div>
        <div class="v" style="color:var(--tinta-3)">${rBruto === null ? "—" : rBruto.toFixed(2)}</div>
        <div class="d">confundida por la estación del año</div></div>
      <div><div class="k">r · en anomalía</div>
        <div class="v" style="color:var(--senal)">${rAnom === null ? "—" : rAnom.toFixed(2)}</div>
        <div class="d">${icAnom
          ? `IC 95% ${icAnom[0].toFixed(2)} a ${icAnom[1].toFixed(2)}` +
            (icAnom[0] <= 0 && icAnom[1] >= 0 ? " — incluye el cero" : "")
          : "descontado el ciclo semanal"}</div></div>
      <div><div class="k">r · temperatura</div>
        <div class="v" style="color:var(--tinta-3)">${rTemp === null ? "—" : rTemp.toFixed(2)}</div>
        <div class="d">el frío también acompaña a las dos</div></div>`;

    $("#paneles").innerHTML = `
      <section class="full">
        <h3>Las dos series, semana a semana</h3>
        <p class="sub">${nom}, ${base.length} semanas. Bandas verticales = invierno.</p>
        <div class="clave">
          <span><i style="background:var(--tinta)"></i>MP2.5 (µg/m³)</span>
          <span><i style="background:var(--senal)"></i>urgencias respiratorias por 100.000</span></div>
        ${serieDoble(base)}
        <p class="lee">Suben y bajan juntas, pero <b>las dos siguen el calendario</b>: el MP2.5
          por calefacción e inversión térmica, las urgencias por circulación viral y frío.
          Leer eso como una relación directa sería confundir la asociación con la estación
          del año.</p>
      </section>

      <section>
        <h3>El problema, en un gráfico</h3>
        <p class="sub">Promedio de cada semana del año, todos los años juntos.</p>
        ${graficoClima(base)}
        <p class="lee">Las dos curvas tienen la misma joroba de invierno. Cualquier
          correlación calculada sobre las series crudas está midiendo, sobre todo,
          <b>esta coincidencia de calendario</b>.</p>
      </section>

      <section>
        <h3>Correlación por rezago</h3>
        <p class="sub">Pearson entre MP2.5 y tasa de urgencias, con y sin descuento estacional.</p>
        <div class="clave">
          <span><i style="background:var(--tinta-3)"></i>serie en bruto</span>
          <span><i style="background:var(--senal)"></i>en anomalía</span></div>
        ${graficoRezagos(filas)}
        <p class="lee">La barra gris se desploma al descontar la estación: <b>casi toda la
          correlación aparente era el calendario</b>. Lo que queda en naranja es la asociación
          entre desviaciones respecto de lo normal para esa fecha, y en las tres ciudades es
          pequeña.</p>
      </section>

      <section class="full">
        <h3>Semana a semana, ${anomalia ? "en anomalía" : "en bruto"}${
          rezago ? `, con ${rezago} semana${rezago > 1 ? "s" : ""} de rezago` : ""}</h3>
        <p class="sub">Cada punto es una semana; las de invierno van marcadas. La recta
          punteada resume la nube — no es un modelo ajustado.</p>
        ${dispersion(par, anomalia)}
        <p class="lee">${par.x.length} semanas con cobertura suficiente.
          r = <b>${r === null ? "—" : r.toFixed(3)}</b>${ic ? `, IC 95% ${ic[0].toFixed(2)} a
          ${ic[1].toFixed(2)}` : ""}.
          ${ic && ic[0] <= 0 && ic[1] >= 0
            ? `<b>El intervalo incluye el cero</b>, así que a esta resolución el dato no
               distingue esta asociación de la ausencia de asociación. Eso no prueba que no
               exista: la semana es una ventana ancha para un efecto que la literatura busca
               en días, y acá no se controla circulación viral.`
            : `El intervalo no cruza el cero.`}
          En cualquier caso describe una tendencia poblacional, no el riesgo de ninguna
          persona.</p>
      </section>`;
  }

  /* ================= controles ================= */
  $("#sel-ciudad").innerHTML = ciudades.map(c =>
    `<option value="${c.id}"${c.id === ciudad ? " selected" : ""}>${c.nombre}</option>`).join("");
  $("#sel-ciudad").addEventListener("change", e => { ciudad = e.target.value; pintar(); });
  $("#sel-rezago").addEventListener("change", e => { rezago = +e.target.value; pintar(); });
  document.querySelectorAll("#modo button").forEach(b =>
    b.addEventListener("click", () => {
      modo = b.dataset.modo;
      document.querySelectorAll("#modo button").forEach(x =>
        x.setAttribute("aria-pressed", x === b));
      pintar();
    }));
  document.addEventListener("au:tema", pintar);

  $("#e-semanas").textContent = AU.miles(semanal.length);
  $("#e-corte").textContent = meta.ultimo_mes;
  pintar();
})();
