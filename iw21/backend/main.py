"""
InfraWatch v2.1 — Backend Completo
Nuevas funciones v2.1:
  ✦ Historial completo de asignaciones por empleado
  ✦ Alta y Baja de equipos con carta PDF
  ✦ Subida de carta firmada (alta/baja)
  ✦ Mantenimiento auto-programado 1 año al registrar agente
  ✦ Alertas de mantenimiento próximo (dashboard + email)
  ✦ Empleados: activar/desactivar, historial de equipos
  ✦ Correo automático carta responsiva en asignación
  ✦ Recordatorio por correo 30 días antes del mantenimiento
"""

from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks, Request, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Text, Boolean, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session, relationship
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timedelta, date
import jwt, bcrypt, os, json, uuid, smtplib, logging, shutil
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication

# ─── CONFIG ───────────────────────────────────────────────────────────────────
DATABASE_URL  = os.getenv("DATABASE_URL", "sqlite:////opt/infrawatch/data/infrawatch.db")
SECRET_KEY    = os.getenv("SECRET_KEY", "infrawatch-secret-2024")
JWT_ALGO      = "HS256"
JWT_EXP_HRS   = 24
VERSION       = "2.1.0"
APP_NAME      = "InfraWatch"
UPLOAD_DIR    = "/opt/infrawatch/data/uploads"
MAINT_MONTHS  = 12   # meses entre mantenimientos
MAINT_WARN_DAYS = 30 # días antes para alertar

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs("/opt/infrawatch/data", exist_ok=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

# ─── DATABASE ─────────────────────────────────────────────────────────────────
engine       = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base         = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ─── MODELS ───────────────────────────────────────────────────────────────────

class Personnel(Base):
    __tablename__ = "personnel"
    id             = Column(Integer, primary_key=True, index=True)
    employee_id    = Column(String, unique=True, index=True)
    full_name      = Column(String, index=True)
    position       = Column(String, default="")
    department     = Column(String, default="")
    email          = Column(String, default="")
    phone          = Column(String, default="")
    location       = Column(String, default="")
    is_active      = Column(Boolean, default=True)
    notes          = Column(Text, default="")
    created_at     = Column(DateTime, default=datetime.utcnow)
    assets         = relationship("Asset", back_populates="personnel")
    history        = relationship("AssetHistory", back_populates="personnel", cascade="all, delete")

class Agent(Base):
    __tablename__ = "agents"
    id            = Column(Integer, primary_key=True, index=True)
    uid           = Column(String, unique=True, index=True, default=lambda: str(uuid.uuid4()))
    hostname      = Column(String, index=True)
    ip_address    = Column(String)
    mac_address   = Column(String)
    os_name       = Column(String)
    os_version    = Column(String)
    cpu_model     = Column(String)
    cpu_cores     = Column(Integer)
    ram_total_gb  = Column(Float)
    disk_total_gb = Column(Float)
    tags          = Column(Text, default="[]")
    status        = Column(String, default="online")
    last_seen     = Column(DateTime, default=datetime.utcnow)
    registered_at = Column(DateTime, default=datetime.utcnow)
    agent_version = Column(String, default="1.0")
    metrics       = relationship("Metric", back_populates="agent", cascade="all, delete")
    asset         = relationship("Asset", back_populates="agent", uselist=False)

class Metric(Base):
    __tablename__ = "metrics"
    id              = Column(Integer, primary_key=True, index=True)
    agent_id        = Column(Integer, ForeignKey("agents.id"))
    timestamp       = Column(DateTime, default=datetime.utcnow)
    cpu_percent     = Column(Float, default=0)
    ram_percent     = Column(Float, default=0)
    disk_percent    = Column(Float, default=0)
    net_bytes_sent  = Column(Float, default=0)
    net_bytes_recv  = Column(Float, default=0)
    uptime_seconds  = Column(Float, default=0)
    process_count   = Column(Integer, default=0)
    open_ports      = Column(Text, default="[]")
    agent           = relationship("Agent", back_populates="metrics")

class Asset(Base):
    __tablename__ = "assets"
    id               = Column(Integer, primary_key=True, index=True)
    asset_code       = Column(String, unique=True, index=True)
    asset_type       = Column(String)
    brand            = Column(String, default="")
    model            = Column(String, default="")
    serial_number    = Column(String, default="")
    purchase_date    = Column(String, default="")
    purchase_cost    = Column(Float, default=0)
    responsible      = Column(String, default="")
    personnel_id     = Column(Integer, ForeignKey("personnel.id"), nullable=True)
    location         = Column(String, default="")
    status           = Column(String, default="active")
    notes            = Column(Text, default="")
    auto_created     = Column(Boolean, default=False)
    # Carta responsiva
    carta_sent       = Column(Boolean, default=False)
    carta_sent_at    = Column(DateTime, nullable=True)
    carta_alta_path  = Column(String, default="")   # carta firmada de alta subida
    carta_baja_path  = Column(String, default="")   # carta firmada de baja subida
    # Timestamps
    assigned_at      = Column(DateTime, nullable=True)
    unassigned_at    = Column(DateTime, nullable=True)
    created_at       = Column(DateTime, default=datetime.utcnow)
    agent_id         = Column(Integer, ForeignKey("agents.id"), nullable=True)
    personnel        = relationship("Personnel", back_populates="assets")
    agent            = relationship("Agent", back_populates="asset")
    maintenances     = relationship("Maintenance", back_populates="asset", cascade="all, delete")
    history          = relationship("AssetHistory", back_populates="asset", cascade="all, delete")

class AssetHistory(Base):
    """Historial completo de asignaciones/bajas por activo y por empleado"""
    __tablename__ = "asset_history"
    id             = Column(Integer, primary_key=True, index=True)
    asset_id       = Column(Integer, ForeignKey("assets.id"))
    personnel_id   = Column(Integer, ForeignKey("personnel.id"), nullable=True)
    action         = Column(String)   # alta / baja
    action_date    = Column(DateTime, default=datetime.utcnow)
    notes          = Column(Text, default="")
    carta_path     = Column(String, default="")  # carta firmada asociada
    created_by     = Column(String, default="")  # usuario que realizó la acción
    asset          = relationship("Asset", back_populates="history")
    personnel      = relationship("Personnel", back_populates="history")

class Maintenance(Base):
    __tablename__ = "maintenances"
    id               = Column(Integer, primary_key=True, index=True)
    asset_id         = Column(Integer, ForeignKey("assets.id"))
    maintenance_date = Column(String)
    next_date        = Column(String, nullable=True)
    technician       = Column(String, default="")
    maint_type       = Column(String, default="preventive")
    observations     = Column(Text, default="")
    status           = Column(String, default="completed")
    auto_created     = Column(Boolean, default=False)
    email_sent       = Column(Boolean, default=False)   # si ya se envió aviso
    created_at       = Column(DateTime, default=datetime.utcnow)
    asset            = relationship("Asset", back_populates="maintenances")

class Alert(Base):
    __tablename__ = "alerts"
    id           = Column(Integer, primary_key=True, index=True)
    agent_id     = Column(Integer, ForeignKey("agents.id"), nullable=True)
    alert_type   = Column(String)
    severity     = Column(String, default="warning")
    message      = Column(Text)
    acknowledged = Column(Boolean, default=False)
    created_at   = Column(DateTime, default=datetime.utcnow)

class User(Base):
    __tablename__ = "users"
    id            = Column(Integer, primary_key=True, index=True)
    username      = Column(String, unique=True, index=True)
    password_hash = Column(String)
    full_name     = Column(String, default="")
    email         = Column(String, default="")
    role          = Column(String, default="viewer")
    is_active     = Column(Boolean, default=True)
    created_at    = Column(DateTime, default=datetime.utcnow)

class SMTPConfig(Base):
    __tablename__ = "smtp_config"
    id         = Column(Integer, primary_key=True)
    host       = Column(String, default="smtp.gmail.com")
    port       = Column(Integer, default=587)
    username   = Column(String, default="")
    password   = Column(String, default="")
    from_name  = Column(String, default="InfraWatch")
    company    = Column(String, default="Mi Empresa")
    enabled    = Column(Boolean, default=False)

Base.metadata.create_all(bind=engine)

# ─── SCHEMAS ──────────────────────────────────────────────────────────────────

class PersonnelSchema(BaseModel):
    employee_id: str
    full_name:   str
    position:    Optional[str] = ""
    department:  Optional[str] = ""
    email:       Optional[str] = ""
    phone:       Optional[str] = ""
    location:    Optional[str] = ""
    is_active:   Optional[bool] = True
    notes:       Optional[str] = ""

class AgentRegisterSchema(BaseModel):
    hostname:      str
    ip_address:    str
    mac_address:   str
    os_name:       Optional[str] = ""
    os_version:    Optional[str] = ""
    cpu_model:     Optional[str] = ""
    cpu_cores:     Optional[int] = 0
    ram_total_gb:  Optional[float] = 0
    disk_total_gb: Optional[float] = 0
    agent_version: Optional[str] = "1.0"

class HeartbeatSchema(BaseModel):
    cpu_percent:    float = 0
    ram_percent:    float = 0
    disk_percent:   float = 0
    net_bytes_sent: float = 0
    net_bytes_recv: float = 0
    uptime_seconds: float = 0
    process_count:  int   = 0
    open_ports:     List[int] = []

class AssetSchema(BaseModel):
    asset_type:    str
    brand:         Optional[str] = ""
    model:         Optional[str] = ""
    serial_number: Optional[str] = ""
    purchase_date: Optional[str] = ""
    purchase_cost: Optional[float] = 0
    responsible:   Optional[str] = ""
    personnel_id:  Optional[int] = None
    location:      Optional[str] = ""
    status:        Optional[str] = "active"
    notes:         Optional[str] = ""
    agent_id:      Optional[int] = None

class AssetAssignSchema(BaseModel):
    personnel_id: int
    send_email:   Optional[bool] = True
    notes:        Optional[str] = ""

class AssetBajaSchema(BaseModel):
    notes:      Optional[str] = ""
    send_email: Optional[bool] = True

class MaintenanceSchema(BaseModel):
    asset_id:         int
    maintenance_date: str
    next_date:        Optional[str] = None
    technician:       Optional[str] = ""
    maint_type:       Optional[str] = "preventive"
    observations:     Optional[str] = ""
    status:           Optional[str] = "completed"

class UserLoginSchema(BaseModel):
    username: str
    password: str

class UserCreateSchema(BaseModel):
    username:  str
    password:  str
    full_name: Optional[str] = ""
    email:     Optional[str] = ""
    role:      Optional[str] = "viewer"

class TagUpdateSchema(BaseModel):
    tags: List[str]

class SMTPConfigSchema(BaseModel):
    host:      str
    port:      int
    username:  str
    password:  Optional[str] = ""
    from_name: Optional[str] = "InfraWatch"
    company:   Optional[str] = "Mi Empresa"
    enabled:   Optional[bool] = True

# ─── AUTH ─────────────────────────────────────────────────────────────────────
security = HTTPBearer(auto_error=False)

def create_token(uid, username, role):
    return jwt.encode({"sub": str(uid), "username": username, "role": role,
                        "exp": datetime.utcnow() + timedelta(hours=JWT_EXP_HRS)},
                       SECRET_KEY, algorithm=JWT_ALGO)

def decode_token(token):
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[JWT_ALGO])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expirado")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Token inválido")

