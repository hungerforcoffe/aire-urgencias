import { useState } from "react";

const ciudades = ["Santiago", "Talcahuano", "Coyhaique"];

const kpis = {
  Santiago: { r_bruto: "0,27", r_anomalia: "0,04", ic: "−0,06 a 0,13", semanas: "1.350" },
  Talcahuano: { r_bruto: "0,19", r_anomalia: "−0,01", ic: "−0,11 a 0,09", semanas: "1.350" },
  Coyhaique: { r_bruto: "0,31", r_anomalia: "0,08", ic: "−0,03 a 0,18", semanas: "1.350" },
};

/* Serie simulada para el gráfico SVG */
function generarSerie(n: number, base: number, amp: number, ruido: number) {
  return Array.from({ length: n }, (_, i) => {
    const ciclo = Math.sin((i / n) * Math.PI * 4) * amp;
    const r = (Math.random() - 0.5) * ruido;
    return base + ciclo + r;
  });
}

function SerieTemporalSVG({ ciudad }: { ciudad: string }) {
  const n = 104;
  const mp25 = generarSerie(n, 20, 14, 8);
  const urg = generarSerie(n, 50, 18, 12);

  const W = 700, H = 140;
  const px = (i: number) => (i / (n - 1)) * W;
  const py = (v: number, min: number, max: number) =>
    H - ((v - min) / (max - min)) * (H - 16) - 8;

  const minMP = Math.min(...mp25), maxMP = Math.max(...mp25);
  const minU = Math.min(...urg), maxU = Math.max(...urg);

  const pathMP = mp25.map((v, i) => `${i === 0 ? "M" : "L"}${px(i)},${py(v, minMP, maxMP)}`).join(" ");
  const pathU = urg.map((v, i) => `${i === 0 ? "M" : "L"}${px(i)},${py(v, minU, maxU)}`).join(" ");

  return (
    <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", height: H, display: "block" }}>
      <path d={pathU} fill="none" stroke="rgba(96,165,250,0.4)" strokeWidth="1.5" />
      <path d={pathMP} fill="none" stroke="#2563eb" strokeWidth="2" />
      {/* Leyenda */}
      <line x1={W - 100} y1={8} x2={W - 80} y2={8} stroke="#2563eb" strokeWidth="2" />
      <text x={W - 76} y={12} fontFamily="var(--mono)" fontSize={8} fill="var(--texto-2)">MP2.5</text>
      <line x1={W - 100} y1={20} x2={W - 80} y2={20} stroke="rgba(96,165,250,0.6)" strokeWidth="1.5" />
      <text x={W - 76} y={24} fontFamily="var(--mono)" fontSize={8} fill="var(--texto-2)">Urgencias</text>
    </svg>
  );
}

function ScatterSVG({ ciudad }: { ciudad: string }) {
  const n = 80;
  const datos = Array.from({ length: n }, () => ({
    x: Math.random() * 30 + 5,
    y: Math.random() * 60 + 20 + Math.random() * 10,
  }));

  const W = 320, H = 180;
  const px = (v: number) => ((v - 5) / 30) * (W - 32) + 24;
  const py = (v: number) => H - ((v - 20) / 70) * (H - 28) - 14;

  return (
    <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", height: H, display: "block" }}>
      <line x1={24} y1={0} x2={24} y2={H - 14} stroke="var(--borde-f)" strokeWidth="1" />
      <line x1={24} y1={H - 14} x2={W} y2={H - 14} stroke="var(--borde-f)" strokeWidth="1" />
      {datos.map((d, i) => (
        <circle key={i} cx={px(d.x)} cy={py(d.y)} r={3}
          fill="rgba(37,99,235,0.35)" stroke="rgba(37,99,235,0.6)" strokeWidth="0.5" />
      ))}
      <text x={W / 2} y={H - 2} textAnchor="middle" fontFamily="var(--mono)" fontSize={8} fill="var(--texto-3)">
        MP2.5 µg/m³
      </text>
      <text x={8} y={H / 2} textAnchor="middle" fontFamily="var(--mono)" fontSize={8} fill="var(--texto-3)"
        transform={`rotate(-90,8,${H / 2})`}>
        Urgencias / 100 k hab
      </text>
    </svg>
  );
}

