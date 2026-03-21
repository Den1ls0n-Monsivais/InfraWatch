"""
╔══════════════════════════════════════════════════════════════╗
║  InfraWatch Agent v2.3 — Instalador Windows                 ║
║  Compilar con PyInstaller → .exe                             ║
║  Incluye:                                                    ║
║  ✦ Descubrimiento automático del servidor                   ║
║  ✦ Si no encuentra en 60s → input manual de IP              ║
║  ✦ Input de tags                                             ║
║  ✦ Instalación como servicio Windows                        ║
║  ✦ UI con tema oscuro InfraWatch                            ║
╚══════════════════════════════════════════════════════════════╝

Compilar:
  pyinstaller --onefile --noconsole --name="InfraWatch-Agent-Installer" ^
              --add-data="agent.py;." installer_windows.py
"""

import tkinter as tk
from tkinter import ttk, messagebox
import threading, os, sys, json, time, subprocess, shutil, ctypes
from pathlib import Path

# Agregar directorio del script al path (para importar agent.py)
_BASE = Path(sys._MEIPASS) if getattr(sys, "frozen", False) else Path(__file__).parent
sys.path.insert(0, str(_BASE))

from agent import (
    discover_server, ping_server,
    VERSION, CONFIG_DIR, save_config, load_config,
    DISCOVERY_TIMEOUT
)

# ── Rutas de instalación ──────────────────────────────────────────────────────
INSTALL_DIR  = Path(os.environ.get("PROGRAMFILES", "C:/Program Files")) / "InfraWatch"
SERVICE_NAME = "InfraWatchAgent"
AGENT_SCRIPT = INSTALL_DIR / "agent.py"
AGENT_EXE    = INSTALL_DIR / "iw-agent.exe"

# ── Paleta ────────────────────────────────────────────────────────────────────
C = {
    "bg":   "#060a0f",
    "bg2":  "#0a1018",
    "bg3":  "#0f1923",
    "bdr":  "#1a2d3d",
    "bdr2": "#243d52",
    "grn":  "#00c864",
    "cyn":  "#00d4ff",
    "ylw":  "#ffcc00",
    "red":  "#ff3355",
    "txt":  "#c8dde8",
    "txt2": "#6a8fa8",
    "txt3": "#3d5f78",
    "mono": "Consolas",
}

# ─────────────────────────────────────────────────────────────────────────────

