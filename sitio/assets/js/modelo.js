/* Resultados del modelo de asociación: case-crossover diario. Requiere comun.js.

   Esta parte de la página NO calcula nada. Los RR y sus intervalos salen de
   `modelo.json`, que escribe `src/sitio/exportar_modelo.py` a partir de los CSV
   del cuaderno de análisis. GitHub Pages sirve archivos y nada más: acá no se
   puede ajustar una Poisson condicional aunque quisiéramos, y por eso los
   resultados llegan precomputados.

   Todo se muestra como cambio porcentual además del RR. «RR 1,0081» y «+0,81 %
   por cada +10 µg/m³» son el mismo número, pero solo el segundo se entiende sin
   haber tomado un curso de epidemiología.

   Nada de lo que se dibuja acá establece causalidad. El diseño compara a cada
   ciudad consigo misma en días vecinos del mismo mes y día de semana, lo que
   controla todo lo que no cambia dentro de esa ventana — pero no lo que sí
   cambia día a día junto con el aire. Los controles negativos del último panel
   son la medida de cuánto de eso quedó adentro. */

/* Los paneles del análisis semanal se añaden a estos mismos contenedores, y
   ambos scripts cargan su JSON en paralelo. Sin un punto de encuentro, el que
   llegue segundo con innerHTML borra al primero. La promesa se declara de forma
   síncrona, antes del cuerpo asíncrono, para que exista cuando el navegador
   evalúe el script siguiente. */
let _modeloListo;
window.MODELO_LISTO = new Promise(r => { _modeloListo = r; });

