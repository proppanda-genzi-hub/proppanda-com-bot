import asyncio
import json
import logging
from datetime import datetime

import pytz
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig

from app.core.state import AgentState
from app.db.repositories.agent_repository import AgentRepository
from app.db.repositories.leads_repository import LeadsRepository
from app.services.email_service import send_lead_notification_email
from app.services.openai_service import OpenAIService
from app.tools.knowledge_base import KnowledgeBaseTool

logger = logging.getLogger(__name__)

# ── Prompts ───────────────────────────────────────────────────────────────────

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

AGENT_SUMMARY_PROMPT = """
You are writing a brief lead summary for a real estate listing agent.

A prospect has been chatting with a property chatbot and has shown interest in
one or more properties listed by this agent. Your job is to summarise what the
agent needs to know about this lead so they can follow up effectively.

### PROPERTIES BY THIS AGENT THAT WERE DISCUSSED
{property_details}

### FULL CONVERSATION SO FAR
{conversation}

### PROSPECT DETAILS
- Nationality : {nationality}
- Pass Type   : {pass_type}
- Phone       : {phone}
- Budget      : {budget}
- Move-in     : {move_in}

Write a professional 3–5 sentence lead summary (third person) for the agent that covers:
1. Which specific properties the prospect asked about (use exact names)
2. What they want to know / any specific concerns or requirements raised
3. Their rental budget and move-in timeline
4. Their overall intent and suitability as a tenant
5. How the agent can best follow up

Do NOT include greetings or sign-offs. Output plain text only.
"""

PENDING_FOLLOW_UP_PROMPT = """
You are {agent_name}, a helpful Real Estate Agent at {company_name}.

The user just provided their personal details. Thank them warmly and naturally,
then immediately answer their original follow-up question below.

### THEIR ORIGINAL QUESTION:
"{pending_question}"

### CURRENT SEARCH RESULTS:
{properties_json}

### COMPANY KNOWLEDGE:
{kb_context}

Answer in 3-4 sentences. Be warm but concise. Do NOT ask for any more details.
"""


# ── Helpers ───────────────────────────────────────────────────────────────────

def _is_residential(target_table: str) -> bool:
    return "residential" in (target_table or "")


def _get_missing_lead_fields(filters, is_residential: bool, user_name: str = None) -> list:
    """Return list of human-readable labels for lead fields that are still missing."""
    missing = []

    # Check if we have a real name (not the default 'User' placeholder)
    has_name = bool(user_name and user_name.strip() and user_name.strip().lower() != "user")
    if not has_name:
        # Also check filter-level tenant_name
        if not (filters and filters.tenant_name):
            missing.append("full name")

    if not filters:
        if is_residential:
            missing += ["nationality", "pass type (EP / SP / PR / Citizen / DP)",
                        "phone number", "intended lease duration (minimum 12 months)"]
        else:
            missing += ["nationality", "occupation", "age group (e.g. 20–30, 30–40)",
                        "pass type (EP / SP / PR / Citizen / DP)", "phone number",
                        "intended lease duration (minimum 3 months)"]
        return missing

    if not filters.tenant_nationality:
        missing.append("nationality")
    if not is_residential and not filters.tenant_profession:
        missing.append("occupation")
    if not is_residential and not filters.tenant_age_group:
        missing.append("age group (e.g. 20–30, 30–40)")
    if not filters.tenant_pass_type:
        missing.append("pass type (EP / SP / PR / Citizen / DP)")
    if not filters.tenant_phone:
        missing.append("phone number")
    if not filters.tenant_lease_months:
        min_months = 12 if is_residential else 3
        missing.append(f"intended lease duration (minimum {min_months} months)")

    return missing


def _find_referenced_property(message: str, found_properties: list, shown_count: int) -> dict | None:
    """
    Identify which property the user is asking about.

    Priority:
    1. Name match (case-insensitive substring in message).
    2. Positional match ("first", "1st", "second" …) against last shown batch.
    """
    if not found_properties:
        return None

    msg_lower = message.lower()

    for p in found_properties:
        for field in ('condo_name', 'property_name'):
            name = (p.get(field) or '').strip()
            if name and name.lower() in msg_lower:
                return p

    batch_size = 3
    start_idx  = max(0, shown_count - batch_size)
    shown_props = found_properties[start_idx:shown_count]

    positional = [
        (['first',  '1st', '#1', 'number 1', 'option 1'], 0),
        (['second', '2nd', '#2', 'number 2', 'option 2'], 1),
        (['third',  '3rd', '#3', 'number 3', 'option 3'], 2),
    ]
    for keywords, idx in positional:
        if any(kw in msg_lower for kw in keywords):
            if idx < len(shown_props):
                return shown_props[idx]

    return None


