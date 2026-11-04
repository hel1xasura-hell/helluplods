from fastapi import APIRouter, Depends

from app.agents.registry import AGENTS, IMPLEMENTATIONS, not_built
from app.auth.deps import get_current_owner
from app.core.config import get_settings
from app.models import Owner
from app.schemas.api import AgentOut
from app.services.integrations_status import integration_status

router = APIRouter(prefix="/api", tags=["system"])

@router.get("/agents", response_model=list[AgentOut])
def list_agents(_: Owner = Depends(get_current_owner)):
    return [
        AgentOut(key=s.key, name=s.name, responsibilities=s.responsibilities, stage=s.stage,
                 implemented=IMPLEMENTATIONS[s.key] is not not_built,
                 allowed_tools=sorted(s.allowed_tools), timeout_seconds=s.timeout_seconds,
                 max_retries=s.max_retries)
        for s in AGENTS.values()
    ]


@router.get("/integrations")
def integrations(_: Owner = Depends(get_current_owner)):
    return integration_status(get_settings())
