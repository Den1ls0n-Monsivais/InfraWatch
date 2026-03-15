"""
InfraWatch v2.0 — Backend API Mejorado
Nuevas funciones:
  - Personal/Responsables (base de datos de empleados)
  - Activos creados automáticamente al registrarse el agente
  - Asignación de equipo a persona responsable
  - Envío de correo al guardar responsiva
  - Generación de Carta Responsiva HTML/PDF
  - Dashboard mejorado con más gráficas
"""

from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Text, Boolean, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session, relationship
from pydantic import BaseModel, EmailStr
from typing import Optional, List
from datetime import datetime, timedelta
import jwt, bcrypt, os, json, uuid, smtplib, logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# ─── CONFIG ────────────────────────────────────────────────────────────────────
DATABASE_URL  = os.getenv("DATABASE_URL", "sqlite:////opt/infrawatch/data/infrawatch.db")
SECRET_KEY    = os.getenv("SECRET_KEY", "infrawatch-secret-2024")
JWT_ALGO      = "HS256"
JWT_EXP_HRS   = 24
VERSION       = "2.0.0"
APP_NAME      = "InfraWatch"

# SMTP Config (opcional, configurar en variables de entorno)
SMTP_HOST     = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT     = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER     = os.getenv("SMTP_USER", "")
SMTP_PASS     = os.getenv("SMTP_PASS", "")
SMTP_FROM     = os.getenv("SMTP_FROM", "InfraWatch <noreply@infrawatch.local>")
COMPANY_NAME  = os.getenv("COMPANY_NAME", "Mi Empresa")
COMPANY_LOGO  = os.getenv("COMPANY_LOGO", "")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

# ─── DATABASE ──────────────────────────────────────────────────────────────────
os.makedirs("/opt/infrawatch/data", exist_ok=True)
engine      = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base        = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ─── MODELS ────────────────────────────────────────────────────────────────────

class Personnel(Base):
    """Base de datos de personal / responsables"""
    __tablename__ = "personnel"
    id             = Column(Integer, primary_key=True, index=True)
    employee_id    = Column(String, unique=True, index=True)  # Número de empleado
    full_name      = Column(String, index=True)
    position       = Column(String)       # Puesto
    department     = Column(String)       # Departamento
    email          = Column(String)
    phone          = Column(String, default="")
    location       = Column(String, default="")  # Ubicación/Sucursal
    is_active      = Column(Boolean, default=True)
    notes          = Column(Text, default="")
    created_at     = Column(DateTime, default=datetime.utcnow)
    assets         = relationship("Asset", back_populates="personnel")

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
    responsible      = Column(String, default="")   # Nombre libre (legacy)
    personnel_id     = Column(Integer, ForeignKey("personnel.id"), nullable=True)
    location         = Column(String, default="")
    status           = Column(String, default="active")
    notes            = Column(Text, default="")
    auto_created     = Column(Boolean, default=False)  # True si fue creado automáticamente
    carta_sent       = Column(Boolean, default=False)  # Si ya se envió carta responsiva
    carta_sent_at    = Column(DateTime, nullable=True)
    created_at       = Column(DateTime, default=datetime.utcnow)
    agent_id         = Column(Integer, ForeignKey("agents.id"), nullable=True)
    personnel        = relationship("Personnel", back_populates="assets")
    agent            = relationship("Agent", back_populates="asset")
    maintenances     = relationship("Maintenance", back_populates="asset", cascade="all, delete")

class Maintenance(Base):
    __tablename__ = "maintenances"
    id               = Column(Integer, primary_key=True, index=True)
    asset_id         = Column(Integer, ForeignKey("assets.id"))
    maintenance_date = Column(String)
    next_date        = Column(String, nullable=True)
    technician       = Column(String)
    maint_type       = Column(String)
    observations     = Column(Text, default="")
    status           = Column(String, default="completed")
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
    full_name     = Column(String)
    email         = Column(String)
    role          = Column(String, default="viewer")
    is_active     = Column(Boolean, default=True)
    created_at    = Column(DateTime, default=datetime.utcnow)

class SMTPConfig(Base):
    """Configuración SMTP guardada en BD"""
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

# ─── SCHEMAS ───────────────────────────────────────────────────────────────────

class PersonnelSchema(BaseModel):
    employee_id: str
    full_name:   str
    position:    str
    department:  str
    email:       str
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
    send_carta:   Optional[bool] = True

class MaintenanceSchema(BaseModel):
    asset_id:         int
    maintenance_date: str
    next_date:        Optional[str] = None
    technician:       str
    maint_type:       str
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
    host:     str
    port:     int
    username: str
    password: str
    from_name: Optional[str] = "InfraWatch"
    company:  Optional[str] = "Mi Empresa"
    enabled:  Optional[bool] = True

# ─── AUTH ──────────────────────────────────────────────────────────────────────

security = HTTPBearer(auto_error=False)

