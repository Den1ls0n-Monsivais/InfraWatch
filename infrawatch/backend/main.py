"""
InfraWatch - Backend API
FastAPI + SQLAlchemy + SQLite
"""

from fastapi import FastAPI, HTTPException, Depends, status, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Text, Boolean, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session, relationship
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timedelta
import jwt
import bcrypt
import os
import json
import uuid
import subprocess
import platform
import logging

# ─── CONFIG ────────────────────────────────────────────────────────────────────

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:////opt/infrawatch/data/infrawatch.db")
SECRET_KEY   = os.getenv("SECRET_KEY", "infrawatch-secret-change-in-prod-2024")
JWT_ALGO     = "HS256"
JWT_EXP_HRS  = 24
VERSION      = "1.0.0"
APP_NAME     = "InfraWatch"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

# ─── DATABASE ──────────────────────────────────────────────────────────────────

os.makedirs("/opt/infrawatch/data", exist_ok=True)
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ─── MODELS ────────────────────────────────────────────────────────────────────

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
    tags          = Column(Text, default="[]")        # JSON array
    status        = Column(String, default="online")  # online/offline/warning
    last_seen     = Column(DateTime, default=datetime.utcnow)
    registered_at = Column(DateTime, default=datetime.utcnow)
    agent_version = Column(String, default="1.0")
    metrics       = relationship("Metric", back_populates="agent", cascade="all, delete")

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
    id            = Column(Integer, primary_key=True, index=True)
    asset_code    = Column(String, unique=True, index=True)
    asset_type    = Column(String)   # laptop/pc/server/switch/firewall/printer/other
    brand         = Column(String)
    model         = Column(String)
    serial_number = Column(String)
    purchase_date = Column(String)
    purchase_cost = Column(Float, default=0)
    responsible   = Column(String)
    location      = Column(String)
    status        = Column(String, default="active")  # active/maintenance/repair/decommissioned
    notes         = Column(Text, default="")
    created_at    = Column(DateTime, default=datetime.utcnow)
    agent_id      = Column(Integer, ForeignKey("agents.id"), nullable=True)
    maintenances  = relationship("Maintenance", back_populates="asset", cascade="all, delete")

class Maintenance(Base):
    __tablename__ = "maintenances"
    id               = Column(Integer, primary_key=True, index=True)
    asset_id         = Column(Integer, ForeignKey("assets.id"))
    maintenance_date = Column(String)
    next_date        = Column(String, nullable=True)
    technician       = Column(String)
    maint_type       = Column(String)   # preventive/corrective/upgrade
    observations     = Column(Text, default="")
    status           = Column(String, default="completed")  # completed/pending/in_progress
    created_at       = Column(DateTime, default=datetime.utcnow)
    asset            = relationship("Asset", back_populates="maintenances")

class Alert(Base):
    __tablename__ = "alerts"
    id           = Column(Integer, primary_key=True, index=True)
    agent_id     = Column(Integer, ForeignKey("agents.id"), nullable=True)
    alert_type   = Column(String)   # cpu/ram/disk/offline/new_device
    severity     = Column(String, default="warning")  # info/warning/critical
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
    role          = Column(String, default="viewer")  # admin/technician/auditor/viewer
    is_active     = Column(Boolean, default=True)
    created_at    = Column(DateTime, default=datetime.utcnow)

Base.metadata.create_all(bind=engine)

# ─── SCHEMAS ───────────────────────────────────────────────────────────────────

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
    agent_version: Optional[str]  = "1.0"

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
    brand:         str
    model:         str
    serial_number: Optional[str] = ""
    purchase_date: Optional[str] = ""
    purchase_cost: Optional[float] = 0
    responsible:   Optional[str] = ""
    location:      Optional[str] = ""
    status:        Optional[str] = "active"
    notes:         Optional[str] = ""
    agent_id:      Optional[int] = None

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

# ─── AUTH ──────────────────────────────────────────────────────────────────────