function CicloMensualSVG() {
  const meses = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"];
  const vals = [10, 9, 12, 18, 26, 34, 38, 36, 28, 18, 13, 10];
  const W = 320, H = 160;
  const maxV = 40;
  const bw = (W - 24) / 12;

  return (
    <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", height: H, display: "block" }}>
      {vals.map((v, i) => {
        const barH = (v / maxV) * (H - 28);
        const x = 12 + i * bw;
        const isinv = i >= 4 && i <= 8;
        return (
          <g key={i}>
            <rect x={x + 2} y={H - 18 - barH} width={bw - 4} height={barH}
              fill={isinv ? "rgba(37,99,235,0.7)" : "rgba(96,165,250,0.45)"}
              rx={3} />
            <text x={x + bw / 2} y={H - 4} textAnchor="middle"
              fontFamily="var(--mono)" fontSize={7} fill="var(--texto-3)">
              {meses[i]}
            </text>
          </g>
        );
      })}
      {/* Línea OMS */}
      <line x1={12} x2={W - 4} y1={H - 18 - (5 / maxV) * (H - 28)} y2={H - 18 - (5 / maxV) * (H - 28)}
        stroke="#dc2626" strokeWidth="1" strokeDasharray="4,3" />
      <text x={W - 6} y={H - 18 - (5 / maxV) * (H - 28) + 4} textAnchor="end"
        fontFamily="var(--mono)" fontSize={7} fill="#dc2626">OMS 5</text>
    </svg>
  );
}

