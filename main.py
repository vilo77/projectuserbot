import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from pydantic import BaseModel
import asyncio


# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("main")

from app.database import init_db, get_db, ClientSession
from app.bot.userbot_manager import manager
from app.bot.assistant import assistant_app

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Initializing database...")
    await init_db()
    
    # Start Assistant Bot
    if os.getenv("ASSISTANT_BOT_TOKEN"):
        logger.info("Starting Telegram Assistant Bot...")
        asyncio.create_task(assistant_app.start())
    else:
        logger.warning("ASSISTANT_BOT_TOKEN not configured. Assistant bot will not start.")
        
    # Start all userbots in the background
    logger.info("Starting all active userbot sessions...")
    asyncio.create_task(manager.start_all())
    
    yield
    
    # Shutdown
    logger.info("Stopping all userbots...")
    await manager.stop_all()
    if os.getenv("ASSISTANT_BOT_TOKEN") and assistant_app.is_connected:
        logger.info("Stopping Assistant Bot...")
        await assistant_app.stop()

app = FastAPI(title="Kurigram Userbot Platform", lifespan=lifespan)

# Mount static files and templates
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

# Frontend Root Route
@app.get("/")
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

# API Routes
@app.get("/api/stats")
async def get_stats(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ClientSession))
    sessions = result.scalars().all()
    
    total = len(sessions)
    active = sum(1 for s in sessions if manager.get_client_status(s.phone_number) == "online")
    
    assistant_online = assistant_app.is_connected if os.getenv("ASSISTANT_BOT_TOKEN") else False
    
    return {
        "total_clients": total,
        "active_clients": active,
        "assistant_online": assistant_online
    }

@app.get("/api/clients")
async def get_clients(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ClientSession))
    sessions = result.scalars().all()
    
    clients_list = []
    for s in sessions:
        clients_list.append({
            "phone_number": s.phone_number,
            "status": manager.get_client_status(s.phone_number),
            "created_at": s.created_at.isoformat()
        })
    return clients_list

@app.post("/api/clients/{phone}/start")
async def start_client(phone: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ClientSession).where(ClientSession.phone_number == phone))
    session_record = result.scalar_one_or_none()
    
    if not session_record:
        raise HTTPException(status_code=404, detail="Client not found")
        
    if not session_record.session_string:
        raise HTTPException(status_code=400, detail="Client session is not authorized yet")
        
    try:
        success = await manager.start_client(phone, session_record.session_string)
        if success:
            session_record.is_active = True
            await db.commit()
            return {"success": True}
    except Exception as e:
        logger.error(f"Error starting client {phone}: {e}")
        return {"success": False, "message": str(e)}

@app.post("/api/clients/{phone}/stop")
async def stop_client(phone: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ClientSession).where(ClientSession.phone_number == phone))
    session_record = result.scalar_one_or_none()
    
    if not session_record:
        raise HTTPException(status_code=404, detail="Client not found")
        
    try:
        success = await manager.stop_client(phone)
        session_record.is_active = False
        await db.commit()
        return {"success": True}
    except Exception as e:
        logger.error(f"Error stopping client {phone}: {e}")
        return {"success": False, "message": str(e)}

@app.delete("/api/clients/{phone}")
async def delete_client(phone: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ClientSession).where(ClientSession.phone_number == phone))
    session_record = result.scalar_one_or_none()
    
    if not session_record:
        raise HTTPException(status_code=404, detail="Client not found")
        
    try:
        # Stop client if running
        if phone in manager.clients:
            await manager.stop_client(phone)
            
        await db.delete(session_record)
        await db.commit()
        return {"success": True}
    except Exception as e:
        logger.error(f"Error deleting client {phone}: {e}")
        return {"success": False, "message": str(e)}

class SessionAddRequest(BaseModel):
    phone_number: str
    session_string: str

@app.post("/api/clients/add_session")
async def add_session(req: SessionAddRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ClientSession).where(ClientSession.phone_number == req.phone_number))
    existing = result.scalar_one_or_none()
    
    if existing:
        existing.session_string = req.session_string
        existing.is_active = True
    else:
        new_session = ClientSession(
            phone_number=req.phone_number,
            session_string=req.session_string,
            is_active=True
        )
        db.add(new_session)
    
    await db.commit()
    
    try:
        # Start the client in userbot_manager
        await manager.start_client(req.phone_number, req.session_string)
        return {"success": True}
    except Exception as e:
        logger.error(f"Error starting client after adding session: {e}")
        return {"success": False, "message": str(e)}

