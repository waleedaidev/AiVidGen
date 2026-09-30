"""LangGraph wiring.

Full pipeline:
  analyze_brief -> write_script -> extract_characters -> build_character_refs -> audio_pipeline
  -> plan_scenes -> map_interactions -> plan_shots -> build_prompts -> generate_shots -> qa_check
  -> (repair_prompts -> generate_shots)* -> assemble

Reshoot pipeline (editor regenerates shots): generate_shots -> qa_check -> ... -> assemble
"""

from langgraph.graph import StateGraph, END

from app.graph.state import GraphState
from app.graph import planning, production

PLANNING = [
    ("analyze_brief", planning.analyze_brief),
    ("write_script", planning.write_script),
    ("extract_characters", planning.extract_characters),
    ("build_character_refs", planning.build_character_refs),
    ("audio_pipeline", planning.audio_pipeline),
    ("plan_scenes", planning.plan_scenes),
    ("map_interactions", planning.map_interactions),
    ("plan_shots", planning.plan_shots),
    ("build_prompts", planning.build_prompts),
]


def _add_production(graph: StateGraph) -> None:
    graph.add_node("generate_shots", production.generate_shots)
    graph.add_node("qa_check", production.qa_check)
    graph.add_node("repair_prompts", production.repair_prompts)
    graph.add_node("assemble", production.assemble)
    graph.add_edge("generate_shots", "qa_check")
    graph.add_conditional_edges(
        "qa_check", production.route_after_qa, {"repair": "repair_prompts", "assemble": "assemble"}
    )
    graph.add_edge("repair_prompts", "generate_shots")
    graph.add_edge("assemble", END)


def build_graph():
    graph = StateGraph(GraphState)
    for name, fn in PLANNING:
        graph.add_node(name, fn)
    _add_production(graph)
    graph.set_entry_point(PLANNING[0][0])
    for (a, _), (b, _) in zip(PLANNING, PLANNING[1:]):
        graph.add_edge(a, b)
    graph.add_edge(PLANNING[-1][0], "generate_shots")
    return graph.compile()


def build_reshoot_graph():
    graph = StateGraph(GraphState)
    _add_production(graph)
    graph.set_entry_point("generate_shots")
    return graph.compile()


_graphs: dict = {}


def get_graph():
    if "full" not in _graphs:
        _graphs["full"] = build_graph()
    return _graphs["full"]


def get_reshoot_graph():
    if "reshoot" not in _graphs:
        _graphs["reshoot"] = build_reshoot_graph()
    return _graphs["reshoot"]
