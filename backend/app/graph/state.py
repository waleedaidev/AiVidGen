from typing import TypedDict


class GraphState(TypedDict, total=False):
    job_id: str
    lead_id: str
    raw_prompt: str

    brief: dict
    script: dict  # {title, logline, characters: [{key, name, role}], scenes: [{location, description, present, dialogue}]}
    scene_audio: list[dict]  # per script scene: {path, duration, timing}
    music_path: str | None

    route: str
    stage: str
