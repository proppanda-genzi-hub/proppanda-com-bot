from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
import uuid
import logging


from app.db.session import get_db
from app.core.agent_resolver import AgentResolver
from app.services.conversation_service import ConversationService
from app.core.persistence import get_checkpointer
from app.graphs.master_graph import get_master_graph

# Initialize Router and Logger
router = APIRouter()
logger = logging.getLogger(__name__)


# ==============================================================================
# REQUEST/RESPONSE MODELS
# ==============================================================================

class ChatRequest(BaseModel):
    """Request model for chat endpoint."""
    message: str = Field(..., description="User's message text", min_length=1)
    agent_id: str = Field(..., description="ID of the agent/bot to interact with")
    session_id: Optional[str] = Field(None, description="Session ID for conversation continuity.")
    user_id: Optional[str] = Field(None, description="Unique user identifier.")
    user_name: Optional[str] = Field("User", description="Display name of the user")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")


class ChatResponse(BaseModel):
    """Response model for chat endpoint."""
    response: str = Field(..., description="AI assistant's response")
    session_id: str = Field(..., description="Session ID for conversation continuity")
    agent_id: str = Field(..., description="Agent ID that processed the request")
    agent_name: Optional[str] = Field(None, description="Name of the AI agent")
    active_flow: Optional[str] = Field(None, description="Current conversation flow")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional response metadata")
    
    # Simplified Structured Output
    properties: Optional[List[Dict[str, Any]]] = Field(default_factory=list, description="List of found properties")
    contextual_suggestions: Optional[List[str]] = Field(default_factory=list)


class AgentInfoResponse(BaseModel):
    """Response model for agent information."""
    agent_id: str
    agent_name: Optional[str]
    company_name: Optional[str]
    bio: Optional[str]
    chatbot_enabled: bool
    capabilities: Dict[str, bool]


# ==============================================================================
# CHAT ENDPOINT
# ==============================================================================