def get_current_user(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
                     db: Session = Depends(get_db)):
    if not credentials:
        raise HTTPException(status_code=401, detail="No autenticado")
    p = decode_token(credentials.credentials)
    u = db.query(User).filter(User.id == int(p["sub"])).first()
    if not u or not u.is_active:
        raise HTTPException(status_code=401, detail="Usuario no válido")
    return u

def require_admin(user: User = Depends(get_current_user)):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Se requiere rol admin")
    return user

def hash_password(pw): return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()
def verify_password(pw, h): return bcrypt.checkpw(pw.encode(), h.encode())

# ─── SMTP ─────────────────────────────────────────────────────────────────────

def get_smtp(db):
    cfg = db.query(SMTPConfig).first()
    if not cfg:
        cfg = SMTPConfig(); db.add(cfg); db.commit(); db.refresh(cfg)
    return cfg

def send_email(to_email: str, subject: str, html_body: str, db: Session,
               attachment_path: str = None, attachment_name: str = None):
    cfg = get_smtp(db)
    if not cfg.enabled or not cfg.username:
        log.warning("SMTP no configurado")
        return False
    try:
        msg = MIMEMultipart("mixed")
        msg["Subject"] = subject
        msg["From"]    = f"{cfg.from_name} <{cfg.username}>"
        msg["To"]      = to_email
        msg.attach(MIMEText(html_body, "html", "utf-8"))
        # Attach file if provided
        if attachment_path and os.path.exists(attachment_path):
            with open(attachment_path, "rb") as f:
                part = MIMEApplication(f.read(), _subtype="html")
                part.add_header("Content-Disposition", "attachment",
                                 filename=attachment_name or os.path.basename(attachment_path))
                msg.attach(part)
        with smtplib.SMTP(cfg.host, cfg.port, timeout=15) as srv:
            srv.starttls()
            srv.login(cfg.username, cfg.password)
            srv.sendmail(cfg.username, [to_email], msg.as_string())
        log.info(f"✉ Email → {to_email}: {subject}")
        return True
    except Exception as e:
        log.error(f"Email error: {e}")
        return False

# ─── CARTAS HTML ──────────────────────────────────────────────────────────────

def _carta_base_style():
    return """
    <style>
      @page { size: letter; margin: 2cm; }
      body { font-family: Arial, sans-serif; color: #1a1a1a; margin: 0; padding: 32px; font-size: 13px; line-height: 1.5; }
      .header { text-align: center; border-bottom: 3px solid #1a56db; padding-bottom: 16px; margin-bottom: 24px; }
      .company { font-size: 20px; font-weight: 900; color: #1a56db; letter-spacing: 1px; }
      .dept { font-size: 13px; color: #555; margin-top: 4px; }
      .folio { text-align: right; font-size: 11px; color: #777; margin-bottom: 16px; font-family: monospace; }
      .doc-title { font-size: 16px; font-weight: 800; text-align: center; text-transform: uppercase;
                   letter-spacing: 1px; margin: 16px 0; padding: 10px; background: #f0f4ff; border-radius: 4px; }
      .intro { margin-bottom: 20px; text-align: justify; }
      .section-title { font-weight: 700; background: #f0f4ff; padding: 6px 12px;
                        border-left: 4px solid #1a56db; margin: 16px 0 8px; font-size: 12px;
                        text-transform: uppercase; letter-spacing: .5px; }
      table { width: 100%; border-collapse: collapse; margin-bottom: 16px; }
      td, th { border: 1px solid #ddd; padding: 7px 12px; font-size: 12px; }
      th { background: #f0f4ff; font-weight: 700; width: 38%; }
      .terms { font-size: 11px; color: #444; border: 1px solid #ddd; padding: 12px;
               background: #fafafa; border-radius: 4px; margin-top: 16px; }
      .terms ol { padding-left: 20px; }
      .terms li { margin-bottom: 5px; }
      .firma-section { display: flex; justify-content: space-around; margin-top: 56px; }
      .firma-box { text-align: center; width: 42%; }
      .firma-line { border-top: 1px solid #333; padding-top: 8px; margin-top: 56px; font-size: 11px; }
      .footer { text-align: center; font-size: 10px; color: #999; margin-top: 32px;
                border-top: 1px solid #eee; padding-top: 10px; }
      .badge-alta { background: #d4edda; color: #155724; border: 1px solid #c3e6cb;
                    padding: 4px 12px; border-radius: 4px; font-weight: 700; display: inline-block; }
      .badge-baja { background: #f8d7da; color: #721c24; border: 1px solid #f5c6cb;
                    padding: 4px 12px; border-radius: 4px; font-weight: 700; display: inline-block; }
      @media print { body { padding: 0; } .no-print { display: none !important; } }
    </style>"""

