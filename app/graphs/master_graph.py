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
from app.graphs.nodes.load_user_data import load_user_data_node


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
workflow.add_node("load_user_data", load_user_data_node)

# Property Sub-System Nodes
workflow.add_node("extractor", extractor_node)
workflow.add_node("decision", decision_node)
workflow.add_node("generator", generator_node)
workflow.add_node("search_tool", search_node)
workflow.add_node("display_results", display_results_node)

# 2. Set Entry Point
workflow.set_entry_point("router")


# 3. Define Master Routing Logic
def master_route_logic(state: AgentState):
    """Route to appropriate node based on intent."""
    intent = state.get("next_step")

    if intent == "LOAD_USER_DATA":
        return "load_user_data"
    elif intent == "PROPERTY_SEARCH":
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
        "load_user_data": "load_user_data",
        "extractor": "extractor",
        "clear_memory": "clear_memory",
        "capability_check": "capability_check",
        "clarification": "clarification",
        "intelligent_chat": "intelligent_chat"
    }
)


# 4. Define load_user_data Routing Logic
def load_user_data_route_logic(state: AgentState):
    """
    After load_user_data:
    - If email was collected → proceed to capability_check
    - If waiting for email (WAIT_EMAIL) → end turn so user can reply
    """
    step = state.get("next_step")
    if step == "CHECK_CAPABILITY":
        return "capability_check"
    else:
        # WAIT_EMAIL — stop and wait for user to provide their email
        return "end"


workflow.add_conditional_edges(
    "load_user_data",
    load_user_data_route_logic,
    {
        "capability_check": "capability_check",
        "end": END
    }
)


# 5. Define Memory Clearing Logic
workflow.add_edge("clear_memory", "capability_check")


# 6. Define Capability Logic
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


# 7. Define Extractor Routing Logic
def extractor_route_logic(state: AgentState):
    """Route based on active flow after extraction."""
    # After COLLECT_LEAD extraction active_flow is cleared to None,
    # but pending_follow_up still holds the question we need to answer.
    if state.get("pending_follow_up"):
        return "intelligent_chat"
    return "decision"


workflow.add_conditional_edges(
    "extractor",
    extractor_route_logic,
    {
        "intelligent_chat": "intelligent_chat",
        "decision": "decision"
    }
)


# 8. Define Property Loop Logic
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


# 9. Connect Search Flow
workflow.add_edge("search_tool", "display_results")


# 10. End Points
workflow.add_edge("display_results", END)
workflow.add_edge("generator", END)
workflow.add_edge("clarification", END)
workflow.add_edge("intelligent_chat", END)


def get_master_graph(checkpointer):
    """
    Compile and return the master graph with checkpointing.
    """
    return workflow.compile(checkpointer=checkpointer)