async def _generate_agent_summary(llm, agent_props: list, messages: list, filters) -> str:
    """Generate a concise lead summary from the agent's perspective using GPT-4o."""
    prop_lines = []
    for p in agent_props:
        name  = p.get("condo_name") or p.get("property_name") or "Property"
        addr  = p.get("property_address") or p.get("nearest_mrt") or ""
        price = p.get("rental_price") or p.get("monthly_rent") or "N/A"
        prop_lines.append(f"• {name} | ${price}/mo | {addr}")
    property_details = "\n".join(prop_lines) if prop_lines else "Not specified"

    convo_lines = []
    for m in messages[-20:]:
        role = "Prospect" if isinstance(m, HumanMessage) else "Bot"
        content = (m.content or "").strip()
        if content:
            convo_lines.append(f"{role}: {content}")
    conversation = "\n".join(convo_lines) if convo_lines else "No conversation recorded."

    nationality = (filters.tenant_nationality if filters else None) or "Not provided"
    pass_type   = (filters.tenant_pass_type   if filters else None) or "Not provided"
    phone       = (filters.tenant_phone        if filters else None) or "Not provided"
    budget      = (filters.budget_max          if filters else None)
    budget_str  = f"Up to ${budget}/mo" if budget else "Not specified"
    move_in     = (filters.move_in_date        if filters else None) or "Flexible"

    try:
        response = await llm.chat.completions.create(
            model="gpt-4o",
            messages=[{
                "role": "system",
                "content": AGENT_SUMMARY_PROMPT.format(
                    property_details=property_details,
                    conversation=conversation,
                    nationality=nationality,
                    pass_type=pass_type,
                    phone=phone,
                    budget=budget_str,
                    move_in=move_in,
                )
            }],
            temperature=0.2,
            max_tokens=300,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.warning(f"Failed to generate agent summary: {e}")
        return (
            f"Prospect enquired about: {property_details}. "
            f"Nationality: {nationality}, Pass: {pass_type}, Phone: {phone}, Budget: {budget_str}."
        )


async def _update_lead_and_notify(
    message:  str,
    state:    AgentState,
    config:   RunnableConfig,
) -> str | None:
    """
    1. Identify the specific property the user is asking about.
    2. Upsert a per-agent lead record in prop_panda_com_leads.
    3. Fire a background email to the listing agent (non-blocking).

    Returns the matched agent_id, or None if no match.
    """
    db         = config.get("configurable", {}).get("db_session")
    user_email = state.get("user_email")
    llm        = OpenAIService().client

    if not db or not user_email:
        return None

    found_properties = state.get("found_properties") or []
    shown_count      = state.get("shown_count", 0)

    # ── 1. Identify referenced property ──────────────────────────────────────
    prop = _find_referenced_property(message, found_properties, shown_count)
    if not prop:
        return None

    property_agent_id = str(prop.get("agent_id") or "").strip()
    if not property_agent_id:
        return None

    property_name = prop.get("condo_name") or prop.get("property_name")

    # ── 2. Gather all properties from the same agent ──────────────────────────
    agent_props = [
        p for p in found_properties
        if str(p.get("agent_id") or "").strip() == property_agent_id
    ]

    # ── 3. Build LLM summary ──────────────────────────────────────────────────
    filters  = state.get("filters")
    messages = state.get("messages", [])
    summary  = await _generate_agent_summary(llm, agent_props, messages, filters)

    # ── 4. Upsert per-agent lead record ───────────────────────────────────────
    try:
        leads_repo = LeadsRepository(db)
        await leads_repo.upsert_agent_interaction(
            email=user_email,
            agent_id=property_agent_id,
            data={
                "name":              state.get("user_name"),
                "session_id":        state.get("user_mobile"),
                "last_target_table": state.get("target_table"),
                "filters":           filters,
            },
            conversation_summary=summary,
        )
        logger.info(f"✅ Agent interaction upserted: email={user_email} agent={property_agent_id}")
    except Exception as e:
        logger.warning(f"Non-critical: failed to upsert agent interaction: {e}")

    # ── 5. Fetch agent email and fire background email ─────────────────────────
    try:
        agent_repo  = AgentRepository(db)
        agent_obj   = await agent_repo.get_agent_by_id(property_agent_id)
        agent_email = (agent_obj.email if agent_obj else None) or ""
        agent_name  = (agent_obj.name  if agent_obj else None) or "Agent"

        if agent_email:
            # Build lead_data dict from state + filters for the email body
            lead_data = {
                "name":             state.get("user_name"),
                "email":            user_email,
                "phone":            (filters.tenant_phone        if filters else None),
                "nationality":      (filters.tenant_nationality  if filters else None),
                "pass_type":        (filters.tenant_pass_type    if filters else None),
                "gender":           (filters.tenant_gender       if filters else None),
                "profession":       (filters.tenant_profession   if filters else None),
                "age_group":        (filters.tenant_age_group    if filters else None),
                "budget_max":       (filters.budget_max          if filters else None),
                "location":         (filters.location_query      if filters else None),
                "move_in_date":     (filters.move_in_date        if filters else None),
                "lease_months":     (filters.tenant_lease_months if filters else None),
                "last_target_table": state.get("target_table"),
            }
            asyncio.create_task(
                send_lead_notification_email(
                    agent_email=agent_email,
                    agent_name=agent_name,
                    lead_data=lead_data,
                    summary=summary,
                    property_name=property_name,
                )
            )
            logger.info(f"📧 Email notification queued for agent {agent_email}")
        else:
            logger.warning(f"Agent {property_agent_id} has no email — skipping notification")
    except Exception as e:
        logger.warning(f"Non-critical: could not queue lead email: {e}")

    return property_agent_id


# ── Main node ─────────────────────────────────────────────────────────────────

async def intelligent_chat_node(state: AgentState, config: RunnableConfig):
    """
    Handle general chat, knowledge base queries, and property QA.

    Flows:
    - CASE A: `pending_follow_up` in state → lead details just collected by extractor.
              Answer the stored follow-up question and clear pending state.
    - CASE B: Properties shown + lead details incomplete + property follow-up →
              Ask for all missing details in ONE message, store follow-up in
              `pending_follow_up`, set `active_flow = "COLLECT_LEAD"`.
    - CASE C: Normal chat — answer directly.
    """
    db           = config.get("configurable", {}).get("db_session")
    agent_id     = state["agent_id"]
    last_message = state["messages"][-1].content
    target_table = state.get("target_table", "")
    is_residential = _is_residential(target_table)
    agent_name   = state.get("agent_name") or "Assistant"
    company_name = state.get("company_name") or "Company"

    # Fetch knowledge-base context
    kb_tool    = KnowledgeBaseTool(db)
    kb_context = await kb_tool.search(agent_id, last_message) or "No specific company documents found."

    properties  = state.get("found_properties", [])
    shown_count = state.get("shown_count", 0)

    if properties and shown_count > 0:
        batch_size = 3
        start_idx  = max(0, shown_count - batch_size)
        context_props = []
        for i, p in enumerate(properties[start_idx:shown_count]):
            p_copy = p.copy()
            p_copy['visual_index'] = i + 1
            context_props.append(p_copy)
        props_json = json.dumps(context_props, indent=2, default=str)
    elif properties:
        props_json = json.dumps(properties[:3], indent=2, default=str)
    else:
        props_json = "No active search results."

    llm = OpenAIService().client

    # ── CASE A: Pending follow-up — lead data just collected ─────────────────
    pending_follow_up = state.get("pending_follow_up")
    if pending_follow_up:
        logger.info("💬 Answering stored pending follow-up question after lead collection")

        await _update_lead_and_notify(pending_follow_up, state, config)

        response = await llm.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": PENDING_FOLLOW_UP_PROMPT.format(
                    agent_name=agent_name,
                    company_name=company_name,
                    pending_question=pending_follow_up,
                    properties_json=props_json,
                    kb_context=kb_context,
                )}
            ],
            temperature=0.3
        )
        ai_reply = response.choices[0].message.content.strip()
        return {
            "messages": [AIMessage(content=ai_reply)],
            "pending_follow_up": None,
        }

    # ── CASE B: Properties shown + missing lead fields ────────────────────────
    properties_shown = bool(properties) and shown_count > 0
    filters          = state.get("filters")
    user_name        = state.get("user_name") or ""
    missing_fields   = _get_missing_lead_fields(filters, is_residential, user_name)

    if properties_shown and missing_fields:
        logger.info(f"📋 Collecting missing lead fields: {missing_fields}")

        # Save lead record + notify agent in background
        await _update_lead_and_notify(last_message, state, config)

        if len(missing_fields) == 1:
            fields_str = missing_fields[0]
        elif len(missing_fields) == 2:
            fields_str = f"{missing_fields[0]} and {missing_fields[1]}"
        else:
            fields_str = ", ".join(missing_fields[:-1]) + f", and {missing_fields[-1]}"

        ask_msg = (
            f"Happy to help with that! Before I answer, I just need a couple of quick details — "
            f"could you share your **{fields_str}**? Just list them in one reply and I'll get right to it. 😊"
        )
        return {
            "messages": [AIMessage(content=ask_msg)],
            "pending_follow_up": last_message,
            "active_flow": "COLLECT_LEAD",
        }

    # ── CASE C: Normal intelligent chat ──────────────────────────────────────
    tz = pytz.timezone('Asia/Singapore')
    h  = datetime.now(tz).hour
    greeting = "Good morning" if 5 <= h < 12 else "Good afternoon" if 12 <= h < 18 else "Good evening"

    is_first_interaction = len(state["messages"]) <= 1
    if is_first_interaction:
        greeting_instruction = (
            f"Start with '{greeting}! I'm {agent_name} from {company_name}. "
            f"What can I do for you today?'"
        )
    else:
        greeting_instruction = "Do NOT start with a formal greeting. Answer naturally."

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
                greeting_instruction=greeting_instruction,
            )}
        ],
        temperature=0.3
    )
    ai_reply = response.choices[0].message.content.strip()

    if properties_shown:
        await _update_lead_and_notify(last_message, state, config)

    return {"messages": [AIMessage(content=ai_reply)]}
