/* Capítulos 4 a 7: el modelo diario. Requiere comun.js.

   Esta parte NO calcula nada. Los RR y sus intervalos salen de `modelo.json`,
   que escribe `src/sitio/exportar_modelo.py` a partir de los CSV del cuaderno
   de análisis. GitHub Pages sirve archivos: acá no se puede ajustar una Poisson
   condicional aunque quisiéramos.

   Todo se muestra también como cambio porcentual. «RR 1,0081» y «+0,81 % por
   cada +10 µg/m³» son el mismo número, pero solo el segundo se entiende sin
   haber tomado un curso de epidemiología.

   Nada de lo que se dibuja establece causalidad. El diseño compara a cada ciudad
   consigo misma en días vecinos del mismo mes y día de semana, lo que controla
   todo lo que no cambia dentro de esa ventana — pero no lo que sí cambia día a
   día junto con el aire. El capítulo 7 mide cuánto de eso quedó adentro. */

(async function () {
  const $ = s => document.querySelector(s);

  let m;
  try { m = await AU.cargar("modelo"); }
  catch (e) { AU.fallo("#s-modelo", e); return; }

  // Escribir en un contenedor que no existe tumbaba el script entero y con el
  // las figuras siguientes. Se falla en silencio y se avisa por consola.
  const pon = (sel, html) => {
    const el = document.querySelector(sel);
    if (el) el.innerHTML = html; else console.warn("falta el contenedor", sel);
  };

  const NOMBRE = { coyhaique: "Coyhaique", santiago: "Santiago", talcahuano: "Talcahuano" };
  const principal = Object.fromEntries(m.principal.map(f => [f.analisis, f]));
  const CONTEMP = principal["Asociación contemporánea"];
  const ACUM = principal["Asociación acumulada"];

  /* ================= formato ================= */
  const pc = rr => (rr - 1) * 100;
  const signo = v => (v < 0 ? "−" : "+") + AU.num(Math.abs(v), 2);
  const pct = rr => signo(pc(rr)) + " %";
  // Un intervalo que contiene al 1 no distingue la asociación de su ausencia.
  const cruza = f => f.ic_inf <= 1 && f.ic_sup >= 1;
  const DIA = '<span class="fuente dia">Modelo diario · case-crossover</span>';

  const marcas = AU.marcas;
  // El dominio SIEMPRE incluye el 0 %. Si el eje empezara en el dato, un
  // intervalo entero por encima del nulo se vería igual que uno que lo cruza.
  function dominio(filas) {
    let lo = 0, hi = 0;
    for (const f of filas) { lo = Math.min(lo, pc(f.ic_inf)); hi = Math.max(hi, pc(f.ic_sup)); }
    const aire = Math.max((hi - lo) * 0.12, 0.05);
    return [lo - aire, hi + aire];
  }

  /* ================= bosque =================
     Una fila por estimación: la línea es el intervalo de 95 %, el punto la
     estimación, la vertical el valor nulo. Es la forma estándar de presentar
     estimaciones con incertidumbre y no se inventa nada acá. */
  function bosque(filas, { w = 700, izq = 190, alto = 27 } = {}) {
    const [lo, hi] = dominio(filas);
    const der = 16, arriba = 10, eje = 30;
    const ancho = w - izq - der;
    const h = arriba + filas.length * alto + eje;
    const x = v => izq + (v - lo) / (hi - lo) * ancho;
    const M = 'font-family="JetBrains Mono,ui-monospace,monospace"';

    const grilla = marcas(lo, hi).map(v => {
      const nulo = Math.abs(v) < 1e-9;
      return `<line x1="${x(v).toFixed(1)}" y1="${arriba}" x2="${x(v).toFixed(1)}"
        y2="${arriba + filas.length * alto}"
        style="stroke:var(--fig-${nulo ? "tinta" : "rejilla"})" stroke-width="1"/>
      <text x="${x(v).toFixed(1)}" y="${h - 13}" text-anchor="middle" ${M}
        font-size="9" style="fill:var(--fig-tinta-3)"
        >${v === 0 ? "0" : signo(v)}</text>`;
    }).join("");

    const cuerpo = filas.map((f, i) => {
      const y = arriba + i * alto + alto / 2;
      const col = f.alerta ? "var(--fig-alerta)" : "var(--fig-s1)";
      const a = x(pc(f.ic_inf)), b = x(pc(f.ic_sup)), p = x(pc(f.rr10));
      return `<text x="${izq - 10}" y="${y + 3.5}" text-anchor="end"
          font-size="11" style="fill:var(--fig-tinta)">${f.nom}</text>
        <line x1="${a.toFixed(1)}" y1="${y}" x2="${b.toFixed(1)}" y2="${y}"
          style="stroke:${col}" stroke-width="1.4"/>
        <line x1="${a.toFixed(1)}" y1="${y - 4}" x2="${a.toFixed(1)}" y2="${y + 4}"
          style="stroke:${col}" stroke-width="1.4"/>
        <line x1="${b.toFixed(1)}" y1="${y - 4}" x2="${b.toFixed(1)}" y2="${y + 4}"
          style="stroke:${col}" stroke-width="1.4"/>
        <circle cx="${p.toFixed(1)}" cy="${y}" r="3.4" style="fill:${col}"/>
        <text x="${w - der}" y="${y + 3.5}" text-anchor="end" ${M} font-size="9"
          style="fill:var(--fig-tinta-2)">${pct(f.rr10)}</text>`;
    }).join("");

    return `<svg viewBox="0 0 ${w} ${h}" role="img"
      aria-label="Estimaciones con intervalo de confianza de 95 %">
      ${grilla}${cuerpo}
      <text x="${izq}" y="${h - 2}" ${M} font-size="9"
        style="fill:var(--fig-tinta-3)">cambio % en las consultas por +10 µg/m³</text>
    </svg>`;
  }

  /* ================= curva de rezagos ================= */
  function curva(filas, { w = 700, h = 250, compacto = false } = {}) {
    const izq = compacto ? 34 : 52, der = 14, arriba = 14, abajo = compacto ? 24 : 32;
    const [lo, hi] = dominio(filas);
    const ancho = w - izq - der, altoUtil = h - arriba - abajo;
    const x = i => izq + (i / (filas.length - 1)) * ancho;
    const y = v => arriba + (hi - v) / (hi - lo) * altoUtil;
    const M = 'font-family="JetBrains Mono,ui-monospace,monospace"';

    const grilla = marcas(lo, hi).map(v => {
      const nulo = Math.abs(v) < 1e-9;
      return `<line x1="${izq}" y1="${y(v).toFixed(1)}" x2="${w - der}" y2="${y(v).toFixed(1)}"
        style="stroke:var(--fig-${nulo ? "tinta" : "rejilla"})" stroke-width="1"/>
      ${compacto && !nulo ? "" : `<text x="${izq - 6}" y="${(y(v) + 3.5).toFixed(1)}"
        text-anchor="end" ${M} font-size="9" style="fill:var(--fig-tinta-3)"
        >${v === 0 ? "0" : signo(v)}</text>`}`;
    }).join("");

    const banda = filas.map((f, i) =>
      `${i ? "L" : "M"} ${x(i).toFixed(1)} ${y(pc(f.ic_sup)).toFixed(1)}`).join(" ")
      + " " + filas.slice().reverse().map((f, i) =>
      `L ${x(filas.length - 1 - i).toFixed(1)} ${y(pc(f.ic_inf)).toFixed(1)}`).join(" ") + " Z";
    const linea = filas.map((f, i) =>
      `${i ? "L" : "M"} ${x(i).toFixed(1)} ${y(pc(f.rr10)).toFixed(1)}`).join(" ");
    const puntos = filas.map((f, i) =>
      `<circle cx="${x(i).toFixed(1)}" cy="${y(pc(f.rr10)).toFixed(1)}"
        r="${cruza(f) ? 2.6 : 3.4}" style="${cruza(f)
          ? "fill:var(--fig-sup);stroke:var(--fig-s1);stroke-width:1.5"
          : "fill:var(--fig-s1)"}"/>`).join("");
    const ejeX = filas.map((f, i) => (compacto && i % 2 ? "" :
      `<text x="${x(i).toFixed(1)}" y="${h - (compacto ? 8 : 14)}" text-anchor="middle"
        ${M} font-size="9" style="fill:var(--fig-tinta-3)">${f.lag}</text>`)).join("");

    return `<svg viewBox="0 0 ${w} ${h}" role="img" aria-label="Asociación por día de rezago">
      ${grilla}
      <path d="${banda}" style="fill:var(--fig-s1)" opacity=".16"/>
      <path d="${linea}" style="stroke:var(--fig-s1);fill:none" stroke-width="1.8"
        stroke-linejoin="round"/>
      ${puntos}${ejeX}
      ${compacto ? "" : `<text x="${w - der}" y="${h - 2}" text-anchor="end" ${M}
        font-size="9" style="fill:var(--fig-tinta-3)">días transcurridos desde la
        exposición</text>`}
    </svg>`;
  }

  /* ================= mapa de cobertura ================= */
  const COBERTURA_MINIMA = 75;   // el mismo 75 % que usa el resto del proyecto
  function mapaCobertura(filas, zonas) {
    const anios = [...new Set(filas.map(f => f.anio))].sort();
    const izq = 92, arriba = 20, celda = 34, alto = 25;
    const w = izq + anios.length * celda + 10;
    const h = arriba + zonas.length * alto + 18;
    const M = 'font-family="JetBrains Mono,ui-monospace,monospace"';

    const cabecera = anios.map((a, j) =>
      `<text x="${izq + j * celda + celda / 2}" y="${arriba - 7}" text-anchor="middle"
        ${M} font-size="9" style="fill:var(--fig-tinta-2)">${String(a).slice(2)}</text>`).join("");

    const celdas = zonas.map((z, i) => {
      const y = arriba + i * alto;
      const rot = `<text x="${izq - 10}" y="${y + alto / 2 + 3.5}" text-anchor="end"
        font-size="11" style="fill:var(--fig-tinta)">${z.zona}</text>`;
      return rot + anios.map((a, j) => {
        const f = filas.find(r => r.zona_id === z.zona_id && r.anio === a);
        if (!f) return "";
        const baja = f.cobertura_pct < COBERTURA_MINIMA;
        // Bajo el umbral cambia el color y no solo la intensidad: una diferencia
        // de tono se ve de un vistazo, una de opacidad hay que compararla.
        const col = baja ? "var(--fig-alerta)" : "var(--fig-s1)";
        const op = baja ? 0.92 : (0.12 + 0.5 * (f.cobertura_pct - COBERTURA_MINIMA) / 25);
        return `<rect x="${izq + j * celda + 1}" y="${y + 1}" width="${celda - 2}"
            height="${alto - 2}" rx="2" style="fill:${col}" opacity="${op.toFixed(2)}"
            ><title>${z.zona} ${a}: ${AU.num(f.cobertura_pct, 1)} % (${f.dias_con_mp25} de ${f.dias} días)</title></rect>
          ${baja ? `<text x="${izq + j * celda + celda / 2}" y="${y + alto / 2 + 3.5}"
            text-anchor="middle" ${M} font-size="9.5" style="fill:#fff"
            >${Math.round(f.cobertura_pct)}</text>` : ""}`;
      }).join("");
    }).join("");

    return `<svg viewBox="0 0 ${w} ${h}" role="img"
      style="max-width:560px" preserveAspectRatio="xMinYMid meet"
      aria-label="Cobertura de MP2.5 por zona de Santiago y año">${cabecera}${celdas}</svg>`;
  }

  /* ================= datos derivados ================= */
  const control = m.controles_negativos.reduce((a, b) => a.casos > b.casos ? a : b);
  const porCiudad = m.ciudad.map(f => ({ ...f, nom: NOMBRE[f.ciudad] }));
  const porEdad = m.edad.map(f => ({ ...f, nom: f.grupo_edad + " años" }));
  const acumCiudad = m.lags_acum_ciudad.map(f => ({ ...f, nom: NOMBRE[f.ciudad] }));
  const sens = m.sensibilidades.map(f => ({ ...f, nom: f.etiqueta || f.especificacion }));
  const placebo = m.placebo.map(f => ({
    ...f,
    nom: f.etiqueta.replace(/PM2\.5/g, "MP2.5").replace(/ \| ajustado por MP2\.5 t$/, ", ajustado"),
    alerta: f.tipo_placebo.startsWith("Exposición futura ajustada") && !cruza(f),
  }));
  const controles = m.controles_negativos.map(f => ({ ...f, nom: f.etiqueta, alerta: true }));
  const ajuste = m.ajuste.map(f => ({ ...f, nom: f.especificacion }));
  const base = ajuste[0], completo = ajuste[ajuste.length - 1];
  const dx = m.diagnosticos.map(f => ({ ...f, nom: f.diagnostico }));
  const dxAlto = dx.reduce((a, b) => a.rr10 > b.rr10 ? a : b);
  const dxNulo = dx.filter(cruza);
  const PERIODOS = [...new Set(m.zonas_rm.map(f => f.periodo))];
  const zonas = PERIODOS.map(p => m.zonas_rm.filter(f => f.periodo === p)
    .map(f => ({ ...f, nom: f.zona })));
  const zonasUnicas = zonas[0].map(f => ({ zona_id: f.zona_id, zona: f.zona }));
  const zonaPeor = m.cobertura_rm.reduce((a, b) => a.cobertura_pct < b.cobertura_pct ? a : b);
  const nomZona = id => (zonasUnicas.find(z => z.zona_id === id) || {}).zona || id;
  const masAlto = porEdad.reduce((a, b) => a.rr10 > b.rr10 ? a : b);
  const lag0 = m.lags[0];
  const conMasSenal = porCiudad.reduce((a, b) => a.rr10 > b.rr10 ? a : b);

  /* ================= indicadores ================= */
  pon("#m-indicadores", `
    <div><div class="k">Mismo día</div>
      <div class="v" style="color:var(--senal)">${pct(CONTEMP.rr10)}</div>
      <div class="d">por cada +10 µg/m³ · RR ${AU.num(CONTEMP.rr10, 4)}</div></div>
    <div><div class="k">Acumulado 0–7 días</div>
      <div class="v" style="color:var(--senal)">${pct(ACUM.rr10)}</div>
      <div class="d">suma de los ocho rezagos</div></div>
    <div><div class="k">Días-ciudad</div>
      <div class="v">${AU.miles(CONTEMP.n_dias)}</div>
      <div class="d">en ${AU.miles(CONTEMP.n_estratos)} bloques de
        ciudad × año × mes × día de semana</div></div>
    <div><div class="k">Control negativo</div>
      <div class="v" style="color:var(--tinta-3)">${pct(control.rr10)}</div>
      <div class="d">debería ser 0 %. Ver capítulo 7</div></div>`);

  /* ================= capítulo 4: la estimación ================= */
  pon("#s-modelo", `
    ${DIA}
    ${AU.figura("Asociación estimada al sumar controles uno a uno.", bosque(ajuste), {
      pie: `Mismas ${AU.miles(completo.n_dias)} días-ciudad y ${AU.miles(completo.casos)} ` +
           "consultas en las cuatro filas: lo único que cambia es el ajuste.",
    })}
    <p>Sin controles la asociación es ${pct(base.rr10)}. La temperatura casi no la mueve;
      <b>la humedad y la circulación viral se llevan más de la mitad</b>. El modelo completo
      queda en ${pct(completo.rr10)} y no llega a cero — con la reserva del capítulo 7.</p>

    ${AU.figura("Asociación según cuántos días antes se midió el aire.", curva(m.lags), {
      pie: "Banda = intervalo de 95 %. Punto hueco = el intervalo contiene el cero.",
    })}
    <p>El máximo está en el <b>mismo día</b> (${pct(lag0.rr10)}) y al segundo día ya no queda
      nada distinguible. Esa forma —rápida y sin cola— es la que explica por qué el análisis
      semanal del capítulo 3 no encontraba nada: promediar siete días diluye algo que dura
      uno.</p>

    ${AU.figura("La misma curva, ciudad por ciudad.", `<div class="trio">
      ${["coyhaique", "santiago", "talcahuano"].map(c => `<div>
        <div class="rot">${NOMBRE[c]}</div>
        ${curva(m.lags_ciudad.filter(f => f.ciudad === c),
          { w: 300, h: 160, compacto: true })}</div>`).join("")}</div>`, {
      pie: "Escala propia en cada una: lo comparable es la forma, no la altura. " +
           "Acumulado 0–7 días: " + acumCiudad.map(f => `${f.nom} ${pct(f.rr10)}`).join(", ") + ".",
    })}
    <p>Talcahuano concentra todo en los días 0 y 1. Santiago aporta él solo el repunte de
      los días 5 y 6. Coyhaique reparte la asociación a lo largo de la semana, coherente con
      episodios de humo que duran días.</p>`);

  /* ================= capítulo 5: dónde ================= */
  pon("#s-donde", `
    ${DIA}
    ${AU.figura("Asociación del mismo día, por ciudad.", bosque(porCiudad, { izq: 130 }), {
      pie: "Cada ciudad se compara consigo misma; no hay comparación entre ellas.",
    })}
    <p><b>${conMasSenal.nom}</b> muestra la asociación más grande. Coyhaique tiene el
      intervalo <b>más angosto</b> pese a aportar 145.200 consultas contra los 8,2 millones
      de Santiago: no es que tenga más datos, es que su aire varía muchísimo más.</p>

    ${AU.figura("Asociación por zona del Gran Santiago.",
      `<div class="conmutador" id="sel-periodo" style="margin-bottom:10px">
        ${PERIODOS.map((p, i) => `<button data-p="${i}" aria-pressed="${i === 0}"
          >${p}</button>`).join("")}
      </div><div id="zonas-svg">${bosque(zonas[0], { izq: 130 })}</div>`, {
      pie: "Diferencias descriptivas: no se hizo prueba formal de interacción entre zonas.",
    })}
    <p>Oriente y Sur Oriente son las únicas zonas cuyo intervalo no toca el cero, y siguen
      sin tocarlo al estirar la ventana hasta 2026. Occidente apunta en sentido contrario.</p>

    ${AU.figura("Días del año con dato de MP2.5, por zona.",
      mapaCobertura(m.cobertura_rm, zonasUnicas), {
      clave: [{ nom: `bajo ${COBERTURA_MINIMA} %`, color: "var(--fig-alerta)" },
              { nom: "cobertura suficiente", color: "var(--fig-s1)" }],
      pie: "El tono más intenso indica mayor cobertura. Los valores en rojo llevan su " +
           "porcentaje escrito.",
    })}
    <p><b>${nomZona(zonaPeor.zona_id)} midió ${zonaPeor.dias_con_mp25} de ${zonaPeor.dias}
      días en ${zonaPeor.anio}</b> (${AU.num(zonaPeor.cobertura_pct, 1)} %). Una zona que
      deja de medir antes del invierno no deja un hueco en el gráfico: deja un promedio más
      limpio. Por eso la ventana principal termina en 2024.</p>`);

  /* ================= capítulo 6: en quién ================= */
  pon("#s-quien", `
    ${DIA}
    <div class="fig-par">
      ${AU.figura("Por grupo de edad.", bosque(porEdad, { w: 430, izq: 96 }), {
        pie: "Mismos ajustes que el modelo principal.",
      })}
      ${AU.figura("Por diagnóstico respiratorio.", bosque(dx, { w: 430, izq: 150 }), {
        pie: "Las seis causas del grupo respiratorio del DEIS, por separado.",
      })}
    </div>
    <p>Ningún grupo de edad toca el cero y <b>${masAlto.nom}</b> encabeza. Entre los
      diagnósticos, ${dxAlto.nom.toLowerCase()} es el más alto${dxNulo.length
        ? ` y «${dxNulo[0].nom.toLowerCase()}» —el cajón de sastre del grupo— el único que
           no se distingue del cero` : ""}. Son cortes descriptivos: <b>no se contrastó
      formalmente si difieren entre sí</b>.</p>`);

  /* ================= capítulo 7: robustez ================= */
  pon("#s-firme", `
    ${DIA}
    ${AU.figura("El resultado bajo otras decisiones de modelado.", bosque(sens), {
      pie: "Forma funcional de la humedad, restricción a mediciones validadas por SINCA " +
           "y ponderación territorial.",
    })}
    <p>Cambiar la humedad de lineal a spline mueve el resultado en la cuarta cifra decimal.
      <b>El número no depende de esas decisiones</b>, que es lo que una sensibilidad debe
      demostrar.</p>

    ${AU.figura("Controles negativos y placebo temporal.",
      bosque(controles.concat(placebo.filter(f =>
        f.tipo_placebo.startsWith("Exposición futura ajustada")))), {
      clave: [{ nom: "debería dar cero y no lo da", color: "var(--fig-alerta)" },
              { nom: "compatible con el cero", color: "var(--fig-s1)" }],
      pie: "Un control negativo es un desenlace que el MP2.5 no puede provocar; un placebo " +
           "temporal usa aire del futuro. Los dos deberían dar 0 %.",
    })}
    <p>Respirar partículas no fractura un hueso ni provoca un choque, así que esas filas
      <b>miden nuestro error, no el aire</b>. Y miden ${pct(control.rr10)}:
      <b>más que el ${pct(CONTEMP.rr10)} del desenlace que interesa</b>. Los días de mucho
      MP2.5 son días de inversión térmica —fríos, sin viento—, y ese mismo clima produce
      caídas y choques por vías que no pasan por los pulmones.</p>
    <p><b>No podemos separar cuánto del resultado es el aire y cuánto es esa estructura
      compartida.</b> Por eso la página informa una asociación y nunca un efecto.</p>`);

  /* ================= conmutador de ventana temporal =================
     Redibuja solo el SVG de las zonas. El bosque se regenera entero porque su
     dominio depende de los datos: reusar el eje de una ventana para la otra
     movería los puntos sin mover las marcas. */
  const selP = $("#sel-periodo");
  if (selP) {
    selP.addEventListener("click", e => {
      const b = e.target.closest("button");
      if (!b) return;
      for (const otro of selP.querySelectorAll("button")) {
        otro.setAttribute("aria-pressed", String(otro === b));
      }
      $("#zonas-svg").innerHTML = bosque(zonas[+b.dataset.p], { izq: 130 });
    });
  }

})();