def generate_carta_alta(asset, person, company):
    today = datetime.now().strftime("%d de %B de %Y")
    atype = {"laptop":"Laptop","pc":"Computadora","server":"Servidor","switch":"Switch",
              "firewall":"Firewall","printer":"Impresora"}.get(asset.asset_type, "Equipo")
    hostname = asset.agent.hostname if asset.agent else "—"
    ip       = asset.agent.ip_address if asset.agent else "—"
    mac      = asset.agent.mac_address if asset.agent else "—"
    so       = f"{asset.agent.os_name} {asset.agent.os_version or ''}" if asset.agent else "—"
    folio    = f"ALTA-{asset.asset_code}-{datetime.now().strftime('%Y%m%d%H%M')}"

    return f"""<!DOCTYPE html><html lang="es"><head><meta charset="UTF-8">
    <title>Carta de Alta — {asset.asset_code}</title>{_carta_base_style()}</head><body>
    <div class="no-print" style="text-align:center;padding:12px;background:#1a56db;color:#fff;margin-bottom:20px;cursor:pointer"
         onclick="window.print()">🖨 Imprimir / Guardar como PDF</div>
    <div class="header">
      <div class="company">{company}</div>
      <div class="dept">Departamento de Tecnologías de Información</div>
    </div>
    <div class="folio">Folio: {folio}</div>
    <div class="doc-title">📋 Carta de Alta — Resguardo de Equipo</div>
    <div style="text-align:center;margin-bottom:16px"><span class="badge-alta">✅ ALTA DE EQUIPO</span></div>
    <p class="intro">Por medio del presente documento, yo <strong>{person.full_name}</strong>,
    con número de empleado <strong>{person.employee_id}</strong>, declaro haber recibido en
    conformidad el siguiente equipo de cómputo asignado por {company}, comprometiéndome a su
    cuidado y uso exclusivo para actividades laborales.</p>

    <div class="section-title">Datos del Responsable</div>
    <table>
      <tr><th>Nombre Completo</th><td>{person.full_name}</td></tr>
      <tr><th>Número de Empleado</th><td>{person.employee_id}</td></tr>
      <tr><th>Puesto</th><td>{person.position}</td></tr>
      <tr><th>Departamento</th><td>{person.department}</td></tr>
      <tr><th>Ubicación</th><td>{person.location or "—"}</td></tr>
      <tr><th>Correo</th><td>{person.email}</td></tr>
      <tr><th>Teléfono</th><td>{person.phone or "—"}</td></tr>
    </table>

    <div class="section-title">Datos del Equipo</div>
    <table>
      <tr><th>Código de Activo</th><td><strong>{asset.asset_code}</strong></td></tr>
      <tr><th>Tipo</th><td>{atype}</td></tr>
      <tr><th>Marca</th><td>{asset.brand or "—"}</td></tr>
      <tr><th>Modelo</th><td>{asset.model or "—"}</td></tr>
      <tr><th>Número de Serie</th><td>{asset.serial_number or "—"}</td></tr>
      <tr><th>Hostname</th><td>{hostname}</td></tr>
      <tr><th>Dirección IP</th><td>{ip}</td></tr>
      <tr><th>MAC Address</th><td>{mac}</td></tr>
      <tr><th>Sistema Operativo</th><td>{so}</td></tr>
      <tr><th>Ubicación Asignada</th><td>{asset.location or "—"}</td></tr>
      <tr><th>Fecha de Alta</th><td><strong>{today}</strong></td></tr>
    </table>

    <div class="terms"><strong>El responsable acepta las siguientes condiciones:</strong>
    <ol>
      <li>El equipo es propiedad de {company} y se usará exclusivamente para actividades laborales.</li>
      <li>Deberá notificar de inmediato al área de TI cualquier falla, pérdida, robo o daño.</li>
      <li>Queda prohibida la instalación de software no autorizado por TI.</li>
      <li>El equipo deberá devolverse en las mismas condiciones al concluir la relación laboral.</li>
      <li>El área de TI puede realizar auditorías y monitoreo del equipo en cualquier momento.</li>
      <li>El responsable no podrá prestar el equipo a terceros sin autorización de TI.</li>
    </ol></div>

    <div class="firma-section">
      <div class="firma-box">
        <div class="firma-line"><strong>{person.full_name}</strong><br>
        {person.employee_id} — {person.position}<br><em>Firma de recibido</em></div>
      </div>
      <div class="firma-box">
        <div class="firma-line"><strong>Responsable de TI</strong><br>
        Departamento de TI — {company}<br><em>Entregó</em></div>
      </div>
    </div>
    <div class="footer">Documento generado por InfraWatch v2.1 — {company} — {today} — Folio: {folio}</div>
    </body></html>"""

def generate_carta_baja(asset, person, company, notes=""):
    today = datetime.now().strftime("%d de %B de %Y")
    atype = {"laptop":"Laptop","pc":"Computadora","server":"Servidor","switch":"Switch",
              "firewall":"Firewall","printer":"Impresora"}.get(asset.asset_type, "Equipo")
    folio = f"BAJA-{asset.asset_code}-{datetime.now().strftime('%Y%m%d%H%M')}"
    assigned_str = asset.assigned_at.strftime("%d/%m/%Y") if asset.assigned_at else "—"

    return f"""<!DOCTYPE html><html lang="es"><head><meta charset="UTF-8">
    <title>Carta de Baja — {asset.asset_code}</title>{_carta_base_style()}</head><body>
    <div class="no-print" style="text-align:center;padding:12px;background:#dc3545;color:#fff;margin-bottom:20px;cursor:pointer"
         onclick="window.print()">🖨 Imprimir / Guardar como PDF</div>
    <div class="header">
      <div class="company">{company}</div>
      <div class="dept">Departamento de Tecnologías de Información</div>
    </div>
    <div class="folio">Folio: {folio}</div>
    <div class="doc-title">📋 Carta de Baja — Devolución de Equipo</div>
    <div style="text-align:center;margin-bottom:16px"><span class="badge-baja">🔴 BAJA DE EQUIPO</span></div>
    <p class="intro">Por medio del presente documento, yo <strong>{person.full_name}</strong>,
    con número de empleado <strong>{person.employee_id}</strong>, declaro haber entregado
    en conformidad el siguiente equipo de cómputo al Departamento de TI de {company}.</p>

    <div class="section-title">Datos del Empleado</div>
    <table>
      <tr><th>Nombre Completo</th><td>{person.full_name}</td></tr>
      <tr><th>Número de Empleado</th><td>{person.employee_id}</td></tr>
      <tr><th>Puesto</th><td>{person.position}</td></tr>
      <tr><th>Departamento</th><td>{person.department}</td></tr>
    </table>

    <div class="section-title">Datos del Equipo Devuelto</div>
    <table>
      <tr><th>Código de Activo</th><td><strong>{asset.asset_code}</strong></td></tr>
      <tr><th>Tipo</th><td>{atype}</td></tr>
      <tr><th>Marca / Modelo</th><td>{asset.brand} {asset.model}</td></tr>
      <tr><th>Número de Serie</th><td>{asset.serial_number or "—"}</td></tr>
      <tr><th>Fecha de Alta</th><td>{assigned_str}</td></tr>
      <tr><th>Fecha de Baja</th><td><strong>{today}</strong></td></tr>
      <tr><th>Motivo / Observaciones</th><td>{notes or "Baja de equipo"}</td></tr>
    </table>

    <p>Ambas partes confirman que el equipo ha sido revisado y devuelto en las condiciones acordadas.</p>

    <div class="firma-section">
      <div class="firma-box">
        <div class="firma-line"><strong>{person.full_name}</strong><br>
        {person.employee_id} — {person.position}<br><em>Firma de entrega</em></div>
      </div>
      <div class="firma-box">
        <div class="firma-line"><strong>Responsable de TI</strong><br>
        Departamento de TI — {company}<br><em>Recibió</em></div>
      </div>
    </div>
    <div class="footer">Documento generado por InfraWatch v2.1 — {company} — {today} — Folio: {folio}</div>
    </body></html>"""

# ─── EMAIL TEMPLATES ──────────────────────────────────────────────────────────

