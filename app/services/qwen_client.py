import asyncio
import base64
import json
from typing import Any 
import httpx
from pydantic import BaseModel, Field, ValidationError
from app.core.config import get_settings
from app.core.logging import get_logger

logger=get_logger(__name__)