security = HTTPBearer(auto_error=False)

def create_token(user_id: int, username: str, role: str) -> str:
    payload = {
        "sub": str(user_id),
        "username": username,
        "role": role,
        "exp": datetime.utcnow() + timedelta(hours=JWT_EXP_HRS)
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=JWT_ALGO)

def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[JWT_ALGO])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expirado")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Token inválido")

def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db)
) -> User:
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

def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()

def verify_password(pw: str, hashed: str) -> bool:
    return bcrypt.checkpw(pw.encode(), hashed.encode())

# ─── INIT DB ───────────────────────────────────────────────────────────────────

def init_db():
    db = SessionLocal()
    admin_exists = db.query(User).filter(User.username == "admin").first()
    if not admin_exists:
        admin = User(
            username      = "admin",
            password_hash = hash_password("infrawatch"),
            full_name     = "Administrador",
            email         = "admin@infrawatch.local",
            role          = "admin",
        )
        db.add(admin)
        db.commit()
        log.info("✅ Usuario admin creado: admin / infrawatch")
    db.close()

# ─── APP ───────────────────────────────────────────────────────────────────────

app = FastAPI(title=APP_NAME, version=VERSION, docs_url="/api/docs")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── AUTH ROUTES ───────────────────────────────────────────────────────────────

@app.post("/api/auth/login")
def login(data: UserLoginSchema, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == data.username).first()
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Credenciales incorrectas")
    token = create_token(user.id, user.username, user.role)
    return {"token": token, "username": user.username, "role": user.role, "full_name": user.full_name}

@app.get("/api/auth/me")
def me(user: User = Depends(get_current_user)):
    return {"id": user.id, "username": user.username, "role": user.role, "full_name": user.full_name, "email": user.email}

# ─── AGENT ROUTES (no auth - agents register themselves) ───────────────────────

@app.post("/api/agents/register")
def agent_register(data: AgentRegisterSchema, db: Session = Depends(get_db)):
    # Find existing agent by MAC or hostname+IP
    agent = db.query(Agent).filter(
        (Agent.mac_address == data.mac_address) | 
        (Agent.hostname == data.hostname)
    ).first()

    is_new = False
    if agent:
        # Update existing
        agent.hostname      = data.hostname
        agent.ip_address    = data.ip_address
        agent.mac_address   = data.mac_address
        agent.os_name       = data.os_name
        agent.os_version    = data.os_version
        agent.cpu_model     = data.cpu_model
        agent.cpu_cores     = data.cpu_cores
        agent.ram_total_gb  = data.ram_total_gb
        agent.disk_total_gb = data.disk_total_gb
        agent.agent_version = data.agent_version
        agent.status        = "online"
        agent.last_seen     = datetime.utcnow()
    else:
        is_new = True
        agent = Agent(
            hostname      = data.hostname,
            ip_address    = data.ip_address,
            mac_address   = data.mac_address,
            os_name       = data.os_name,
            os_version    = data.os_version,
            cpu_model     = data.cpu_model,
            cpu_cores     = data.cpu_cores,
            ram_total_gb  = data.ram_total_gb,
            disk_total_gb = data.disk_total_gb,
            agent_version = data.agent_version,
            status        = "online",
        )
        db.add(agent)
        db.flush()
        # Alert for new device
        alert = Alert(
            agent_id   = agent.id,
            alert_type = "new_device",
            severity   = "info",
            message    = f"Nuevo dispositivo registrado: {data.hostname} ({data.ip_address})"
        )
        db.add(alert)

    db.commit()
    db.refresh(agent)
    log.info(f"{'📥 Nuevo' if is_new else '🔄 Update'} agente: {agent.hostname} [{agent.ip_address}]")
    return {"uid": agent.uid, "id": agent.id, "registered": is_new}

