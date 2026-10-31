"""
coachia/gui.py
==============
Interfaz de Élite para Coachia usando CustomTkinter (CTk):
  - Bordes redondeados (corner_radius), animaciones hover y sombras.
  - Tema Oscuro Mate & Dorado Premium (Dark & Gold / Amber Aesthetic).
  - Matriz de 7 Habilidades con Barras de Progreso (CTkProgressBar).
  - Panel "Por Qué Perdimos" con Diagnóstico % de Causas Raíz.
  - Línea de Tiempo de Tiempo de Partido (00:00 - 05:00).
  - Acordeón Conversacional Desplegable ("Paso a Paso", "Qué Haría un SSL", "Custom Training").
"""

import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk
import subprocess
import threading
import json
import sys
import os
from pathlib import Path

from advisor import generate_coaching_report
from voice_coach import speak_async, stop_speech, listen_mic_to_text
from claude_coach import chat_with_claude_coach

# Configuración global de CustomTkinter
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("dark-blue")

# ─────────────────────────────────────────────────────────────────────────────
COACHIA_DIR   = Path(__file__).resolve().parent
EXTRACTOR     = COACHIA_DIR / "extractor.py"
RRROCKET      = COACHIA_DIR / "rrrocket-0.11.5-x86_64-pc-windows-msvc" / "rrrocket.exe"

BG_DARK      = "#0a0b10"
BG_SURFACE   = "#12141e"
BG_CARD      = "#181c2e"
BG_CARD_HOT  = "#231f38"

GOLD         = "#f59e0b"
GOLD_HOVER   = "#fbbf24"
TEXT_DARK    = "#0a0b10"

GREEN        = "#10b981"
RED          = "#ef4444"
AMBER        = "#fbbf24"
CYAN         = "#06b6d4"
BLUE_TEAM    = "#2563eb"
ORANGE_TEAM  = "#ea580c"
TEXT_MAIN    = "#f8fafc"
TEXT_DIM     = "#94a3b8"

FONT_TITLE   = ("Segoe UI", 20, "bold")
FONT_HEADER  = ("Segoe UI", 14, "bold")
FONT_BOLD    = ("Segoe UI", 11, "bold")
FONT_NORMAL  = ("Segoe UI", 11)
FONT_SM      = ("Segoe UI", 9)
MONO         = ("Consolas", 10, "bold")
# ─────────────────────────────────────────────────────────────────────────────