def email_alta_html(asset, person, company, carta_url):
    return f"""<div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;background:#f5f7fa;padding:20px">
    <div style="background:#1a56db;color:#fff;padding:24px;border-radius:8px 8px 0 0;text-align:center">
      <h1 style="margin:0;font-size:22px">🛡 InfraWatch — {company}</h1>
      <p style="margin:6px 0 0;opacity:.9">Asignación de Equipo de Cómputo</p>
    </div>
    <div style="background:#fff;padding:28px;border-radius:0 0 8px 8px">
      <p>Estimado/a <strong>{person.full_name}</strong>,</p>
      <p>Se le ha asignado el siguiente equipo. Por favor imprima la carta, fírmela y entréguela al área de TI.</p>
      <table style="width:100%;border-collapse:collapse;margin:16px 0">
        <tr style="background:#f0f4ff"><td style="padding:8px 12px;font-weight:700;border:1px solid #ddd;width:40%">Código Activo</td>
            <td style="padding:8px 12px;border:1px solid #ddd"><strong>{asset.asset_code}</strong></td></tr>
        <tr><td style="padding:8px 12px;font-weight:700;border:1px solid #ddd">Equipo</td>
            <td style="padding:8px 12px;border:1px solid #ddd">{asset.asset_type} — {asset.brand} {asset.model}</td></tr>
        <tr style="background:#f0f4ff"><td style="padding:8px 12px;font-weight:700;border:1px solid #ddd">Hostname</td>
            <td style="padding:8px 12px;border:1px solid #ddd">{asset.agent.hostname if asset.agent else '—'}</td></tr>
        <tr><td style="padding:8px 12px;font-weight:700;border:1px solid #ddd">IP</td>
            <td style="padding:8px 12px;border:1px solid #ddd">{asset.agent.ip_address if asset.agent else '—'}</td></tr>
      </table>
      <div style="text-align:center;margin:24px 0">
        <a href="{carta_url}" style="background:#1a56db;color:#fff;padding:14px 28px;border-radius:6px;text-decoration:none;font-weight:700">
          📄 Ver e Imprimir Carta de Alta
        </a>
      </div>
      <p style="color:#666;font-size:12px">Si tiene dudas, comuníquese con el área de TI.</p>
    </div></div>"""

def email_baja_html(asset, person, company, carta_url):
    return f"""<div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;background:#f5f7fa;padding:20px">
    <div style="background:#dc3545;color:#fff;padding:24px;border-radius:8px 8px 0 0;text-align:center">
      <h1 style="margin:0;font-size:22px">🛡 InfraWatch — {company}</h1>
      <p style="margin:6px 0 0;opacity:.9">Baja de Equipo de Cómputo</p>
    </div>
    <div style="background:#fff;padding:28px;border-radius:0 0 8px 8px">
      <p>Estimado/a <strong>{person.full_name}</strong>,</p>
      <p>Se ha procesado la <strong>baja del equipo</strong> a su nombre. Por favor imprima la carta y fírmela.</p>
      <table style="width:100%;border-collapse:collapse;margin:16px 0">
        <tr style="background:#fff5f5"><td style="padding:8px 12px;font-weight:700;border:1px solid #ddd;width:40%">Código Activo</td>
            <td style="padding:8px 12px;border:1px solid #ddd"><strong>{asset.asset_code}</strong></td></tr>
        <tr><td style="padding:8px 12px;font-weight:700;border:1px solid #ddd">Equipo</td>
            <td style="padding:8px 12px;border:1px solid #ddd">{asset.asset_type} — {asset.brand} {asset.model}</td></tr>
        <tr style="background:#fff5f5"><td style="padding:8px 12px;font-weight:700;border:1px solid #ddd">Fecha de Baja</td>
            <td style="padding:8px 12px;border:1px solid #ddd">{datetime.now().strftime('%d/%m/%Y')}</td></tr>
      </table>
      <div style="text-align:center;margin:24px 0">
        <a href="{carta_url}" style="background:#dc3545;color:#fff;padding:14px 28px;border-radius:6px;text-decoration:none;font-weight:700">
          📄 Ver e Imprimir Carta de Baja
        </a>
      </div>
    </div></div>"""

def email_mantenimiento_html(asset, person, company, days_left, next_date):
    urgency_color = "#dc3545" if days_left <= 7 else "#fd7e14" if days_left <= 14 else "#ffc107"
    return f"""<div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;background:#f5f7fa;padding:20px">
    <div style="background:{urgency_color};color:#fff;padding:24px;border-radius:8px 8px 0 0;text-align:center">
      <h1 style="margin:0;font-size:22px">⚠️ InfraWatch — {company}</h1>
      <p style="margin:6px 0 0;opacity:.9">Aviso de Mantenimiento Preventivo</p>
    </div>
    <div style="background:#fff;padding:28px;border-radius:0 0 8px 8px">
      <p>Estimado/a <strong>{person.full_name}</strong>,</p>
      <p>Le informamos que el equipo a su cargo requiere <strong>mantenimiento preventivo</strong>
      en <strong style="color:{urgency_color}">{days_left} días</strong>.</p>
      <table style="width:100%;border-collapse:collapse;margin:16px 0">
        <tr style="background:#fff8e1"><td style="padding:8px 12px;font-weight:700;border:1px solid #ddd;width:40%">Código Activo</td>
            <td style="padding:8px 12px;border:1px solid #ddd"><strong>{asset.asset_code}</strong></td></tr>
        <tr><td style="padding:8px 12px;font-weight:700;border:1px solid #ddd">Equipo</td>
            <td style="padding:8px 12px;border:1px solid #ddd">{asset.asset_type} — {asset.brand} {asset.model}</td></tr>
        <tr style="background:#fff8e1"><td style="padding:8px 12px;font-weight:700;border:1px solid #ddd">Hostname</td>
            <td style="padding:8px 12px;border:1px solid #ddd">{asset.agent.hostname if asset.agent else '—'}</td></tr>
        <tr><td style="padding:8px 12px;font-weight:700;border:1px solid #ddd;color:{urgency_color}">📅 Fecha Límite</td>
            <td style="padding:8px 12px;border:1px solid #ddd;font-weight:700;color:{urgency_color}">{next_date}</td></tr>
      </table>
      <p>Por favor coordine con el área de TI para programar el mantenimiento preventivo a tiempo.</p>
    </div></div>"""

# ─── MANTENIMIENTO AUTO ────────────────────────────────────────────────────────

def create_auto_maintenance(db, asset_id):
    """Crea mantenimiento preventivo automático a 1 año"""
    today     = date.today()
    next_date = date(today.year + 1, today.month, today.day)
    # Evitar duplicado
    existing = db.query(Maintenance).filter(
        Maintenance.asset_id == asset_id,
        Maintenance.auto_created == True,
        Maintenance.status == "pending"
    ).first()
    if existing:
        return existing
    m = Maintenance(
        asset_id         = asset_id,
        maintenance_date = today.strftime("%Y-%m-%d"),
        next_date        = next_date.strftime("%Y-%m-%d"),
        technician       = "TI",
        maint_type       = "preventive",
        observations     = "Mantenimiento preventivo anual generado automáticamente al registrar el equipo.",
        status           = "pending",
        auto_created     = True,
    )
    db.add(m)
    return m

def check_maintenance_alerts(db):
    """Revisa mantenimientos próximos y genera alertas + emails"""
    today     = date.today()
    warn_date = today + timedelta(days=MAINT_WARN_DAYS)

    pending = db.query(Maintenance).filter(
        Maintenance.status == "pending",
        Maintenance.next_date != None,
    ).all()

    for m in pending:
        try:
            nd = datetime.strptime(m.next_date, "%Y-%m-%d").date()
        except:
            continue
        days_left = (nd - today).days
        if days_left < 0:
            # Vencido
            _create_alert_if_new(db, None, "maintenance_overdue", "critical",
                f"⚠ Mantenimiento VENCIDO: {m.asset.asset_code if m.asset else ''} (venció {abs(days_left)} días)")
        elif days_left <= MAINT_WARN_DAYS:
            _create_alert_if_new(db, None, "maintenance_due", "warning",
                f"🔧 Mantenimiento próximo en {days_left} días: {m.asset.asset_code if m.asset else ''} — {m.next_date}")
            # Enviar email al responsable si no se ha enviado
            if not m.email_sent and m.asset and m.asset.personnel and m.asset.personnel.email:
                html = email_mantenimiento_html(m.asset, m.asset.personnel, 
                       get_smtp(db).company or "Mi Empresa", days_left, m.next_date)
                ok = send_email(m.asset.personnel.email,
                    f"⚠ Mantenimiento preventivo en {days_left} días — {m.asset.asset_code}", html, db)
                if ok:
                    m.email_sent = True
    db.commit()

def _create_alert_if_new(db, agent_id, atype, severity, message):
    cutoff = datetime.utcnow() - timedelta(hours=24)
    exists = db.query(Alert).filter(
        Alert.alert_type == atype,
        Alert.message    == message,
        Alert.created_at > cutoff,
        Alert.acknowledged == False
    ).first()
    if not exists:
        db.add(Alert(agent_id=agent_id, alert_type=atype, severity=severity, message=message))

# ─── INIT DB ──────────────────────────────────────────────────────────────────