def create_token(user_id, username, role):
    payload = {"sub": str(user_id), "username": username, "role": role,
               "exp": datetime.utcnow() + timedelta(hours=JWT_EXP_HRS)}
    return jwt.encode(payload, SECRET_KEY, algorithm=JWT_ALGO)

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
    payload = decode_token(credentials.credentials)
    user = db.query(User).filter(User.id == int(payload["sub"])).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Usuario no válido")
    return user

def require_admin(user: User = Depends(get_current_user)):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Se requiere rol admin")
    return user

def hash_password(pw): return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()
def verify_password(pw, h): return bcrypt.checkpw(pw.encode(), h.encode())

# ─── EMAIL ─────────────────────────────────────────────────────────────────────

def get_smtp_config(db: Session):
    cfg = db.query(SMTPConfig).first()
    if not cfg:
        cfg = SMTPConfig()
        db.add(cfg); db.commit(); db.refresh(cfg)
    return cfg

def send_email_bg(to_email: str, subject: str, html_body: str, db: Session):
    cfg = get_smtp_config(db)
    if not cfg.enabled or not cfg.username:
        log.warning("SMTP no configurado, email no enviado")
        return False
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = f"{cfg.from_name} <{cfg.username}>"
        msg["To"]      = to_email
        msg.attach(MIMEText(html_body, "html", "utf-8"))
        with smtplib.SMTP(cfg.host, cfg.port, timeout=15) as server:
            server.starttls()
            server.login(cfg.username, cfg.password)
            server.sendmail(cfg.username, [to_email], msg.as_string())
        log.info(f"✉ Email enviado a {to_email}: {subject}")
        return True
    except Exception as e:
        log.error(f"Error enviando email: {e}")
        return False

