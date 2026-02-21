from langgraph.graph import StateGraph, END
from langchain_core.messages import AIMessage
from app.core.state import AgentState

# Import nodes
from app.graphs.nodes.router import router_node
from app.graphs.nodes.intelligent_chat import intelligent_chat_node
from app.graphs.nodes.capability_check import capability_check_node
from app.graphs.nodes.extractor import extractor_node
from app.graphs.nodes.decision import decision_node
from app.graphs.nodes.generator import generator_node
from app.graphs.nodes.search_tool import search_node
from app.graphs.nodes.display_results import display_results_node
from app.graphs.nodes.clear_memory import clear_memory_node
from app.graphs.nodes.appointment_manager import appointment_manager_node


# Helper node for clarification
async def clarification_node(state: AgentState):
    """Generate clarification question when user intent is ambiguous."""
    question = state.get("clarification_question", "Could you clarify what you are looking for?")
    return {"messages": [AIMessage(content=question)]}


# Build the graph
workflow = StateGraph(AgentState)

# 1. Add All Nodes
workflow.add_node("router", router_node)
workflow.add_node("intelligent_chat", intelligent_chat_node)
workflow.add_node("capability_check", capability_check_node)
workflow.add_node("clarification", clarification_node)
workflow.add_node("clear_memory", clear_memory_node)

# Property Sub-System Nodes
workflow.add_node("extractor", extractor_node)
workflow.add_node("decision", decision_node)
workflow.add_node("generator", generator_node)
workflow.add_node("search_tool", search_node)
workflow.add_node("display_results", display_results_node)
workflow.add_node("appointment_manager", appointment_manager_node)

# 2. Set Entry Point
workflow.set_entry_point("router")


# 3. Define Master Routing Logic
def master_route_logic(state: AgentState):
    """Route to appropriate node based on intent."""
    intent = state.get("next_step")
    active_flow = state.get("active_flow")
    
    if intent == "PROPERTY_SEARCH":
        return "extractor"
    elif intent == "APPOINTMENT":
        return "extractor"
    elif intent == "RESET_MEMORY":
        return "clear_memory"
    elif intent == "CHECK_CAPABILITY":
        return "capability_check"
    elif intent == "ASK_CLARIFICATION":
        return "clarification"
    else:
        return "intelligent_chat"


workflow.add_conditional_edges(
    "router",
    master_route_logic,
    {
        "extractor": "extractor",
        "appointment_manager": "appointment_manager",
        "clear_memory": "clear_memory",
        "capability_check": "capability_check",
        "clarification": "clarification",
        "intelligent_chat": "intelligent_chat"
    }
)


# 4. Define Memory Clearing Logic
workflow.add_edge("clear_memory", "capability_check")


# 5. Define Capability Logic
def capability_route_logic(state: AgentState):
    """Route based on capability check result."""
    step = state.get("next_step")
    if step == "PROPERTY_SEARCH_APPROVED":
        return "extractor" 
    else:
        return "end" 


workflow.add_conditional_edges(
    "capability_check",
    capability_route_logic,
    {
        "extractor": "extractor",
        "end": END
    }
)


# 6. Define Extractor Routing Logic
def extractor_route_logic(state: AgentState):
    """Route based on active flow after extraction."""
    active_flow = state.get("active_flow")
    if active_flow == "APPOINTMENT":
        return "appointment_manager"
    else:
        return "decision"


workflow.add_conditional_edges(
    "extractor",
    extractor_route_logic,
    {
        "appointment_manager": "appointment_manager",
        "decision": "decision"
    }
)


# 7. Define Property Loop Logic
def property_route_logic(state: AgentState):
    """Route based on property search state."""
    step = state.get("next_step")
    
    if step == "execute_search":
        return "search_tool"
    elif step == "display_results":
        return "display_results"
    elif step == "check_inventory": 
        return "generator"
    else:
        return "generator"


workflow.add_conditional_edges(
    "decision",
    property_route_logic,
    {
        "search_tool": "search_tool",
        "display_results": "display_results",
        "generator": "generator"
    }
)


# 8. Connect Search Flow
workflow.add_edge("search_tool", "display_results")


# 9. End Points
workflow.add_edge("display_results", END)
workflow.add_edge("generator", END)
workflow.add_edge("clarification", END)
workflow.add_edge("intelligent_chat", END)
workflow.add_edge("appointment_manager", END)


def get_master_graph(checkpointer):
    """
    Compile and return the master graph with checkpointing.
    """
    return workflow.compile(checkpointer=checkpointer)