@app.post("/api/agents/{agent_uid}/heartbeat")
def agent_heartbeat(agent_uid: str, data: HeartbeatSchema, db: Session = Depends(get_db)):
    agent = db.query(Agent).filter(Agent.uid == agent_uid).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agente no encontrado")

    agent.status    = "online"
    agent.last_seen = datetime.utcnow()

    metric = Metric(
        agent_id        = agent.id,
        cpu_percent     = data.cpu_percent,
        ram_percent     = data.ram_percent,
        disk_percent    = data.disk_percent,
        net_bytes_sent  = data.net_bytes_sent,
        net_bytes_recv  = data.net_bytes_recv,
        uptime_seconds  = data.uptime_seconds,
        process_count   = data.process_count,
        open_ports      = json.dumps(data.open_ports),
    )
    db.add(metric)

    # Auto alerts
    if data.cpu_percent > 90:
        _create_alert(db, agent.id, "cpu", "critical", f"{agent.hostname}: CPU al {data.cpu_percent:.0f}%")
    elif data.cpu_percent > 75:
        _create_alert(db, agent.id, "cpu", "warning", f"{agent.hostname}: CPU al {data.cpu_percent:.0f}%")

    if data.ram_percent > 90:
        _create_alert(db, agent.id, "ram", "critical", f"{agent.hostname}: RAM al {data.ram_percent:.0f}%")

    if data.disk_percent > 90:
        _create_alert(db, agent.id, "disk", "critical", f"{agent.hostname}: Disco al {data.disk_percent:.0f}%")

    db.commit()
    return {"status": "ok", "server_time": datetime.utcnow().isoformat()}

def _create_alert(db, agent_id, atype, severity, message):
    # Avoid duplicate alerts in last 30 min
    cutoff = datetime.utcnow() - timedelta(minutes=30)
    existing = db.query(Alert).filter(
        Alert.agent_id == agent_id,
        Alert.alert_type == atype,
        Alert.created_at > cutoff,
        Alert.acknowledged == False
    ).first()
    if not existing:
        db.add(Alert(agent_id=agent_id, alert_type=atype, severity=severity, message=message))

# ─── AGENTS CRUD ───────────────────────────────────────────────────────────────