(async function () {
  const $ = s => document.querySelector(s);

  let m;
  try { m = await AU.cargar("modelo"); }
  catch (e) { AU.fallo("#p-asociacion", e); _modeloListo(); return; }

  const NOMBRE = { coyhaique: "Coyhaique", santiago: "Santiago", talcahuano: "Talcahuano" };
  const principal = Object.fromEntries(m.principal.map(f => [f.analisis, f]));
  const CONTEMP = principal["Asociación contemporánea"];
  const ACUM = principal["Asociación acumulada"];

  /* ================= formato =================
     El RR se convierte a cambio porcentual porque es la lectura directa: 1,0081
     es «0,81 % más consultas». El signo se escribe siempre, incluso el «+», para
     que un intervalo que cruza el cero se vea cruzar. */
  const pc = rr => (rr - 1) * 100;
  const signo = v => (v < 0 ? "−" : "+") + AU.num(Math.abs(v), 2);
  const pct = rr => signo(pc(rr)) + " %";
  const rrTxt = f => `RR ${AU.num(f.rr10, 4)} (${AU.num(f.ic_inf, 4)}–${AU.num(f.ic_sup, 4)})`;
  // Un intervalo que contiene al 1 no distingue la asociación de su ausencia.
  const cruza = f => f.ic_inf <= 1 && f.ic_sup >= 1;

  /* ================= ejes ================= */
  // El paso de grilla vive en comun.js: lo comparten los dos análisis de la
  // página, y dos versiones de la misma función acaban dando ejes distintos.
  const marcas = AU.marcas;
  // El dominio SIEMPRE incluye el 0 % (el valor nulo). Si el eje empezara en el
  // dato, un intervalo entero sobre el nulo se vería igual que uno que lo cruza.
  function dominio(filas) {
    let lo = 0, hi = 0;
    for (const f of filas) { lo = Math.min(lo, pc(f.ic_inf)); hi = Math.max(hi, pc(f.ic_sup)); }
    const aire = Math.max((hi - lo) * 0.12, 0.05);
    return [lo - aire, hi + aire];
  }

  /* ================= bosque =================
     Una fila por estimación: la línea es el intervalo de 95 %, el punto es la
     estimación. La vertical marca el valor nulo. */
  function bosque(filas, { w = 340, izq = 104, alto = 26, titulo = "" } = {}) {
    const [lo, hi] = dominio(filas);
    const der = 10, arriba = 6, eje = 30;
    const ancho = w - izq - der;
    const h = arriba + filas.length * alto + eje;
    const x = v => izq + (v - lo) / (hi - lo) * ancho;
    const x0 = x(0);

    const grilla = marcas(lo, hi).map(v => {
      const nulo = Math.abs(v) < 1e-9;
      return `<line x1="${x(v).toFixed(1)}" y1="${arriba}" x2="${x(v).toFixed(1)}"
        y2="${arriba + filas.length * alto}"
        style="stroke:var(--linea${nulo ? "-2" : ""})" stroke-width="1"
        ${nulo ? "" : 'stroke-dasharray="2 3"'}/>
      <text x="${x(v).toFixed(1)}" y="${h - 12}" text-anchor="middle"
        style="fill:var(--tinta-3)" font-size="9.5" font-family="var(--mono)"
        >${v === 0 ? "0" : signo(v)}</text>`;
    }).join("");

    const filasSvg = filas.map((f, i) => {
      const y = arriba + i * alto + alto / 2;
      const col = f.alerta ? "var(--senal)" : "var(--s2)";
      const a = x(pc(f.ic_inf)), b = x(pc(f.ic_sup)), p = x(pc(f.rr10));
      return `<text x="${izq - 8}" y="${y + 3.5}" text-anchor="end"
          style="fill:var(--tinta-2)" font-size="11">${f.nom}</text>
        <line x1="${a.toFixed(1)}" y1="${y}" x2="${b.toFixed(1)}" y2="${y}"
          style="stroke:${col}" stroke-width="1.6" opacity=".55"/>
        <line x1="${a.toFixed(1)}" y1="${y - 3.5}" x2="${a.toFixed(1)}" y2="${y + 3.5}"
          style="stroke:${col}" stroke-width="1.6" opacity=".55"/>
        <line x1="${b.toFixed(1)}" y1="${y - 3.5}" x2="${b.toFixed(1)}" y2="${y + 3.5}"
          style="stroke:${col}" stroke-width="1.6" opacity=".55"/>
        <circle cx="${p.toFixed(1)}" cy="${y}" r="3.6" style="fill:${col}"/>`;
    }).join("");

    return `<svg class="grafico" viewBox="0 0 ${w} ${h}" role="img"
      aria-label="${titulo || "Estimaciones con intervalo de confianza de 95%"}">
      ${grilla}
      <line x1="${x0.toFixed(1)}" y1="${arriba}" x2="${x0.toFixed(1)}"
        y2="${arriba + filas.length * alto}" style="stroke:var(--tinta-3)" stroke-width="1.2"/>
      ${filasSvg}
      <text x="${w - der}" y="${h - 4}" text-anchor="end" style="fill:var(--tinta-3)"
        font-size="9" font-family="var(--mono)">cambio % por +10 µg/m³</text>
    </svg>`;
  }

  /* ================= curva de rezagos =================
     El eje x son días desde la exposición. La banda es el intervalo; la línea,
     la estimación puntual. La horizontal en 0 % es el valor nulo. */
  function curva(filas, { w = 700, h = 240, titulo = "", compacto = false } = {}) {
    const izq = compacto ? 30 : 46, der = 10, arriba = 10, abajo = compacto ? 22 : 30;
    const [lo, hi] = dominio(filas);
    const ancho = w - izq - der, altoUtil = h - arriba - abajo;
    const x = i => izq + (i / (filas.length - 1)) * ancho;
    const y = v => arriba + (hi - v) / (hi - lo) * altoUtil;

    const grilla = marcas(lo, hi).map(v => {
      const nulo = Math.abs(v) < 1e-9;
      return `<line x1="${izq}" y1="${y(v).toFixed(1)}" x2="${w - der}" y2="${y(v).toFixed(1)}"
        style="stroke:var(--linea${nulo ? "-2" : ""})" stroke-width="1"
        ${nulo ? "" : 'stroke-dasharray="2 3"'}/>
      ${compacto && !nulo ? "" : `<text x="${izq - 5}" y="${(y(v) + 3.5).toFixed(1)}"
        text-anchor="end" style="fill:var(--tinta-3)" font-size="9.5"
        font-family="var(--mono)">${v === 0 ? "0" : signo(v)}</text>`}`;
    }).join("");

    const banda = filas.map((f, i) => `${i ? "L" : "M"} ${x(i).toFixed(1)} ${y(pc(f.ic_sup)).toFixed(1)}`)
      .join(" ") + " " + filas.slice().reverse()
      .map((f, i) => `L ${x(filas.length - 1 - i).toFixed(1)} ${y(pc(f.ic_inf)).toFixed(1)}`).join(" ") + " Z";
    const linea = filas.map((f, i) =>
      `${i ? "L" : "M"} ${x(i).toFixed(1)} ${y(pc(f.rr10)).toFixed(1)}`).join(" ");
    const puntos = filas.map((f, i) =>
      `<circle cx="${x(i).toFixed(1)}" cy="${y(pc(f.rr10)).toFixed(1)}"
        r="${cruza(f) ? 2.4 : 3.4}" style="fill:var(--s2);${cruza(f)
          ? "fill:var(--panel);stroke:var(--s2);stroke-width:1.5" : ""}"/>`).join("");
    const ejeX = filas.map((f, i) => (compacto && i % 2 ? "" :
      `<text x="${x(i).toFixed(1)}" y="${h - (compacto ? 6 : 12)}" text-anchor="middle"
        style="fill:var(--tinta-3)" font-size="9.5" font-family="var(--mono)">${f.lag}</text>`)).join("");

    return `<svg class="grafico" viewBox="0 0 ${w} ${h}" role="img"
      aria-label="${titulo || "Asociación por día de rezago"}">
      ${grilla}
      <path d="${banda}" style="fill:var(--s2)" opacity=".14"/>
      <path d="${linea}" style="stroke:var(--s2);fill:none" stroke-width="1.8"
        stroke-linejoin="round"/>
      ${puntos}
      ${ejeX}
      ${compacto ? "" : `<text x="${w - der}" y="${h - 4}" text-anchor="end"
        style="fill:var(--tinta-3)" font-size="9" font-family="var(--mono)"
        >días de rezago →</text>`}
    </svg>`;
  }

  /* ================= indicadores ================= */
  const control = m.controles_negativos.reduce((a, b) => a.casos > b.casos ? a : b);

  $("#m-indicadores").innerHTML = `
    <div><div class="k">Mismo día</div>
      <div class="v" style="color:var(--s2)">${pct(CONTEMP.rr10)}</div>
      <div class="d">${rrTxt(CONTEMP)}<br>por cada +10 µg/m³ de MP2.5</div></div>
    <div><div class="k">Acumulado 0–7 días</div>
      <div class="v" style="color:var(--s2)">${pct(ACUM.rr10)}</div>
      <div class="d">${rrTxt(ACUM)}<br>suma de los ocho rezagos</div></div>
    <div><div class="k">Días-ciudad</div>
      <div class="v">${AU.miles(CONTEMP.n_dias)}</div>
      <div class="d">en ${AU.miles(CONTEMP.n_estratos)} estratos de
        ciudad × año × mes × día de semana</div></div>
    <div><div class="k">Control negativo</div>
      <div class="v" style="color:var(--senal)">${pct(control.rr10)}</div>
      <div class="d">${control.etiqueta.toLowerCase()} — debería ser 0 %.
        Ver el último panel.</div></div>`;

  /* ================= mapa de cobertura =================
     Zonas en filas, años en columnas. No es un gráfico de la asociación: es la
     razón por la que la ventana principal termina en 2024, y sin verlo la
     comparación territorial parece una decisión arbitraria. */
  const COBERTURA_MINIMA = 75;   // el mismo 75 % que usa el resto del proyecto
  function mapaCobertura(filas, zonas) {
    const anios = [...new Set(filas.map(f => f.anio))].sort();
    const izq = 88, arriba = 18, celda = 30, alto = 22;
    const w = izq + anios.length * celda + 8;
    const h = arriba + zonas.length * alto + 16;

    const cabecera = anios.map((a, j) =>
      `<text x="${izq + j * celda + celda / 2}" y="${arriba - 6}" text-anchor="middle"
        style="fill:var(--tinta-3)" font-size="9" font-family="var(--mono)"
        >${String(a).slice(2)}</text>`).join("");

    const celdas = zonas.map((z, i) => {
      const y = arriba + i * alto;
      const rot = `<text x="${izq - 8}" y="${y + alto / 2 + 3.5}" text-anchor="end"
        style="fill:var(--tinta-2)" font-size="11">${z.zona}</text>`;
      const cs = anios.map((a, j) => {
        const f = filas.find(r => r.zona_id === z.zona_id && r.anio === a);
        if (!f) return "";
        const baja = f.cobertura_pct < COBERTURA_MINIMA;
        // Bajo el umbral el color cambia, no solo la intensidad: una diferencia
        // de tono se ve de un vistazo, una de opacidad hay que compararla.
        const col = baja ? "var(--senal)" : "var(--cobertura-ok)";
        const op = baja ? 0.9 : (0.15 + 0.75 * (f.cobertura_pct - COBERTURA_MINIMA) / 25);
        return `<rect x="${izq + j * celda + 1}" y="${y + 1}" width="${celda - 2}"
            height="${alto - 2}" rx="2" style="fill:${col}" opacity="${op.toFixed(2)}"
            ><title>${z.zona} ${a}: ${AU.num(f.cobertura_pct, 1)} % (${f.dias_con_mp25} de ${f.dias} días)</title></rect>
          ${baja ? `<text x="${izq + j * celda + celda / 2}" y="${y + alto / 2 + 3}"
            text-anchor="middle" style="fill:#fff" font-size="8.5"
            font-family="var(--mono)">${Math.round(f.cobertura_pct)}</text>` : ""}`;
      }).join("");
      return rot + cs;
    }).join("");

    // El tope de ancho es necesario acá y no en los demás gráficos: este es el
    // más angosto de la página y vive en un panel de ancho completo, así que sin
    // él se estira más de 3x y las celdas quedan del tamaño de un botón.
    return `<svg class="grafico" viewBox="0 0 ${w} ${h}" role="img"
      style="max-width:620px;margin:0 auto"
      aria-label="Cobertura de MP2.5 por zona de Santiago y año">
      ${cabecera}${celdas}
      <text x="${w - 8}" y="${h - 3}" text-anchor="end" style="fill:var(--tinta-3)"
        font-size="9" font-family="var(--mono)">% de días del año con dato</text>
    </svg>`;
  }

  /* ================= paneles ================= */
  const porCiudad = m.ciudad.map(f => ({ ...f, nom: NOMBRE[f.ciudad] }));
  const porEdad = m.edad.map(f => ({ ...f, nom: f.grupo_edad + " años" }));
  const acumCiudad = m.lags_acum_ciudad.map(f => ({ ...f, nom: NOMBRE[f.ciudad] }));
  const sens = m.sensibilidades.map(f => ({ ...f, nom: f.especificacion }));
  const placebo = m.placebo.map(f => ({
    ...f, nom: f.etiqueta.replace(/PM2\.5/g, "MP2.5").replace(/ \| ajustado por MP2\.5 t$/, ", ajustado"),
    alerta: f.tipo_placebo.startsWith("Exposición futura ajustada") && !cruza(f),
  }));
  const controles = m.controles_negativos.map(f => ({ ...f, nom: f.etiqueta, alerta: true }));

  const masAlto = porEdad.reduce((a, b) => a.rr10 > b.rr10 ? a : b);
  const masBajo = porEdad.reduce((a, b) => a.rr10 < b.rr10 ? a : b);
  const lag0 = m.lags[0];
  const conMasSenal = porCiudad.reduce((a, b) => a.rr10 > b.rr10 ? a : b);

  // Bloques nuevos de la segunda entrega.
  const ajuste = m.ajuste.map(f => ({ ...f, nom: f.especificacion }));
  const base = ajuste[0], completo = ajuste[ajuste.length - 1];
  const dx = m.diagnosticos.map(f => ({ ...f, nom: f.diagnostico }));
  const dxAlto = dx.reduce((a, b) => a.rr10 > b.rr10 ? a : b);
  const dxNulo = dx.filter(f => cruza(f));
  const PERIODOS = [...new Set(m.zonas_rm.map(f => f.periodo))];
  const zonas = PERIODOS.map(p => m.zonas_rm.filter(f => f.periodo === p)
    .map(f => ({ ...f, nom: f.zona })));
  const zonasUnicas = zonas[0].map(f => ({ zona_id: f.zona_id, zona: f.zona }));
  const zonaPeor = m.cobertura_rm.reduce((a, b) => a.cobertura_pct < b.cobertura_pct ? a : b);
  const nomZona = id => (zonasUnicas.find(z => z.zona_id === id) || {}).zona || id;

  // Origen de cada panel: dos análisis distintos comparten la página y el
  // lector tiene derecho a saber cuál produjo el número que está mirando.
  const DIA = '<span class="origen dia">Modelo diario · case-crossover</span>';

  /* --- Pregunta 1: ¿queda algo al descontar lo demás? --- */
  $("#p-asociacion").innerHTML = `
    <section class="full">
      ${DIA}
      <h3>Qué queda al descontar el frío y los virus</h3>
      <p class="sub">La misma asociación, estimada cuatro veces: sola, y sumando controles uno
        a uno. Cambio porcentual por cada +10 µg/m³.</p>
      ${bosque(ajuste, { w: 700, izq: 210, titulo: "Modelos progresivamente ajustados" })}
      <p class="lee">Sin controles la asociación es ${pct(base.rr10)}. Al sumar temperatura
        casi no se mueve, pero <b>la humedad y sobre todo la circulación viral se llevan
        más de la mitad</b>: el modelo completo queda en ${pct(completo.rr10)}.
        Que baje es lo esperable y es el punto — parte de lo que parecía aire era invierno.
        Que <b>no llegue a cero</b> es lo que sostiene el resto de la página, con la reserva
        del último bloque. Los ${AU.miles(completo.casos)} casos y los
        ${AU.miles(completo.n_dias)} días-ciudad son los mismos en las cuatro filas, así que
        lo único que cambia entre ellas es el ajuste.</p>
    </section>`;

  /* --- Pregunta 2: ¿cuándo ocurre? --- */
  $("#p-cuando").innerHTML = `
    <section class="full">
      ${DIA}
      <h3>Cuánto dura la asociación</h3>
      <p class="sub">Cambio porcentual en las consultas por cada +10 µg/m³, según cuántos
        días antes se midió el aire. Banda = intervalo de 95 %; punto hueco = el intervalo
        contiene el cero.</p>
      ${curva(m.lags, { titulo: "Asociación por día de rezago, 0 a 7 días" })}
      <p class="lee">El máximo está en el <b>mismo día</b> (${pct(lag0.rr10)}) y para los días
        2 y 3 ya cae por debajo del cero, con intervalos que lo cruzan: a esa altura
        <b>no queda nada distinguible</b>. Esa forma —rápida y sin cola— es la que uno
        esperaría de una irritación respiratoria. Hay un segundo repunte en los días 5 y 6
        que sí excluye el cero y que el diseño no explica; abajo se ve que lo aporta
        Santiago, y puede ser el eco de episodios de contaminación que duran varios días
        seguidos más que una respuesta tardía.</p>
    </section>

    <section class="full">
      ${DIA}
      <h3>La misma curva, ciudad por ciudad</h3>
      <p class="sub">Rezagos 0 a 7 días. Escala propia en cada una: lo comparable es la
        forma, no la altura.</p>
      <div class="trio">
        ${["coyhaique", "santiago", "talcahuano"].map(c => `<div>
          <div class="rot">${NOMBRE[c]}</div>
          ${curva(m.lags_ciudad.filter(f => f.ciudad === c),
            { w: 300, h: 150, compacto: true, titulo: `Rezagos en ${NOMBRE[c]}` })}
        </div>`).join("")}
      </div>
      <p class="lee">Talcahuano lo concentra casi todo en los días 0 y 1, y cae de golpe.
        Santiago repite el día 0 y además <b>aporta él solo el repunte de los días 5 y 6</b>
        que aparecía en la curva combinada. Coyhaique es el caso distinto: su día 0 ni
        siquiera se separa del cero y la asociación se reparte a lo largo de la semana,
        coherente con episodios de humo que duran días. Sumando los ocho rezagos, el
        acumulado por ciudad da
        ${acumCiudad.map(f => `<b>${f.nom} ${pct(f.rr10)}</b>`).join(", ")} —
        y el de Talcahuano <b>sí cruza el cero</b>, así que su total no se distingue de la
        ausencia de asociación aunque su día 0 sea el más marcado.</p>
    </section>`;

  /* --- Pregunta 3: ¿dónde? --- */
  $("#p-donde").innerHTML = `
    <section>
      ${DIA}
      <h3>Por ciudad</h3>
      <p class="sub">Asociación del mismo día. Cada ciudad se compara consigo misma.</p>
      ${bosque(porCiudad, { titulo: "Asociación por ciudad" })}
      <p class="lee">Las tres apuntan en la misma dirección y ninguna toca el cero.
        <b>${conMasSenal.nom}</b> muestra la asociación más grande (${pct(conMasSenal.rr10)}).
        Ojo con una lectura tentadora: Coyhaique tiene el intervalo <b>más angosto</b> pese a
        aportar 145.200 consultas contra los 8,2 millones de Santiago. No es que tenga más
        datos, es que su aire <b>varía muchísimo más</b> — de un dígito a más de 150 µg/m³ —
        y cada día contrasta más.</p>
    </section>

    <section>
      ${DIA}
      <h3>Dentro de Santiago</h3>
      <p class="sub">Las seis zonas del Gran Santiago, cada una con sus propias estaciones y
        sus propios establecimientos.</p>
      <div class="conmutador" id="sel-periodo" style="margin-bottom:10px">
        ${PERIODOS.map((p, i) => `<button data-p="${i}" aria-pressed="${i === 0}"
          >${p}</button>`).join("")}
      </div>
      <div id="zonas-svg">${bosque(zonas[0], { titulo: "Asociación por zona de Santiago" })}</div>
      <p class="lee">Santiago no se comporta como un bloque. <b>Oriente y Sur Oriente</b> son
        las únicas dos zonas cuyo intervalo no toca el cero, y lo siguen sin tocarlo al
        estirar la ventana hasta 2026; Occidente apunta en sentido contrario. Conviene no
        leerlo como un mapa de riesgo: <b>no se hizo una prueba formal de interacción entre
        zonas</b>, así que esto describe seis estimaciones, no demuestra que difieran. Y la
        cobertura de medición tampoco es igual en las seis — el último bloque de la página
        muestra cuánto.</p>
    </section>`;

  /* --- Pregunta 4: ¿en quién? --- */
  $("#p-quien").innerHTML = `
    <section>
      ${DIA}
      <h3>Por grupo de edad</h3>
      <p class="sub">Asociación del mismo día, con los mismos ajustes.</p>
      ${bosque(porEdad, { titulo: "Asociación por grupo de edad" })}
      <p class="lee"><b>Ningún intervalo toca el cero</b>, y el orden tiene sentido clínico:
        <b>${masAlto.nom}</b> encabeza con ${pct(masAlto.rr10)} y los escolares de 5–14
        le siguen. Pero conviene no forzar el relato de «los extremos de la vida»: los
        <b>menores de 1 año</b> quedan en ${pct(porEdad.find(f => f.grupo_edad === "<1").rr10)},
        prácticamente empatados con los adultos de ${masBajo.nom.replace(" años", "")}. Que
        el orden salga solo, sin habérselo pedido al modelo, es de las señales más
        tranquilizadoras del conjunto.</p>
    </section>

    <section>
      ${DIA}
      <h3>Por diagnóstico respiratorio</h3>
      <p class="sub">Las seis causas del grupo respiratorio, por separado.</p>
      ${bosque(dx, { izq: 150, titulo: "Asociación por diagnóstico" })}
      <p class="lee"><b>${dxAlto.nom}</b> encabeza con ${pct(dxAlto.rr10)}, seguida de
        neumonía y crisis obstructiva — las tres que más se agravan por vía inflamatoria.
        ${dxNulo.length
          ? `La única que <b>no se distingue del cero</b> es «${dxNulo[0].nom.toLowerCase()}», que es
             justamente el cajón de sastre del grupo.`
          : ""}
        Como en el panel de edad, esto <b>describe</b> seis estimaciones: no hay prueba formal
        de que los diagnósticos difieran entre sí.</p>
    </section>`;

  /* --- Pregunta 5: ¿cuán robusto? --- */
  $("#p-robustez").innerHTML = `
    <section class="full">
      ${DIA}
      <h3>¿Aguanta si se cambia el modelo?</h3>
      <p class="sub">La misma pregunta con otras decisiones de ajuste y otra muestra.</p>
      ${bosque(sens, { w: 700, izq: 230, titulo: "Análisis de sensibilidad" })}
      <p class="lee">Sí. Cambiar la humedad de lineal a spline mueve el resultado en la
        cuarta cifra decimal, y restringir a las mediciones SINCA validadas tampoco lo
        altera. <b>El número no depende de esas decisiones</b>, que es exactamente lo que
        una sensibilidad debe demostrar.</p>
    </section>

    <section class="full">
      ${DIA}
      <h3 class="alerta">Las dos pruebas que no salieron limpias</h3>
      <p class="sub">Un control negativo es un desenlace que el MP2.5 no puede provocar; un
        placebo temporal usa aire del futuro. Los dos deberían dar 0 %.</p>
      <div class="clave">
        <span><i style="background:var(--senal)"></i>debería dar cero y no lo da</span>
        <span><i style="background:var(--s2)"></i>compatible con el cero</span></div>
      ${bosque(controles.concat(placebo.filter(f => f.tipo_placebo.startsWith("Exposición futura ajustada"))),
        { w: 700, izq: 230, titulo: "Controles negativos y placebo temporal" })}
      <p class="lee">Respirar partículas no fractura un hueso ni provoca un choque, así que
        esas dos filas <b>miden nuestro error, no el aire</b>. Y miden
        ${pct(control.rr10)}: <b>más que el ${pct(CONTEMP.rr10)} del desenlace que nos
        interesa</b>. Los días de mucho MP2.5 son días de inversión térmica —fríos, sin
        viento, con neblina—, y ese mismo clima causa caídas y choques por vías que no pasan
        por los pulmones. El aire del día siguiente también conserva algo de señal
        (${pct(placebo.find(f => f.etiqueta.includes("t+1 |")).rr10)}), aunque t+2 y t+3 ya
        no. <b>No podemos separar cuánto del resultado es el aire y cuánto es esa estructura
        compartida.</b> Por eso la página informa una asociación y nunca un efecto.</p>
    </section>

    <section class="full">
      ${DIA}
      <h3>Cuánto aire se midió de verdad</h3>
      <p class="sub">Días del año con dato de MP2.5, por zona de Santiago. En naranja, los
        que no llegan al ${COBERTURA_MINIMA} % que el proyecto exige para promediar.</p>
      ${mapaCobertura(m.cobertura_rm, zonasUnicas)}
      <p class="lee">Casi todo el tablero está completo, y por eso resaltan las excepciones:
        <b>${nomZona(zonaPeor.zona_id)} midió solo ${zonaPeor.dias_con_mp25} de
        ${zonaPeor.dias} días en ${zonaPeor.anio}</b> (${AU.num(zonaPeor.cobertura_pct, 1)} %).
        Una zona que deja de medir justo antes del invierno no aparece como un hueco en el
        gráfico: aparece como un promedio más limpio. Esa es la razón de que la comparación
        territorial de arriba use <b>2018–2024</b> como ventana principal y deje 2025–2026
        como sensibilidad, y no al revés.</p>
    </section>`;

  /* ================= el conmutador de ventana temporal =================
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
      $("#zonas-svg").innerHTML = bosque(zonas[+b.dataset.p],
        { titulo: `Asociación por zona de Santiago, ${PERIODOS[+b.dataset.p]}` });
    });
  }

  _modeloListo();
})();