@router.post("/chat", response_model=ChatResponse)
async def chat_with_agent(
    request: ChatRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Main chat endpoint for the agentic chatbot.
    Works with or without a specific agent (common chatbot mode).
    """
    try:
        # --- A. RESOLVE THE AGENT (Optional - use defaults if not found) ---
        agent = None
        agent_id = request.agent_id or "common_chatbot"
        agent_name = "Proppanda Assistant"
        chatbot_name = "Proppanda Assistant"
        company_name = "Proppanda"
        agent_bio = "Your AI-powered real estate assistant"
        chatbot_enabled = True
        
        # Try to resolve agent if ID provided
        if request.agent_id:
            resolver = AgentResolver(db)
            agent = await resolver.resolve_by_agent_id(request.agent_id)
            
            if agent:
                # Extract agent data if found
                agent_id = agent.agent_id
                agent_name = agent.name
                chatbot_name = agent.chatbot_name or agent.name
                company_name = agent.company_name or "Proppanda"
                agent_bio = agent.bio or ""
                chatbot_enabled = agent.chatbot_enabled if agent.chatbot_enabled is not None else True

        if not chatbot_enabled:
            return ChatResponse(
                response="Hello! I am currently offline. Please try again later or contact support.",
                session_id=request.session_id or str(uuid.uuid4()),
                agent_id=agent_id,
                agent_name=chatbot_name,
                active_flow=None,
                metadata={"reason": "chatbot_disabled"}
            )
        
        # --- B. MANAGE SESSION ---
        session_id = request.session_id or str(uuid.uuid4())
        user_id = request.user_id or session_id
        user_name = request.user_name or "User"
        
        logger.info(f"🟢 AGENT '{agent_name}' received from {user_name} ({session_id}): {request.message}")

        # --- C. LOG USER MESSAGE ---
        conv_service = ConversationService(db)
        active_session_id = await conv_service.get_active_session_id(user_id, session_id)
        
        await conv_service.log_message(
            session_id=active_session_id,
            user_id=user_id,
            agent_id=agent_id,
            sender="user",
            message=request.message,
            metadata=request.metadata
        )
        await db.commit()
        logger.info(f"✅ User message logged to database")

        # --- D. SETUP PERSISTENCE & GRAPH ---
        logger.info(f"📦 Setting up checkpointer and graph...")
        checkpointer = await get_checkpointer(db.bind)
        graph = get_master_graph(checkpointer)
        logger.info(f"✅ Graph initialized")

        # --- E. CONFIGURE THREAD ---
        config = {
            "configurable": {
                "thread_id": active_session_id,
                "db_session": db
            }
        }
        logger.info(f"✅ Config prepared with thread_id: {active_session_id}")

        # --- F. PREPARE INPUT ---
        input_data = {
            "messages": [HumanMessage(content=request.message)],
            "agent_id": agent_id,
            "user_mobile": user_id,
            "user_name": user_name,
            "agent_name": chatbot_name or agent_name or "Assistant",
            "company_name": company_name or "Company",
            "agent_bio": agent_bio or ""
        }
        logger.info(f"✅ Input data prepared: messages={len(input_data['messages'])}, agent_id={agent_id}")

        # --- G. RUN GRAPH ---
        print("=" * 80)
        print(f"🚀 ABOUT TO RUN GRAPH - agent_id={agent_id}, user={user_name}")
        print(f"📝 Input message: {request.message}")
        print("=" * 80)
        logger.info(f"🚀 Running graph with agent_id: {agent_id}, user: {user_name}")
        try:
            final_state = await graph.ainvoke(input_data, config=config)
            print(f"✅ GRAPH COMPLETED - Messages in state: {len(final_state.get('messages', []))}")
            logger.info(f"✅ Graph completed. Messages count: {len(final_state.get('messages', []))}")
        except Exception as graph_error:
            logger.error(f"❌ Graph execution error: {graph_error}", exc_info=True)
            raise
        
        # --- H. GET REPLY ---
        messages = final_state.get("messages", [])
        if len(messages) < 2:
            logger.error(f"⚠️ Graph returned only {len(messages)} messages - expected at least 2")
            # Fallback response
            ai_reply = "I apologize, but I'm having trouble processing your request. Please try again or rephrase your question."
        else:
            ai_reply = messages[-1].content
            logger.info(f"💬 AI Reply (first 100 chars): {ai_reply[:100]}")
        
        active_flow = final_state.get("active_flow")
        
        # Log AI Response
        await conv_service.log_message(
            session_id=active_session_id,
            user_id=user_id,
            agent_id=agent_id,
            sender="assistant",
            message=ai_reply,
            metadata={"flow": active_flow}
        )
        await db.commit()

        logger.info(f"🔵 AGENT '{agent_name}' replied: {ai_reply[:100]}...")
        
        # --- I. PROPERTIES OUTPUT ---
        properties = final_state.get("found_properties", [])
            
        return ChatResponse(
            response=ai_reply,
            session_id=active_session_id,
            agent_id=agent_id,
            agent_name=chatbot_name or agent_name,
            active_flow=active_flow,
            metadata={
                "flow": active_flow,
                "filters": final_state.get("filters").model_dump() if final_state.get("filters") else None,
                "properties_count": len(properties)
            },
            properties=properties,
            contextual_suggestions=["Show me cheaper options", "Show me near MRT"] if properties else []
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing chat request: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, 
            detail=f"An error occurred while processing your request: {str(e)}"
        )


# ==============================================================================
# AGENT INFO ENDPOINT
# ==============================================================================

@router.get("/agent/{agent_id}", response_model=AgentInfoResponse)
async def get_agent_info(
    agent_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Get information about a specific agent.
    """
    resolver = AgentResolver(db)
    agent = await resolver.resolve_by_agent_id(agent_id)
    
    if not agent:
        raise HTTPException(
            status_code=404, 
            detail=f"Agent with ID '{agent_id}' not found"
        )
    
    # Extract all values immediately to avoid lazy loading
    return AgentInfoResponse(
        agent_id=agent.agent_id,
        agent_name=agent.chatbot_name or agent.name,
        company_name=agent.company_name,
        bio=agent.bio,
        chatbot_enabled=agent.chatbot_enabled if agent.chatbot_enabled is not None else False,
        capabilities={
            "co_living": agent.co_living_property or False,
            "rooms_for_rent": agent.rooms_for_rent or False,
            "residential_rent": agent.residential_property_rent or False,
            "residential_resale": agent.residential_property_resale or False,
            "residential_developer": agent.residential_property_developer or False,
            "commercial_rent": agent.commercial_property_rent or False,
            "commercial_resale": agent.commercial_property_resale or False,
            "commercial_developer": agent.commercial_property_developer or False
        }
    )


# ==============================================================================
# SESSION MANAGEMENT ENDPOINTS
# ==============================================================================

class NewSessionResponse(BaseModel):
    """Response for new session creation."""
    session_id: str
    message: str


@router.post("/session/new", response_model=NewSessionResponse)
async def create_new_session():
    """
    Create a new conversation session.
    """
    session_id = str(uuid.uuid4())
    return NewSessionResponse(
        session_id=session_id,
        message="New session created successfully"
    )


class SessionHistoryRequest(BaseModel):
    """Request model for session history."""
    session_id: str
    limit: Optional[int] = Field(50, description="Maximum number of messages to return")


class MessageEntry(BaseModel):
    """Single message entry in history."""
    sender: str
    message: str
    timestamp: str
    metadata: Optional[Dict[str, Any]] = None


class SessionHistoryResponse(BaseModel):
    """Response model for session history."""
    session_id: str
    messages: list[MessageEntry]
    total_count: int


@router.post("/session/history", response_model=SessionHistoryResponse)
async def get_session_history(
    request: SessionHistoryRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Retrieve conversation history for a specific session.
    """
    conv_service = ConversationService(db)
    messages = await conv_service.get_session_history(
        session_id=request.session_id,
        limit=request.limit
    )
    
    return SessionHistoryResponse(
        session_id=request.session_id,
        messages=[
            MessageEntry(
                sender=msg["sender"],
                message=msg["message"],
                timestamp=str(msg["created_at"]),
                metadata=msg.get("metadata")
            )
            for msg in messages
        ],
        total_count=len(messages)
    )


# ==============================================================================
# HEALTH CHECK
# ==============================================================================

@router.get("/health")
async def api_health():
    """API health check endpoint."""
    return {"status": "healthy", "service": "chat-api"}