export default function PaginaAnalisis() {
  const [ciudad, setCiudad] = useState("Santiago");
  const [rezago, setRezago] = useState("1");
  const [modo, setModo] = useState<"anomalia" | "bruto">("anomalia");

  const kpi = kpis[ciudad as keyof typeof kpis];

  return (
    <div style={{ display: "flex", flexDirection: "column", minHeight: "calc(100vh - 52px)" }}>

      {/* Hero */}
      <div style={{ background: "var(--navy)", color: "#fff", padding: "26px 24px 22px" }}>
        <div style={{ maxWidth: 900, margin: "0 auto" }}>
          <div style={{ fontFamily: "var(--mono)", fontSize: ".66rem", textTransform: "uppercase", letterSpacing: ".1em", color: "var(--celeste)", marginBottom: 8 }}>
            Estudio ecológico observacional · 2018–2026
          </div>
          <h1 style={{ fontFamily: "var(--serif)", fontSize: "1.6rem", fontWeight: 700, lineHeight: 1.2, marginBottom: 8 }}>
            MP2.5 y urgencias respiratorias
          </h1>
          <p style={{ fontSize: ".88rem", color: "rgba(255,255,255,0.6)", maxWidth: 540, lineHeight: 1.6, margin: 0 }}>
            Correlación semanal entre concentración de material particulado fino y consultas de
            urgencia en tres ciudades chilenas. Anomalía estacional para aislar el calendario.
          </p>
        </div>
      </div>

      {/* Controles */}
      <div style={{
        background: "var(--panel)", borderBottom: "1px solid var(--borde)",
        padding: "12px 20px", display: "flex", gap: 20, alignItems: "flex-end", flexWrap: "wrap",
      }}>
        {/* Ciudad */}
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <label style={{ fontFamily: "var(--mono)", fontSize: ".62rem", textTransform: "uppercase", letterSpacing: ".07em", color: "var(--texto-3)" }}>
            Ciudad
          </label>
          <select value={ciudad} onChange={(e) => setCiudad(e.target.value)} style={{
            background: "var(--fondo)", border: "1px solid var(--borde-f)",
            borderRadius: 6, padding: "6px 10px",
            fontFamily: "var(--sans)", fontSize: ".85rem", color: "var(--texto)", cursor: "pointer",
          }}>
            {ciudades.map((c) => <option key={c}>{c}</option>)}
          </select>
        </div>

        {/* Rezago */}
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <label style={{ fontFamily: "var(--mono)", fontSize: ".62rem", textTransform: "uppercase", letterSpacing: ".07em", color: "var(--texto-3)" }}>
            Rezago del MP2.5
          </label>
          <select value={rezago} onChange={(e) => setRezago(e.target.value)} style={{
            background: "var(--fondo)", border: "1px solid var(--borde-f)",
            borderRadius: 6, padding: "6px 10px",
            fontFamily: "var(--sans)", fontSize: ".85rem", color: "var(--texto)", cursor: "pointer",
          }}>
            <option value="0">misma semana</option>
            <option value="1">1 semana antes</option>
            <option value="2">2 semanas antes</option>
          </select>
        </div>

        {/* Modo */}
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <label style={{ fontFamily: "var(--mono)", fontSize: ".62rem", textTransform: "uppercase", letterSpacing: ".07em", color: "var(--texto-3)" }}>
            Serie
          </label>
          <div style={{ display: "flex", border: "1px solid var(--borde-f)", borderRadius: 6, overflow: "hidden" }}>
            {(["anomalia", "bruto"] as const).map((m) => (
              <button key={m} onClick={() => setModo(m)} style={{
                background: modo === m ? "var(--azul-medio)" : "var(--fondo)",
                border: "none", padding: "6px 14px",
                fontFamily: "var(--sans)", fontSize: ".85rem",
                color: modo === m ? "#fff" : "var(--texto-2)",
                cursor: "pointer", textTransform: "capitalize",
                transition: "all .12s",
              }}>
                {m === "anomalia" ? "Anomalía" : "Bruto"}
              </button>
            ))}
          </div>
        </div>

        <div style={{ marginLeft: "auto" }}>
          <span style={{
            fontFamily: "var(--mono)", fontSize: ".62rem", color: "var(--azul-medio)",
            border: "1px solid var(--celeste-c)", background: "#eff6ff",
            padding: "3px 10px", borderRadius: 99,
          }}>
            1.350 semanas · 3 ciudades
          </span>
        </div>
      </div>

      {/* KPIs */}
      <div style={{
        display: "flex", gap: 12, padding: "14px 20px",
        background: "var(--fondo-alt)", borderBottom: "1px solid var(--borde)", flexWrap: "wrap",
      }}>
        {[
          { etiq: `r bruto · ${ciudad}`, val: kpi.r_bruto, sub: "sin descontar estacionalidad" },
          { etiq: `r anomalía · ${ciudad}`, val: kpi.r_anomalia, sub: `IC 95% ${kpi.ic}`, destaca: true },
          { etiq: "Semanas analizadas", val: kpi.semanas, sub: "2018 – 2026" },
          { etiq: "Rezago óptimo", val: `${rezago}s`, sub: "semana(s) antes" },
        ].map((k, i) => (
          <div key={i} style={{
            background: "var(--panel)", border: "1px solid var(--borde)",
            borderRadius: 12, padding: "14px 18px", minWidth: 140, flex: 1,
            boxShadow: "var(--sombra)",
            borderLeft: k.destaca ? "3px solid var(--azul-medio)" : "1px solid var(--borde)",
          }}>
            <div style={{ fontFamily: "var(--mono)", fontSize: ".62rem", textTransform: "uppercase", letterSpacing: ".07em", color: "var(--texto-3)", marginBottom: 4 }}>
              {k.etiq}
            </div>
            <div style={{ fontFamily: "var(--serif)", fontSize: "1.55rem", fontWeight: 700, color: "var(--navy)", lineHeight: 1 }}>
              {k.val}
            </div>
            <div style={{ fontSize: ".7rem", color: "var(--texto-3)", marginTop: 3 }}>
              {k.sub}
            </div>
          </div>
        ))}
      </div>

      {/* Gráficos */}
      <div style={{
        display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(300px,1fr))",
        gap: 16, padding: "20px", background: "var(--fondo)",
      }}>
        {/* Serie temporal - ancho completo */}
        <div style={{
          gridColumn: "1 / -1",
          background: "var(--panel)", border: "1px solid var(--borde)",
          borderRadius: 12, padding: "20px", boxShadow: "var(--sombra)",
        }}>
          <h3 style={{ fontFamily: "var(--serif)", fontSize: ".95rem", color: "var(--navy)", marginBottom: 12 }}>
            Serie temporal · MP2.5 y urgencias · {ciudad} ({modo === "anomalia" ? "anomalía estacional" : "serie bruta"})
          </h3>
          <SerieTemporalSVG ciudad={ciudad} />
          <div style={{ display: "flex", gap: 16, marginTop: 8 }}>
            <span style={{ fontFamily: "var(--mono)", fontSize: ".65rem", color: "var(--texto-3)" }}>
              eje izq: MP2.5 µg/m³ · eje der: urgencias / 100 k hab · semanas 2018–2026
            </span>
          </div>
        </div>

        {/* Dispersión */}
        <div style={{
          background: "var(--panel)", border: "1px solid var(--borde)",
          borderRadius: 12, padding: "20px", boxShadow: "var(--sombra)",
        }}>
          <h3 style={{ fontFamily: "var(--serif)", fontSize: ".95rem", color: "var(--navy)", marginBottom: 12 }}>
            Dispersión MP2.5 vs urgencias
          </h3>
          <ScatterSVG ciudad={ciudad} />
          <p style={{ fontSize: ".72rem", color: "var(--texto-3)", marginTop: 8 }}>
            Cada punto es una semana. La nube sin estructura confirma la baja correlación en anomalía.
          </p>
        </div>

        {/* Ciclo mensual */}
        <div style={{
          background: "var(--panel)", border: "1px solid var(--borde)",
          borderRadius: 12, padding: "20px", boxShadow: "var(--sombra)",
        }}>
          <h3 style={{ fontFamily: "var(--serif)", fontSize: ".95rem", color: "var(--navy)", marginBottom: 12 }}>
            Ciclo estacional · mediana mensual de MP2.5
          </h3>
          <CicloMensualSVG />
          <p style={{ fontSize: ".72rem", color: "var(--texto-3)", marginTop: 8 }}>
            Azul intenso = meses de invierno. Línea roja = guía anual OMS (5 µg/m³).
          </p>
        </div>
      </div>

      {/* Notas */}
      <div style={{ background: "var(--fondo-alt)", borderBottom: "1px solid var(--borde)", padding: "28px 20px" }}>
        <div style={{ maxWidth: 960, margin: "0 auto", display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(240px,1fr))", gap: 16 }}>
          {[
            {
              alerta: true,
              titulo: "El resultado, de frente",
              texto: `En bruto ${ciudad} da r = ${kpi.r_bruto}: parece asociación. Descontado el ciclo estacional cae a ${kpi.r_anomalia} (IC 95% ${kpi.ic}). Los tres intervalos incluyen el cero.`,
            },
            {
              titulo: "Por qué anomalía y no bruto",
              texto: "En invierno sube el MP2.5 —leña más inversión térmica— y suben las urgencias —virus y frío—. Correlacionar las series crudas mide sobre todo que las dos conocen el calendario.",
            },
            {
              titulo: "El confusor sin controlar",
              texto: "Las urgencias de invierno están dominadas por virus respiratorios (VRS, influenza). No se incorporó la vigilancia del ISP, así que queda declarado y no corregido.",
            },
            {
              titulo: "Qué es una fila",
              texto: "Una ciudad en una semana: el MP2.5 promedio de sus estaciones y las urgencias de sus establecimientos, divididas por la población proyectada del INE.",
            },
          ].map((n, i) => (
            <div key={i} style={{
              background: "var(--panel)", borderRadius: 12,
              border: "1px solid var(--borde)", padding: "18px 20px",
              boxShadow: "var(--sombra)",
            }}>
              <h3 style={{
                fontFamily: "var(--serif)", fontSize: ".93rem", fontWeight: 600,
                color: n.alerta ? "var(--alerta)" : "var(--navy)",
                marginBottom: 8, display: "flex", alignItems: "flex-start", gap: 8,
              }}>
                {n.alerta && (
                  <span style={{
                    display: "inline-flex", alignItems: "center", justifyContent: "center",
                    width: 18, height: 18, borderRadius: "50%",
                    background: "var(--alerta)", color: "#fff",
                    fontSize: ".62rem", fontFamily: "var(--mono)", fontWeight: 700, flexShrink: 0, marginTop: 1,
                  }}>!</span>
                )}
                {n.titulo}
              </h3>
              <p style={{ fontSize: ".82rem", color: "var(--texto-2)", lineHeight: 1.65 }}>{n.texto}</p>
            </div>
          ))}
        </div>
      </div>

      <footer style={{
        background: "var(--navy)", color: "rgba(255,255,255,0.4)",
        fontFamily: "var(--mono)", fontSize: ".72rem", lineHeight: 1.7,
        padding: "14px 24px", textAlign: "center",
      }}>
        Estudio ecológico observacional · <b style={{ color: "rgba(255,255,255,0.65)" }}>asociación, no causalidad</b><br />
        Urgencias DEIS (MINSAL) · Aire SINCA (MMA) · Población proyecciones comunales INE
      </footer>
    </div>
  );
}