def generate_carta_html(asset: Asset, person: Personnel, company: str) -> str:
    today = datetime.now().strftime("%d de %B de %Y")
    asset_type_es = {
        "laptop": "Laptop", "pc": "Computadora de escritorio", "server": "Servidor",
        "switch": "Switch de red", "firewall": "Firewall", "printer": "Impresora", "other": "Equipo"
    }.get(asset.asset_type, "Equipo")

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<style>
  body {{ font-family: Arial, sans-serif; color: #222; margin: 0; padding: 40px; }}
  .header {{ text-align: center; border-bottom: 3px solid #1a56db; padding-bottom: 20px; margin-bottom: 30px; }}
  .company {{ font-size: 22px; font-weight: bold; color: #1a56db; }}
  .title {{ font-size: 18px; font-weight: bold; margin: 20px 0; text-align: center; text-transform: uppercase; }}
  .folio {{ text-align: right; color: #666; font-size: 12px; margin-bottom: 20px; }}
  .section {{ margin-bottom: 20px; }}
  .section-title {{ font-weight: bold; background: #f0f4ff; padding: 6px 12px; border-left: 4px solid #1a56db; margin-bottom: 10px; }}
  table {{ width: 100%; border-collapse: collapse; margin-bottom: 20px; }}
  td, th {{ border: 1px solid #ddd; padding: 8px 12px; font-size: 13px; }}
  th {{ background: #f0f4ff; font-weight: bold; width: 35%; }}
  .firma-section {{ display: flex; justify-content: space-around; margin-top: 60px; }}
  .firma-box {{ text-align: center; width: 40%; }}
  .firma-line {{ border-top: 1px solid #333; padding-top: 8px; margin-top: 60px; font-size: 12px; }}
  .terms {{ font-size: 11px; color: #555; border: 1px solid #ddd; padding: 12px; margin-top: 20px; background: #fafafa; }}
  .footer {{ text-align: center; font-size: 11px; color: #888; margin-top: 40px; border-top: 1px solid #eee; padding-top: 12px; }}
  @media print {{ body {{ padding: 20px; }} }}
</style>
</head>
<body>
<div class="header">
  <div class="company">{company}</div>
  <div style="color:#666;font-size:13px">Departamento de Tecnologías de Información</div>
</div>

<div class="folio">Folio: RESP-{asset.asset_code}-{datetime.now().strftime('%Y%m%d')}</div>

<div class="title">Carta Responsiva de Equipo de Cómputo</div>

<p>Por medio del presente documento, yo <strong>{person.full_name}</strong>, con número de empleado <strong>{person.employee_id}</strong>,
me comprometo a resguardar y hacer buen uso del equipo de cómputo que me ha sido asignado por {company},
bajo las condiciones que a continuación se detallan:</p>

<div class="section">
  <div class="section-title">Datos del Responsable</div>
  <table>
    <tr><th>Nombre Completo</th><td>{person.full_name}</td></tr>
    <tr><th>Número de Empleado</th><td>{person.employee_id}</td></tr>
    <tr><th>Puesto</th><td>{person.position}</td></tr>
    <tr><th>Departamento</th><td>{person.department}</td></tr>
    <tr><th>Ubicación</th><td>{person.location or '—'}</td></tr>
    <tr><th>Correo Electrónico</th><td>{person.email}</td></tr>
    <tr><th>Teléfono</th><td>{person.phone or '—'}</td></tr>
  </table>
</div>

<div class="section">
  <div class="section-title">Datos del Equipo Asignado</div>
  <table>
    <tr><th>Código de Activo</th><td><strong>{asset.asset_code}</strong></td></tr>
    <tr><th>Tipo de Equipo</th><td>{asset_type_es}</td></tr>
    <tr><th>Marca</th><td>{asset.brand or '—'}</td></tr>
    <tr><th>Modelo</th><td>{asset.model or '—'}</td></tr>
    <tr><th>Número de Serie</th><td>{asset.serial_number or '—'}</td></tr>
    <tr><th>Hostname</th><td>{asset.agent.hostname if asset.agent else '—'}</td></tr>
    <tr><th>Dirección IP</th><td>{asset.agent.ip_address if asset.agent else '—'}</td></tr>
    <tr><th>MAC Address</th><td>{asset.agent.mac_address if asset.agent else '—'}</td></tr>
    <tr><th>Sistema Operativo</th><td>{(asset.agent.os_name + ' ' + (asset.agent.os_version or '')) if asset.agent else '—'}</td></tr>
    <tr><th>Ubicación Asignada</th><td>{asset.location or '—'}</td></tr>
    <tr><th>Fecha de Asignación</th><td>{today}</td></tr>
  </table>
</div>

<div class="terms">
  <strong>Términos y Condiciones:</strong>
  <ol>
    <li>El equipo asignado es propiedad exclusiva de {company} y deberá utilizarse únicamente para actividades laborales.</li>
    <li>El responsable se compromete a dar aviso inmediato al área de TI ante cualquier falla, pérdida, robo o daño del equipo.</li>
    <li>Queda estrictamente prohibida la instalación de software no autorizado por el área de TI.</li>
    <li>El equipo deberá ser devuelto en las mismas condiciones en que fue entregado al concluir la relación laboral.</li>
    <li>En caso de pérdida o daño por negligencia, el responsable deberá cubrir el costo de reposición o reparación.</li>
    <li>El responsable no deberá prestar el equipo a terceros sin autorización del área de TI.</li>
    <li>El área de TI se reserva el derecho de realizar auditorías y monitoreo del equipo en cualquier momento.</li>
  </ol>
</div>

<div class="firma-section">
  <div class="firma-box">
    <div class="firma-line">
      <strong>{person.full_name}</strong><br>
      {person.employee_id} — {person.position}<br>
      <em>Firma del Responsable</em>
    </div>
  </div>
  <div class="firma-box">
    <div class="firma-line">
      <strong>Responsable de TI</strong><br>
      Departamento de Tecnologías de Información<br>
      <em>Autorizado por</em>
    </div>
  </div>
</div>

<div class="footer">
  Documento generado por InfraWatch v2.0 — {company} — {today}<br>
  Este documento tiene validez interna. Conserve una copia firmada en el expediente del empleado.
</div>
</body>
</html>"""

# ─── EMAIL TEMPLATES ───────────────────────────────────────────────────────────

def email_asignacion_html(asset: Asset, person: Personnel, company: str, carta_url: str) -> str:
    return f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;background:#f5f7fa;padding:20px">
      <div style="background:#1a56db;color:white;padding:24px;border-radius:8px 8px 0 0;text-align:center">
        <h1 style="margin:0;font-size:22px">🛡 InfraWatch</h1>
        <p style="margin:6px 0 0;opacity:.9">{company} — Asignación de Equipo</p>
      </div>
      <div style="background:white;padding:28px;border-radius:0 0 8px 8px">
        <p>Estimado/a <strong>{person.full_name}</strong>,</p>
        <p>Se le ha asignado el siguiente equipo de cómputo a su nombre:</p>
        <table style="width:100%;border-collapse:collapse;margin:16px 0">
          <tr style="background:#f0f4ff"><td style="padding:10px;font-weight:bold;border:1px solid #ddd;width:40%">Código de Activo</td>
              <td style="padding:10px;border:1px solid #ddd"><strong>{asset.asset_code}</strong></td></tr>
          <tr><td style="padding:10px;font-weight:bold;border:1px solid #ddd">Tipo</td>
              <td style="padding:10px;border:1px solid #ddd">{asset.asset_type}</td></tr>
          <tr style="background:#f0f4ff"><td style="padding:10px;font-weight:bold;border:1px solid #ddd">Equipo</td>
              <td style="padding:10px;border:1px solid #ddd">{asset.brand} {asset.model}</td></tr>
          <tr><td style="padding:10px;font-weight:bold;border:1px solid #ddd">Serie</td>
              <td style="padding:10px;border:1px solid #ddd">{asset.serial_number or '—'}</td></tr>
          <tr style="background:#f0f4ff"><td style="padding:10px;font-weight:bold;border:1px solid #ddd">Hostname</td>
              <td style="padding:10px;border:1px solid #ddd">{asset.agent.hostname if asset.agent else '—'}</td></tr>
          <tr><td style="padding:10px;font-weight:bold;border:1px solid #ddd">IP</td>
              <td style="padding:10px;border:1px solid #ddd">{asset.agent.ip_address if asset.agent else '—'}</td></tr>
          <tr style="background:#f0f4ff"><td style="padding:10px;font-weight:bold;border:1px solid #ddd">Ubicación</td>
              <td style="padding:10px;border:1px solid #ddd">{asset.location or '—'}</td></tr>
        </table>
        <p>Al recibir este equipo, usted acepta los términos de uso establecidos por el departamento de TI.</p>
        <div style="text-align:center;margin:24px 0">
          <a href="{carta_url}" style="background:#1a56db;color:white;padding:12px 28px;border-radius:6px;text-decoration:none;font-weight:bold">
            📄 Ver Carta Responsiva
          </a>
        </div>
        <p style="color:#666;font-size:12px">Si tiene alguna duda, comuníquese con el departamento de TI.<br>
        Por favor conserve este correo como comprobante de asignación.</p>
      </div>
      <p style="text-align:center;color:#aaa;font-size:11px;margin-top:12px">
        InfraWatch v2.0 — {company} — {datetime.now().strftime('%d/%m/%Y %H:%M')}
      </p>
    </div>"""

# ─── INIT DB ───────────────────────────────────────────────────────────────────

def init_db():
    db = SessionLocal()
    if not db.query(User).filter(User.username == "admin").first():
        db.add(User(username="admin", password_hash=hash_password("infrawatch"),
                    full_name="Administrador", email="admin@infrawatch.local", role="admin"))
        db.commit()
        log.info("✅ Usuario admin creado: admin / infrawatch")
    if not db.query(SMTPConfig).first():
        db.add(SMTPConfig())
        db.commit()
    db.close()

# ─── APP ───────────────────────────────────────────────────────────────────────

app = FastAPI(title=APP_NAME, version=VERSION, docs_url="/api/docs")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ─── AUTH ──────────────────────────────────────────────────────────────────────

@app.post("/api/auth/login")
def login(data: UserLoginSchema, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == data.username).first()
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Credenciales incorrectas")
    return {"token": create_token(user.id, user.username, user.role),
            "username": user.username, "role": user.role, "full_name": user.full_name}

@app.get("/api/auth/me")
def me(user: User = Depends(get_current_user)):
    return {"id": user.id, "username": user.username, "role": user.role, "full_name": user.full_name}

# ─── PERSONNEL ─────────────────────────────────────────────────────────────────

@app.get("/api/personnel")
def list_personnel(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    people = db.query(Personnel).order_by(Personnel.full_name).all()
    return [{
        "id": p.id, "employee_id": p.employee_id, "full_name": p.full_name,
        "position": p.position, "department": p.department, "email": p.email,
        "phone": p.phone, "location": p.location, "is_active": p.is_active,
        "notes": p.notes, "created_at": p.created_at.isoformat(),
        "asset_count": len(p.assets)
    } for p in people]

@app.post("/api/personnel")
def create_personnel(data: PersonnelSchema, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if db.query(Personnel).filter(Personnel.employee_id == data.employee_id).first():
        raise HTTPException(status_code=400, detail="ID de empleado ya existe")
    p = Personnel(**data.dict())
    db.add(p); db.commit(); db.refresh(p)
    return {"id": p.id, "employee_id": p.employee_id}

@app.put("/api/personnel/{pid}")
def update_personnel(pid: int, data: PersonnelSchema, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    p = db.query(Personnel).filter(Personnel.id == pid).first()
    if not p: raise HTTPException(status_code=404, detail="Personal no encontrado")
    for k, v in data.dict().items():
        setattr(p, k, v)
    db.commit()
    return {"updated": True}

@app.delete("/api/personnel/{pid}")
def delete_personnel(pid: int, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    p = db.query(Personnel).filter(Personnel.id == pid).first()
    if not p: raise HTTPException(status_code=404, detail="Personal no encontrado")
    db.delete(p); db.commit()
    return {"deleted": True}

# ─── AGENTS ────────────────────────────────────────────────────────────────────

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

    # ── AUTO-CREAR ACTIVO si no existe ──────────────────────────────────────
    if is_new and not db.query(Asset).filter(Asset.agent_id == agent.id).first():
        count = db.query(Asset).count()
        # Detectar tipo por hostname/OS
        hostname_lower = data.hostname.lower()
        if any(k in hostname_lower for k in ["srv", "server", "svr"]):
            atype = "server"
        elif any(k in hostname_lower for k in ["lap", "notebook", "nb"]):
            atype = "laptop"
        elif data.os_name and "windows" in data.os_name.lower():
            atype = "pc"
        else:
            atype = "pc"

        asset = Asset(
            asset_code    = f"AUTO-{str(count+1).zfill(5)}",
            asset_type    = atype,
            brand         = "",
            model         = data.cpu_model or "",
            serial_number = "",
            notes         = f"Creado automáticamente al registrarse el agente {data.hostname}",
            auto_created  = True,
            agent_id      = agent.id,
            status        = "active",
        )
        db.add(asset); db.commit()
        log.info(f"🖥 Activo auto-creado: {asset.asset_code} para {agent.hostname}")

    log.info(f"{'📥 Nuevo' if is_new else '🔄 Update'}: {agent.hostname} [{agent.ip_address}]")
    return {"uid": agent.uid, "id": agent.id, "registered": is_new}

@app.post("/api/agents/{agent_uid}/heartbeat")
def agent_heartbeat(agent_uid: str, data: HeartbeatSchema, db: Session = Depends(get_db)):
    agent = db.query(Agent).filter(Agent.uid == agent_uid).first()
    if not agent: raise HTTPException(status_code=404, detail="Agente no encontrado")
    agent.status = "online"; agent.last_seen = datetime.utcnow()
    db.add(Metric(agent_id=agent.id, **{k: v for k, v in data.dict().items() if k != "open_ports"},
                  open_ports=json.dumps(data.open_ports)))
    if data.cpu_percent > 90: _alert(db, agent.id, "cpu", "critical", f"{agent.hostname}: CPU {data.cpu_percent:.0f}%")
    elif data.cpu_percent > 75: _alert(db, agent.id, "cpu", "warning", f"{agent.hostname}: CPU {data.cpu_percent:.0f}%")
    if data.ram_percent > 90: _alert(db, agent.id, "ram", "critical", f"{agent.hostname}: RAM {data.ram_percent:.0f}%")
    if data.disk_percent > 90: _alert(db, agent.id, "disk", "critical", f"{agent.hostname}: Disco {data.disk_percent:.0f}%")
    db.commit()
    return {"status": "ok", "server_time": datetime.utcnow().isoformat()}

def _alert(db, agent_id, atype, severity, message):
    cutoff = datetime.utcnow() - timedelta(minutes=30)
    if not db.query(Alert).filter(Alert.agent_id==agent_id, Alert.alert_type==atype,
                                   Alert.created_at>cutoff, Alert.acknowledged==False).first():
        db.add(Alert(agent_id=agent_id, alert_type=atype, severity=severity, message=message))

@app.get("/api/agents")
def list_agents(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    cutoff = datetime.utcnow() - timedelta(minutes=5)
    for a in db.query(Agent).filter(Agent.last_seen < cutoff, Agent.status == "online").all():
        a.status = "offline"
        _alert(db, a.id, "offline", "warning", f"{a.hostname} está OFFLINE")
    db.commit()
    result = []
    for a in db.query(Agent).all():
        m = db.query(Metric).filter(Metric.agent_id==a.id).order_by(Metric.timestamp.desc()).first()
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
            "asset_id": asset.id if asset else None,
            "personnel": {
                "id": asset.personnel.id, "full_name": asset.personnel.full_name,
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
    if not a: raise HTTPException(status_code=404, detail="Agente no encontrado")
    metrics = db.query(Metric).filter(Metric.agent_id==agent_id).order_by(Metric.timestamp.desc()).limit(60).all()
    asset = db.query(Asset).filter(Asset.agent_id==agent_id).first()
    return {
        "id": a.id, "uid": a.uid, "hostname": a.hostname,
        "ip_address": a.ip_address, "mac_address": a.mac_address,
        "os_name": a.os_name, "os_version": a.os_version,
        "cpu_model": a.cpu_model, "cpu_cores": a.cpu_cores,
        "ram_total_gb": a.ram_total_gb, "disk_total_gb": a.disk_total_gb,
        "tags": json.loads(a.tags or "[]"), "status": a.status,
        "last_seen": a.last_seen.isoformat() if a.last_seen else None,
        "asset": {"id": asset.id, "asset_code": asset.asset_code,
                  "personnel_id": asset.personnel_id,
                  "personnel_name": asset.personnel.full_name if asset and asset.personnel else None,
                  "auto_created": asset.auto_created} if asset else None,
        "metrics_history": [{"timestamp": m.timestamp.isoformat(),
            "cpu_percent": m.cpu_percent, "ram_percent": m.ram_percent,
            "disk_percent": m.disk_percent, "net_sent": m.net_bytes_sent,
            "net_recv": m.net_bytes_recv, "process_count": m.process_count,
            "open_ports": json.loads(m.open_ports or "[]")} for m in reversed(metrics)]
    }

@app.put("/api/agents/{agent_id}/tags")
def update_tags(agent_id: int, data: TagUpdateSchema, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    a = db.query(Agent).filter(Agent.id == agent_id).first()
    if not a: raise HTTPException(status_code=404, detail="Agente no encontrado")
    a.tags = json.dumps([t.upper().strip() for t in data.tags])
    db.commit()
    return {"tags": json.loads(a.tags)}

@app.delete("/api/agents/{agent_id}")
def delete_agent(agent_id: int, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    a = db.query(Agent).filter(Agent.id == agent_id).first()
    if not a: raise HTTPException(status_code=404, detail="Agente no encontrado")
    db.delete(a); db.commit()
    return {"deleted": True}

# ─── ASSETS ────────────────────────────────────────────────────────────────────

def _asset_to_dict(a: Asset):
    return {
        "id": a.id, "asset_code": a.asset_code, "asset_type": a.asset_type,
        "brand": a.brand, "model": a.model, "serial_number": a.serial_number,
        "purchase_date": a.purchase_date, "purchase_cost": a.purchase_cost,
        "responsible": a.responsible, "personnel_id": a.personnel_id,
        "location": a.location, "status": a.status, "notes": a.notes,
        "auto_created": a.auto_created, "carta_sent": a.carta_sent,
        "carta_sent_at": a.carta_sent_at.isoformat() if a.carta_sent_at else None,
        "created_at": a.created_at.isoformat(),
        "agent_id": a.agent_id,
        "agent": {"hostname": a.agent.hostname, "ip_address": a.agent.ip_address,
                  "mac_address": a.agent.mac_address, "os_name": a.agent.os_name,
                  "os_version": a.agent.os_version, "status": a.agent.status} if a.agent else None,
        "personnel": {"id": a.personnel.id, "full_name": a.personnel.full_name,
                      "employee_id": a.personnel.employee_id, "position": a.personnel.position,
                      "department": a.personnel.department, "email": a.personnel.email} if a.personnel else None,
        "maintenance_count": len(a.maintenances),
        "last_maintenance": max((m.maintenance_date for m in a.maintenances), default=None)
    }

@app.get("/api/assets")
def list_assets(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return [_asset_to_dict(a) for a in db.query(Asset).all()]

@app.post("/api/assets")
def create_asset(data: AssetSchema, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    count = db.query(Asset).count()
    asset = Asset(asset_code=f"ACT-{str(count+1).zfill(5)}", **data.dict())
    db.add(asset); db.commit(); db.refresh(asset)
    return {"id": asset.id, "asset_code": asset.asset_code}

@app.put("/api/assets/{asset_id}")
def update_asset(asset_id: int, data: AssetSchema, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    asset = db.query(Asset).filter(Asset.id == asset_id).first()
    if not asset: raise HTTPException(status_code=404, detail="Activo no encontrado")
    for k, v in data.dict().items(): setattr(asset, k, v)
    db.commit()
    return {"updated": True}

@app.post("/api/assets/{asset_id}/assign")
def assign_asset(asset_id: int, data: AssetAssignSchema, background_tasks: BackgroundTasks,
                 request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    asset  = db.query(Asset).filter(Asset.id == asset_id).first()
    person = db.query(Personnel).filter(Personnel.id == data.personnel_id).first()
    if not asset:  raise HTTPException(status_code=404, detail="Activo no encontrado")
    if not person: raise HTTPException(status_code=404, detail="Personal no encontrado")

    asset.personnel_id = data.personnel_id
    asset.responsible  = person.full_name
    asset.carta_sent   = False
    db.commit(); db.refresh(asset)

    cfg = get_smtp_config(db)
    base_url = str(request.base_url).rstrip("/")
    carta_url = f"{base_url}/api/assets/{asset_id}/carta"

    if data.send_email and cfg.enabled and person.email:
        html = email_asignacion_html(asset, person, cfg.company, carta_url)
        background_tasks.add_task(send_email_bg, person.email,
            f"Asignación de equipo {asset.asset_code} — {cfg.company}", html, db)
        asset.carta_sent = True
        asset.carta_sent_at = datetime.utcnow()
        db.commit()

    return {"assigned": True, "personnel": person.full_name, "carta_url": carta_url}

@app.get("/api/assets/{asset_id}/carta", response_class=HTMLResponse)
def get_carta(asset_id: int, db: Session = Depends(get_db)):
    asset = db.query(Asset).filter(Asset.id == asset_id).first()
    if not asset: raise HTTPException(status_code=404, detail="Activo no encontrado")
    if not asset.personnel: raise HTTPException(status_code=400, detail="Sin responsable asignado")
    cfg = get_smtp_config(db)
    return HTMLResponse(generate_carta_html(asset, asset.personnel, cfg.company or COMPANY_NAME))

@app.delete("/api/assets/{asset_id}")
def delete_asset(asset_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    asset = db.query(Asset).filter(Asset.id == asset_id).first()
    if not asset: raise HTTPException(status_code=404, detail="Activo no encontrado")
    db.delete(asset); db.commit()
    return {"deleted": True}

# ─── MAINTENANCE ───────────────────────────────────────────────────────────────

@app.get("/api/maintenance")
def list_maintenance(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return [{"id": m.id, "asset_id": m.asset_id,
             "asset_code": m.asset.asset_code if m.asset else "",
             "asset_name": f"{m.asset.brand} {m.asset.model}" if m.asset else "",
             "maintenance_date": m.maintenance_date, "next_date": m.next_date,
             "technician": m.technician, "maint_type": m.maint_type,
             "observations": m.observations, "status": m.status,
             "created_at": m.created_at.isoformat()}
            for m in db.query(Maintenance).order_by(Maintenance.created_at.desc()).all()]

@app.post("/api/maintenance")
def create_maintenance(data: MaintenanceSchema, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    m = Maintenance(**data.dict()); db.add(m)
    asset = db.query(Asset).filter(Asset.id == data.asset_id).first()
    if asset: asset.status = "active" if data.status == "completed" else "maintenance"
    db.commit(); db.refresh(m)
    return {"id": m.id}

@app.delete("/api/maintenance/{mid}")
def delete_maintenance(mid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    m = db.query(Maintenance).filter(Maintenance.id == mid).first()
    if not m: raise HTTPException(status_code=404, detail="No encontrado")
    db.delete(m); db.commit()
    return {"deleted": True}

# ─── ALERTS ────────────────────────────────────────────────────────────────────

@app.get("/api/alerts")
def list_alerts(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return [{"id": a.id, "agent_id": a.agent_id, "alert_type": a.alert_type,
             "severity": a.severity, "message": a.message, "acknowledged": a.acknowledged,
             "created_at": a.created_at.isoformat()}
            for a in db.query(Alert).order_by(Alert.created_at.desc()).limit(200).all()]

@app.put("/api/alerts/{alert_id}/acknowledge")
def ack_alert(alert_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    a = db.query(Alert).filter(Alert.id == alert_id).first()
    if not a: raise HTTPException(status_code=404)
    a.acknowledged = True; db.commit()
    return {"acknowledged": True}

@app.post("/api/alerts/ack-all")
def ack_all(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    db.query(Alert).filter(Alert.acknowledged==False).update({"acknowledged": True})
    db.commit(); return {"acknowledged": True}

# ─── DASHBOARD ─────────────────────────────────────────────────────────────────

@app.get("/api/dashboard")
def dashboard(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    agents  = db.query(Agent).all()
    online  = [a for a in agents if a.status == "online"]
    offline = [a for a in agents if a.status == "offline"]
    assets  = db.query(Asset).all()
    unack   = db.query(Alert).filter(Alert.acknowledged==False).count()
    crit    = db.query(Alert).filter(Alert.acknowledged==False, Alert.severity=="critical").count()
    pending = db.query(Maintenance).filter(Maintenance.status=="pending").count()
    pending_assign = db.query(Asset).filter(Asset.personnel_id==None).count()
    auto_assets    = db.query(Asset).filter(Asset.auto_created==True).count()
    total_personnel = db.query(Personnel).count()

    # OS distribution
    os_dist = {}
    for a in agents:
        key = a.os_name or "Unknown"
        os_dist[key] = os_dist.get(key, 0) + 1

    # Asset type distribution
    type_dist = {}
    for a in assets:
        type_dist[a.asset_type] = type_dist.get(a.asset_type, 0) + 1

    # Dept distribution
    dept_dist = {}
    for p in db.query(Personnel).all():
        dept_dist[p.department] = dept_dist.get(p.department, 0) + 1

    # Avg metrics
    cpus = rams = disks = []
    for a in online:
        m = db.query(Metric).filter(Metric.agent_id==a.id).order_by(Metric.timestamp.desc()).first()
        if m:
            cpus.append(m.cpu_percent); rams.append(m.ram_percent); disks.append(m.disk_percent)

    return {
        "agents":   {"total": len(agents), "online": len(online), "offline": len(offline)},
        "assets":   {"total": len(assets), "active": sum(1 for a in assets if a.status=="active"),
                     "pending_assign": pending_assign, "auto_created": auto_assets},
        "personnel":{"total": total_personnel},
        "maintenance":{"pending": pending},
        "alerts":   {"unacknowledged": unack, "critical": crit},
        "avg_metrics": {"cpu": round(sum(cpus)/len(cpus),1) if cpus else 0,
                        "ram": round(sum(rams)/len(rams),1) if rams else 0,
                        "disk": round(sum(disks)/len(disks),1) if disks else 0},
        "os_distribution":   os_dist,
        "asset_distribution": type_dist,
        "dept_distribution":  dept_dist,
        "server_time": datetime.utcnow().isoformat(),
        "version": VERSION,
    }

# ─── USERS ─────────────────────────────────────────────────────────────────────

@app.get("/api/users")
def list_users(user: User = Depends(require_admin), db: Session = Depends(get_db)):
    return [{"id": u.id, "username": u.username, "full_name": u.full_name,
             "email": u.email, "role": u.role, "is_active": u.is_active,
             "created_at": u.created_at.isoformat()} for u in db.query(User).all()]

@app.post("/api/users")
def create_user(data: UserCreateSchema, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    if db.query(User).filter(User.username == data.username).first():
        raise HTTPException(status_code=400, detail="Usuario ya existe")
    u = User(username=data.username, password_hash=hash_password(data.password),
             full_name=data.full_name, email=data.email, role=data.role)
    db.add(u); db.commit()
    return {"id": u.id}

@app.delete("/api/users/{uid}")
def delete_user(uid: int, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    u = db.query(User).filter(User.id == uid).first()
    if not u: raise HTTPException(status_code=404)
    if u.username == "admin": raise HTTPException(status_code=400, detail="No se puede eliminar admin")
    db.delete(u); db.commit()
    return {"deleted": True}

# ─── SMTP CONFIG ───────────────────────────────────────────────────────────────

@app.get("/api/config/smtp")
def get_smtp(user: User = Depends(require_admin), db: Session = Depends(get_db)):
    cfg = get_smtp_config(db)
    return {"host": cfg.host, "port": cfg.port, "username": cfg.username,
            "password": "***" if cfg.password else "", "from_name": cfg.from_name,
            "company": cfg.company, "enabled": cfg.enabled}

@app.put("/api/config/smtp")
def update_smtp(data: SMTPConfigSchema, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    cfg = get_smtp_config(db)
    cfg.host = data.host; cfg.port = data.port; cfg.username = data.username
    if data.password and data.password != "***": cfg.password = data.password
    cfg.from_name = data.from_name; cfg.company = data.company; cfg.enabled = data.enabled
    db.commit()
    return {"updated": True}

@app.post("/api/config/smtp/test")
def test_smtp(user: User = Depends(require_admin), db: Session = Depends(get_db)):
    cfg = get_smtp_config(db)
    ok = send_email_bg(cfg.username, "✅ Test InfraWatch SMTP", "<h2>✅ SMTP configurado correctamente</h2><p>InfraWatch puede enviar correos.</p>", db)
    return {"success": ok, "message": "Email enviado" if ok else "Error al enviar. Verifica configuración."}

# ─── REPORTS ───────────────────────────────────────────────────────────────────

@app.get("/api/reports/inventory")
def report_inventory(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    agents = db.query(Agent).all()
    return {"generated_at": datetime.utcnow().isoformat(), "total": len(agents),
            "data": [{"hostname": a.hostname, "ip": a.ip_address, "mac": a.mac_address,
                       "os": f"{a.os_name} {a.os_version}", "cpu": a.cpu_model,
                       "ram_gb": a.ram_total_gb, "disk_gb": a.disk_total_gb,
                       "status": a.status, "tags": json.loads(a.tags or "[]"),
                       "last_seen": a.last_seen.isoformat() if a.last_seen else ""} for a in agents]}

@app.get("/api/reports/assets")
def report_assets(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    assets = db.query(Asset).all()
    return {"generated_at": datetime.utcnow().isoformat(), "total": len(assets),
            "data": [{"asset_code": a.asset_code, "type": a.asset_type, "brand": a.brand,
                       "model": a.model, "serial": a.serial_number, "responsible": a.responsible,
                       "personnel": a.personnel.full_name if a.personnel else "",
                       "department": a.personnel.department if a.personnel else "",
                       "location": a.location, "status": a.status,
                       "carta_sent": a.carta_sent} for a in assets]}

@app.get("/api/reports/personnel")
def report_personnel(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    people = db.query(Personnel).all()
    return {"generated_at": datetime.utcnow().isoformat(), "total": len(people),
            "data": [{"employee_id": p.employee_id, "full_name": p.full_name,
                       "position": p.position, "department": p.department,
                       "email": p.email, "phone": p.phone, "location": p.location,
                       "assets": [a.asset_code for a in p.assets],
                       "asset_count": len(p.assets)} for p in people]}

# ─── HEALTH & STATIC ───────────────────────────────────────────────────────────

@app.get("/api/health")
def health():
    return {"status": "ok", "app": APP_NAME, "version": VERSION, "time": datetime.utcnow().isoformat()}

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/", include_in_schema=False)
    @app.get("/{full_path:path}", include_in_schema=False)
    def serve_spa(full_path: str = ""):
        if full_path.startswith("api/"): raise HTTPException(status_code=404)
        idx = os.path.join(STATIC_DIR, "index.html")
        return FileResponse(idx) if os.path.exists(idx) else JSONResponse({"status": "ok"})

@app.on_event("startup")
def startup():
    log.info(f"🚀 {APP_NAME} v{VERSION} iniciando...")
    init_db()
    log.info("✅ Base de datos lista")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
