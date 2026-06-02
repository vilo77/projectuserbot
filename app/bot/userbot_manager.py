import os
import asyncio
import logging
from typing import Dict
from kurigram import Client
from sqlalchemy.future import select
from app.database import AsyncSessionLocal, ClientSession

logger = logging.getLogger("userbot_manager")

API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")

class UserbotManager:
    def __init__(self):
        self.clients: Dict[str, Client] = {}
        self.auth_states: Dict[str, dict] = {} # temporary storage for login flow

    async def start_all(self):
        """Starts all active userbots from the database."""
        if not API_ID or not API_HASH:
            logger.error("API_ID or API_HASH not configured in environment variables.")
            return

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(ClientSession).where(ClientSession.is_active == True, ClientSession.session_string != None)
            )
            sessions = result.scalars().all()
            
            logger.info(f"Found {len(sessions)} active userbot session(s) in database.")
            for s in sessions:
                try:
                    await self.start_client(s.phone_number, s.session_string)
                except Exception as e:
                    logger.error(f"Failed to start userbot for {s.phone_number}: {e}")

    async def start_client(self, phone_number: str, session_string: str) -> bool:
        """Starts a single userbot client in memory."""
        if phone_number in self.clients:
            logger.warning(f"Client {phone_number} is already running.")
            return True

        # Use in_memory=True so no local .session files are written (perfect for Railway)
        client = Client(
            name=phone_number,
            api_id=API_ID,
            api_hash=API_HASH,
            session_string=session_string,
            in_memory=True,
            plugins=dict(root="app/modules")
        )

        await client.start()
        self.clients[phone_number] = client
        logger.info(f"Successfully started userbot for {phone_number}")
        return True

    async def stop_client(self, phone_number: str) -> bool:
        """Stops a running userbot client."""
        if phone_number not in self.clients:
            logger.warning(f"Client {phone_number} is not running.")
            return False

        client = self.clients.pop(phone_number)
        await client.stop()
        logger.info(f"Successfully stopped userbot for {phone_number}")
        return True

    def get_client_status(self, phone_number: str) -> str:
        """Gets status of a client."""
        if phone_number in self.clients:
            return "online" if self.clients[phone_number].is_connected else "connecting"
        return "offline"

    async def stop_all(self):
        """Stops all running userbots."""
        for phone_number in list(self.clients.keys()):
            await self.stop_client(phone_number)

# Global Instance
manager = UserbotManager()