class CoachiaGUI:
    def __init__(self, root: ctk.CTk):
        self.root = root
        self.root.title("Coachia — Sesión de Coaching Táctico con IA")
        self.root.geometry("1100x880")
        self.root.minsize(900, 680)
        self.root.configure(fg_color=BG_DARK)

        self.replay_path    = tk.StringVar()
        self.out_json       = tk.BooleanVar(value=True)
        self.out_csv_pl     = tk.BooleanVar(value=True)
        self.out_csv_ball   = tk.BooleanVar(value=False)
        self.out_dir        = tk.StringVar(value=str(COACHIA_DIR))
        self.running        = False
        self._proc          = None
        self.extracted_data = None
        self.coaching_report= None
        self.selected_player= None
        self.expanded_play_index = None
        self.show_all_plays_flag = False

        # Main Container
        self.container = ctk.CTkFrame(self.root, fg_color=BG_DARK, corner_radius=0)
        self.container.pack(fill="both", expand=True)

        self.extraction_view = ctk.CTkFrame(self.container, fg_color=BG_DARK, corner_radius=0)
        self.dashboard_view  = ctk.CTkFrame(self.container, fg_color=BG_DARK, corner_radius=0)

        self._build_extraction_view()
        self._build_dashboard_view()

        self.show_extraction_view()
        self._check_dependencies()

    # ── VISTAS ───────────────────────────────────────────────────────────────

    def show_extraction_view(self):
        stop_speech()
        self.dashboard_view.pack_forget()
        self.extraction_view.pack(fill="both", expand=True)

    def show_dashboard_view(self):
        self.extraction_view.pack_forget()
        self.dashboard_view.pack(fill="both", expand=True)
        self._render_dashboard()

    # ── VISTA DE EXTRACCION CON CUSTOMTKINTER ─────────────────────────────────

    def _build_extraction_view(self):
        # Header bar
        header = ctk.CTkFrame(self.extraction_view, fg_color=BG_SURFACE, corner_radius=0, height=70)
        header.pack(fill="x")

        logo_frame = ctk.CTkFrame(header, fg_color="transparent")
        logo_frame.pack(side="left", padx=24, pady=12)

        ctk.CTkLabel(logo_frame, text="👑", font=("Segoe UI", 26)).pack(side="left", padx=(0, 8))
        ctk.CTkLabel(logo_frame, text="COACHIA", font=("Segoe UI", 22, "bold"), text_color="white").pack(side="left")
        ctk.CTkLabel(logo_frame, text=" AI", font=("Segoe UI", 22, "bold"), text_color=GOLD).pack(side="left")
        ctk.CTkLabel(logo_frame, text=" — ANALIZADOR & COACHING TÁCTICO DE ÉLITE", font=("Segoe UI", 10, "bold"), text_color=TEXT_DIM).pack(side="left", padx=16)

        main = ctk.CTkFrame(self.extraction_view, fg_color=BG_DARK)
        main.pack(fill="both", expand=True, padx=24, pady=16)

        # Replay selector card
        card1 = ctk.CTkFrame(main, fg_color=BG_SURFACE, corner_radius=14)
        card1.pack(fill="x", pady=(0, 16), padx=4, ipadx=8, ipady=8)

        ctk.CTkLabel(card1, text="REPLAY DE ROCKET LEAGUE", font=FONT_BOLD, text_color=TEXT_DIM).pack(anchor="w", padx=16, pady=(12, 6))
        
        row1 = ctk.CTkFrame(card1, fg_color="transparent")
        row1.pack(fill="x", padx=16, pady=(0, 8))

        self.entry_replay = ctk.CTkEntry(row1, textvariable=self.replay_path, placeholder_text="Selecciona un archivo .replay...", font=FONT_NORMAL, height=40, fg_color=BG_CARD, border_color=BG_CARD)
        self.entry_replay.pack(side="left", fill="x", expand=True, padx=(0, 12))

        ctk.CTkButton(row1, text="📂 Elegir Replay", font=FONT_BOLD, fg_color=GOLD, hover_color=GOLD_HOVER, text_color=TEXT_DARK, height=40, corner_radius=8, command=self._pick_replay).pack(side="left")

        ctk.CTkLabel(card1, text="Tip: Tus replays están en Documents\\My Games\\Rocket League\\TAGame\\DemosEpic", font=FONT_SM, text_color=TEXT_DIM).pack(anchor="w", padx=16, pady=(0, 8))

        # Output options card
        card2 = ctk.CTkFrame(main, fg_color=BG_SURFACE, corner_radius=14)
        card2.pack(fill="x", pady=(0, 16), padx=4, ipadx=8, ipady=8)

        ctk.CTkLabel(card2, text="OPCIONES DE EXPORTACIÓN Y ANÁLISIS", font=FONT_BOLD, text_color=TEXT_DIM).pack(anchor="w", padx=16, pady=(12, 6))

        opts = ctk.CTkFrame(card2, fg_color="transparent")
        opts.pack(fill="x", padx=16, pady=(0, 8))

        ctk.CTkCheckBox(opts, text="JSON completo + Coaching Data", variable=self.out_json, font=FONT_NORMAL, text_color=TEXT_MAIN, fg_color=GOLD, hover_color=GOLD_HOVER).pack(side="left", padx=(0, 24))
        ctk.CTkCheckBox(opts, text="CSV jugadores (Telemetría 3D)", variable=self.out_csv_pl, font=FONT_NORMAL, text_color=TEXT_MAIN, fg_color=GOLD, hover_color=GOLD_HOVER).pack(side="left", padx=(0, 24))
        ctk.CTkCheckBox(opts, text="CSV pelota", variable=self.out_csv_ball, font=FONT_NORMAL, text_color=TEXT_MAIN, fg_color=GOLD, hover_color=GOLD_HOVER).pack(side="left")

        row2 = ctk.CTkFrame(card2, fg_color="transparent")
        row2.pack(fill="x", padx=16, pady=(4, 8))
        ctk.CTkLabel(row2, text="Carpeta de salida:", font=FONT_SM, text_color=TEXT_DIM).pack(side="left", padx=(0, 8))
        ctk.CTkEntry(row2, textvariable=self.out_dir, font=FONT_NORMAL, height=36, fg_color=BG_CARD, border_color=BG_CARD).pack(side="left", fill="x", expand=True, padx=(0, 8))
        ctk.CTkButton(row2, text="📁", width=40, height=36, fg_color=BG_CARD, hover_color=BG_CARD_HOT, text_color=TEXT_MAIN, command=self._pick_outdir).pack(side="left")

        # Action Buttons
        actions = ctk.CTkFrame(main, fg_color="transparent")
        actions.pack(fill="x", pady=(0, 14), padx=4)

        self.btn_run = ctk.CTkButton(actions, text="▶  Iniciar Sesión de Coaching", font=("Segoe UI", 12, "bold"), fg_color=GOLD, hover_color=GOLD_HOVER, text_color=TEXT_DARK, height=44, corner_radius=10, command=self._run)
        self.btn_run.pack(side="left")

        self.btn_stop = ctk.CTkButton(actions, text="⏹  Detener", font=FONT_BOLD, fg_color="#3f1515", hover_color="#5a1a1a", text_color=RED, height=44, corner_radius=10, command=self._stop)
        self.btn_stop.pack(side="left", padx=12)
        self.btn_stop.configure(state="disabled")

        # Log Frame
        log_card = ctk.CTkFrame(main, fg_color=BG_SURFACE, corner_radius=14)
        log_card.pack(fill="both", expand=True, padx=4, pady=(0, 8))

        ctk.CTkLabel(log_card, text="CONSOLA DE ANÁLISIS DE TELEMETRÍA", font=FONT_BOLD, text_color=TEXT_DIM).pack(anchor="w", padx=16, pady=(10, 4))

        self.log = tk.Text(log_card, bg="#08090f", fg=TEXT_MAIN, font=MONO, relief="flat", bd=0, insertbackground=GOLD, selectbackground=GOLD, wrap="word", state="disabled")
        scroll = ctk.CTkScrollbar(log_card, command=self.log.yview)
        self.log.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y", padx=(0, 8), pady=8)
        self.log.pack(fill="both", expand=True, padx=12, pady=(0, 8))

        self.log.tag_configure("ok",     foreground=GREEN)
        self.log.tag_configure("err",    foreground=RED)
        self.log.tag_configure("warn",   foreground=AMBER)
        self.log.tag_configure("accent", foreground=GOLD)
        self.log.tag_configure("dim",    foreground=TEXT_DIM)
        self.log.tag_configure("sep",    foreground=GOLD, font=("Consolas", 10, "bold"))

        # Status Bar
        self.status_var = tk.StringVar(value="Listo — elige un replay para empezar")
        status = ctk.CTkFrame(self.extraction_view, fg_color=BG_SURFACE, corner_radius=0, height=32)
        status.pack(fill="x", side="bottom")
        self.status_dot = ctk.CTkLabel(status, text="●", font=FONT_SM, text_color=TEXT_DIM)
        self.status_dot.pack(side="left", padx=(16, 4))
        ctk.CTkLabel(status, textvariable=self.status_var, font=FONT_SM, text_color=TEXT_DIM).pack(side="left")

    # ── VISTA DE DASHBOARD DE COACHING CON CUSTOMTKINTER ───────────────────────

    def _build_dashboard_view(self):
        # Header bar compacto
        header_dash = ctk.CTkFrame(self.dashboard_view, fg_color=BG_SURFACE, corner_radius=0, height=60)
        header_dash.pack(fill="x")

        logo_dash = ctk.CTkFrame(header_dash, fg_color="transparent")
        logo_dash.pack(side="left", padx=20, pady=10)

        ctk.CTkLabel(logo_dash, text="👑 COACHIA", font=("Segoe UI", 16, "bold"), text_color="white").pack(side="left")
        ctk.CTkLabel(logo_dash, text=" AI", font=("Segoe UI", 16, "bold"), text_color=GOLD).pack(side="left")
        ctk.CTkLabel(logo_dash, text=" — SESIÓN DE COACHING TÁCTICO PERSONALIZADA", font=("Segoe UI", 9, "bold"), text_color=TEXT_DIM).pack(side="left", padx=12)

        ctk.CTkButton(header_dash, text="🔄 Analizar Otro Replay", font=FONT_BOLD, fg_color=GOLD, hover_color=GOLD_HOVER, text_color=TEXT_DARK, height=36, corner_radius=8, command=self.show_extraction_view).pack(side="right", padx=16)
        ctk.CTkButton(header_dash, text="📋 Ver Log", font=FONT_BOLD, fg_color=BG_CARD, hover_color=BG_CARD_HOT, text_color=TEXT_MAIN, height=36, corner_radius=8, command=self.show_extraction_view).pack(side="right")

        # Container principal
        self.dash_main = ctk.CTkFrame(self.dashboard_view, fg_color=BG_DARK, corner_radius=0)
        self.dash_main.pack(fill="both", expand=True, padx=16, pady=10)

        # Tabs de Selección de Jugador
        self.player_tabs_frame = ctk.CTkFrame(self.dash_main, fg_color="transparent")
        self.player_tabs_frame.pack(fill="x", pady=(0, 8))

        # ── HERO CARD DEL COACH: MATRIZ DE 7 HABILIDADES + POR QUE PERDIMOS ───────
        self.coach_hero_card = ctk.CTkFrame(self.dash_main, fg_color=BG_SURFACE, corner_radius=14)
        self.coach_hero_card.pack(fill="x", pady=(0, 10), ipadx=10, ipady=10)

        hero_top = ctk.CTkFrame(self.coach_hero_card, fg_color="transparent")
        hero_top.pack(fill="x", padx=12, pady=8)

        # Columna 1: Matriz de 7 Habilidades Exactas (0-100)
        self.scores_matrix_frame = ctk.CTkFrame(hero_top, fg_color="transparent")
        self.scores_matrix_frame.pack(side="left", padx=(0, 16))

        # Columna 2: Panel "Por Qué Perdimos" (Root Cause Breakdown %)
        self.root_cause_frame = ctk.CTkFrame(hero_top, fg_color="transparent")
        self.root_cause_frame.pack(side="left", fill="both", expand=True, padx=(0, 16))

        # Columna 3: Controles de Audio Conversacional
        self.voice_action_frame = ctk.CTkFrame(hero_top, fg_color="transparent")
        self.voice_action_frame.pack(side="right")

        self.btn_voice = ctk.CTkButton(self.voice_action_frame, text="🔊 Escuchar al Coach", font=("Segoe UI", 11, "bold"), fg_color=GOLD, hover_color=GOLD_HOVER, text_color=TEXT_DARK, height=40, corner_radius=10, command=self._play_player_voice)
        self.btn_voice.pack(side="top", pady=2)
        
        ctk.CTkButton(self.voice_action_frame, text="▶ Guía Paso a Paso", font=FONT_BOLD, fg_color=BG_CARD, hover_color=BG_CARD_HOT, text_color=TEXT_MAIN, height=34, corner_radius=8, command=self._start_step_by_step_coaching).pack(side="top", pady=2)
        ctk.CTkButton(self.voice_action_frame, text="⏹ Detener Voz", font=FONT_SM, fg_color="#3f1515", hover_color="#5a1a1a", text_color=RED, height=28, corner_radius=6, command=stop_speech).pack(side="top", pady=2)

        # ── BARRA DE PROGRESO DE TIEMPO DEL PARTIDO (00:00 - 05:00 CON HOTSPOTS) ──
        timeline_bar_header = ctk.CTkFrame(self.dash_main, fg_color="transparent")
        timeline_bar_header.pack(fill="x", pady=(2, 2))

        ctk.CTkLabel(timeline_bar_header, text="BARRA DE TIEMPO DEL PARTIDO (Haz clic en cualquier punto para saltar a la jugada):", font=("Segoe UI", 8, "bold"), text_color=TEXT_DIM).pack(side="left")

        self.match_timeline_canvas = tk.Canvas(self.dash_main, bg="#1a1d2e", height=28, highlightthickness=0)
        self.match_timeline_canvas.pack(fill="x", pady=(0, 8))
        self.match_timeline_canvas.bind("<Button-1>", self._on_timeline_bar_click)

        # Bar de Filtro "Top 5 Jugadas" vs "Ver Análisis Completo"
        filter_bar = ctk.CTkFrame(self.dash_main, fg_color="transparent")
        filter_bar.pack(fill="x", pady=(2, 6))

        self.lbl_plays_title = ctk.CTkLabel(filter_bar, text="⭐⭐⭐⭐⭐ 5 JUGADAS CLAVE DE MAYOR IMPACTO:", font=("Segoe UI", 10, "bold"), text_color=GOLD)
        self.lbl_plays_title.pack(side="left")

        self.btn_toggle_all_plays = ctk.CTkButton(
            filter_bar,
            text="▼ Ver Análisis Completo de la Partida",
            font=FONT_SM,
            fg_color=BG_SURFACE,
            hover_color=BG_CARD_HOT,
            text_color=TEXT_DIM,
            height=30, corner_radius=6,
            command=self._toggle_show_all_plays
        )
        self.btn_toggle_all_plays.pack(side="right")

        # CTkScrollableFrame de Lista de Jugadas Causa-Efecto
        self.timeline_scroll_frame = ctk.CTkScrollableFrame(self.dash_main, fg_color=BG_DARK, corner_radius=12)
        self.timeline_scroll_frame.pack(fill="both", expand=True)

    # ── RENDER DEL DASHBOARD DE COACHING CON DATOS CARGADOS ────────────────────

    def _render_dashboard(self):
        if not self.coaching_report:
            return

        for w in self.player_tabs_frame.winfo_children():
            w.destroy()

        reports = self.coaching_report.get("player_reports", {})
        if not reports:
            return

        player_names = list(reports.keys())
        if not self.selected_player or self.selected_player not in player_names:
            self.selected_player = player_names[0]

        # Tabs de jugadores con CustomTkinter
        for pname in player_names:
            pr = reports[pname]
            tcolor = BLUE_TEAM if pr["team"] == 0 else ORANGE_TEAM

            btn_fg = tcolor if pname == self.selected_player else BG_SURFACE
            btn_txt = "white" if pname == self.selected_player else TEXT_DIM

            b = ctk.CTkButton(
                self.player_tabs_frame,
                text=f"👤 {pname} ({pr['team_name']})",
                font=FONT_BOLD,
                fg_color=btn_fg,
                hover_color=tcolor,
                text_color=btn_txt,
                height=34, corner_radius=8,
                command=lambda p=pname: self._select_player(p)
            )
            b.pack(side="left", padx=(0, 8))

        pr = reports[self.selected_player]
        scores = pr["scores"]

        # ── 1. MATRIZ DE 7 HABILIDADES EXACTAS (0 - 100) CON BARRAS DE PROGRESO ─
        for w in self.scores_matrix_frame.winfo_children():
            w.destroy()

        matrix_items = [
            ("🛡️ Defensa",          scores["defense"]),
            ("⚔️ Challenge Timing", scores["challenge"]),
            ("🔄 Rotaciones",       scores["rotation"]),
            ("⚡ Recoveries",       scores["recovery"]),
            ("⛽ Boost Management", scores["boost"]),
            ("👀 Awareness",        scores["awareness"]),
            ("🧠 Decision Making",  scores["decision"]),
        ]

        ctk.CTkLabel(self.scores_matrix_frame, text="ÍNDICES HEURÍSTICOS (0-100)", font=("Segoe UI", 7, "bold"), text_color=TEXT_DIM).pack(anchor="w", pady=(0, 2))
        m_row = ctk.CTkFrame(self.scores_matrix_frame, fg_color="transparent")
        m_row.pack(fill="x")

        for label, val in matrix_items:
            color = GREEN if val >= 75 else (AMBER if val >= 55 else RED)
            chip = ctk.CTkFrame(m_row, fg_color=BG_CARD, corner_radius=8)
            chip.pack(side="left", padx=(0, 4), ipadx=6, ipady=4)
            ctk.CTkLabel(chip, text=label, font=("Segoe UI", 7, "bold"), text_color=TEXT_DIM).pack(anchor="w")
            ctk.CTkLabel(chip, text=str(val), font=("Segoe UI", 12, "bold"), text_color=color).pack(anchor="w")

            # Barra de progreso miniaturizada
            p_bar = ctk.CTkProgressBar(chip, width=65, height=4, fg_color=BG_SURFACE, progress_color=color)
            p_bar.pack(anchor="w", pady=(2, 0))
            p_bar.set(val / 100.0)

        # ── 2. PANEL DE INDICADORES DETECTADOS ─────────────────────────────────
        for w in self.root_cause_frame.winfo_children():
            w.destroy()

        ctk.CTkLabel(self.root_cause_frame, text="INDICADORES DETECTADOS (DISTRIBUCIÓN %)", font=("Segoe UI", 8, "bold"), text_color=TEXT_DIM).pack(anchor="w", pady=(0, 4))

        detected_indicators = pr.get("root_cause_breakdown", [])
        if not detected_indicators:
            ctk.CTkLabel(self.root_cause_frame, text="Sin errores detectados por estos indicadores.", font=FONT_SM, text_color=TEXT_DIM).pack(anchor="w")

        for rc in detected_indicators:
            rc_row = ctk.CTkFrame(self.root_cause_frame, fg_color="transparent")
            rc_row.pack(fill="x", pady=1)

            ctk.CTkLabel(rc_row, text=f"{rc['pct']}%", font=("Segoe UI", 9, "bold"), text_color=rc["color"], width=32, anchor="e").pack(side="left")
            ctk.CTkLabel(rc_row, text=rc["label"], font=FONT_SM, text_color=TEXT_MAIN, anchor="w").pack(side="left", padx=(6, 0))

        # ── 3. DIBUJAR BARRA DE TIEMPO INTERACTIVA DEL PARTIDO (00:00 - 05:00) ─
        self._draw_match_timeline_bar(pr.get("all_plays", []))

        # ── 4. RENDER DE LISTADO DE JUGADAS (TOP 5 VS COMPLETO) ───────────────
        if self.show_all_plays_flag:
            self.lbl_plays_title.configure(text=f"📋 ANÁLISIS COMPLETO DE LA PARTIDA ({pr['total_plays_count']} Jugadas Causa-Efecto):")
            self.btn_toggle_all_plays.configure(text="▲ Mostrar Solo Top 5 Jugadas Clave")
            plays_to_show = pr.get("all_plays", [])
        else:
            self.lbl_plays_title.configure(text=f"⭐⭐⭐⭐⭐ TOP 5 JUGADAS CLAVE DE MAYOR IMPACTO:")
            self.btn_toggle_all_plays.configure(text=f"▼ Ver Análisis Completo ({pr['total_plays_count']} Jugadas)")
            plays_to_show = pr.get("top_5_plays", [])

        self._render_play_sequences(plays_to_show)

    def _draw_match_timeline_bar(self, all_plays: list):
        c = self.match_timeline_canvas
        c.delete("all")

        w = c.winfo_width() if c.winfo_width() > 100 else 1020
        h = 28

        c.create_rectangle(0, 0, w, h, fill="#1a1d2e", outline="")
        c.create_line(30, 14, w - 30, 14, fill=TEXT_DIM, width=2)

        max_t = 300.0
        for sec in range(0, 301, 60):
            x = 30 + (sec / max_t) * (w - 60)
            c.create_line(x, 7, x, 21, fill=TEXT_DIM, width=1)
            c.create_text(x, 22, text=f"{sec//60:02d}:00", fill=TEXT_DIM, font=("Segoe UI", 7))

        self._timeline_hotspots = []
        for p in all_plays:
            t_mid = (p["t_start"] + p["t_end"]) / 2.0
            x = 30 + (t_mid / max_t) * (w - 60)
            
            color = RED if p["severity"] in ["CRITICAL", "GOAL_CONCEDED"] else (AMBER if p["severity"] == "WARNING" else GREEN)
            r = 6 if p["severity"] == "GOAL_CONCEDED" else 5

            oval_id = c.create_oval(x - r, 14 - r, x + r, 14 + r, fill=color, outline="white", width=1)
            self._timeline_hotspots.append((oval_id, x, p))

    def _on_timeline_bar_click(self, event):
        ex = event.x
        if not hasattr(self, "_timeline_hotspots") or not self._timeline_hotspots:
            return

        closest_play = min(self._timeline_hotspots, key=lambda item: abs(item[1] - ex))[2]
        if closest_play:
            self.expanded_play_index = closest_play["play_number"]
            self._render_dashboard()

    def _toggle_show_all_plays(self):
        self.show_all_plays_flag = not self.show_all_plays_flag
        self._render_dashboard()

    def _select_player(self, pname: str):
        stop_speech()
        self.selected_player = pname
        self.expanded_play_index = None
        self.show_all_plays_flag = False
        self._render_dashboard()

    def _play_player_voice(self):
        if not self.coaching_report or not self.selected_player:
            return
        pr = self.coaching_report["player_reports"].get(self.selected_player)
        if pr and pr.get("voice_script"):
            speak_async(pr["voice_script"])

    def _start_step_by_step_coaching(self):
        if not self.coaching_report or not self.selected_player:
            return
        pr = self.coaching_report["player_reports"].get(self.selected_player)
        if not pr or not pr.get("top_5_plays"):
            return

        self.expanded_play_index = pr["top_5_plays"][0]["play_number"]
        self._render_dashboard()
        first_play = pr["top_5_plays"][0]
        speech_text = f"Comencemos con la Jugada Número {first_play['play_number']} a los {first_play['time_str']}. {first_play['title']}. {first_play['outcome_str']}"
        speak_async(speech_text)

    # ── RENDER DE TARJETAS DE JUGADAS CAUSA-EFECTO CON CUSTOMTKINTER ─────────

    def _render_play_sequences(self, plays: list):
        for w in self.timeline_scroll_frame.winfo_children():
            w.destroy()

        if not plays:
            card = ctk.CTkFrame(self.timeline_scroll_frame, fg_color=BG_SURFACE, corner_radius=12)
            card.pack(fill="x", pady=6)
            ctk.CTkLabel(card, text="🎉 No hay secuencias críticas registradas en este segmento.", font=FONT_HEADER, text_color=GREEN).pack(anchor="w", padx=16, pady=16)
            return

        for p in plays:
            p_num = p["play_number"]
            is_expanded = (self.expanded_play_index == p_num)
            sev = p.get("severity", "WARNING")
            
            border_color = RED if sev in ["CRITICAL", "GOAL_CONCEDED"] else (AMBER if sev == "WARNING" else GREEN)
            bg_color = BG_CARD_HOT if is_expanded else BG_CARD

            card = ctk.CTkFrame(self.timeline_scroll_frame, fg_color=bg_color, corner_radius=12, border_width=1, border_color=border_color)
            card.pack(fill="x", pady=(0, 8), expand=True)

            top_row = ctk.CTkFrame(card, fg_color="transparent")
            top_row.pack(fill="x", padx=12, pady=10)

            # Timestamp Badge
            ts_chip = ctk.CTkFrame(top_row, fg_color=BG_SURFACE, corner_radius=6)
            ts_chip.pack(side="left", padx=(0, 10))
            ctk.CTkLabel(ts_chip, text=f"⏱️ {p['time_str']}", font=MONO, text_color=AMBER).pack(padx=8, pady=2)

            # Badge Severidad
            ctk.CTkLabel(top_row, text=p["badge"], font=("Segoe UI", 9, "bold"), text_color=border_color).pack(side="left", padx=(0, 6))

            # Chip de Responsabilidad Estimada %
            if p.get("resp_pct", 0) > 0:
                resp_color = RED if p["resp_pct"] >= 65 else (AMBER if p["resp_pct"] >= 35 else GREEN)
                resp_chip = ctk.CTkFrame(top_row, fg_color=BG_SURFACE, corner_radius=6)
                resp_chip.pack(side="left", padx=(0, 10))
                ctk.CTkLabel(resp_chip, text=f"Responsabilidad: {p['resp_pct']}%", font=("Segoe UI", 8, "bold"), text_color=resp_color).pack(padx=6, pady=2)

            # Título de la Jugada
            title_lbl = ctk.CTkLabel(top_row, text=f"{p['title']} — {p['outcome_str']}", font=FONT_BOLD, text_color=TEXT_MAIN, anchor="w")
            title_lbl.pack(side="left", fill="x", expand=True)
            title_lbl.bind("<Button-1>", lambda e, n=p_num: self._toggle_play_expand(n))

            # Botón de audio por jugada
            alts_speech = " ".join([f"Opción {i+1}: {alt}" for i, alt in enumerate(p.get("alternatives", []))])
            steps_speech = " ".join(p.get("steps", []))
            card_speech = (
                f"Hablemos de la Jugada número {p_num} a los {p['time_str']}. {p['outcome_str']} "
                f"Secuencia causa y efecto: {steps_speech}. "
                f"Las opciones alternativas recomendadas son: {alts_speech}. "
                f"Un jugador Supersonic Legend habría hecho lo siguiente: {p.get('ssl_insight', '')}."
            )

            ctk.CTkButton(
                top_row,
                text="🔊 Voz",
                font=FONT_SM,
                fg_color=BG_SURFACE,
                hover_color=GOLD_HOVER,
                text_color=GOLD,
                width=50, height=28, corner_radius=6,
                command=lambda st=card_speech: speak_async(st)
            ).pack(side="right", padx=(8, 0))

            # Botón Desplegar / Contraer
            ctk.CTkButton(
                top_row,
                text="▲ Ocultar" if is_expanded else "▼ Ver Conversación",
                font=FONT_SM,
                fg_color=BG_SURFACE,
                hover_color=BG_CARD_HOT,
                text_color=TEXT_DIM,
                height=28, corner_radius=6,
                command=lambda n=p_num: self._toggle_play_expand(n)
            ).pack(side="right")

            # PANEL DESPLEGABLE CONVERSACIONAL (CAUSA RAÍZ + EVIDENCIAS + SSL)
            if is_expanded:
                detail_panel = ctk.CTkFrame(card, fg_color="transparent")
                detail_panel.pack(fill="x", padx=12, pady=(0, 10))

                ctk.CTkLabel(detail_panel, text=f"💬 COACH: \"Diagnóstico de Causa Raíz para la Jugada #{p_num}:\"", font=("Segoe UI", 10, "bold"), text_color=GOLD).pack(anchor="w", pady=(0, 4))

                # Box Causa Raíz Principal + Distribución de Certeza %
                root_box = ctk.CTkFrame(detail_panel, fg_color=BG_SURFACE, corner_radius=10)
                root_box.pack(fill="x", pady=(2, 6), ipadx=8, ipady=6)

                ctk.CTkLabel(root_box, text=f"🎯 CAUSA RAÍZ PRINCIPAL: {p.get('primary_cause', 'Challenge Innecesario').upper()} ({p.get('conf_primary', 76)}% Certeza)", font=("Segoe UI", 9, "bold"), text_color=RED if p.get('severity') == 'CRITICAL' else AMBER).pack(anchor="w", padx=8, pady=(4, 2))
                ctk.CTkLabel(root_box, text=f"   • Factores Secundarios: {p.get('secondary_1', '')} ({p.get('conf_sec1', 18)}%) | {p.get('secondary_2', '')} ({p.get('conf_sec2', 6)}%)", font=FONT_SM, text_color=TEXT_DIM).pack(anchor="w", padx=8, pady=(0, 4))

                # Evidencias Telemétricas
                ctk.CTkLabel(root_box, text="EVIDENCIAS TELEMÉTRICAS DETECTADAS:", font=("Segoe UI", 8, "bold"), text_color=CYAN).pack(anchor="w", padx=8, pady=(4, 2))
                for ev_str in p.get("evidences", []):
                    ctk.CTkLabel(root_box, text=f"   • {ev_str}", font=FONT_SM, text_color=TEXT_MAIN, anchor="w").pack(anchor="w", padx=8, pady=1)

                # Cadena Causa-Efecto Paso a Paso
                seq_box = ctk.CTkFrame(detail_panel, fg_color=BG_SURFACE, corner_radius=10)
                seq_box.pack(fill="x", pady=(2, 6), ipadx=8, ipady=6)

                ctk.CTkLabel(seq_box, text="SECUENCIA CAUSA Y EFECTO DETECTADA:", font=("Segoe UI", 8, "bold"), text_color=TEXT_DIM).pack(anchor="w", padx=8, pady=(4, 2))
                for step_str in p["steps"]:
                    ctk.CTkLabel(seq_box, text=f"↓ {step_str}", font=FONT_NORMAL, text_color=TEXT_MAIN, anchor="w").pack(anchor="w", padx=8, pady=1)

                # Alternativas Recomendadas
                alt_box = ctk.CTkFrame(detail_panel, fg_color=BG_SURFACE, corner_radius=10)
                alt_box.pack(fill="x", pady=(2, 6), ipadx=8, ipady=6)

                ctk.CTkLabel(alt_box, text="💡 OPCIONES ALTERNATIVAS PARA ESTA JUGADA:", font=("Segoe UI", 8, "bold"), text_color=GREEN).pack(anchor="w", padx=8, pady=(4, 2))
                for alt in p["alternatives"]:
                    ctk.CTkLabel(alt_box, text=f"• {alt}", font=FONT_NORMAL, text_color=TEXT_MAIN, anchor="w", wraplength=820, justify="left").pack(anchor="w", padx=8, pady=1)

                # Box del Árbol de Decisión Táctico Determinista (Sección 3)
                eval_box = ctk.CTkFrame(detail_panel, fg_color=BG_SURFACE, corner_radius=10)
                eval_box.pack(fill="x", pady=(2, 6), ipadx=8, ipady=6)

                ctk.CTkLabel(eval_box, text=f"📊 CLASIFICACIÓN TÁCTICA CALCULADA: {p.get('clasificacion', 'Evaluación Táctica').upper()}", font=("Segoe UI", 9, "bold"), text_color=GOLD).pack(anchor="w", padx=8, pady=(4, 2))
                ctk.CTkLabel(eval_box, text=f"💬 CONSEJO CONCLUYENTE: \"{p.get('consejo_concluyente', '')}\"", font=FONT_BOLD, text_color=TEXT_MAIN, wraplength=820, justify="left").pack(anchor="w", padx=8, pady=(2, 4))

                # Telemetría Clave
                t_info = f"• Distancia a Arco Propio: {p.get('dist_pelota_a_arco_propio', 0)}u | ETA Llegada Pelota: {p.get('tiempo_estimado_llegada_pelota', 0)}s | Inercia Jugador: {p.get('inercia_jugador_hacia_pelota', 0)}u/s | Boost: {p.get('boost_jugador', 0)}%"
                ctk.CTkLabel(eval_box, text=t_info, font=FONT_SM, text_color=TEXT_DIM).pack(anchor="w", padx=8, pady=(0, 2))

                # ¿Qué habría hecho un SSL? + Práctica Recomendada
                ssl_box = ctk.CTkFrame(detail_panel, fg_color=BG_SURFACE, corner_radius=10)
                ssl_box.pack(fill="x", pady=(2, 0), ipadx=8, ipady=6)

                ctk.CTkLabel(ssl_box, text="🧠 ¿QUÉ HABRÍA HECHO UN SSL (SUPERSONIC LEGEND)?:", font=("Segoe UI", 8, "bold"), text_color=AMBER).pack(anchor="w", padx=8, pady=(4, 2))
                ctk.CTkLabel(ssl_box, text=p["ssl_insight"], font=FONT_NORMAL, text_color=TEXT_MAIN, anchor="w", wraplength=820, justify="left").pack(anchor="w", padx=8, pady=(0, 4))

                ctk.CTkLabel(ssl_box, text="🎯 PRÁCTICA RECOMENDADA EN ROCKET LEAGUE:", font=("Segoe UI", 8, "bold"), text_color=CYAN).pack(anchor="w", padx=8, pady=(2, 2))
                ctk.CTkLabel(ssl_box, text=p["training_pack"], font=MONO, text_color=CYAN).pack(anchor="w", padx=8, pady=(0, 4))

                # 💬 SECCIÓN DE DEBATE Y CONVERSACIÓN CON COACHIA IA
                chat_box = ctk.CTkFrame(detail_panel, fg_color=BG_SURFACE, corner_radius=10)
                chat_box.pack(fill="x", pady=(6, 0), ipadx=8, ipady=6)

                ctk.CTkLabel(chat_box, text="💬 DEBATE CON TU COACH IA:", font=("Segoe UI", 8, "bold"), text_color=GOLD).pack(anchor="w", padx=8, pady=(4, 2))

                chat_row = ctk.CTkFrame(chat_box, fg_color="transparent")
                chat_row.pack(fill="x", padx=8, pady=4)

                chat_entry = ctk.CTkEntry(chat_row, placeholder_text="Pregunta o debate esta jugada (ej: ¿Por qué no debía saltar en el minuto 01:23?)...", font=FONT_NORMAL, height=36, fg_color=BG_CARD, border_color=BG_CARD)
                chat_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))

                chat_res_label = ctk.CTkLabel(chat_box, text="", font=FONT_NORMAL, text_color=TEXT_MAIN, wraplength=820, justify="left")

                def _send_debate_question(p_context=p, entry_widget=chat_entry, res_lbl=chat_res_label):
                    q_text = entry_widget.get().strip()
                    if not q_text:
                        return
                    entry_widget.delete(0, "end")
                    res_lbl.configure(text="💬 Generando respuesta táctica...")
                    res_lbl.pack(anchor="w", padx=8, pady=(4, 2))
                    
                    def _async_reply():
                        answer = chat_with_claude_coach(self.selected_player or "Jugador", q_text, p_context)
                        self.root.after(0, lambda: res_lbl.configure(text=f"🤖 Coach IA: {answer}"))
                        speak_async(answer)

                    threading.Thread(target=_async_reply, daemon=True).start()

                ctk.CTkButton(chat_row, text="💬 Debatir", font=FONT_BOLD, fg_color=GOLD, hover_color=GOLD_HOVER, text_color=TEXT_DARK, height=36, corner_radius=6, command=_send_debate_question).pack(side="left", padx=(0, 6))

                def _listen_mic_debate(p_context=p, entry_widget=chat_entry, res_lbl=chat_res_label):
                    res_lbl.configure(text="🎙️ Escuchando tu voz por el micrófono... (Habla ahora)")
                    res_lbl.pack(anchor="w", padx=8, pady=(4, 2))

                    def _async_mic_worker():
                        try:
                            spoken_text = listen_mic_to_text(language="es-ES", timeout=6.0, phrase_time_limit=8.0)
                            self.root.after(0, lambda: entry_widget.delete(0, "end"))
                            self.root.after(0, lambda: entry_widget.insert(0, spoken_text))
                            self.root.after(0, lambda: res_lbl.configure(text=f"🎙️ Transcrito de tu micrófono: '{spoken_text}'\n🤖 Consultando a Claude API..."))
                            
                            answer = chat_with_claude_coach(self.selected_player or "Jugador", spoken_text, p_context)
                            self.root.after(0, lambda: res_lbl.configure(text=f"🎙️ Tu voz: '{spoken_text}'\n🤖 Coach IA (Claude): {answer}"))
                            speak_async(answer)
                        except Exception as err:
                            self.root.after(0, lambda: res_lbl.configure(text=f"⚠️ Micrófono: {err}"))

                    threading.Thread(target=_async_mic_worker, daemon=True).start()

                ctk.CTkButton(chat_row, text="🎙️ Hablar (Micrófono)", font=FONT_BOLD, fg_color=CYAN, hover_color="#0891b2", text_color=TEXT_DARK, height=36, corner_radius=6, command=_listen_mic_debate).pack(side="left")
                chat_entry.bind("<Return>", lambda e: _send_debate_question())

    def _toggle_play_expand(self, play_number: int):
        if self.expanded_play_index == play_number:
            self.expanded_play_index = None
        else:
            self.expanded_play_index = play_number
        self._render_dashboard()

    # ── UTILIDADES ───────────────────────────────────────────────────────────

    def _pick_replay(self):
        demos = Path.home() / "OneDrive" / "Documents" / "My Games" / \
                "Rocket League" / "TAGame" / "DemosEpic"
        init = str(demos) if demos.exists() else str(Path.home())
        path = filedialog.askopenfilename(
            title="Seleccionar archivo .replay",
            initialdir=init,
            filetypes=[("Rocket League Replay", "*.replay"), ("Todos", "*.*")]
        )
        if path:
            self.replay_path.set(path)
            name = Path(path).stem[:40]
            self._set_status(f"Replay seleccionado: {name}")

    def _pick_outdir(self):
        d = filedialog.askdirectory(initialdir=self.out_dir.get(),
                                    title="Carpeta de salida")
        if d:
            self.out_dir.set(d)

    def _check_dependencies(self):
        ok = True
        if not RRROCKET.exists():
            self._log(f"[ERROR] rrrocket.exe no encontrado en:\n  {RRROCKET}\n", "err")
            ok = False
        if not EXTRACTOR.exists():
            self._log(f"[ERROR] extractor.py no encontrado en:\n  {EXTRACTOR}\n", "err")
            ok = False
        if ok:
            self._log("Sistema listo. Elige un replay y presiona Iniciar Sesión de Coaching.\n", "dim")

    def _run(self):
        replay = self.replay_path.get().strip()
        if not replay:
            messagebox.showwarning("Sin replay", "Primero elige un archivo .replay.")
            return
        if not Path(replay).exists():
            messagebox.showerror("Error", f"El archivo no existe:\n{replay}")
            return
        if self.running:
            return

        out_dir  = Path(self.out_dir.get())
        stem     = Path(replay).stem
        out_json = str(out_dir / f"{stem}.json")
        out_csv  = str(out_dir / f"{stem}_jugadores.csv") if self.out_csv_pl.get() else None
        out_ball = str(out_dir / f"{stem}_pelota.csv") if self.out_csv_ball.get() else None

        cmd = [sys.executable, str(EXTRACTOR), "--replay", replay, "--out", out_json]
        if out_csv:  cmd += ["--csv", out_csv]
        if out_ball: cmd += ["--csv-ball", out_ball]

        self._clear_log()
        self._log(f"Replay:  {replay}\n", "accent")
        self._log(f"Salida:  {out_dir}\n", "dim")
        self._log("─" * 68 + "\n", "sep")

        self.running = True
        self.btn_run.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self._set_status("Procesando telemetría y analizando decisiones tácticas...", busy=True)

        thread = threading.Thread(target=self._run_proc, args=(cmd, out_json, out_csv, out_ball), daemon=True)
        thread.start()

    def _run_proc(self, cmd, out_json, out_csv, out_ball):
        try:
            self._proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace"
            )
            for line in self._proc.stdout:
                self._log_line(line)
            self._proc.wait()
            rc = self._proc.returncode
        except Exception as e:
            self._log(f"\n[ERROR] {e}\n", "err")
            rc = -1
        finally:
            self._proc = None
            self.running = False
            self.root.after(0, self._on_done, rc, out_json, out_csv, out_ball)

    def _log_line(self, line: str):
        tag = "normal"
        l = line.lower()
        if any(x in l for x in ["error", "[err", "traceback", "exception"]):
            tag = "err"
        elif any(x in l for x in ["[ok]", "exitosamente", "listo", "pass", "csv", "json"]):
            tag = "ok"
        elif any(x in l for x in ["[warn", "warning", "omitido"]):
            tag = "warn"
        elif line.startswith("=") or line.startswith("─") or line.startswith("-"):
            tag = "sep"
        elif any(x in l for x in ["coachia", "replay:", "salida:", "mapa", "fecha", "score", "duracion"]):
            tag = "accent"
        self.root.after(0, self._log, line, tag)

    def _on_done(self, rc: int, out_json, out_csv, out_ball):
        self.btn_run.configure(state="normal")
        self.btn_stop.configure(state="disabled")
        self._log("─" * 68 + "\n", "sep")

        if rc == 0 and out_json and Path(out_json).exists():
            self._log("\n✓ Extracción de telemetría completada. Generando análisis táctico...\n", "ok")
            self._set_status("Generando reporte de coaching táctico...", busy=True)

            def _async_generate_report():
                try:
                    self.root.after(0, self._set_status, "Cargando datos del replay...", True)
                    import time
                    data_loaded = None
                    last_err = None
                    for attempt in range(6):
                        try:
                            for enc in ["utf-8", "utf-16", "utf-8-sig"]:
                                try:
                                    with open(out_json, "r", encoding=enc) as f:
                                        data_loaded = json.load(f)
                                    break
                                except (UnicodeDecodeError, UnicodeError):
                                    continue
                            if data_loaded is not None:
                                break
                        except (PermissionError, IOError) as pe:
                            last_err = pe
                            time.sleep(0.3)

                    if data_loaded is None and last_err:
                        raise last_err

                    self.extracted_data = data_loaded
                    self.root.after(0, self._set_status, "Construyendo análisis táctico...", True)

                    def report_progress(player_name, completed, total):
                        status = f"Generando consejos IA para {player_name}: {completed}/{total} jugadas..."
                        self.root.after(0, self._set_status, status, True)

                    report = generate_coaching_report(self.extracted_data, progress_callback=report_progress)
                    self.coaching_report = report
                    
                    self.root.after(0, self._on_report_ready)
                except Exception as e:
                    self.root.after(0, lambda error=e: self._log(f"\n[ERROR cargando coaching report] {error}\n", "err"))
                    self.root.after(0, lambda: self._set_status("Error al generar coaching report.", busy=False, ok=False))

            threading.Thread(target=_async_generate_report, daemon=True).start()
        else:
            self._log(f"\n✗ El proceso terminó con código de error {rc}.\n", "err")
            self._set_status("Error en la extracción.", busy=False, ok=False)

    def _on_report_ready(self):
        self._set_status("Análisis completado — Cambiando a Sesión de Coaching...", busy=False, ok=True)
        self.show_dashboard_view()

    def _stop(self):
        if self._proc:
            self._proc.terminate()
            self._log("\n[!] Proceso detenido por el usuario.\n", "warn")
        self.running = False
        self.btn_run.configure(state="normal")
        self.btn_stop.configure(state="disabled")
        self._set_status("Detenido.")

    def _log(self, text: str, tag: str = "normal"):
        self.log.configure(state="normal")
        self.log.insert("end", text, tag)
        self.log.see("end")
        self.log.configure(state="disabled")

    def _clear_log(self):
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")

    def _set_status(self, msg: str, busy: bool = False, ok: bool = None):
        self.status_var.set(msg)
        if busy:
            self.status_dot.configure(text_color=AMBER)
        elif ok is True:
            self.status_dot.configure(text_color=GREEN)
        elif ok is False:
            self.status_dot.configure(text_color=RED)
        else:
            self.status_dot.configure(text_color=TEXT_DIM)


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    root = ctk.CTk()
    app = CoachiaGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