@app.get("/api/agents")
def list_agents(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # Mark offline agents (no heartbeat in 5 min)
    cutoff = datetime.utcnow() - timedelta(minutes=5)
    offline = db.query(Agent).filter(Agent.last_seen < cutoff, Agent.status == "online").all()
    for a in offline:
        a.status = "offline"
        _create_alert(db, a.id, "offline", "warning", f"{a.hostname} está OFFLINE")
    if offline:
        db.commit()

    agents = db.query(Agent).all()
    result = []
    for a in agents:
        latest = db.query(Metric).filter(Metric.agent_id == a.id).order_by(Metric.timestamp.desc()).first()
        result.append({
            "id": a.id, "uid": a.uid, "hostname": a.hostname,
            "ip_address": a.ip_address, "mac_address": a.mac_address,
            "os_name": a.os_name, "os_version": a.os_version,
            "cpu_model": a.cpu_model, "cpu_cores": a.cpu_cores,
            "ram_total_gb": a.ram_total_gb, "disk_total_gb": a.disk_total_gb,
            "tags": json.loads(a.tags or "[]"),
            "status": a.status,
            "last_seen": a.last_seen.isoformat() if a.last_seen else None,
            "registered_at": a.registered_at.isoformat() if a.registered_at else None,
            "metrics": {
                "cpu_percent":    latest.cpu_percent if latest else 0,
                "ram_percent":    latest.ram_percent if latest else 0,
                "disk_percent":   latest.disk_percent if latest else 0,
                "uptime_seconds": latest.uptime_seconds if latest else 0,
                "process_count":  latest.process_count if latest else 0,
            } if latest else None
        })
    return result

@app.get("/api/agents/{agent_id}")
def get_agent(agent_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agente no encontrado")
    metrics = db.query(Metric).filter(Metric.agent_id == agent_id).order_by(Metric.timestamp.desc()).limit(60).all()
    return {
        "id": agent.id, "uid": agent.uid, "hostname": agent.hostname,
        "ip_address": agent.ip_address, "mac_address": agent.mac_address,
        "os_name": agent.os_name, "os_version": agent.os_version,
        "cpu_model": agent.cpu_model, "cpu_cores": agent.cpu_cores,
        "ram_total_gb": agent.ram_total_gb, "disk_total_gb": agent.disk_total_gb,
        "tags": json.loads(agent.tags or "[]"),
        "status": agent.status,
        "last_seen": agent.last_seen.isoformat() if agent.last_seen else None,
        "metrics_history": [
            {
                "timestamp":     m.timestamp.isoformat(),
                "cpu_percent":   m.cpu_percent,
                "ram_percent":   m.ram_percent,
                "disk_percent":  m.disk_percent,
                "net_sent":      m.net_bytes_sent,
                "net_recv":      m.net_bytes_recv,
                "process_count": m.process_count,
                "open_ports":    json.loads(m.open_ports or "[]"),
            } for m in reversed(metrics)
        ]
    }

@app.put("/api/agents/{agent_id}/tags")
def update_tags(agent_id: int, data: TagUpdateSchema, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agente no encontrado")
    agent.tags = json.dumps([t.upper().strip() for t in data.tags])
    db.commit()
    return {"tags": json.loads(agent.tags)}

@app.delete("/api/agents/{agent_id}")
def delete_agent(agent_id: int, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agente no encontrado")
    db.delete(agent)
    db.commit()
    return {"deleted": True}

# ─── ASSETS CRUD ───────────────────────────────────────────────────────────────

@app.get("/api/assets")
def list_assets(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    assets = db.query(Asset).all()
    return [
        {
            "id": a.id, "asset_code": a.asset_code, "asset_type": a.asset_type,
            "brand": a.brand, "model": a.model, "serial_number": a.serial_number,
            "purchase_date": a.purchase_date, "purchase_cost": a.purchase_cost,
            "responsible": a.responsible, "location": a.location,
            "status": a.status, "notes": a.notes,
            "created_at": a.created_at.isoformat(),
            "agent_id": a.agent_id,
            "maintenance_count": len(a.maintenances),
            "last_maintenance": max((m.maintenance_date for m in a.maintenances), default=None)
        } for a in assets
    ]

@app.post("/api/assets")
def create_asset(data: AssetSchema, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    count = db.query(Asset).count()
    asset = Asset(
        asset_code    = f"ACT-{str(count+1).zfill(5)}",
        asset_type    = data.asset_type,
        brand         = data.brand,
        model         = data.model,
        serial_number = data.serial_number,
        purchase_date = data.purchase_date,
        purchase_cost = data.purchase_cost,
        responsible   = data.responsible,
        location      = data.location,
        status        = data.status,
        notes         = data.notes,
        agent_id      = data.agent_id,
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return {"id": asset.id, "asset_code": asset.asset_code}

@app.put("/api/assets/{asset_id}")
def update_asset(asset_id: int, data: AssetSchema, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    asset = db.query(Asset).filter(Asset.id == asset_id).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Activo no encontrado")
    for k, v in data.dict().items():
        setattr(asset, k, v)
    db.commit()
    return {"updated": True}

@app.delete("/api/assets/{asset_id}")
def delete_asset(asset_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    asset = db.query(Asset).filter(Asset.id == asset_id).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Activo no encontrado")
    db.delete(asset)
    db.commit()
    return {"deleted": True}

# ─── MAINTENANCE CRUD ──────────────────────────────────────────────────────────

@app.get("/api/maintenance")
def list_maintenance(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    records = db.query(Maintenance).order_by(Maintenance.created_at.desc()).all()
    return [
        {
            "id": m.id, "asset_id": m.asset_id,
            "asset_code": m.asset.asset_code if m.asset else "",
            "asset_name":  f"{m.asset.brand} {m.asset.model}" if m.asset else "",
            "maintenance_date": m.maintenance_date,
            "next_date": m.next_date,
            "technician": m.technician,
            "maint_type": m.maint_type,
            "observations": m.observations,
            "status": m.status,
            "created_at": m.created_at.isoformat(),
        } for m in records
    ]

@app.post("/api/maintenance")
def create_maintenance(data: MaintenanceSchema, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    m = Maintenance(**data.dict())
    db.add(m)
    # Update asset status
    asset = db.query(Asset).filter(Asset.id == data.asset_id).first()
    if asset:
        asset.status = "active" if data.status == "completed" else "maintenance"
    db.commit()
    db.refresh(m)
    return {"id": m.id}

@app.delete("/api/maintenance/{maint_id}")
def delete_maintenance(maint_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    m = db.query(Maintenance).filter(Maintenance.id == maint_id).first()
    if not m:
        raise HTTPException(status_code=404, detail="Mantenimiento no encontrado")
    db.delete(m)
    db.commit()
    return {"deleted": True}

# ─── ALERTS ────────────────────────────────────────────────────────────────────

@app.get("/api/alerts")
def list_alerts(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    alerts = db.query(Alert).order_by(Alert.created_at.desc()).limit(100).all()
    return [
        {
            "id": a.id, "agent_id": a.agent_id,
            "alert_type": a.alert_type, "severity": a.severity,
            "message": a.message, "acknowledged": a.acknowledged,
            "created_at": a.created_at.isoformat()
        } for a in alerts
    ]

@app.put("/api/alerts/{alert_id}/acknowledge")
def ack_alert(alert_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alerta no encontrada")
    alert.acknowledged = True
    db.commit()
    return {"acknowledged": True}

@app.post("/api/alerts/ack-all")
def ack_all_alerts(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    db.query(Alert).filter(Alert.acknowledged == False).update({"acknowledged": True})
    db.commit()
    return {"acknowledged": True}

# ─── DASHBOARD ─────────────────────────────────────────────────────────────────

@app.get("/api/dashboard")
def dashboard(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    total_agents    = db.query(Agent).count()
    online_agents   = db.query(Agent).filter(Agent.status == "online").count()
    offline_agents  = db.query(Agent).filter(Agent.status == "offline").count()
    total_assets    = db.query(Asset).count()
    active_assets   = db.query(Asset).filter(Asset.status == "active").count()
    pending_maint   = db.query(Maintenance).filter(Maintenance.status == "pending").count()
    unack_alerts    = db.query(Alert).filter(Alert.acknowledged == False).count()
    critical_alerts = db.query(Alert).filter(Alert.acknowledged == False, Alert.severity == "critical").count()

    # Average metrics from last heartbeat per agent
    agents = db.query(Agent).filter(Agent.status == "online").all()
    avg_cpu = avg_ram = avg_disk = 0
    if agents:
        cpus = rams = disks = []
        for a in agents:
            m = db.query(Metric).filter(Metric.agent_id == a.id).order_by(Metric.timestamp.desc()).first()
            if m:
                cpus.append(m.cpu_percent)
                rams.append(m.ram_percent)
                disks.append(m.disk_percent)
        if cpus:
            avg_cpu  = sum(cpus)  / len(cpus)
            avg_ram  = sum(rams)  / len(rams)
            avg_disk = sum(disks) / len(disks)

    return {
        "agents": {"total": total_agents, "online": online_agents, "offline": offline_agents},
        "assets": {"total": total_assets, "active": active_assets},
        "maintenance": {"pending": pending_maint},
        "alerts": {"unacknowledged": unack_alerts, "critical": critical_alerts},
        "avg_metrics": {"cpu": round(avg_cpu, 1), "ram": round(avg_ram, 1), "disk": round(avg_disk, 1)},
        "server_time": datetime.utcnow().isoformat(),
        "version": VERSION,
    }

# ─── USERS CRUD ────────────────────────────────────────────────────────────────

@app.get("/api/users")
def list_users(user: User = Depends(require_admin), db: Session = Depends(get_db)):
    users = db.query(User).all()
    return [
        {"id": u.id, "username": u.username, "full_name": u.full_name,
         "email": u.email, "role": u.role, "is_active": u.is_active,
         "created_at": u.created_at.isoformat()}
        for u in users
    ]

@app.post("/api/users")
def create_user(data: UserCreateSchema, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    if db.query(User).filter(User.username == data.username).first():
        raise HTTPException(status_code=400, detail="Usuario ya existe")
    u = User(
        username      = data.username,
        password_hash = hash_password(data.password),
        full_name     = data.full_name,
        email         = data.email,
        role          = data.role,
    )
    db.add(u)
    db.commit()
    return {"id": u.id, "username": u.username}

@app.delete("/api/users/{user_id}")
def delete_user(user_id: int, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    u = db.query(User).filter(User.id == user_id).first()
    if not u:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    if u.username == "admin":
        raise HTTPException(status_code=400, detail="No se puede eliminar el admin principal")
    db.delete(u)
    db.commit()
    return {"deleted": True}

# ─── REPORTS ───────────────────────────────────────────────────────────────────

@app.get("/api/reports/inventory")
def report_inventory(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    agents = db.query(Agent).all()
    return {
        "generated_at": datetime.utcnow().isoformat(),
        "total": len(agents),
        "data": [
            {
                "hostname": a.hostname, "ip": a.ip_address, "mac": a.mac_address,
                "os": f"{a.os_name} {a.os_version}", "cpu": a.cpu_model,
                "ram_gb": a.ram_total_gb, "disk_gb": a.disk_total_gb,
                "status": a.status, "tags": json.loads(a.tags or "[]"),
                "last_seen": a.last_seen.isoformat() if a.last_seen else ""
            } for a in agents
        ]
    }

@app.get("/api/reports/assets")
def report_assets(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    assets = db.query(Asset).all()
    return {
        "generated_at": datetime.utcnow().isoformat(),
        "total": len(assets),
        "data": [
            {
                "asset_code": a.asset_code, "type": a.asset_type,
                "brand": a.brand, "model": a.model, "serial": a.serial_number,
                "purchase_date": a.purchase_date, "cost": a.purchase_cost,
                "responsible": a.responsible, "location": a.location,
                "status": a.status
            } for a in assets
        ]
    }

@app.get("/api/reports/maintenance")
def report_maintenance(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    records = db.query(Maintenance).order_by(Maintenance.maintenance_date.desc()).all()
    return {
        "generated_at": datetime.utcnow().isoformat(),
        "total": len(records),
        "data": [
            {
                "asset_code": m.asset.asset_code if m.asset else "",
                "asset": f"{m.asset.brand} {m.asset.model}" if m.asset else "",
                "date": m.maintenance_date, "next": m.next_date,
                "technician": m.technician, "type": m.maint_type,
                "status": m.status, "observations": m.observations
            } for m in records
        ]
    }

# ─── HEALTH & STATIC ───────────────────────────────────────────────────────────

@app.get("/api/health")
def health():
    return {"status": "ok", "app": APP_NAME, "version": VERSION, "time": datetime.utcnow().isoformat()}

# Serve frontend SPA
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/", include_in_schema=False)
    @app.get("/{full_path:path}", include_in_schema=False)
    def serve_spa(full_path: str = ""):
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404)
        index = os.path.join(STATIC_DIR, "index.html")
        if os.path.exists(index):
            return FileResponse(index)
        return JSONResponse({"status": "ok", "message": "InfraWatch API running"})

# ─── STARTUP ───────────────────────────────────────────────────────────────────

@app.on_event("startup")
def startup():
    log.info(f"🚀 {APP_NAME} v{VERSION} iniciando...")
    init_db()
    log.info("✅ Base de datos lista")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