def init_db():
    db = SessionLocal()
    if not db.query(User).filter(User.username == "admin").first():
        db.add(User(username="admin", password_hash=hash_password("infrawatch"),
                    full_name="Administrador", email="admin@infrawatch.local", role="admin"))
        db.commit()
        log.info("✅ Admin creado: admin / infrawatch")
    if not db.query(SMTPConfig).first():
        db.add(SMTPConfig()); db.commit()
    db.close()

# ─── APP ──────────────────────────────────────────────────────────────────────
app = FastAPI(title=APP_NAME, version=VERSION, docs_url="/api/docs")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ─── AUTH ─────────────────────────────────────────────────────────────────────

@app.post("/api/auth/login")
def login(data: UserLoginSchema, db: Session = Depends(get_db)):
    u = db.query(User).filter(User.username == data.username).first()
    if not u or not verify_password(data.password, u.password_hash):
        raise HTTPException(status_code=401, detail="Credenciales incorrectas")
    return {"token": create_token(u.id, u.username, u.role),
            "username": u.username, "role": u.role, "full_name": u.full_name}

@app.get("/api/auth/me")
def me(user: User = Depends(get_current_user)):
    return {"id": user.id, "username": user.username, "role": user.role, "full_name": user.full_name}

# ─── PERSONNEL ────────────────────────────────────────────────────────────────

