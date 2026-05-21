import asyncio

from fastapi import APIRouter, Depends, HTTPException

from app.core.security import get_current_user
from app.db.redis import get_redis_client
from app.db.supabase import supabase
from app.schemas.chat import ChatHistoryResponse, ChatMessageRequest, ChatResponse
from app.services import chat_service

router = APIRouter()


def _verify_plant_access(plant_id: str, user_id: str) -> None:
    result = supabase.table("plants").select("user_id").eq("plant_id", plant_id).execute()
    if not result.data:
        raise ValueError("Planta no encontrada")
    if result.data[0]["user_id"] != user_id:
        raise PermissionError("No tienes acceso a esta planta")


@router.post("/{plant_id}", response_model=ChatResponse)
async def send_message(
    plant_id: str,
    body: ChatMessageRequest,
    user_id: str = Depends(get_current_user),
    redis=Depends(get_redis_client),
):
    """Envía un mensaje a la planta y recibe su respuesta."""
    try:
        return await chat_service.chat_with_plant(
            plant_id=plant_id,
            user_id=user_id,
            message=body.message,
            language=body.language,
            response_format=body.response_format,
            redis_client=redis,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error procesando el mensaje: {str(e)}")


@router.get("/{plant_id}/history", response_model=ChatHistoryResponse)
async def get_history(
    plant_id: str,
    limit: int = 50,
    user_id: str = Depends(get_current_user),
):
    """Devuelve el historial de conversación de una planta."""
    try:
        await asyncio.to_thread(_verify_plant_access, plant_id, user_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))

    messages = await chat_service.get_chat_history(plant_id, user_id, limit)
    return ChatHistoryResponse(plant_id=plant_id, messages=messages)
