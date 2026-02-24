from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig
from app.core.state import AgentState
from app.services.n8n_client import N8NClient
from app.services.openai_service import OpenAIService
import json
import logging
import re

logger = logging.getLogger(__name__)

SUMMARY_PROMPT = """
You are a helpful assistant summarizing a real estate conversation for a human agent.
Generate a concise but detailed summary of the user's requirements and the booking context.

CONTEXT:
- User Name: {user_name}
- Property: {property_name}
- Viewing Type: {viewing_type}
- Extracted Filters: {filters}

CHAT HISTORY:
{history}

OUTPUT FORMAT:
Start with "User [Name] is looking for...". Include budget, location preferences, move-in date, and any specific questions they asked.
"""


async def appointment_manager_node(state: AgentState, config: RunnableConfig):
    """
    Manages the appointment booking flow.
    """
    appt = state.get("appointment_state") or {}
    last_message = state["messages"][-1].content.strip()
    last_lower = last_message.lower()
    
    # 1. IDENTIFY PROPERTY
    found_props = state.get("found_properties") or []
    target_property = state.get("selected_property") 
    
    if not target_property:
        # CASE A: Only 1 result -> Auto-select
        if len(found_props) == 1:
            target_property = found_props[0]
            
        # CASE B: User gave input
        elif found_props:
            index = -1
            if any(w in last_lower for w in ["1st", "first", "one"]): 
                index = 0
            elif any(w in last_lower for w in ["2nd", "second", "two"]): 
                index = 1
            elif any(w in last_lower for w in ["3rd", "third", "three"]): 
                index = 2
            
            if index == -1:
                digits = re.findall(r"\b[1-3]\b", last_lower)
                if digits and len(last_lower) < 10: 
                    index = int(digits[0]) - 1

            if index > -1 and index < len(found_props):
                target_property = found_props[index]
            
            # Name Matching
            if not target_property:
                for p in found_props:
                    p_name = p.get("property_name", "").lower()
                    if p_name in last_lower or last_lower in p_name:
                        target_property = p
                        break
            
            # Room Number Matching
            if not target_property:
                for p in found_props:
                    r_num = str(p.get("room_number", "")).lower()
                    if r_num and r_num in last_lower:
                        target_property = p
                        break

        if not target_property:
            return {
                "messages": [AIMessage(content="Got it! Which place are you thinking about? You can tell me the name, the number, or even say something like 'the second one'.")],
                "next_step": "APPOINTMENT_LOOP"
            }
    
    # 2. COLLECT DETAILS
    state_update = {"selected_property": target_property, "next_step": "APPOINTMENT_LOOP"}

    if not appt.get("email"):
        return {
            **state_update,
            "messages": [AIMessage(content=f"Awesome choice! 🎉 To lock in a viewing for **{target_property.get('property_name')}**, could you share your email with me?")]
        }

    if not appt.get("pass_type"):
        return {
            **state_update,
            "messages": [AIMessage(content="Perfect! And what type of pass do you hold? (EP, SP, Student Pass, PR, Citizen… anything works!)")]
        }

    if not appt.get("lease_months"):
        _target_table = state.get("target_table", "")
        _min_lease = 12 if "residential" in _target_table else 3
        return {
            **state_update,
            "messages": [AIMessage(content=f"Got it! How long are you planning to stay? (Minimum lease for this property type is {_min_lease} months.)")]
        }

    # 3. COLLECT PREFERENCES
    if not appt.get("viewing_type"):
        return {
            **state_update,
            "messages": [AIMessage(content="How would you like to view the place — a quick **Virtual tour**, or should we book an **In-Person** viewing?")]
        }

    time_pref = appt.get("time_preference")
    if not time_pref:
        return {
            **state_update,
            "messages": [AIMessage(content="Sweet! What time usually works best for you — **Morning**, **After Lunch**, or **After Work**?")]
        }

    # 4. FETCH & SHOW SLOTS
    if not state.get("available_slots"):
        logger.info("🔍 Fetching available slots from N8N...")
        n8n = N8NClient()
        # Use property's agent_id if available, fallback to chatbot agent_id
        property_agent_id = target_property.get("agent_id") if target_property else None
        appointment_agent_id = property_agent_id or state["agent_id"]
        slots_data = await n8n.get_available_slots(appointment_agent_id, time_pref)
        
        if not slots_data:
            return {
                **state_update,
                "messages": [AIMessage(content="I couldn't find available slots for that time preference. Would you like to try a different time? (Morning, After Lunch, or After Work)")],
                "appointment_state": {**appt, "time_preference": None}
            }
        
        # Parse N8N response - it returns [{"slots_string": "[{...}]"}]
        try:
            if isinstance(slots_data, str):
                slots_data = json.loads(slots_data)
            
            if isinstance(slots_data, list) and len(slots_data) > 0:
                first_item = slots_data[0]
                if isinstance(first_item, dict) and "slots_string" in first_item:
                    # Parse the slots_string JSON
                    slots_data = json.loads(first_item["slots_string"])
                    
            if not isinstance(slots_data, list):
                slots_data = []
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.error(f"Error parsing slots data: {e}")
            slots_data = []

        display_slots = slots_data[:5]
        slot_lines = []
        
        for day_obj in display_slots:
            if not isinstance(day_obj, dict): 
                continue
            date_str = day_obj.get("date", "")
            day_name = day_obj.get("day", "")
            slots = day_obj.get("slots", [])
            
            if slots:
                time_slots = ", ".join(slots)
                slot_lines.append(f"• **{day_name}** ({date_str}): {time_slots}")
        
        if not slot_lines:
            return {
                **state_update,
                "messages": [AIMessage(content="No slots available for that time. Would you like to try a different time preference?")],
                "appointment_state": {**appt, "time_preference": None}
            }

        message = "📅 **Available Slots (Next 5 Days)**\n\n"
        message += "\n".join(slot_lines)
        message += "\n\n💬 Reply with your choice"
        
        return {
            **state_update,
            "messages": [AIMessage(content=message)],
            "available_slots": slots_data, 
            "appointment_state": {**appt, "step": "select_slot"}
        }

    # 5. FINALIZE BOOKING
    logger.info("✅ Finalizing booking...")
    selected_slot = appt.get("selected_slot") or last_message

    # Parse date and time
    slot_text = selected_slot.strip()
    date_match = re.search(r"\b\d{4}-\d{2}-\d{2}\b", slot_text)
    clean_date = date_match.group(0) if date_match else "UNKNOWN-DATE"

    text_for_time = slot_text
    if date_match:
        text_for_time = slot_text.replace(clean_date, "")

    time_match = re.search(r"\b(\d{1,2})\s*-\s*(\d{1,2})\b", text_for_time)

    if time_match:
        start_h = int(time_match.group(1))
        end_h = int(time_match.group(2))
        clean_time = f"{start_h:02d}:00 - {end_h:02d}:00"
    else:
        clean_time = "UNKNOWN-TIME"

    filters = state.get("filters")
    filter_dict = filters.model_dump() if filters else {}
    def get_f(k): return filter_dict.get(k, "-")

    # Generate Summary
    llm = OpenAIService().client
    chat_summary = f"User {state.get('user_name')} booked {target_property.get('property_name')}."
    try:
        history_str = "\n".join([f"{m.type}: {m.content}" for m in state["messages"][-10:]])
        summary_res = await llm.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "system", "content": SUMMARY_PROMPT.format(
                user_name=state.get("user_name"),
                property_name=target_property.get("property_name"),
                viewing_type=appt.get("viewing_type"),
                filters=json.dumps(filter_dict, default=str),
                history=history_str
            )}],
            temperature=0.5
        )
        chat_summary = summary_res.choices[0].message.content
    except:
        pass

    # Build Payload
    # Use property's agent_id if available, fallback to chatbot agent_id
    property_agent_id = target_property.get("agent_id") if target_property else None
    appointment_agent_id = property_agent_id or state["agent_id"]
    
    payload = [{
        "agent_id": appointment_agent_id,
        "name": state.get("user_name"),
        "clientgender": get_f("tenant_gender"),
        "clientnationality": get_f("tenant_nationality"),
        "property": target_property.get("property_name"),
        "property_address": target_property.get("property_address"),
        "roomnumber": target_property.get("room_number", "N/A"),
        "monthly_rent": target_property.get("monthly_rent"),
        "session_id": state["user_mobile"],
        "email": appt["email"],
        "userpass": appt["pass_type"],
        "clientleaseperiod": str(appt["lease_months"]),
        "appointment_date": clean_date,
        "time": clean_time,
        "appointment_time_from": time_pref,
        "clientmoveindate": get_f("move_in_date"),
        "chatsummary": chat_summary
    }]

    n8n = N8NClient()
    success = await n8n.schedule_appointment(payload)

    if success:
        return {
            "messages": [AIMessage(content=f"✅ **Appointment Confirmed!**\n\n**Date:** {clean_date}\n**Time:** {clean_time}\n\nYou will receive a confirmation email shortly at {appt['email']}. Is there anything else I can help you with?")],
            "active_flow": None,
            "appointment_state": None,
            "available_slots": None,
            "selected_property": None,
            "next_step": "END"
        }
    else:
        return {
            "messages": [AIMessage(content="I apologize, but I couldn't finalize the booking automatically. I've notified a human agent to assist you.")],
            "active_flow": None,
            "appointment_state": None,
            "next_step": "END"
        }