@app.get("/api/personnel")
def list_personnel(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    people = db.query(Personnel).order_by(Personnel.full_name).all()
    return [{
        "id": p.id, "employee_id": p.employee_id, "full_name": p.full_name,
        "position": p.position, "department": p.department, "email": p.email,
        "phone": p.phone, "location": p.location, "is_active": p.is_active,
        "notes": p.notes, "created_at": p.created_at.isoformat(),
        "asset_count": len([a for a in p.assets if a.personnel_id == p.id]),
        "current_assets": [{
            "id": a.id, "asset_code": a.asset_code, "asset_type": a.asset_type,
            "brand": a.brand, "model": a.model, "assigned_at": a.assigned_at.isoformat() if a.assigned_at else None
        } for a in p.assets if a.personnel_id == p.id],
    } for p in people]

@app.get("/api/personnel/{pid}/history")
def personnel_history(pid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    p = db.query(Personnel).filter(Personnel.id == pid).first()
    if not p: raise HTTPException(404, "Personal no encontrado")
    hist = db.query(AssetHistory).filter(AssetHistory.personnel_id == pid)\
              .order_by(AssetHistory.action_date.desc()).all()
    return [{
        "id": h.id, "action": h.action,
        "action_date": h.action_date.isoformat(),
        "notes": h.notes, "created_by": h.created_by,
        "carta_path": h.carta_path,
        "asset": {
            "id": h.asset.id, "asset_code": h.asset.asset_code,
            "asset_type": h.asset.asset_type, "brand": h.asset.brand, "model": h.asset.model,
        } if h.asset else None
    } for h in hist]

@app.post("/api/personnel")
def create_personnel(data: PersonnelSchema, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if db.query(Personnel).filter(Personnel.employee_id == data.employee_id).first():
        raise HTTPException(400, "ID de empleado ya existe")
    p = Personnel(**data.dict()); db.add(p); db.commit(); db.refresh(p)
    return {"id": p.id, "employee_id": p.employee_id}

@app.put("/api/personnel/{pid}")
def update_personnel(pid: int, data: PersonnelSchema, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    p = db.query(Personnel).filter(Personnel.id == pid).first()
    if not p: raise HTTPException(404, "Personal no encontrado")
    for k, v in data.dict().items(): setattr(p, k, v)
    db.commit()
    return {"updated": True}

@app.delete("/api/personnel/{pid}")
def delete_personnel(pid: int, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    p = db.query(Personnel).filter(Personnel.id == pid).first()
    if not p: raise HTTPException(404)
    db.delete(p); db.commit()
    return {"deleted": True}

# ─── AGENTS ───────────────────────────────────────────────────────────────────

@app.post("/api/agents/register")
def agent_register(data: AgentRegisterSchema, db: Session = Depends(get_db)):
    agent = db.query(Agent).filter(
        (Agent.mac_address == data.mac_address) | (Agent.hostname == data.hostname)
    ).first()
    is_new = not agent
    if agent:
        for k, v in data.dict().items(): setattr(agent, k, v)
        agent.status = "online"; agent.last_seen = datetime.utcnow()
    else:
        agent = Agent(**data.dict(), status="online")
        db.add(agent); db.flush()
        db.add(Alert(agent_id=agent.id, alert_type="new_device", severity="info",
                     message=f"Nuevo dispositivo: {data.hostname} ({data.ip_address})"))
    db.commit(); db.refresh(agent)

    # Auto-crear activo si es nuevo
    if is_new and not db.query(Asset).filter(Asset.agent_id == agent.id).first():
        count = db.query(Asset).count()
        hn = data.hostname.lower()
        atype = "server" if any(k in hn for k in ["srv","server","svr"]) else \
                "laptop" if any(k in hn for k in ["lap","notebook","nb"]) else "pc"
        asset = Asset(
            asset_code   = f"AUTO-{str(count+1).zfill(5)}",
            asset_type   = atype,
            model        = data.cpu_model or "",
            notes        = f"Auto-creado al registrarse: {data.hostname}",
            auto_created = True,
            agent_id     = agent.id,
            status       = "active",
        )
        db.add(asset); db.flush()
        # Mantenimiento preventivo automático a 1 año
        create_auto_maintenance(db, asset.id)
        db.commit()
        log.info(f"🖥 Auto-activo + mantenimiento programado: {asset.asset_code}")

    log.info(f"{'📥 Nuevo' if is_new else '🔄'} agente: {agent.hostname}")
    return {"uid": agent.uid, "id": agent.id, "registered": is_new}

@app.post("/api/agents/{uid}/heartbeat")
def agent_heartbeat(uid: str, data: HeartbeatSchema, db: Session = Depends(get_db)):
    a = db.query(Agent).filter(Agent.uid == uid).first()
    if not a: raise HTTPException(404)
    a.status = "online"; a.last_seen = datetime.utcnow()
    db.add(Metric(agent_id=a.id, **{k:v for k,v in data.dict().items() if k!="open_ports"},
                  open_ports=json.dumps(data.open_ports)))
    if data.cpu_percent > 90: _create_alert_if_new(db, a.id, "cpu","critical",f"{a.hostname}: CPU {data.cpu_percent:.0f}%")
    elif data.cpu_percent > 75: _create_alert_if_new(db, a.id, "cpu","warning",f"{a.hostname}: CPU {data.cpu_percent:.0f}%")
    if data.ram_percent > 90:  _create_alert_if_new(db, a.id, "ram","critical",f"{a.hostname}: RAM {data.ram_percent:.0f}%")
    if data.disk_percent > 90: _create_alert_if_new(db, a.id, "disk","critical",f"{a.hostname}: Disco {data.disk_percent:.0f}%")
    db.commit()
    return {"status": "ok", "server_time": datetime.utcnow().isoformat()}

@app.get("/api/agents")
def list_agents(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    cutoff = datetime.utcnow() - timedelta(minutes=5)
    for a in db.query(Agent).filter(Agent.last_seen < cutoff, Agent.status == "online").all():
        a.status = "offline"
        _create_alert_if_new(db, a.id, "offline", "warning", f"{a.hostname} está OFFLINE")
    db.commit()
    check_maintenance_alerts(db)
    result = []
    for a in db.query(Agent).all():
        m     = db.query(Metric).filter(Metric.agent_id==a.id).order_by(Metric.timestamp.desc()).first()
        asset = db.query(Asset).filter(Asset.agent_id==a.id).first()
        result.append({
            "id": a.id, "uid": a.uid, "hostname": a.hostname,
            "ip_address": a.ip_address, "mac_address": a.mac_address,
            "os_name": a.os_name, "os_version": a.os_version,
            "cpu_model": a.cpu_model, "cpu_cores": a.cpu_cores,
            "ram_total_gb": a.ram_total_gb, "disk_total_gb": a.disk_total_gb,
            "tags": json.loads(a.tags or "[]"), "status": a.status,
            "last_seen": a.last_seen.isoformat() if a.last_seen else None,
            "registered_at": a.registered_at.isoformat() if a.registered_at else None,
            "asset_code": asset.asset_code if asset else None,
            "asset_id":   asset.id if asset else None,
            "personnel":  {"id": asset.personnel.id, "full_name": asset.personnel.full_name,
                           "position": asset.personnel.position, "department": asset.personnel.department
                          } if asset and asset.personnel else None,
            "metrics": {"cpu_percent": m.cpu_percent, "ram_percent": m.ram_percent,
                        "disk_percent": m.disk_percent, "uptime_seconds": m.uptime_seconds,
                        "process_count": m.process_count} if m else None
        })
    return result

@app.get("/api/agents/{agent_id}")
def get_agent(agent_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    a = db.query(Agent).filter(Agent.id == agent_id).first()
    if not a: raise HTTPException(404)
    metrics = db.query(Metric).filter(Metric.agent_id==agent_id).order_by(Metric.timestamp.desc()).limit(60).all()
    asset   = db.query(Asset).filter(Asset.agent_id==agent_id).first()
    # próximo mantenimiento
    next_maint = None
    if asset:
        m = db.query(Maintenance).filter(Maintenance.asset_id==asset.id, Maintenance.status=="pending")\
              .order_by(Maintenance.next_date).first()
        if m: next_maint = {"next_date": m.next_date, "days_left": (datetime.strptime(m.next_date,"%Y-%m-%d").date() - date.today()).days if m.next_date else None}
    return {
        "id": a.id, "uid": a.uid, "hostname": a.hostname,
        "ip_address": a.ip_address, "mac_address": a.mac_address,
        "os_name": a.os_name, "os_version": a.os_version,
        "cpu_model": a.cpu_model, "cpu_cores": a.cpu_cores,
        "ram_total_gb": a.ram_total_gb, "disk_total_gb": a.disk_total_gb,
        "tags": json.loads(a.tags or "[]"), "status": a.status,
        "last_seen": a.last_seen.isoformat() if a.last_seen else None,
        "asset": {"id": asset.id, "asset_code": asset.asset_code, "personnel_id": asset.personnel_id,
                  "personnel_name": asset.personnel.full_name if asset.personnel else None,
                  "auto_created": asset.auto_created, "carta_alta_path": bool(asset.carta_alta_path),
                  "carta_baja_path": bool(asset.carta_baja_path)} if asset else None,
        "next_maintenance": next_maint,
        "metrics_history": [{"timestamp": m.timestamp.isoformat(), "cpu_percent": m.cpu_percent,
            "ram_percent": m.ram_percent, "disk_percent": m.disk_percent,
            "net_sent": m.net_bytes_sent, "net_recv": m.net_bytes_recv,
            "process_count": m.process_count, "open_ports": json.loads(m.open_ports or "[]")}
            for m in reversed(metrics)]
    }

@app.put("/api/agents/{agent_id}/tags")
def update_tags(agent_id: int, data: TagUpdateSchema, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    a = db.query(Agent).filter(Agent.id == agent_id).first()
    if not a: raise HTTPException(404)
    a.tags = json.dumps([t.upper().strip() for t in data.tags])
    db.commit()
    return {"tags": json.loads(a.tags)}

@app.delete("/api/agents/{agent_id}")
def delete_agent(agent_id: int, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    a = db.query(Agent).filter(Agent.id == agent_id).first()
    if not a: raise HTTPException(404)
    db.delete(a); db.commit()
    return {"deleted": True}

# ─── ASSETS ───────────────────────────────────────────────────────────────────

def _asset_dict(a: Asset):
    return {
        "id": a.id, "asset_code": a.asset_code, "asset_type": a.asset_type,
        "brand": a.brand, "model": a.model, "serial_number": a.serial_number,
        "purchase_date": a.purchase_date, "purchase_cost": a.purchase_cost,
        "responsible": a.responsible, "personnel_id": a.personnel_id,
        "location": a.location, "status": a.status, "notes": a.notes,
        "auto_created": a.auto_created, "carta_sent": a.carta_sent,
        "carta_sent_at": a.carta_sent_at.isoformat() if a.carta_sent_at else None,
        "carta_alta_uploaded": bool(a.carta_alta_path),
        "carta_baja_uploaded": bool(a.carta_baja_path),
        "assigned_at":   a.assigned_at.isoformat() if a.assigned_at else None,
        "unassigned_at": a.unassigned_at.isoformat() if a.unassigned_at else None,
        "created_at":    a.created_at.isoformat(),
        "agent_id": a.agent_id,
        "agent": {"hostname": a.agent.hostname, "ip_address": a.agent.ip_address,
                  "mac_address": a.agent.mac_address, "os_name": a.agent.os_name,
                  "os_version": a.agent.os_version, "status": a.agent.status} if a.agent else None,
        "personnel": {"id": a.personnel.id, "full_name": a.personnel.full_name,
                      "employee_id": a.personnel.employee_id, "position": a.personnel.position,
                      "department": a.personnel.department, "email": a.personnel.email} if a.personnel else None,
        "maintenance_count": len(a.maintenances),
        "last_maintenance": max((m.maintenance_date for m in a.maintenances), default=None),
        "next_maintenance": min((m.next_date for m in a.maintenances if m.next_date and m.status=="pending"), default=None),
    }

@app.get("/api/assets")
def list_assets(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return [_asset_dict(a) for a in db.query(Asset).all()]

@app.post("/api/assets")
def create_asset(data: AssetSchema, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    count = db.query(Asset).count()
    asset = Asset(asset_code=f"ACT-{str(count+1).zfill(5)}", **data.dict())
    db.add(asset); db.flush()
    create_auto_maintenance(db, asset.id)
    db.commit(); db.refresh(asset)
    return {"id": asset.id, "asset_code": asset.asset_code}

@app.put("/api/assets/{asset_id}")
def update_asset(asset_id: int, data: AssetSchema, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    a = db.query(Asset).filter(Asset.id == asset_id).first()
    if not a: raise HTTPException(404)
    for k, v in data.dict().items(): setattr(a, k, v)
    db.commit()
    return {"updated": True}

@app.post("/api/assets/{asset_id}/assign")
def assign_asset(asset_id: int, data: AssetAssignSchema, background_tasks: BackgroundTasks,
                 request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    asset  = db.query(Asset).filter(Asset.id == asset_id).first()
    person = db.query(Personnel).filter(Personnel.id == data.personnel_id).first()
    if not asset:  raise HTTPException(404, "Activo no encontrado")
    if not person: raise HTTPException(404, "Personal no encontrado")

    # Si tenía responsable anterior, registrar baja del anterior
    if asset.personnel_id and asset.personnel_id != data.personnel_id:
        prev_person = db.query(Personnel).filter(Personnel.id == asset.personnel_id).first()
        if prev_person:
            db.add(AssetHistory(asset_id=asset_id, personnel_id=asset.personnel_id,
                                action="baja", notes="Reasignación automática a nuevo responsable",
                                created_by=user.username))

    asset.personnel_id = data.personnel_id
    asset.responsible  = person.full_name
    asset.assigned_at  = datetime.utcnow()
    asset.unassigned_at = None
    asset.carta_sent   = False

    # Registrar historial de alta
    db.add(AssetHistory(asset_id=asset_id, personnel_id=data.personnel_id,
                        action="alta", notes=data.notes or "Asignación de equipo",
                        created_by=user.username))
    db.commit(); db.refresh(asset)

    base_url   = str(request.base_url).rstrip("/")
    carta_url  = f"{base_url}/api/assets/{asset_id}/carta/alta"

    if data.send_email and person.email:
        html = email_alta_html(asset, person, get_smtp(db).company or "Mi Empresa", carta_url)
        background_tasks.add_task(send_email, person.email,
            f"📋 Asignación de equipo {asset.asset_code}", html, db)
        asset.carta_sent    = True
        asset.carta_sent_at = datetime.utcnow()
        db.commit()

    return {"assigned": True, "personnel": person.full_name, "carta_url": carta_url}

@app.post("/api/assets/{asset_id}/baja")
def baja_asset(asset_id: int, data: AssetBajaSchema, background_tasks: BackgroundTasks,
               request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    asset = db.query(Asset).filter(Asset.id == asset_id).first()
    if not asset: raise HTTPException(404)
    if not asset.personnel_id: raise HTTPException(400, "El activo no tiene responsable asignado")

    person = db.query(Personnel).filter(Personnel.id == asset.personnel_id).first()
    base_url  = str(request.base_url).rstrip("/")
    carta_url = f"{base_url}/api/assets/{asset_id}/carta/baja"

    # Registrar baja en historial
    db.add(AssetHistory(asset_id=asset_id, personnel_id=asset.personnel_id,
                        action="baja", notes=data.notes or "Baja de equipo",
                        created_by=user.username))

    if data.send_email and person and person.email:
        html = email_baja_html(asset, person, get_smtp(db).company or "Mi Empresa", carta_url)
        background_tasks.add_task(send_email, person.email,
            f"📋 Baja de equipo {asset.asset_code}", html, db)

    asset.unassigned_at = datetime.utcnow()
    asset.personnel_id  = None
    asset.responsible   = ""
    asset.carta_sent    = False
    db.commit()

    return {"baja": True, "carta_url": carta_url}

# ─── CARTAS HTML ──────────────────────────────────────────────────────────────

@app.get("/api/assets/{asset_id}/carta/alta", response_class=HTMLResponse)
def carta_alta(asset_id: int, db: Session = Depends(get_db)):
    a = db.query(Asset).filter(Asset.id == asset_id).first()
    if not a: raise HTTPException(404)
    if not a.personnel:
        return HTMLResponse("<h2>Sin responsable asignado</h2>", status_code=400)
    cfg = get_smtp(db)
    return HTMLResponse(generate_carta_alta(a, a.personnel, cfg.company or "Mi Empresa"))

@app.get("/api/assets/{asset_id}/carta/baja", response_class=HTMLResponse)
def carta_baja_view(asset_id: int, db: Session = Depends(get_db)):
    a = db.query(Asset).filter(Asset.id == asset_id).first()
    if not a: raise HTTPException(404)
    # Para baja, tomar el último historial de baja
    hist = db.query(AssetHistory).filter(AssetHistory.asset_id==asset_id,
                    AssetHistory.action=="baja").order_by(AssetHistory.action_date.desc()).first()
    if not hist or not hist.personnel:
        return HTMLResponse("<h2>Sin historial de baja</h2>", status_code=400)
    cfg = get_smtp(db)
    return HTMLResponse(generate_carta_baja(a, hist.personnel, cfg.company or "Mi Empresa", hist.notes))

# Carta legacy
@app.get("/api/assets/{asset_id}/carta", response_class=HTMLResponse)
def carta_legacy(asset_id: int, db: Session = Depends(get_db)):
    return carta_alta(asset_id, db)

# ─── UPLOAD CARTAS FIRMADAS ───────────────────────────────────────────────────

@app.post("/api/assets/{asset_id}/upload/alta")
async def upload_carta_alta(asset_id: int, file: UploadFile = File(...),
                             user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    a = db.query(Asset).filter(Asset.id == asset_id).first()
    if not a: raise HTTPException(404)
    ext      = os.path.splitext(file.filename)[1] if file.filename else ".pdf"
    filename = f"carta_alta_{asset_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}{ext}"
    path     = os.path.join(UPLOAD_DIR, filename)
    with open(path, "wb") as f:
        shutil.copyfileobj(file.file, f)
    a.carta_alta_path = path
    # Actualizar historial
    hist = db.query(AssetHistory).filter(AssetHistory.asset_id==asset_id,
                    AssetHistory.action=="alta").order_by(AssetHistory.action_date.desc()).first()
    if hist: hist.carta_path = path
    db.commit()
    return {"uploaded": True, "filename": filename}

@app.post("/api/assets/{asset_id}/upload/baja")
async def upload_carta_baja(asset_id: int, file: UploadFile = File(...),
                             user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    a = db.query(Asset).filter(Asset.id == asset_id).first()
    if not a: raise HTTPException(404)
    ext      = os.path.splitext(file.filename)[1] if file.filename else ".pdf"
    filename = f"carta_baja_{asset_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}{ext}"
    path     = os.path.join(UPLOAD_DIR, filename)
    with open(path, "wb") as f:
        shutil.copyfileobj(file.file, f)
    a.carta_baja_path = path
    hist = db.query(AssetHistory).filter(AssetHistory.asset_id==asset_id,
                    AssetHistory.action=="baja").order_by(AssetHistory.action_date.desc()).first()
    if hist: hist.carta_path = path
    db.commit()
    return {"uploaded": True, "filename": filename}

@app.get("/api/assets/{asset_id}/download/alta")
def download_carta_alta(asset_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    a = db.query(Asset).filter(Asset.id == asset_id).first()
    if not a or not a.carta_alta_path or not os.path.exists(a.carta_alta_path):
        raise HTTPException(404, "Carta no encontrada")
    return FileResponse(a.carta_alta_path, filename=f"carta_alta_{a.asset_code}.pdf")

@app.get("/api/assets/{asset_id}/download/baja")
def download_carta_baja(asset_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    a = db.query(Asset).filter(Asset.id == asset_id).first()
    if not a or not a.carta_baja_path or not os.path.exists(a.carta_baja_path):
        raise HTTPException(404, "Carta no encontrada")
    return FileResponse(a.carta_baja_path, filename=f"carta_baja_{a.asset_code}.pdf")

@app.delete("/api/assets/{asset_id}")
def delete_asset(asset_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    a = db.query(Asset).filter(Asset.id == asset_id).first()
    if not a: raise HTTPException(404)
    db.delete(a); db.commit()
    return {"deleted": True}

# ─── MAINTENANCE ──────────────────────────────────────────────────────────────

@app.get("/api/maintenance")
def list_maintenance(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    records = db.query(Maintenance).order_by(Maintenance.created_at.desc()).all()
    today   = date.today()
    return [{
        "id": m.id, "asset_id": m.asset_id,
        "asset_code": m.asset.asset_code if m.asset else "",
        "asset_name": f"{m.asset.brand} {m.asset.model}" if m.asset else "",
        "responsible": m.asset.personnel.full_name if m.asset and m.asset.personnel else "Sin asignar",
        "resp_email":  m.asset.personnel.email if m.asset and m.asset.personnel else "",
        "maintenance_date": m.maintenance_date, "next_date": m.next_date,
        "technician": m.technician, "maint_type": m.maint_type,
        "observations": m.observations, "status": m.status,
        "auto_created": m.auto_created, "email_sent": m.email_sent,
        "days_left": (datetime.strptime(m.next_date,"%Y-%m-%d").date()-today).days if m.next_date else None,
        "created_at": m.created_at.isoformat(),
    } for m in records]

@app.post("/api/maintenance")
def create_maintenance(data: MaintenanceSchema, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    m = Maintenance(**data.dict()); db.add(m)
    a = db.query(Asset).filter(Asset.id == data.asset_id).first()
    if a: a.status = "active" if data.status == "completed" else "maintenance"
    db.commit(); db.refresh(m)
    return {"id": m.id}

@app.put("/api/maintenance/{mid}/complete")
def complete_maintenance(mid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    m = db.query(Maintenance).filter(Maintenance.id == mid).first()
    if not m: raise HTTPException(404)
    m.status           = "completed"
    m.maintenance_date = date.today().strftime("%Y-%m-%d")
    # Crear nuevo mantenimiento para el próximo año
    if m.asset_id:
        next_year = date.today() + timedelta(days=365)
        db.add(Maintenance(
            asset_id=m.asset_id, maintenance_date=date.today().strftime("%Y-%m-%d"),
            next_date=next_year.strftime("%Y-%m-%d"), technician=m.technician,
            maint_type="preventive",
            observations="Mantenimiento preventivo anual (renovado automáticamente)",
            status="pending", auto_created=True
        ))
    db.commit()
    return {"completed": True}

@app.delete("/api/maintenance/{mid}")
def delete_maintenance(mid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    m = db.query(Maintenance).filter(Maintenance.id == mid).first()
    if not m: raise HTTPException(404)
    db.delete(m); db.commit()
    return {"deleted": True}

# ─── ALERTS ───────────────────────────────────────────────────────────────────

@app.get("/api/alerts")
def list_alerts(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return [{"id": a.id, "agent_id": a.agent_id, "alert_type": a.alert_type,
             "severity": a.severity, "message": a.message, "acknowledged": a.acknowledged,
             "created_at": a.created_at.isoformat()}
            for a in db.query(Alert).order_by(Alert.created_at.desc()).limit(200).all()]

@app.put("/api/alerts/{alert_id}/acknowledge")
def ack_alert(alert_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    a = db.query(Alert).filter(Alert.id == alert_id).first()
    if not a: raise HTTPException(404)
    a.acknowledged = True; db.commit()
    return {"acknowledged": True}

@app.post("/api/alerts/ack-all")
def ack_all(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    db.query(Alert).filter(Alert.acknowledged==False).update({"acknowledged": True})
    db.commit(); return {"acknowledged": True}

# ─── DASHBOARD ────────────────────────────────────────────────────────────────

@app.get("/api/dashboard")
def dashboard(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    check_maintenance_alerts(db)
    agents  = db.query(Agent).all()
    online  = [a for a in agents if a.status == "online"]
    assets  = db.query(Asset).all()
    today   = date.today()

    # Mantenimientos
    pending_m    = db.query(Maintenance).filter(Maintenance.status=="pending").count()
    overdue_m    = 0; upcoming_m = 0
    maint_upcoming = []
    for m in db.query(Maintenance).filter(Maintenance.status=="pending", Maintenance.next_date!=None).all():
        try:
            nd = datetime.strptime(m.next_date, "%Y-%m-%d").date()
            dl = (nd - today).days
            if dl < 0: overdue_m += 1
            elif dl <= 30:
                upcoming_m += 1
                maint_upcoming.append({
                    "asset_code": m.asset.asset_code if m.asset else "",
                    "asset_name": f"{m.asset.brand} {m.asset.model}" if m.asset else "",
                    "responsible": m.asset.personnel.full_name if m.asset and m.asset.personnel else "Sin asignar",
                    "next_date": m.next_date, "days_left": dl
                })
        except: pass
    maint_upcoming.sort(key=lambda x: x["days_left"])

    unack  = db.query(Alert).filter(Alert.acknowledged==False).count()
    crit   = db.query(Alert).filter(Alert.acknowledged==False, Alert.severity=="critical").count()
    cpus   = []; rams = []; disks = []
    for a in online:
        m = db.query(Metric).filter(Metric.agent_id==a.id).order_by(Metric.timestamp.desc()).first()
        if m: cpus.append(m.cpu_percent); rams.append(m.ram_percent); disks.append(m.disk_percent)

    os_dist    = {}
    type_dist  = {}
    dept_dist  = {}
    for a in agents:
        k = a.os_name or "Unknown"; os_dist[k] = os_dist.get(k, 0) + 1
    for a in assets:
        type_dist[a.asset_type] = type_dist.get(a.asset_type, 0) + 1
    for p in db.query(Personnel).all():
        dept_dist[p.department] = dept_dist.get(p.department, 0) + 1

    return {
        "agents":    {"total": len(agents), "online": len(online), "offline": len(agents)-len(online)},
        "assets":    {"total": len(assets), "active": sum(1 for a in assets if a.status=="active"),
                      "pending_assign": sum(1 for a in assets if not a.personnel_id),
                      "auto_created": sum(1 for a in assets if a.auto_created)},
        "personnel": {"total": db.query(Personnel).count()},
        "maintenance": {"pending": pending_m, "overdue": overdue_m, "upcoming_30d": upcoming_m,
                        "upcoming_list": maint_upcoming[:5]},
        "alerts":    {"unacknowledged": unack, "critical": crit},
        "avg_metrics": {"cpu": round(sum(cpus)/len(cpus),1) if cpus else 0,
                        "ram": round(sum(rams)/len(rams),1) if rams else 0,
                        "disk": round(sum(disks)/len(disks),1) if disks else 0},
        "os_distribution":    os_dist,
        "asset_distribution": type_dist,
        "dept_distribution":  dept_dist,
        "server_time": datetime.utcnow().isoformat(),
        "version": VERSION,
    }

# ─── USERS ────────────────────────────────────────────────────────────────────

@app.get("/api/users")
def list_users(user: User = Depends(require_admin), db: Session = Depends(get_db)):
    return [{"id": u.id, "username": u.username, "full_name": u.full_name, "email": u.email,
             "role": u.role, "is_active": u.is_active, "created_at": u.created_at.isoformat()}
            for u in db.query(User).all()]

@app.post("/api/users")
def create_user(data: UserCreateSchema, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    if db.query(User).filter(User.username == data.username).first():
        raise HTTPException(400, "Usuario ya existe")
    u = User(username=data.username, password_hash=hash_password(data.password),
             full_name=data.full_name, email=data.email, role=data.role)
    db.add(u); db.commit()
    return {"id": u.id}

@app.delete("/api/users/{uid}")
def delete_user(uid: int, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    u = db.query(User).filter(User.id == uid).first()
    if not u: raise HTTPException(404)
    if u.username == "admin": raise HTTPException(400, "No se puede eliminar admin")
    db.delete(u); db.commit()
    return {"deleted": True}

# ─── SMTP CONFIG ──────────────────────────────────────────────────────────────

@app.get("/api/config/smtp")
def get_smtp_cfg(user: User = Depends(require_admin), db: Session = Depends(get_db)):
    c = get_smtp(db)
    return {"host": c.host, "port": c.port, "username": c.username,
            "password": "***" if c.password else "", "from_name": c.from_name,
            "company": c.company, "enabled": c.enabled}

@app.put("/api/config/smtp")
def update_smtp_cfg(data: SMTPConfigSchema, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    c = get_smtp(db)
    c.host=data.host; c.port=data.port; c.username=data.username
    if data.password and data.password != "***": c.password = data.password
    c.from_name=data.from_name; c.company=data.company; c.enabled=data.enabled
    db.commit()
    return {"updated": True}

@app.post("/api/config/smtp/test")
def test_smtp_cfg(user: User = Depends(require_admin), db: Session = Depends(get_db)):
    cfg = get_smtp(db)
    ok  = send_email(cfg.username, "✅ Test InfraWatch",
                     "<h2>✅ SMTP funciona correctamente</h2><p>InfraWatch puede enviar correos.</p>", db)
    return {"success": ok, "message": "Email enviado" if ok else "Error al enviar. Verifica configuración SMTP."}

# ─── REPORTS ──────────────────────────────────────────────────────────────────

@app.get("/api/reports/inventory")
def rep_inventory(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    agents = db.query(Agent).all()
    return {"generated_at": datetime.utcnow().isoformat(), "total": len(agents),
            "data": [{"hostname": a.hostname, "ip": a.ip_address, "mac": a.mac_address,
                       "os": f"{a.os_name} {a.os_version}", "cpu": a.cpu_model,
                       "ram_gb": a.ram_total_gb, "disk_gb": a.disk_total_gb,
                       "status": a.status, "tags": json.loads(a.tags or "[]"),
                       "last_seen": a.last_seen.isoformat() if a.last_seen else ""} for a in agents]}

@app.get("/api/reports/assets")
def rep_assets(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    assets = db.query(Asset).all()
    return {"generated_at": datetime.utcnow().isoformat(), "total": len(assets),
            "data": [{"asset_code": a.asset_code, "type": a.asset_type, "brand": a.brand,
                       "model": a.model, "serial": a.serial_number,
                       "responsible": a.responsible, "personnel": a.personnel.full_name if a.personnel else "",
                       "department": a.personnel.department if a.personnel else "",
                       "location": a.location, "status": a.status, "carta_sent": a.carta_sent,
                       "next_maintenance": a.next_maintenance if hasattr(a,'next_maintenance') else ""
                      } for a in assets]}

@app.get("/api/reports/personnel")
def rep_personnel(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    people = db.query(Personnel).all()
    return {"generated_at": datetime.utcnow().isoformat(), "total": len(people),
            "data": [{"employee_id": p.employee_id, "full_name": p.full_name,
                       "position": p.position, "department": p.department, "email": p.email,
                       "assets": [a.asset_code for a in p.assets], "asset_count": len(p.assets)} for p in people]}

# ─── HEALTH & STATIC ──────────────────────────────────────────────────────────

@app.get("/api/health")
def health():
    return {"status": "ok", "app": APP_NAME, "version": VERSION, "time": datetime.utcnow().isoformat()}

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/", include_in_schema=False)
    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str = ""):
        if full_path.startswith("api/"): raise HTTPException(404)
        idx = os.path.join(STATIC_DIR, "index.html")
        return FileResponse(idx) if os.path.exists(idx) else JSONResponse({"status":"ok"})

@app.on_event("startup")
def startup():
    log.info(f"🚀 {APP_NAME} v{VERSION} iniciando...")
    init_db(); log.info("✅ BD lista")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
