/* Capítulos 1 a 3: el fenómeno, el calendario y la trampa. Requiere comun.js.

   El punto delicado de la página es la confusión estacional. En invierno sube el
   MP2.5 (leña, inversión térmica) y suben las urgencias respiratorias (virus,
   frío). Correlacionar las series en bruto mide sobre todo que ambas conocen el
   calendario, y esa es exactamente la trampa que el capítulo 3 desarma.

   Todos los gráficos se dibujan sobre la lámina de figura, con los tokens
   --fig-* escritos dentro del SVG. Eso los hace independientes del tema de la
   página: no hay que repintarlos al cambiar de claro a oscuro, y se pueden
   exportar o imprimir tal cual.

   Nada de esto establece causalidad. Es un estudio ecológico observacional. */

(async function () {
  const $ = s => document.querySelector(s);

  let meta, semanal, ciudades;
  try { [meta, semanal, ciudades] = await AU.cargar("meta", "semanal", "ciudades"); }
  catch (e) { AU.fallo("#s-fenomeno", e); return; }

  // El rezago recorre el arreglo, así que el orden es parte del cálculo.
  semanal.sort((a, b) => a.ciudad_id.localeCompare(b.ciudad_id) ||
                         a.semana_id.localeCompare(b.semana_id));

  // Escribir en un contenedor que no existe tumbaba el script entero y con el
  // las figuras siguientes. Se falla en silencio y se avisa por consola.
  const pon = (sel, html) => {
    const el = document.querySelector(sel);
    if (el) el.innerHTML = html; else console.warn("falta el contenedor", sel);
  };

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
  // Intervalo al 95 % por transformación de Fisher: un r sin incertidumbre
  // invita a leer diferencias que no existen.
  function ic95(r, n) {
    if (r === null || n < 10) return null;
    const z = 0.5 * Math.log((1 + r) / (1 - r)), s = 1 / Math.sqrt(n - 3);
    return [Math.tanh(z - 1.96 * s), Math.tanh(z + 1.96 * s)];
  }

  /* Anomalía: a cada semana se le resta el promedio histórico de esa misma
     semana epidemiológica en esa ciudad. Es el descuento estacional más simple
     que existe y no supone forma de la curva. */
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
      });
    });
  }

  const climatologia = filas => {
    const m = new Map();
    for (const f of filas) {
      if (!m.has(f.semana_epi)) m.set(f.semana_epi, { mp: [], tasa: [], temp: [] });
      const c = m.get(f.semana_epi);
      if (f.mp25_media !== null) c.mp.push(f.mp25_media);
      if (f.tasa_resp_100k !== null) c.tasa.push(f.tasa_resp_100k);
      if (f.temp_media !== null) c.temp.push(f.temp_media);
    }
    return [...m.entries()].sort((a, b) => a[0] - b[0]).map(([k, c]) => ({
      semana: k,
      mp: c.mp.length ? media(c.mp) : null,
      tasa: c.tasa.length ? media(c.tasa) : null,
      temp: c.temp.length ? media(c.temp) : null,
    }));
  };

  /* El rezago sale de las columnas ya calculadas (`mp25_media_lag1`, `lag2`), no
     de correr el índice: así respeta los huecos de semanas sin cobertura. */
  function paresRezago(filas, k, anomalia) {
    const col = k === 0 ? "mp25_media" : (k === 1 ? "mp25_media_lag1" : "mp25_media_lag2");
    if (!anomalia) {
      const x = [], y = [], meta = [];
      for (const f of filas) if (f[col] !== null && f.tasa_resp_100k !== null && f.cobertura_ok) {
        x.push(f[col]); y.push(f.tasa_resp_100k); meta.push(f);
      }
      return { x, y, meta };
    }
    const idx = new Map(filas.map((f, i) => [f.semana_id, i]));
    const x = [], y = [], meta = [];
    for (const f of filas) {
      if (f.tasa_anom === null || !f.cobertura_ok) continue;
      const orig = k === 0 ? f : filas[idx.get(f.semana_id) - k];
      if (!orig || orig.mp_anom === null) continue;
      if (k > 0 && f[col] === null) continue;
      x.push(orig.mp_anom); y.push(f.tasa_anom); meta.push(f);
    }
    return { x, y, meta };
  }

  /* ================= dibujo =================
     Márgenes generosos a la izquierda: el eje lleva rótulo y unidad, y con menos
     sitio los números de tres cifras se montaban sobre la línea. */
  const P = { l: 52, r: 16, t: 20, b: 34 };
  const MONO = 'font-family="JetBrains Mono,ui-monospace,monospace"';
  const escala = (v0, v1, p0, p1) => v => p0 + (v - v0) / (v1 - v0 || 1) * (p1 - p0);
  const bonito = m => { const p = Math.pow(10, Math.floor(Math.log10(m)));
    return Math.ceil(m / p) * p; };

  /* Marco de figura: eje inferior e izquierdo sólidos, rejilla horizontal
     punteada. Es la convención de un gráfico técnico y no de un panel de
     dashboard — el marco dice dónde termina el dato. */
  function marco(w, h, xt, yt, { ylab = "", ycol = "var(--fig-tinta-2)" } = {}) {
    let g = "";
    for (const t of yt) g += `<line x1="${P.l}" y1="${t.y.toFixed(1)}" x2="${w - P.r}"
      y2="${t.y.toFixed(1)}" style="stroke:var(--fig-rejilla)" stroke-width="1"/>
      <text x="${P.l - 6}" y="${(t.y + 3).toFixed(1)}" text-anchor="end" ${MONO}
        font-size="9" style="fill:${t.color || ycol}">${t.t}</text>`;
    g += `<line x1="${P.l}" y1="${P.t}" x2="${P.l}" y2="${h - P.b}"
        style="stroke:var(--fig-linea)" stroke-width="1"/>
      <line x1="${P.l}" y1="${h - P.b}" x2="${w - P.r}" y2="${h - P.b}"
        style="stroke:var(--fig-linea)" stroke-width="1"/>`;
    for (const t of xt) g += `<line x1="${t.x.toFixed(1)}" y1="${h - P.b}"
        x2="${t.x.toFixed(1)}" y2="${h - P.b + 3}" style="stroke:var(--fig-linea)"/>
      <text x="${t.x.toFixed(1)}" y="${h - P.b + 14}" text-anchor="middle" ${MONO}
        font-size="9" style="fill:var(--fig-tinta-3)">${t.t}</text>`;
    if (ylab) g += `<text x="2" y="11" ${MONO} font-size="9"
      style="fill:${ycol}">${ylab}</text>`;
    return g;
  }

  function serieDoble(filas) {
    const w = 760, h = 260;
    const mps = filas.map(f => f.mp25_media).filter(v => v !== null);
    const tas = filas.map(f => f.tasa_resp_100k).filter(v => v !== null);
    if (!mps.length) return '<p class="aviso">Sin datos para esta ciudad.</p>';
    const maxMp = bonito(Math.max(...mps)), maxTa = bonito(Math.max(...tas));
    const X = escala(0, filas.length - 1, P.l, w - P.r);
    const Ymp = escala(0, maxMp, h - P.b, P.t), Yta = escala(0, maxTa, h - P.b, P.t);

    let bandas = "";
    filas.forEach((f, i) => {
      if (f.es_invierno) bandas += `<rect x="${(X(i) - (X(1) - X(0)) / 2).toFixed(1)}"
        y="${P.t}" width="${(X(1) - X(0)).toFixed(2)}" height="${h - P.b - P.t}"
        style="fill:var(--fig-sombra)"/>`;
    });
    const linea = (campo, Y, color, gruesa) => {
      let d = "", run = [];
      const cerrar = () => { if (run.length > 1) d += `<polyline points="${run.join(" ")}"
        fill="none" style="stroke:${color}" stroke-width="${gruesa}"
        stroke-linejoin="round"/>`; run = []; };
      filas.forEach((f, i) => f[campo] === null ? cerrar()
        : run.push(X(i).toFixed(1) + "," + Y(f[campo]).toFixed(1)));
      cerrar(); return d;
    };
    const xt = [];
    filas.forEach((f, i) => { if (f.semana_epi === 1) xt.push({ x: X(i), t: f.anio_epi }); });
    const yt = [0, .25, .5, .75, 1].map(f => ({ y: Ymp(maxMp * f),
      t: (maxMp * f).toFixed(0), color: "var(--fig-s1)" }));

    return `<svg viewBox="0 0 ${w} ${h}" role="img"
      aria-label="MP2.5 y tasa de urgencias respiratorias por semana">
      ${bandas}${marco(w, h, xt, yt, { ylab: "µg/m³", ycol: "var(--fig-s1)" })}
      ${linea("tasa_resp_100k", Yta, "var(--fig-s2)", 1.4)}
      ${linea("mp25_media", Ymp, "var(--fig-s1)", 1.4)}
      <text x="${w - P.r}" y="${P.t - 6}" text-anchor="end" ${MONO} font-size="9"
        style="fill:var(--fig-s2)">tasa /100k — máximo ${maxTa.toFixed(0)}</text></svg>`;
  }

  /* Climatología: el promedio de cada semana del año con todos los años
     encima. Tres series sobre el mismo eje temporal, cada una con su escala,
     porque lo comparable es la forma y no la altura. */
  function graficoClima(filas) {
    const w = 760, h = 250, c = climatologia(filas);
    if (!c.length) return "";
    const rango = campo => {
      const v = c.map(x => x[campo]).filter(x => x !== null);
      return [Math.min(...v), Math.max(...v)];
    };
    const [, maxMp] = rango("mp"), [, maxTa] = rango("tasa");
    const [minT, maxT] = rango("temp");
    const X = escala(1, 53, P.l, w - P.r);
    const Ymp = escala(0, bonito(maxMp), h - P.b, P.t);
    const Yta = escala(0, bonito(maxTa), h - P.b, P.t);
    const Yt = escala(minT - 1, maxT + 1, h - P.b, P.t);
    const traza = (campo, Y, color, guion) => `<polyline points="${c
      .filter(x => x[campo] !== null)
      .map(x => X(x.semana).toFixed(1) + "," + Y(x[campo]).toFixed(1)).join(" ")}"
      fill="none" style="stroke:${color}" stroke-width="1.9" stroke-linejoin="round"
      ${guion ? 'stroke-dasharray="4 3"' : ""}/>`;
    // Invierno austral: semanas 18 a 35, mayo a agosto.
    const inv = `<rect x="${X(18).toFixed(1)}" y="${P.t}"
      width="${(X(35) - X(18)).toFixed(1)}" height="${h - P.b - P.t}"
      style="fill:var(--fig-sombra)"/>
      <text x="${((X(18) + X(35)) / 2).toFixed(1)}" y="${P.t + 11}" text-anchor="middle"
        ${MONO} font-size="9" style="fill:var(--fig-tinta-3)">invierno</text>`;
    const xt = [1, 13, 26, 39, 52].map(s => ({ x: X(s), t: "S" + s }));
    const yt = [0, .5, 1].map(f => ({ y: Ymp(bonito(maxMp) * f),
      t: (bonito(maxMp) * f).toFixed(0), color: "var(--fig-s1)" }));
    return `<svg viewBox="0 0 ${w} ${h}" role="img"
      aria-label="Promedio de cada semana del año: MP2.5, urgencias y temperatura">
      ${inv}${marco(w, h, xt, yt, { ylab: "µg/m³", ycol: "var(--fig-s1)" })}
      ${traza("temp", Yt, "var(--fig-s3)", true)}
      ${traza("tasa", Yta, "var(--fig-s2)", false)}
      ${traza("mp", Ymp, "var(--fig-s1)", false)}</svg>`;
  }

  function dispersion(par, anomalia) {
    const w = 760, h = 300;
    if (par.x.length < 8) return '<p class="aviso">Muy pocas semanas para graficar.</p>';
    const x0 = Math.min(...par.x), x1 = Math.max(...par.x);
    const y0 = Math.min(...par.y), y1 = Math.max(...par.y);
    const X = escala(x0, x1, P.l, w - P.r), Y = escala(y0, y1, h - P.b, P.t);
    const pts = par.x.map((v, i) => `<circle cx="${X(v).toFixed(1)}"
      cy="${Y(par.y[i]).toFixed(1)}" r="2.4" style="fill:${par.meta[i].es_invierno
        ? "var(--fig-s2)" : "var(--fig-tinta-3)"}" fill-opacity=".55"/>`).join("");
    // Recta de mínimos cuadrados como resumen visual de la nube. NO es un modelo
    // ajustado: no controla temperatura, pandemia ni circulación viral.
    const mx = media(par.x), my = media(par.y);
    let sxy = 0, sxx = 0;
    for (let i = 0; i < par.x.length; i++) {
      sxy += (par.x[i] - mx) * (par.y[i] - my); sxx += (par.x[i] - mx) ** 2;
    }
    const b = sxx ? sxy / sxx : 0, a = my - b * mx;
    const recta = `<line x1="${X(x0).toFixed(1)}" y1="${Y(a + b * x0).toFixed(1)}"
      x2="${X(x1).toFixed(1)}" y2="${Y(a + b * x1).toFixed(1)}"
      style="stroke:var(--fig-tinta)" stroke-width="1.4" stroke-dasharray="5 3"/>`;
    const xt = [x0, (x0 + x1) / 2, x1].map(v => ({ x: X(v), t: v.toFixed(0) }));
    const yt = [y0, (y0 + y1) / 2, y1].map(v => ({ y: Y(v), t: v.toFixed(0) }));
    return `<svg viewBox="0 0 ${w} ${h}" role="img"
      aria-label="Dispersión entre MP2.5 y tasa de urgencias">
      ${marco(w, h, xt, yt, { ylab: anomalia ? "anomalía tasa" : "tasa /100k" })}
      ${pts}${recta}
      <text x="${w - P.r}" y="${h - 3}" text-anchor="end" ${MONO} font-size="9"
        style="fill:var(--fig-tinta-3)">${anomalia
          ? "anomalía de MP2.5 (µg/m³)" : "MP2.5 (µg/m³)"}</text></svg>`;
  }

  /* La figura que sostiene el capítulo 3: la misma correlación, antes y después
     de descontar la estación del año, en los tres rezagos. */
  function graficoRezagos(filas) {
    const w = 380, h = 230;
    const barras = [0, 1, 2].map(k => ({
      k,
      bruto: pearson(...(p => [p.x, p.y])(paresRezago(filas, k, false))),
      anom: pearson(...(p => [p.x, p.y])(paresRezago(filas, k, true))),
    }));
    const todos = barras.flatMap(b => [b.bruto, b.anom]).filter(v => v !== null);
    const lim = Math.max(.35, ...todos.map(Math.abs));
    const Y = escala(-lim, lim, h - P.b, P.t);
    const anchoG = (w - P.l - P.r) / 3, aB = anchoG * 0.3;
    const yt = [-lim, -lim / 2, 0, lim / 2, lim].map(v => ({ y: Y(v), t: v.toFixed(2) }));
    const xt = barras.map((b, i) => ({ x: P.l + anchoG * (i + .5),
      t: b.k === 0 ? "0 sem" : b.k + " sem" }));
    let g = marco(w, h, xt, yt, { ylab: "r de Pearson" });
    g += `<line x1="${P.l}" y1="${Y(0).toFixed(1)}" x2="${w - P.r}" y2="${Y(0).toFixed(1)}"
      style="stroke:var(--fig-tinta)" stroke-width="1"/>`;
    barras.forEach((b, i) => {
      const cx = P.l + anchoG * (i + .5);
      [[b.bruto, -aB * 1.05, "var(--fig-tinta-3)"],
       [b.anom, aB * 0.05, "var(--fig-s2)"]].forEach(([v, dx, col]) => {
        if (v === null) return;
        const y = Y(v), yc = Y(0);
        g += `<rect x="${(cx + dx).toFixed(1)}" y="${Math.min(y, yc).toFixed(1)}"
          width="${aB.toFixed(1)}" height="${Math.max(Math.abs(y - yc), 1).toFixed(1)}"
          style="fill:${col}" fill-opacity=".9"/>
          <text x="${(cx + dx + aB / 2).toFixed(1)}"
          y="${(v >= 0 ? y - 4 : y + 11).toFixed(1)}" text-anchor="middle" ${MONO}
          font-size="9" style="fill:${col}">${v.toFixed(2)}</text>`;
      });
    });
    return `<svg viewBox="0 0 ${w} ${h}" role="img"
      aria-label="Correlación por rezago, en bruto y en anomalía">${g}</svg>`;
  }

  /* ================= render ================= */
  function pintar() {
    const base = semanal.filter(f => f.ciudad_id === ciudad);
    const filas = conAnomalias(base);
    const anomalia = modo === "anomalia";
    const par = paresRezago(filas, rezago, anomalia);
    const r = pearson(par.x, par.y), ic = ic95(r, par.x.length);
    const rBruto = pearson(...(p => [p.x, p.y])(paresRezago(filas, rezago, false)));
    const parAnom = paresRezago(filas, rezago, true);
    const rAnom = pearson(parAnom.x, parAnom.y);
    const icAnom = ic95(rAnom, parAnom.x.length);
    const nom = NOMBRE.get(ciudad);

    const tempPar = { x: [], y: [] };
    for (const f of filas) if (f.temp_media !== null && f.tasa_resp_100k !== null) {
      tempPar.x.push(f.temp_media); tempPar.y.push(f.tasa_resp_100k);
    }
    const rTemp = pearson(tempPar.x, tempPar.y);

    pon("#s-fenomeno", `
      ${AU.figura(`MP2.5 y urgencias respiratorias por semana. ${nom}, ${base.length} semanas.`,
        serieDoble(base), {
        clave: [{ nom: "MP2.5 (µg/m³)", color: "var(--fig-s1)" },
                { nom: "urgencias respiratorias /100.000 hab", color: "var(--fig-s2)" },
                { nom: "invierno", color: "var(--fig-sombra)" }],
        pie: "Semanas epidemiológicas MMWR. Ejes independientes: lo comparable es la " +
             "forma, no la altura. Fuente: SINCA (MMA) y DEIS (MINSAL).",
      })}
      <p>Las dos curvas suben y bajan a la vez, todos los años. Es lo que hace evidente
        la pregunta y también lo que la vuelve difícil: <b>coincidir en el tiempo no es
        depender una de la otra</b>.</p>`);

    pon("#s-clima", `
      ${AU.figura(`Promedio de cada semana del año, todos los años superpuestos. ${nom}.`,
        graficoClima(filas), {
        clave: [{ nom: "MP2.5", color: "var(--fig-s1)" },
                { nom: "urgencias /100k", color: "var(--fig-s2)" },
                { nom: "temperatura media (°C)", color: "var(--fig-s3)" }],
        pie: "Cada serie en su propia escala. La temperatura va punteada por ser la " +
             "única que baja cuando las otras suben.",
      })}
      <p>La misma joroba de invierno en las tres. La temperatura es su espejo:
        cuando cae, suben el humo y las consultas. Con
        <b>r = ${rTemp === null ? "—" : rTemp.toFixed(2)}</b> entre temperatura y urgencias,
        el frío por sí solo explica buena parte de lo que se ve arriba.</p>`);

    pon("#indicadores", `
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
        <div class="d">el frío también acompaña a las dos</div></div>`);

    pon("#s-trampa", `
      <div class="fig-par">
        ${AU.figura(`Correlación por rezago, antes y después de descontar la estación. ${nom}.`,
          graficoRezagos(filas), {
          clave: [{ nom: "serie en bruto", color: "var(--fig-tinta-3)" },
                  { nom: "en anomalía", color: "var(--fig-s2)" }],
          pie: "Anomalía = cada semana menos el promedio histórico de esa misma semana " +
               "del año en esa ciudad.",
        })}
        ${AU.figura(`Semanas ${anomalia ? "en anomalía" : "en bruto"}${rezago
            ? `, MP2.5 de ${rezago} semana${rezago > 1 ? "s" : ""} antes` : ""}. ${nom}.`,
          dispersion(par, anomalia), {
          clave: [{ nom: "semana de invierno", color: "var(--fig-s2)" },
                  { nom: "resto del año", color: "var(--fig-tinta-3)" }],
          pie: `${par.x.length} semanas con cobertura suficiente. La recta es de mínimos ` +
               "cuadrados y resume la nube; no es un modelo ajustado.",
        })}
      </div>
      <p>La barra gris se desploma al descontar la estación: <b>casi toda la correlación
        aparente era el calendario</b>. Lo que queda es
        r = ${rAnom === null ? "—" : rAnom.toFixed(3)}${icAnom
          ? ` (IC 95 % ${icAnom[0].toFixed(2)} a ${icAnom[1].toFixed(2)})` : ""}, y
        ${icAnom && icAnom[0] <= 0 && icAnom[1] >= 0
          ? `<b>el intervalo incluye el cero</b>. A esta resolución el dato no distingue
             la asociación de su ausencia.`
          : `el intervalo no cruza el cero.`}
        Eso no prueba que no exista: la semana es una ventana ancha para algo que la
        literatura busca en días. Ese es el motivo del capítulo siguiente.</p>`);
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
  // Ya no hace falta repintar al cambiar de tema: los gráficos viven en la
  // lámina y sus colores son fijos.

  $("#e-semanas").textContent = AU.miles(semanal.length);
  $("#e-corte").textContent = meta.ultimo_mes;
  pintar();
})();
