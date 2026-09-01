from langgraph.graph import StateGraph, END

from app.graph.state import GraphState
from app.graph import nodes


def build_graph():
    graph = StateGraph(GraphState)

    graph.add_node("parse_intent", nodes.parse_intent)
    graph.add_node("generate_script", nodes.generate_script)
    graph.add_node("generate_assets", nodes.generate_assets)
    graph.add_node("generate_video", nodes.generate_video)
    graph.add_node("fallback_stock", nodes.fallback_stock)

    graph.set_entry_point("parse_intent")
    graph.add_edge("parse_intent", "generate_script")
    graph.add_edge("generate_script", "generate_assets")
    graph.add_edge("generate_assets", "generate_video")

    graph.add_conditional_edges(
        "generate_video",
        nodes.should_retry,
        {
            "retry": "generate_video",
            "fallback": "fallback_stock",
            "done": END,
        },
    )
    graph.add_edge("fallback_stock", END)

    return graph.compile()


_compiled_graph = None


def get_graph():
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_graph()
    return _compiled_graph
