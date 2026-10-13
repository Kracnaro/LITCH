"""
orbe.py — Orbe HD v3 de Litch con pulso de habla tipo IA.

Mejoras v3:
- Canvas 170×170, 30 fps
- 12 meridianos suavizados, 80 puntos por órbita
- Glow multicapa (radial gradient aproximado)
- Pulso de habla: anillos que se expanden y desvanecen (estilo Alexa / Jarvis)
- Modo Rostro: cara estilizada holográfica con labios animados
- Líneas con smooth=True para bordes antialiasing
"""
import math
import tkinter as tk

# ── Paleta de color ────────────────────────────────────────────────────────────
C_BG     = "#050d15"       # fondo del canvas (ligeramente distinto al panel)
C_GLOW0  = "#071a0e"       # primer glow radial (más oscuro)
C_GLOW1  = "#0b2a18"       # segundo glow
C_DIM    = "#0a4522"       # meridianos traseros
C_MED    = "#1a9a52"       # meridianos medios
C_BRIGHT = "#22ee7a"       # meridianos frontales / paralelos
C_NEON   = "#4dffc0"       # núcleo central
C_ELEC1  = "#7dffc0"
C_ELEC2  = "#5dffb0"
C_ELEC3  = "#9dffd0"

# ── Paleta cara holográfica (azul cian) ───────────────────────────────────────
CF_BG    = "#020a14"
CF_GLOW0 = "#040e22"
CF_GLOW1 = "#071830"
CF_DIM   = "#0a2a5a"
CF_MED   = "#0a4acc"
CF_EDGE  = "#1560e0"
CF_BRITE = "#28a0ff"
CF_NEON  = "#55d0ff"
CF_WHITE = "#b8eeff"

N_MERIDIANOS = 12
N_PASOS      = 80   # pasos por órbita de electrón (suavidad)
VELOCIDAD    = 30   # intervalo en ms ≈ 33 fps