class InstallerApp:

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("InfraWatch Agent — Instalador v2.3")
        self.root.geometry("500x600")
        self.root.resizable(False, False)
        self.root.configure(bg=C["bg"])
        self._center_window()

        # Verificar privilegios de administrador
        if not self._is_admin():
            messagebox.showerror(
                "Permisos requeridos",
                "Por favor ejecuta el instalador\ncomo Administrador.\n\n"
                "Clic derecho → Ejecutar como administrador"
            )
            self.root.destroy()
            return

        # Variables de estado
        self.found_server   = None
        self.discovery_done = threading.Event()
        self.sv_server_ip   = tk.StringVar()
        self.sv_tags        = tk.StringVar()
        self.sv_status      = tk.StringVar(value="🔍 Iniciando búsqueda de servidor...")

        self._build_ui()
        self.root.after(300, self._start_discovery)  # pequeño delay para que se pinte la UI
        self.root.mainloop()

    # ── Helpers del sistema ───────────────────────────────────────────────

    @staticmethod
    def _is_admin() -> bool:
        try:
            return ctypes.windll.shell32.IsUserAnAdmin()
        except Exception:
            return False

    def _center_window(self):
        self.root.update_idletasks()
        w, h = 500, 600
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x  = (sw - w) // 2
        y  = (sh - h) // 2 - 40
        self.root.geometry(f"{w}x{h}+{x}+{y}")

    # ── UI ────────────────────────────────────────────────────────────────

    def _build_ui(self):
        """Construye la interfaz completa"""

        # ── Header ────────────────────────────────────────────────────────
        hdr = tk.Frame(self.root, bg="#0d1f2e", pady=22)
        hdr.pack(fill="x")

        tk.Label(hdr, text="⬡", font=("Segoe UI", 36), fg=C["grn"],
                 bg="#0d1f2e").pack()
        tk.Label(hdr, text="InfraWatch Agent",
                 font=("Segoe UI", 20, "bold"), fg=C["txt"], bg="#0d1f2e").pack()
        tk.Label(hdr, text=f"IT Infrastructure Monitor  v{VERSION}",
                 font=(C["mono"], 9), fg=C["txt3"], bg="#0d1f2e").pack(pady=(2, 0))

        # ── Cuerpo ────────────────────────────────────────────────────────
        body = tk.Frame(self.root, bg=C["bg"], padx=28, pady=22)
        body.pack(fill="both", expand=True)

        # ╔═ Sección: Servidor ═════════════════════════════════════════════╗
        srv_lf = self._lframe(body, "  Servidor InfraWatch  ")
        srv_lf.pack(fill="x", pady=(0, 14))

        # Estado de búsqueda
        self.lbl_status = tk.Label(
            srv_lf, textvariable=self.sv_status,
            font=(C["mono"], 9), fg=C["cyn"], bg=C["bg"],
            anchor="w", wraplength=420, justify="left", pady=4
        )
        self.lbl_status.pack(fill="x", padx=12)

        # Barra de progreso
        style = ttk.Style()
        style.theme_use("default")
        style.configure("IW.Horizontal.TProgressbar",
                        troughcolor=C["bg3"], background=C["cyn"],
                        darkcolor=C["cyn"], lightcolor=C["cyn"],
                        bordercolor=C["bdr"], thickness=6)
        self.progress = ttk.Progressbar(
            srv_lf, mode="indeterminate", length=440,
            style="IW.Horizontal.TProgressbar"
        )
        self.progress.pack(padx=12, pady=(2, 8))
        self.progress.start(12)

        # Frame de IP manual (oculto hasta que falle la búsqueda)
        self.manual_frame = tk.Frame(srv_lf, bg=C["bg"])
        self._lbl(self.manual_frame, "IP del servidor:").pack(
            anchor="w", padx=12, pady=(4, 2))
        self.ent_ip = self._entry(self.manual_frame, self.sv_server_ip)
        self.ent_ip.pack(fill="x", padx=12, pady=(0, 10), ipady=7)
        self.ent_ip.insert(0, "192.168.1.")

        # ╔═ Sección: Tags ═════════════════════════════════════════════════╗
        tag_lf = self._lframe(body, "  Tags del equipo (opcional)  ")
        tag_lf.pack(fill="x", pady=(0, 14))

        self._lbl(tag_lf,
                  "Etiquetas separadas por coma — ej: SERVIDOR, PRODUCCION, CRITICO",
                  small=True).pack(anchor="w", padx=12, pady=(6, 2))
        self.ent_tags = self._entry(tag_lf, self.sv_tags)
        self.ent_tags.pack(fill="x", padx=12, pady=(0, 10), ipady=7)

        # ╔═ Botón instalar ════════════════════════════════════════════════╗
        self.btn = tk.Button(
            body, text="⚡   Instalar Agente",
            font=("Segoe UI", 12, "bold"),
            bg=C["grn"], fg="#000",
            activebackground="#00a050", activeforeground="#000",
            bd=0, pady=13, cursor="hand2",
            relief="flat", state="disabled",
            command=self._on_install
        )
        self.btn.pack(fill="x", pady=(0, 12))

        # ╔═ Log de salida ═════════════════════════════════════════════════╗
        self.log = tk.Text(
            body, height=4, bg=C["bg2"], fg=C["txt2"],
            font=(C["mono"], 8), bd=0, state="disabled",
            relief="flat", highlightthickness=1,
            highlightbackground=C["bdr"],
            insertbackground=C["cyn"]
        )
        self.log.pack(fill="x")

        # ── Footer ────────────────────────────────────────────────────────
        tk.Label(
            self.root,
            text=f"v{VERSION} — InfraWatch · Denilson Monsivais · SiiX EMS",
            font=(C["mono"], 8), fg=C["txt3"], bg=C["bg"]
        ).pack(pady=8)

    # ── Widget helpers ────────────────────────────────────────────────────

    def _lframe(self, parent, text) -> tk.LabelFrame:
        lf = tk.LabelFrame(
            parent, text=text,
            bg=C["bg"], fg=C["txt3"],
            font=("Segoe UI", 8), bd=1, relief="solid",
            labelanchor="nw"
        )
        lf.configure(highlightbackground=C["bdr"])
        return lf

    def _lbl(self, parent, text, small=False) -> tk.Label:
        return tk.Label(
            parent, text=text,
            font=("Segoe UI", 8 if small else 9),
            fg=C["txt3" if small else "txt2"], bg=C["bg"]
        )

    def _entry(self, parent, var) -> tk.Entry:
        return tk.Entry(
            parent, textvariable=var,
            font=(C["mono"], 11), bg=C["bg3"], fg=C["txt"],
            insertbackground=C["grn"], bd=0, relief="flat",
            highlightthickness=1,
            highlightbackground=C["bdr"],
            highlightcolor=C["grn"]
        )

    def _log(self, msg: str):
        def _do():
            self.log.config(state="normal")
            self.log.insert("end", f"› {msg}\n")
            self.log.see("end")
            self.log.config(state="disabled")
        self.root.after(0, _do)

    def _set_status(self, msg: str, color: str = None):
        def _do():
            self.sv_status.set(msg)
            if color:
                self.lbl_status.config(fg=color)
        self.root.after(0, _do)

    # ── Descubrimiento ────────────────────────────────────────────────────

    def _start_discovery(self):
        threading.Thread(target=self._discovery_worker, daemon=True,
                         name="discovery").start()

    def _progress_cb(self, msg: str, pct: int):
        self._set_status(f"🔍 {msg}")
        self._log(msg)

    def _discovery_worker(self):
        self._log(f"Iniciando búsqueda de servidor (timeout: {DISCOVERY_TIMEOUT}s)...")

        ip = discover_server(
            timeout_total=DISCOVERY_TIMEOUT,
            progress_cb=self._progress_cb
        )

        self.discovery_done.set()

        if ip:
            self.found_server = ip
            self.sv_server_ip.set(ip)
            self.root.after(0, self._on_found, ip)
        else:
            self.root.after(0, self._on_not_found)

    def _on_found(self, ip: str):
        self.progress.stop()
        self.progress.config(mode="determinate", value=100,
                              style="IW.Horizontal.TProgressbar")
        style = ttk.Style()
        style.configure("IW.Horizontal.TProgressbar", background=C["grn"])

        self._set_status(f"✅ Servidor encontrado: {ip}:8000", C["grn"])
        self._log(f"InfraWatch detectado en {ip}:8000")
        self.btn.config(state="normal")

    def _on_not_found(self):
        self.progress.stop()
        self.progress.config(mode="determinate", value=100)
        style = ttk.Style()
        style.configure("IW.Horizontal.TProgressbar", background=C["ylw"])

        self._set_status(
            "⚠️  Servidor no encontrado — ingresa la IP del servidor:", C["ylw"]
        )
        self._log("No se encontró servidor automáticamente.")
        self._log("Ingresa la IP manualmente y presiona Instalar.")
        self.manual_frame.pack(fill="x")
        self.ent_ip.focus()
        self.btn.config(state="normal")

    # ── Instalación ───────────────────────────────────────────────────────

    def _on_install(self):
        ip = self.found_server or self.sv_server_ip.get().strip()
        if not ip or not ip.replace(".", "").isdigit():
            messagebox.showerror("IP inválida", "Ingresa una IP válida del servidor.")
            return

        # Verificar conectividad
        self._set_status(f"🔗 Verificando {ip}:8000...", C["cyn"])
        self.btn.config(state="disabled", text="Instalando...")
        self.root.update()

        if not ping_server(ip):
            self._set_status(f"❌ No se puede conectar a {ip}:8000", C["red"])
            self.btn.config(state="normal", text="⚡   Instalar Agente")
            messagebox.showerror(
                "Sin conexión",
                f"No se puede conectar a InfraWatch en {ip}:8000\n\n"
                "Verifica que el servidor esté corriendo y sea accesible."
            )
            return

        tags = [t.strip().upper() for t in self.sv_tags.get().split(",") if t.strip()]
        threading.Thread(
            target=self._install_worker, args=(ip, tags),
            daemon=True, name="installer"
        ).start()

    def _install_worker(self, server_ip: str, tags: list):
        try:
            # ── 1. Crear directorios ───────────────────────────────────────
            self._set_status("📁 Creando directorios...", C["cyn"])
            self._log(f"Directorio de instalación: {INSTALL_DIR}")
            INSTALL_DIR.mkdir(parents=True, exist_ok=True)
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)

            # ── 2. Copiar agent.py ─────────────────────────────────────────
            self._set_status("📋 Copiando archivos...", C["cyn"])
            if getattr(sys, "frozen", False):
                # Empaquetado como .exe — agent.py está en _MEIPASS
                src = Path(sys._MEIPASS) / "agent.py"
                if src.exists():
                    shutil.copy2(src, INSTALL_DIR / "agent.py")
                    self._log("agent.py copiado desde bundle")
                else:
                    raise FileNotFoundError("agent.py no encontrado en el bundle")
            else:
                # Desarrollo: copiar el archivo real
                src = _BASE / "agent.py"
                shutil.copy2(src, INSTALL_DIR / "agent.py")
                self._log(f"agent.py copiado desde {src}")

            # ── 3. Guardar configuración ───────────────────────────────────
            self._set_status("⚙️  Guardando configuración...", C["cyn"])
            cfg = {
                "server_url": f"http://{server_ip}:8000",
                "tags":       tags,
                "version":    VERSION,
                "installed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
            save_config(cfg)
            self._log(f"Config guardada: {CONFIG_DIR / 'config.json'}")
            self._log(f"Tags: {tags or '(ninguna)'}")

            # ── 4. Instalar Python si es necesario ─────────────────────────
            python_exe = self._find_python()
            if not python_exe:
                self._set_status("🐍 Instalando Python...", C["cyn"])
                python_exe = self._install_python()
            self._log(f"Python: {python_exe}")

            # ── 5. Instalar dependencias ───────────────────────────────────
            self._set_status("📦 Instalando dependencias...", C["cyn"])
            subprocess.run(
                [python_exe, "-m", "pip", "install", "psutil", "pywin32", "-q"],
                capture_output=True, timeout=120
            )
            self._log("psutil y pywin32 instalados")

            # ── 6. Registrar servicio Windows ──────────────────────────────
            self._set_status("⚙️  Registrando servicio Windows...", C["cyn"])
            self._install_windows_service(python_exe)

            # ── 7. Iniciar servicio ────────────────────────────────────────
            self._set_status("▶️  Iniciando servicio...", C["cyn"])
            result = subprocess.run(
                ["sc", "start", SERVICE_NAME],
                capture_output=True, text=True, timeout=30
            )
            time.sleep(3)

            # ── 8. Verificar ───────────────────────────────────────────────
            r = subprocess.run(
                ["sc", "query", SERVICE_NAME],
                capture_output=True, text=True
            )
            if "RUNNING" in r.stdout:
                self._log("✅ Servicio RUNNING")
                self.root.after(0, self._install_success, server_ip)
            else:
                self._log("⚠️  Servicio instalado pero no corriendo")
                self.root.after(0, self._install_warning, server_ip)

        except Exception as e:
            self._log(f"ERROR: {e}")
            self.root.after(0, self._install_error, str(e))

    def _find_python(self) -> str:
        """Busca un Python 3.8+ instalado en el sistema"""
        candidates = [
            sys.executable,
            r"C:\Python312\python.exe",
            r"C:\Python311\python.exe",
            r"C:\Python310\python.exe",
            r"C:\Python39\python.exe",
            r"C:\Python38\python.exe",
        ]
        # Agregar Python de PATH
        try:
            r = subprocess.run(["where", "python3"], capture_output=True, text=True)
            if r.returncode == 0:
                candidates.insert(0, r.stdout.strip().splitlines()[0])
            r2 = subprocess.run(["where", "python"], capture_output=True, text=True)
            if r2.returncode == 0:
                candidates.insert(0, r2.stdout.strip().splitlines()[0])
        except Exception:
            pass

        for p in candidates:
            if p and os.path.exists(p):
                try:
                    r = subprocess.run([p, "--version"], capture_output=True, text=True, timeout=5)
                    ver_str = r.stdout + r.stderr
                    if "Python 3." in ver_str:
                        major, minor = int(ver_str.split("Python 3.")[1].split(".")[0]), 0
                        return p
                except Exception:
                    pass
        return ""

    def _install_python(self) -> str:
        """Descarga e instala Python 3.12 via winget (requiere Win10+)"""
        self._log("Intentando instalar Python via winget...")
        r = subprocess.run(
            ["winget", "install", "Python.Python.3.12", "--silent", "--accept-package-agreements"],
            capture_output=True, text=True, timeout=300
        )
        if r.returncode == 0:
            return r"C:\Python312\python.exe"
        raise RuntimeError(
            "No se pudo instalar Python automáticamente.\n"
            "Instala Python 3.8+ desde https://python.org y vuelve a ejecutar el instalador."
        )

    def _install_windows_service(self, python_exe: str):
        """Crea y configura el servicio Windows"""
        # Usar PyInstaller si está disponible para crear iw-agent.exe
        agent_script = str(INSTALL_DIR / "agent.py")
        bin_path     = f'"{python_exe}" "{agent_script}" --run'

        # Detener y eliminar servicio anterior
        subprocess.run(["sc", "stop", SERVICE_NAME],
                       capture_output=True, timeout=15)
        subprocess.run(["sc", "delete", SERVICE_NAME],
                       capture_output=True, timeout=15)
        time.sleep(2)

        # Crear nuevo servicio
        r = subprocess.run([
            "sc", "create", SERVICE_NAME,
            f"binPath= {bin_path}",
            f"DisplayName= InfraWatch Agent v{VERSION}",
            "start= auto",
            "obj= LocalSystem",
        ], capture_output=True, text=True, timeout=20)

        if r.returncode != 0:
            raise RuntimeError(f"sc create falló: {r.stdout} {r.stderr}")

        # Descripción
        subprocess.run([
            "sc", "description", SERVICE_NAME,
            "Agente de monitoreo InfraWatch - IT Infrastructure Monitor"
        ], capture_output=True)

        # Reintentar en caso de falla
        subprocess.run([
            "sc", "failure", SERVICE_NAME,
            "reset= 3600", "actions= restart/5000/restart/10000/restart/30000"
        ], capture_output=True)

        self._log(f"Servicio '{SERVICE_NAME}' creado correctamente")

    # ── Resultados de instalación ─────────────────────────────────────────

    def _install_success(self, server_ip: str):
        self.progress.config(mode="determinate", value=100)
        style = ttk.Style()
        style.configure("IW.Horizontal.TProgressbar", background=C["grn"])
        self._set_status("✅ Instalación completada — Agente activo", C["grn"])
        self.btn.config(
            text="✅  Instalado correctamente",
            bg=C["grn"], state="disabled"
        )
        messagebox.showinfo(
            "✅ Instalación exitosa",
            f"InfraWatch Agent v{VERSION} instalado correctamente.\n\n"
            f"El agente está activo y reportando a:\n{server_ip}:8000\n\n"
            f"Puedes cerrar esta ventana."
        )

    def _install_warning(self, server_ip: str):
        self._set_status("⚠️  Instalado — verifica el servicio", C["ylw"])
        self.btn.config(text="⚠️  Instalado con advertencias", bg=C["ylw"],
                        fg="#000", state="disabled")
        messagebox.showwarning(
            "⚠️ Instalado con advertencias",
            f"El agente fue instalado en {INSTALL_DIR}\n\n"
            f"El servicio no pudo iniciar automáticamente.\n\n"
            f"Para iniciarlo manualmente:\n"
            f"  sc start {SERVICE_NAME}\n\n"
            f"O verifica los logs en:\n  {CONFIG_DIR / 'agent.log'}"
        )

    def _install_error(self, err: str):
        self._set_status(f"❌ Error en instalación", C["red"])
        self.btn.config(
            text="↺  Reintentar", bg=C["bg3"], fg=C["red"],
            state="normal"
        )
        messagebox.showerror(
            "Error de instalación",
            f"Ocurrió un error:\n\n{err}\n\n"
            f"Verifica que ejecutas como Administrador\n"
            f"y que tienes conexión de red al servidor."
        )


# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    InstallerApp()
