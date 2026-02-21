from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig
from app.core.state import AgentState
from app.tools.knowledge_base import KnowledgeBaseTool
from app.services.openai_service import OpenAIService
import json
from datetime import datetime
import pytz
import logging

logger = logging.getLogger(__name__)

SUPER_SYSTEM_PROMPT = """
You are {agent_name}, a warm, engaging, and helpful Real Estate Agent at {company_name}. 🏠

### 1. COMPANY KNOWLEDGE (Policies, Fees, Rules)
{kb_context}

### 2. CURRENT SEARCH RESULTS (Properties discussed)
{properties_json}

### INSTRUCTIONS

1. **Analyze the Question:**
   - If it's about **company rules, contracts, viewings, deposits, policies** → Use Section 1.
   - If it's about a **specific property** already discussed → Use Section 2.
   - If it's about **Singapore living, nearby amenities, transport, neighbourhoods** → Use your **general knowledge**.
   - If it's **small talk or greetings** → Be warm.

2. **THE RULE OF RELEVANCE:**
   - Answer ANY question related to housing, living, lifestyle, locations, property surroundings.
   - ONLY decline questions that are **clearly unrelated**.

3. **THE RULE OF TRUTH:**
   - If you don't know the answer, say politely that you don't have that information.

4. **Tone:**
   - Sound like a friendly human.
   - Keep answers to 3–4 sentences.

5. **Greeting:** {greeting_instruction}

### USER MESSAGE
"{user_message}"
"""


async def intelligent_chat_node(state: AgentState, config: RunnableConfig):
    """
    Handle general chat, knowledge base queries, and property QA.
    """
    db = config.get("configurable", {}).get("db_session")
    agent_id = state["agent_id"]
    last_message = state["messages"][-1].content
    
    # 1. Fetch Contexts
    kb_tool = KnowledgeBaseTool(db)
    kb_context = await kb_tool.search(agent_id, last_message) or "No specific company documents found."

    properties = state.get("found_properties", [])
    shown_count = state.get("shown_count", 0)
    
    if properties and shown_count > 0:
        # Get the most recently shown batch (e.g., last 3)
        batch_size = 3
        start_idx = max(0, shown_count - batch_size)
        current_view_props = properties[start_idx:shown_count]
        
        context_props = []
        for i, p in enumerate(current_view_props):
            p_copy = p.copy()
            # "Option 1" corresponds to the first in the current view
            p_copy['visual_index'] = i + 1 
            context_props.append(p_copy)
            
        props_json = json.dumps(context_props, indent=2, default=str)
    elif properties:
        # Fallback if shown_count is weird, show first 3
        props_json = json.dumps(properties[:3], indent=2, default=str)
    else:
        props_json = "No active search results."

    # 2. Determine Greeting
    tz = pytz.timezone('Asia/Singapore')
    h = datetime.now(tz).hour
    greeting = "Good morning" if 5 <= h < 12 else "Good afternoon" if 12 <= h < 18 else "Good evening"
    
    is_first_interaction = len(state["messages"]) <= 1
    if is_first_interaction:
        agent_name = state.get("agent_name") or "Assistant"
        company_name = state.get("company_name") or "Company"
        greeting_instruction = f"Start with '{greeting}! I'm {agent_name} from {company_name}. What can I do for you today?'"
    else:
        greeting_instruction = "Do NOT start with a formal greeting. Answer naturally."

    # 3. Call AI
    llm = OpenAIService().client
    agent_name = state.get("agent_name") or "Assistant"
    company_name = state.get("company_name") or "Company"
    
    response = await llm.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": SUPER_SYSTEM_PROMPT.format(
                agent_name=agent_name,
                company_name=company_name,
                kb_context=kb_context,
                properties_json=props_json,
                user_message=last_message,
                time_greeting=greeting,
                greeting_instruction=greeting_instruction
            )}
        ],
        temperature=0.3
    )
    
    ai_reply = response.choices[0].message.content.strip()

    return {"messages": [AIMessage(content=ai_reply)]}