class Orbe:
    def __init__(self, parent, tam: int = 160, bg: str = "#0a1420"):
        self.tam  = tam
        self.cx   = self.cy = tam / 2
        self.R    = tam * 0.33
        self._bg  = bg          # color de ventana (esquinas del canvas = invisibles)

        # bg=bg → el canvas tiene el mismo color que la ventana,
        # así sus 4 esquinas son imperceptibles y el globo parece circular.
        self.canvas = tk.Canvas(parent, width=tam, height=tam,
                                bg=bg, highlightthickness=0)
        self.t         = 0.0
        self.hablando  = False
        self.escuchando = False
        self._nivel    = 0.0    # suavizado 0–1
        self._modo_rostro = False   # False = globo, True = cara

        # Pulsos de habla (cada elemento = fase 0.0→1.0)
        self._pulsos: list[float] = []
        self._t_pulso = 0        # contador de frames para spawning

        # Electrones (radio_orbital, inclinación°, velocidad, fase_rad, color)
        self.electrones = [
            (1.05,  25,  1.7,  0.0,  C_ELEC1),
            (1.05, -40, -1.3,  2.1,  C_ELEC2),
            (0.98,  80,  1.1,  4.0,  C_ELEC3),
        ]

        # Estado de labios para modo rostro
        self._boca_open = 0.0   # 0=cerrada, 1=abierta

        self._animar()

    # ── API pública ───────────────────────────────────────────────────────────

    def widget(self) -> tk.Canvas:
        return self.canvas

    def set_hablando(self, v: bool) -> None:
        self.hablando = bool(v)

    def set_escuchando(self, v: bool) -> None:
        self.escuchando = bool(v)

    def set_modo_rostro(self, v: bool) -> None:
        self._modo_rostro = bool(v)

    # ── Animación ─────────────────────────────────────────────────────────────

    def _animar(self) -> None:
        try:
            self._dibujar()
        except Exception:
            pass
        try:
            self.canvas.after(VELOCIDAD, self._animar)
        except Exception:
            pass

    def _dibujar(self) -> None:
        c = self.canvas
        c.delete("all")
        self.t += 0.040

        # Nivel de actividad suavizado
        objetivo   = 1.0 if (self.hablando or self.escuchando) else 0.0
        self._nivel += (objetivo - self._nivel) * 0.15
        brillo     = self._nivel

        if self._modo_rostro:
            self._dibujar_rostro(c, brillo)
        else:
            self._dibujar_globo(c, brillo)

    # ═══════════════════════════════════════════════════════════════════════════
    # GLOBO
    # ═══════════════════════════════════════════════════════════════════════════

    def _dibujar_globo(self, c: tk.Canvas, brillo: float) -> None:
        R  = self.R * (1.0 + 0.055 * brillo * math.sin(self.t * 7))
        cx, cy = self.cx, self.cy
        m  = 1   # margen interior (px)

        # ── BASE CIRCULAR: rellena todo el área visible del canvas con un
        #    círculo oscuro. Las esquinas del canvas quedan con el color de
        #    la ventana (self._bg), por lo que el globo aparece perfectamente
        #    redondo sin bordes cuadrados. ──────────────────────────────────
        c.create_oval(m, m, self.tam - m, self.tam - m,
                      fill=C_BG, outline="#122a1a", width=2)

        # ── Glow radial (capas rellenas, de exterior a interior) ──────────────
        for k, (factor, col) in enumerate([
            (1.70, C_GLOW0),
            (1.40, C_GLOW1),
            (1.15, "#0f3520"),
        ]):
            r = R * factor
            c.create_oval(cx - r, cy - r, cx + r, cy + r,
                          fill=col, outline="")

        # ── Pulsos de habla ───────────────────────────────────────────────────
        self._actualizar_pulsos(c, R, cx, cy, brillo)

        # ── Halos exteriores delgados ──────────────────────────────────────────
        for k in (1.28, 1.14):
            col = C_MED if brillo > 0.3 else C_DIM
            c.create_oval(cx - R*k, cy - R*k, cx + R*k, cy + R*k,
                          outline=col, width=1)

        # ── Paralelos (fijos, perspectiva 0.27) ───────────────────────────────
        for frac, col_par in [(0.26, C_BRIGHT), (0.52, C_MED),
                               (0.76, C_DIM),   (0.95, C_DIM)]:
            ry    = R * frac
            rx    = R * math.sqrt(max(1e-9, 1.0 - frac**2))
            ryvis = ry * 0.27
            col_p = self._lerp(col_par, C_DIM, 1.0 - brillo * 0.5) if frac > 0.5 else col_par
            if rx > 2:
                c.create_oval(cx - rx, cy - ry - ryvis,
                              cx + rx, cy - ry + ryvis,
                              outline=col_p, width=1)
                c.create_oval(cx - rx, cy + ry - ryvis,
                              cx + rx, cy + ry + ryvis,
                              outline=col_p, width=1)

        # Ecuador
        c.create_oval(cx - R, cy - R*0.22, cx + R, cy + R*0.22,
                      outline=C_BRIGHT, width=2 if brillo > 0.4 else 1)

        # ── Meridianos rotantes ────────────────────────────────────────────────
        vel_rot = 0.36 + brillo * 0.16
        rot     = self.t * vel_rot
        for i in range(N_MERIDIANOS):
            lon  = rot + math.pi * i / N_MERIDIANOS
            cosv = abs(math.cos(lon))
            rx_m = cosv * R
            if rx_m < 2:
                continue
            if   cosv > 0.70: col_m, w_m = C_BRIGHT, (2 if brillo > 0.3 else 1)
            elif cosv > 0.35: col_m, w_m = C_MED, 1
            else:             col_m, w_m = C_DIM, 1
            c.create_oval(cx - rx_m, cy - R, cx + rx_m, cy + R,
                          outline=col_m, width=w_m)

        # Esfera exterior y ejes
        c.create_oval(cx - R, cy - R, cx + R, cy + R,
                      outline=C_BRIGHT, width=2)
        c.create_line(cx - R, cy, cx + R, cy, fill=C_BRIGHT, width=1)
        c.create_line(cx, cy - R, cx, cy + R, fill=C_MED, width=1)

        # ── Núcleo pulsante ────────────────────────────────────────────────────
        nr = 5.5 + 3.5 * brillo + 2.0 * math.sin(self.t * 5.5)
        # Halo del núcleo (3 capas)
        for fac, col_n in [(3.5, "#1a3a28"), (2.5, "#1de57a44"[:7]), (1.0, C_NEON)]:
            r_n = nr * fac
            nc  = C_NEON if fac == 1.0 else (C_MED if fac == 2.5 else "#0a2a18")
            if fac == 1.0:
                c.create_oval(cx - r_n, cy - r_n, cx + r_n, cy + r_n,
                              fill=C_NEON, outline="")
            else:
                c.create_oval(cx - r_n, cy - r_n, cx + r_n, cy + r_n,
                              outline=nc, width=1)
        c.create_oval(cx - nr*2.5, cy - nr*2.5, cx + nr*2.5, cy + nr*2.5,
                      outline=C_NEON, width=1)

        # Destellos cruzados al hablar
        if brillo > 0.25:
            lg = nr * (2.8 + brillo * 0.8)
            c.create_line(cx - lg, cy, cx + lg, cy, fill=C_NEON, width=1)
            c.create_line(cx, cy - lg, cx, cy + lg, fill=C_NEON, width=1)

        # ── Electrones ────────────────────────────────────────────────────────
        for radio, incl, vel, fase, color in self.electrones:
            ang   = math.radians(incl)
            a_orb = R * radio
            b_orb = R * (0.28 + 0.13 * brillo)
            # Órbita (suave, 80 pasos)
            self._orbita(c, cx, cy, a_orb, b_orb, ang,
                         C_BRIGHT if brillo > 0.2 else C_MED)
            # Electrón
            theta = self.t * vel + fase
            ox    = a_orb * math.cos(theta)
            oy    = b_orb * math.sin(theta)
            px    = cx + ox * math.cos(ang) - oy * math.sin(ang)
            py    = cy + ox * math.sin(ang) + oy * math.cos(ang)
            er    = 3.5 + 1.8 * brillo
            # Halo del electrón
            c.create_oval(px - er*2.8, py - er*2.8, px + er*2.8, py + er*2.8,
                          outline=self._lerp(color, C_BG, 0.6), width=1)
            c.create_oval(px - er*1.7, py - er*1.7, px + er*1.7, py + er*1.7,
                          outline=self._lerp(color, C_BG, 0.3), width=1)
            c.create_oval(px - er, py - er, px + er, py + er,
                          fill=color, outline="")

    # ── Pulsos de habla ───────────────────────────────────────────────────────

    def _actualizar_pulsos(self, c: tk.Canvas, R: float,
                            cx: float, cy: float, brillo: float) -> None:
        # Spawn nuevo pulso cada ~12 frames cuando está hablando o escuchando
        if self.hablando or self.escuchando:
            self._t_pulso += 1
            if self._t_pulso >= 12 and len(self._pulsos) < 5:
                self._pulsos.append(0.0)
                self._t_pulso = 0
        else:
            self._t_pulso = 10  # listo para disparar al instante cuando empiece

        # Dibujar y avanzar cada pulso
        nuevos: list[float] = []
        for fase in self._pulsos:
            radio_p = R * (1.06 + fase * 1.0)
            col_p   = self._lerp(C_BRIGHT, C_BG, fase)
            w_p     = max(1, int(3 * (1.0 - fase)))
            c.create_oval(cx - radio_p, cy - radio_p,
                          cx + radio_p, cy + radio_p,
                          outline=col_p, width=w_p)
            siguiente = fase + 0.045
            if siguiente < 1.0:
                nuevos.append(siguiente)
        self._pulsos = nuevos

    # ═══════════════════════════════════════════════════════════════════════════
    # MODO ROSTRO — cara holográfica estilizada
    # ═══════════════════════════════════════════════════════════════════════════

    def _dibujar_rostro(self, c: tk.Canvas, brillo: float) -> None:
        """
        Rostro holográfico tipo constelación/wireframe azul — low-poly triangulado
        con nodos pulsantes, iris animado, scan line y brackets de reconocimiento.
        """
        cx, cy = self.cx, self.cy
        Rf     = self.R * 0.88
        t      = self.t
        m      = 1

        # ── BASE CIRCULAR ──────────────────────────────────────────────────────
        c.create_oval(m, m, self.tam - m, self.tam - m,
                      fill=CF_BG, outline="#0a1a30", width=2)

        # ── GLOW radial azul ───────────────────────────────────────────────────
        for fac, col in [(1.52, CF_GLOW0), (1.22, CF_GLOW1), (0.90, "#071428")]:
            r = Rf * fac
            c.create_oval(cx-r, cy-r, cx+r, cy+r, fill=col, outline="")

        # ── PULSOS de habla en azul ────────────────────────────────────────────
        if self.hablando or self.escuchando:
            self._t_pulso += 1
            if self._t_pulso >= 12 and len(self._pulsos) < 5:
                self._pulsos.append(0.0)
                self._t_pulso = 0
        else:
            self._t_pulso = 10
        nuevos: list[float] = []
        for fase in self._pulsos:
            rp = Rf * (1.10 + fase * 0.95)
            cp = self._lerp(CF_NEON, CF_BG, fase)
            wp = max(1, int(3 * (1.0 - fase)))
            c.create_oval(cx-rp, cy-rp, cx+rp, cy+rp, outline=cp, width=wp)
            sig = fase + 0.045
            if sig < 1.0:
                nuevos.append(sig)
        self._pulsos = nuevos

        # ── Boca: calcular apertura ────────────────────────────────────────────
        obj_boca = 1.0 if self.hablando else 0.0
        self._boca_open += (obj_boca - self._boca_open) * 0.18
        bo = self._boca_open

        # ── NODOS (coordenadas normalizadas → canvas) ──────────────────────────
        def N(x, y):
            return (cx + x * Rf, cy + y * Rf)

        nd = {
            # Contorno del cráneo
            'crown':  N(0,     -0.98),
            'fh_l':   N(-0.30, -0.78),  'fh_r':   N(0.30, -0.78),
            'tmp_l':  N(-0.75, -0.38),  'tmp_r':  N(0.75, -0.38),
            'chk_l':  N(-0.88,  0.10),  'chk_r':  N(0.88,  0.10),
            'jaw_l':  N(-0.60,  0.56),  'jaw_r':  N(0.60,  0.56),
            'uch_l':  N(-0.24,  0.78),  'uch_r':  N(0.24,  0.78),
            'chin':   N(0,      0.92),
            # Cejas
            'bro_lo': N(-0.58, -0.32),  'bro_ro': N(0.58, -0.32),
            'bro_lm': N(-0.32, -0.27),  'bro_rm': N(0.32, -0.27),
            'bro_li': N(-0.12, -0.25),  'bro_ri': N(0.12, -0.25),
            # Esquinas de ojos
            'elo':    N(-0.52, -0.17),  'elc':    N(-0.18, -0.14),
            'ero':    N(0.52,  -0.17),  'erc':    N(0.18,  -0.14),
            # Centros de ojos (solo para dibujar iris)
            'elx':    N(-0.35, -0.155), 'erx':   N(0.35,  -0.155),
            # Nariz
            'nb_t':   N(0,     -0.20),
            'ns_l':   N(-0.14,  0.22),  'ns_r':  N(0.14,  0.22),
            'ns_c':   N(0,      0.28),
            # Boca
            'ml':     N(-0.28,  0.45),  'mr':    N(0.28,  0.45),
            'mt':     N(0,      0.41),
            'mb':     N(0,      0.41 + bo * 0.18),
            # Mentón inferior
            'mn_l':   N(-0.13,  0.68),  'mn_r':  N(0.13,  0.68),
        }

        # ── TRIÁNGULOS low-poly (relleno oscuro azulado, dibujado primero) ─────
        tris = [
            ('crown', 'fh_l',   'fh_r',   "#060d1c"),
            ('fh_l',  'tmp_l',  'bro_lo', "#050f1e"),
            ('fh_r',  'tmp_r',  'bro_ro', "#050f1e"),
            ('fh_l',  'fh_r',   'bro_lm', "#071120"),
            ('tmp_l', 'chk_l',  'bro_lo', "#060e1d"),
            ('tmp_r', 'chk_r',  'bro_ro', "#060e1d"),
            ('bro_lo','elo',    'tmp_l',  "#040c1a"),
            ('bro_ro','ero',    'tmp_r',  "#040c1a"),
            ('bro_lo','bro_lm', 'elo',    "#040c1a"),
            ('bro_ro','bro_rm', 'ero',    "#040c1a"),
            ('chk_l', 'jaw_l',  'ml',     "#050d1a"),
            ('chk_r', 'jaw_r',  'mr',     "#050d1a"),
            ('jaw_l', 'uch_l',  'mn_l',   "#040c18"),
            ('jaw_r', 'uch_r',  'mn_r',   "#040c18"),
            ('uch_l', 'mn_l',   'chin',   "#030a14"),
            ('uch_r', 'mn_r',   'chin',   "#030a14"),
        ]
        for na, nb, nk, fcol in tris:
            if na in nd and nb in nd and nk in nd:
                ax, ay = nd[na]
                bx, by = nd[nb]
                kx, ky = nd[nk]
                c.create_polygon([ax, ay, bx, by, kx, ky], fill=fcol, outline="")

        # ── ARISTAS wireframe (constelación) ───────────────────────────────────
        col_e = self._lerp(CF_EDGE, CF_BRITE, brillo * 0.5)
        edges = [
            # Cráneo exterior
            ('crown','fh_l'), ('crown','fh_r'),
            ('fh_l','tmp_l'), ('fh_r','tmp_r'),
            ('tmp_l','chk_l'), ('tmp_r','chk_r'),
            ('chk_l','jaw_l'), ('chk_r','jaw_r'),
            ('jaw_l','uch_l'), ('jaw_r','uch_r'),
            ('uch_l','chin'), ('uch_r','chin'),
            ('jaw_l','mn_l'), ('jaw_r','mn_r'),
            ('mn_l','chin'), ('mn_r','chin'),
            # Frente
            ('fh_l','fh_r'),
            # Cejas
            ('bro_lo','bro_lm'), ('bro_lm','bro_li'),
            ('bro_ro','bro_rm'), ('bro_rm','bro_ri'),
            ('tmp_l','bro_lo'), ('tmp_r','bro_ro'),
            ('fh_l','bro_lo'),  ('fh_r','bro_ro'),
            ('fh_l','bro_lm'),  ('fh_r','bro_rm'),
            # Ceja → esquina ojo
            ('bro_lo','elo'), ('bro_li','elc'),
            ('bro_ro','ero'), ('bro_ri','erc'),
            # Borde horizontal del ojo
            ('elo','elc'), ('ero','erc'),
            # Puente nariz
            ('bro_li','nb_t'), ('bro_ri','nb_t'),
            # Nariz
            ('nb_t','ns_l'), ('nb_t','ns_r'),
            ('ns_l','ns_c'), ('ns_r','ns_c'),
            # Ojo → nariz
            ('elc','nb_t'), ('erc','nb_t'),
            # Mejilla → nariz y boca
            ('chk_l','ns_l'), ('chk_r','ns_r'),
            ('chk_l','ml'),   ('chk_r','mr'),
            ('jaw_l','ml'),   ('jaw_r','mr'),
            ('ns_l','ml'),    ('ns_r','mr'),
            # Boca
            ('ml','mt'), ('mr','mt'),
            ('ml','mb'), ('mr','mb'),
        ]
        for na, nb in edges:
            if na in nd and nb in nd:
                ax, ay = nd[na]
                bx, by = nd[nb]
                c.create_line(ax, ay, bx, by, fill=col_e, width=1)

        # ── OJOS (especiales, sobre el wireframe) ─────────────────────────────
        eye_rx = Rf * 0.168
        eye_ry = Rf * 0.088
        for key in ('elx', 'erx'):
            ex, ey = nd[key]
            # Halo exterior
            c.create_oval(ex-eye_rx*1.9, ey-eye_ry*1.9,
                          ex+eye_rx*1.9, ey+eye_ry*1.9,
                          outline=self._lerp(CF_NEON, CF_BG, 0.50), width=1)
            # Esclerótica
            c.create_oval(ex-eye_rx, ey-eye_ry,
                          ex+eye_rx, ey+eye_ry,
                          fill=CF_GLOW1, outline=CF_BRITE, width=1)
            # Iris pulsante
            iris_r = eye_ry * (0.72 + 0.22 * brillo * math.sin(t * 3.8))
            c.create_oval(ex-iris_r, ey-iris_r,
                          ex+iris_r, ey+iris_r,
                          fill=CF_NEON, outline="")
            # Pupila
            pupil = iris_r * 0.42
            c.create_oval(ex-pupil, ey-pupil, ex+pupil, ey+pupil,
                          fill="#010810", outline="")
            # Reflejo (punto blanco)
            c.create_oval(ex-iris_r*0.30, ey-iris_r*0.42,
                          ex+iris_r*0.30, ey+iris_r*0.42,
                          fill=CF_WHITE, outline="")

        # ── BOCA animada ──────────────────────────────────────────────────────
        mlx, mly = nd['ml']
        mrx, mry = nd['mr']
        mtx, mty = nd['mt']
        mbx, mby = nd['mb']
        if bo > 0.03:
            c.create_polygon([mlx, mly, mtx, mty, mrx, mry, mbx, mby],
                             fill="#020812", outline="")
            c.create_line(mlx, mly, mtx, mty, mrx, mry,
                          fill=CF_NEON, width=2, smooth=True)
            c.create_line(mlx, mly, mbx, mby, mrx, mry,
                          fill=CF_BRITE, width=2, smooth=True)
            if bo > 0.40:
                ty = mty + (mby - mty) * 0.38
                c.create_rectangle(mlx + (mrx-mlx)*0.18, ty-2,
                                   mrx - (mrx-mlx)*0.18, ty,
                                   fill=CF_WHITE, outline="")
        else:
            c.create_line(mlx, mly, mtx, mty, mrx, mry,
                          fill=CF_BRITE, width=2, smooth=True)

        # ── NODOS brillantes en landmarks clave ───────────────────────────────
        bright_nd = {'crown', 'tmp_l', 'tmp_r', 'chk_l', 'chk_r',
                     'chin', 'bro_lo', 'bro_ro', 'ns_c', 'ml', 'mr'}
        skip_nd   = {'elx', 'erx', 'mt', 'mb', 'nb_t'}
        for key, (nx, ny) in nd.items():
            if key in skip_nd:
                continue
            if key in bright_nd:
                phase = sum(ord(ch) for ch in key) % 7
                pulse = 0.5 + 0.5 * math.sin(t * 2.2 + phase)
                rg = 3.5 + 1.5 * pulse
                c.create_oval(nx-rg*2.2, ny-rg*2.2, nx+rg*2.2, ny+rg*2.2,
                              outline=self._lerp(CF_NEON, CF_BG, 0.58), width=1)
                c.create_oval(nx-rg, ny-rg, nx+rg, ny+rg,
                              fill=CF_NEON, outline="")
            else:
                c.create_oval(nx-2, ny-2, nx+2, ny+2,
                              fill=CF_BRITE, outline="")

        # ── SCAN LINE (efecto holograma que barre la cara) ─────────────────────
        sc_t   = (t * 0.15) % 1.0
        sc_y   = cy - Rf + sc_t * Rf * 2.0
        sc_a   = 1.0 - abs(sc_t - 0.5) * 2.2
        col_sc = self._lerp(CF_NEON, CF_BG, max(0.0, 1.0 - sc_a * 0.55))
        c.create_line(cx - Rf*0.95, sc_y, cx + Rf*0.95, sc_y,
                      fill=col_sc, width=1)

        # ── ANILLO exterior + BRACKETS de escáner facial ───────────────────────
        c.create_oval(cx-Rf*1.06, cy-Rf*1.06, cx+Rf*1.06, cy+Rf*1.06,
                      outline=CF_DIM, width=1)
        br_len = Rf * 0.22
        for bsx, bsy in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
            bx = cx + bsx * Rf * 0.88
            by = cy + bsy * Rf * 0.88
            c.create_line(bx, by, bx + bsx*br_len, by,
                          fill=CF_WHITE, width=2)
            c.create_line(bx, by, bx, by + bsy*br_len,
                          fill=CF_WHITE, width=2)

    # ═══════════════════════════════════════════════════════════════════════════
    # Helpers
    # ═══════════════════════════════════════════════════════════════════════════

    @staticmethod
    def _lerp(hex1: str, hex2: str, t: float) -> str:
        """Interpola entre dos colores hexadecimales. t=0 → hex1, t=1 → hex2."""
        t = max(0.0, min(1.0, t))
        try:
            r1, g1, b1 = int(hex1[1:3],16), int(hex1[3:5],16), int(hex1[5:7],16)
            r2, g2, b2 = int(hex2[1:3],16), int(hex2[3:5],16), int(hex2[5:7],16)
            r = int(r1*(1-t) + r2*t)
            g = int(g1*(1-t) + g2*t)
            b = int(b1*(1-t) + b2*t)
            return f"#{r:02x}{g:02x}{b:02x}"
        except Exception:
            return hex1

    def _orbita(self, c: tk.Canvas, cx: float, cy: float,
                a: float, b: float, ang: float,
                color: str, pasos: int = N_PASOS) -> None:
        pts: list[float] = []
        for i in range(pasos + 1):
            th = 2 * math.pi * i / pasos
            ox = a * math.cos(th)
            oy = b * math.sin(th)
            pts.extend((cx + ox * math.cos(ang) - oy * math.sin(ang),
                        cy + ox * math.sin(ang) + oy * math.cos(ang)))
        c.create_line(*pts, fill=color, width=1, smooth=True)
