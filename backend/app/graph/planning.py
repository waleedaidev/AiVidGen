"""Pre-production stages 1-8: brief -> script -> characters -> audio -> scenes -> interactions
-> shots -> prompts. Every LLM stage has a rule-based fallback so the pipeline runs without keys."""

import json
import math
import os
import zlib
from concurrent.futures import ThreadPoolExecutor

from app.config import get_settings
from app.graph.common import session, job_dir, set_status, llm_json, log
from app.graph.state import GraphState
from app.models_db import Character, Lead, Scene, SceneCharacter, Shot
from app.providers import get_audio_provider, get_image_provider
from app.providers.base import GenerationError
from app.providers.mock import MockImageProvider
from app.utils.ffmpeg_utils import build_scene_audio
from app.utils.model_router import allowed_durations

NARRATOR = "NARRATOR"
CHAR_KEYS = ["A", "B", "C", "D"]
NEGATIVE_PROMPT = (
    "blurry, low quality, distorted face, deformed hands, extra fingers, extra limbs, extra people, "
    "duplicate person, morphing, flicker, jitter, text, subtitles, captions, watermark, logo artifacts"
)


# 1. BRIEF ANALYZER --------------------------------------------------------------------------

def analyze_brief(state: GraphState) -> GraphState:
    set_status(state["job_id"], "analyzing_brief")
    settings = get_settings()
    prompt = state["raw_prompt"]

    with session() as db:
        lead = db.get(Lead, state["lead_id"])
        extras = {k: getattr(lead, k) for k in ("business_type", "tone", "target_audience", "use_case", "preferred_style")
                  if lead is not None and getattr(lead, k)}

    result = llm_json(
        "You are a creative director for short social video ads. Analyze the brief and reply as JSON: "
        '{"title": str, "goal": str, "product_or_subject": str, "audience": str, "tone": str, '
        '"visual_style": str (concrete look: lighting, palette, lens), "setting": str, '
        f'"call_to_action": str, "industry": one of restaurant|fitness|real_estate|fashion|salon|retail|other, '
        f'"num_characters": int 1-{settings.max_characters}, "language": str}}',
        f"Brief: {prompt}\nKnown details: {json.dumps(extras)}",
        temperature=0.4,
    )
    brief = {
        "title": prompt[:60],
        "goal": "promote",
        "product_or_subject": prompt[:120],
        "audience": extras.get("target_audience", "general audience"),
        "tone": extras.get("tone", "warm and professional"),
        "visual_style": "cinematic commercial look, soft natural light, shallow depth of field, 35mm",
        "setting": "modern bright interior",
        "call_to_action": "Get in touch today",
        "industry": "other",
        "num_characters": 2,
        "language": "English",
    }
    if result:
        brief.update({k: v for k, v in result.items() if v})
    brief["num_characters"] = max(1, min(int(brief.get("num_characters") or 1), settings.max_characters))

    set_status(state["job_id"], "analyzing_brief", brief=brief)
    return {"brief": brief}


# 2. SCRIPT AGENT -----------------------------------------------------------------------------

def _fallback_script(brief: dict, prompt: str) -> dict:
    setting = brief.get("setting", "modern bright interior")
    return {
        "title": brief.get("title", prompt[:60]),
        "logline": prompt,
        "characters": [
            {"key": "A", "name": "Sara", "role": "host"},
            {"key": "B", "name": "Adam", "role": "customer"},
        ],
        "scenes": [
            {
                "location": setting,
                "description": f"Adam looks around curiously; Sara greets him warmly. Context: {prompt}",
                "present": ["A", "B"],
                "dialogue": [
                    {"speaker": "B", "text": "I've been looking for something like this for ages.", "emotion": "curious"},
                    {"speaker": "A", "text": "You're going to love it. Let me show you.", "emotion": "confident"},
                ],
            },
            {
                "location": setting,
                "description": f"Adam's face lights up; Sara turns to the camera. Context: {prompt}",
                "present": ["A", "B"],
                "dialogue": [
                    {"speaker": "B", "text": "Wow, this is exactly what I needed!", "emotion": "delighted"},
                    {"speaker": "A", "text": brief.get("call_to_action", "Get yours today."), "emotion": "happy"},
                ],
            },
        ],
    }


def _sanitize_script(script: dict, max_scenes: int, max_chars: int) -> dict:
    chars = [c for c in script.get("characters", []) if isinstance(c, dict)][:max_chars]
    for i, c in enumerate(chars):
        c["key"] = CHAR_KEYS[i] if c.get("key") not in CHAR_KEYS else c["key"]
        c.setdefault("name", f"Character {c['key']}")
        c.setdefault("role", "support")
    keys = {c["key"] for c in chars}

    scenes = []
    for sc in [s for s in script.get("scenes", []) if isinstance(s, dict)][:max_scenes]:
        dialogue = [
            {"speaker": d.get("speaker") if d.get("speaker") in keys else NARRATOR,
             "text": str(d.get("text", "")).strip(), "emotion": d.get("emotion", "neutral")}
            for d in sc.get("dialogue", []) if isinstance(d, dict) and str(d.get("text", "")).strip()
        ]
        present = [k for k in sc.get("present", []) if k in keys]
        present += [d["speaker"] for d in dialogue if d["speaker"] in keys and d["speaker"] not in present]
        scenes.append({
            "location": sc.get("location", "interior"),
            "description": sc.get("description", ""),
            "present": present,
            "dialogue": dialogue,
        })
    return {**script, "characters": chars, "scenes": scenes}


def write_script(state: GraphState) -> GraphState:
    set_status(state["job_id"], "writing_script")
    settings = get_settings()
    brief = state["brief"]
    max_scenes = settings.max_shots
    words = int(settings.target_duration_seconds * 2.3)

    result = llm_json(
        "You are a screenwriter for short video ads. Write a script with characters and spoken dialogue. "
        f"Hard limits: {brief['num_characters']} characters max (keys A, B, C), {max_scenes} scenes max, "
        f"about {words} spoken words total (the video is {settings.target_duration_seconds} seconds), "
        "dialogue must be natural and speakable, end on the call to action. Every scene must be visually "
        "filmable in one location. Reply as JSON: "
        '{"title": str, "logline": str, "characters": [{"key": "A", "name": str, "role": str}], '
        '"scenes": [{"location": str, "description": str (visible action only), "present": ["A", ...], '
        '"dialogue": [{"speaker": "A" | "NARRATOR", "text": str, "emotion": str}]}]}',
        f"Original request: {state['raw_prompt']}\nCreative brief: {json.dumps(brief)}",
        temperature=0.8,
    )
    script = _sanitize_script(result or {}, max_scenes, settings.max_characters)
    if not script["characters"] or not script["scenes"]:
        script = _sanitize_script(_fallback_script(brief, state["raw_prompt"]), max_scenes, settings.max_characters)

    flat = "\n".join(
        f"[Scene {i}] {sc['location']}: {sc['description']}\n"
        + "\n".join(f"  {d['speaker']}: {d['text']}" for d in sc["dialogue"])
        for i, sc in enumerate(script["scenes"], 1)
    )
    set_status(state["job_id"], "writing_script", full_script=script, script=flat)
    return {"script": script}


# 3. CHARACTER EXTRACTION + REGISTRY ----------------------------------------------------------

def extract_characters(state: GraphState) -> GraphState:
    set_status(state["job_id"], "extracting_characters")
    job_id, brief, script = state["job_id"], state["brief"], state["script"]

    result = llm_json(
        "You are a casting director. For each character write a precise, reusable visual identity so an "
        "image model draws the SAME person every time: gender, age, ethnicity, body type, face, hair "
        "(style+color), outfit with exact colors, one distinctive detail. Reply as JSON: "
        '{"characters": [{"key": "A", "appearance": str (one dense sentence), "personality": str, '
        '"voice": "male ..." or "female ..."}]}',
        f"Brief: {json.dumps(brief)}\nScript: {json.dumps(script)}",
        temperature=0.5,
    )
    details = {c.get("key"): c for c in (result or {}).get("characters", []) if isinstance(c, dict)}

    with session() as db:
        db.query(Character).filter(Character.job_id == job_id).delete()
        for i, c in enumerate(script["characters"]):
            d = details.get(c["key"], {})
            female = i % 2 == 0
            db.add(Character(
                job_id=job_id,
                key=c["key"],
                name=c["name"],
                role=c.get("role", "support"),
                appearance=d.get("appearance") or (
                    f"{'woman' if female else 'man'} in {'her' if female else 'his'} early 30s, warm smile, neat dark hair, "
                    f"smart casual {'navy blazer' if female else 'grey sweater'}"
                ),
                personality=d.get("personality", ""),
                voice=d.get("voice") or ("female, warm" if female else "male, friendly"),
                seed=zlib.crc32(f"{job_id}:{c['key']}".encode()) % 1_000_000,
            ))
    return {"stage": "extract_characters"}


def _reference_image(char_id: str, style: str, out_dir: str) -> None:
    w, h = get_settings().frame_size
    with session() as db:
        char = db.get(Character, char_id)
        prompt = (
            f"Character reference portrait of {char.appearance}. Waist-up, facing camera, neutral expression, "
            f"plain light-grey studio background, even soft lighting, sharp focus, photorealistic. {style}"
        )
        out = os.path.join(out_dir, f"char_{char.key}.jpg")
        try:
            get_image_provider().generate_subject_image(prompt, out, width=w, height=h, seed=char.seed)
        except GenerationError as exc:
            log.warning("reference image for %s failed (%s), using placeholder", char.name, exc)
            MockImageProvider().generate_subject_image(char.appearance, out, width=w, height=h)
        char.reference_image_path = out


def build_character_refs(state: GraphState) -> GraphState:
    set_status(state["job_id"], "generating_references")
    out_dir = job_dir(state["job_id"], "characters")
    with session() as db:
        ids = [c.id for c in db.query(Character).filter(Character.job_id == state["job_id"]).all()]
    with ThreadPoolExecutor(max_workers=max(1, len(ids))) as pool:
        list(pool.map(lambda cid: _reference_image(cid, state["brief"].get("visual_style", ""), out_dir), ids))
    return {"stage": "build_character_refs"}


# 4. AUDIO PIPELINE ---------------------------------------------------------------------------

def pick_music(tone: str) -> str | None:
    music_dir = get_settings().music_dir_abs
    if not os.path.isdir(music_dir):
        return None
    tracks = sorted(f for f in os.listdir(music_dir) if f.lower().endswith((".mp3", ".wav", ".m4a")))
    if not tracks:
        return None
    words = set((tone or "").lower().replace(",", " ").split())
    best = max(tracks, key=lambda t: len(words & set(os.path.splitext(t.lower())[0].replace("-", "_").split("_"))))
    return os.path.join(music_dir, best)


def audio_pipeline(state: GraphState) -> GraphState:
    set_status(state["job_id"], "generating_audio")
    out_dir = job_dir(state["job_id"], "audio")
    provider = get_audio_provider()
    with session() as db:
        voices = {c.key: c.voice for c in db.query(Character).filter(Character.job_id == state["job_id"]).all()}

    scene_audio = []
    for i, scene in enumerate(state["script"]["scenes"], 1):
        lines = []
        for j, line in enumerate(scene["dialogue"], 1):
            path = os.path.join(out_dir, f"s{i}_l{j}.wav")
            provider.generate_tts(line["text"], path, voice=voices.get(line["speaker"], "female"))
            lines.append((line["speaker"], line["text"], path))
        if lines:
            scene_path = os.path.join(out_dir, f"scene_{i}.wav")
            duration, timing = build_scene_audio(lines, scene_path)
            scene_audio.append({"path": scene_path, "duration": duration, "timing": timing})
        else:
            scene_audio.append({"path": None, "duration": 0.0, "timing": []})

    return {"scene_audio": scene_audio, "music_path": pick_music(state["brief"].get("tone", ""))}


# 5. SCENE PLANNER ----------------------------------------------------------------------------

def plan_scenes(state: GraphState) -> GraphState:
    set_status(state["job_id"], "planning_scenes")
    job_id = state["job_id"]
    with session() as db:
        for old in db.query(Scene).filter(Scene.job_id == job_id).all():
            db.delete(old)
        db.flush()
        chars = {c.key: c for c in db.query(Character).filter(Character.job_id == job_id).all()}
        for i, (sc, audio) in enumerate(zip(state["script"]["scenes"], state["scene_audio"]), 1):
            scene = Scene(
                job_id=job_id, scene_number=i, location=sc["location"], description=sc["description"],
                dialogue=sc["dialogue"], audio_path=audio["path"], audio_duration=audio["duration"],
                timing=audio["timing"],
            )
            speakers = {d["speaker"] for d in sc["dialogue"]}
            for key in sc["present"] or list(chars)[:1]:
                if key in chars:
                    scene.cast.append(SceneCharacter(character_id=chars[key].id, speaks=key in speakers))
            db.add(scene)
    return {"stage": "plan_scenes"}


# 6. CHARACTER + INTERACTION MAPPING ----------------------------------------------------------

def _default_blocking(cast: list[SceneCharacter], scene: Scene, key_of: dict) -> None:
    positions = {1: ["center"], 2: ["left", "right"], 3: ["left", "center", "right"]}.get(len(cast), ["center"] * len(cast))
    emotions = {d["speaker"]: d.get("emotion", "neutral") for d in scene.dialogue or []}
    for sc_char, pos in zip(cast, positions):
        key = key_of[sc_char.character_id]
        others = [key_of[c.character_id] for c in cast if c is not sc_char]
        sc_char.position = pos
        sc_char.looks_at = others[0] if others and not sc_char.speaks else "camera" if not others else others[0]
        sc_char.emotion = emotions.get(key, "neutral")
        sc_char.action = "speaking with natural gestures" if sc_char.speaks else "listening and reacting"


def map_interactions(state: GraphState) -> GraphState:
    set_status(state["job_id"], "mapping_interactions")
    job_id = state["job_id"]
    with session() as db:
        scenes = db.query(Scene).filter(Scene.job_id == job_id).order_by(Scene.scene_number).all()
        chars = db.query(Character).filter(Character.job_id == job_id).all()
        key_of = {c.id: c.key for c in chars}
        payload = [
            {"scene_number": s.scene_number, "location": s.location, "description": s.description,
             "present": [key_of[c.character_id] for c in s.cast], "dialogue": s.dialogue}
            for s in scenes
        ]
        result = llm_json(
            "You are a film director doing blocking. For every character present in each scene decide: "
            "position in frame (left/center/right, foreground/background), who they look at (a character key "
            "or 'camera'), what physical action they do, their emotion, and whether they speak. Reply as JSON: "
            '{"scenes": [{"scene_number": int, "cast": [{"key": "A", "position": str, "looks_at": str, '
            '"action": str, "emotion": str, "speaks": bool}]}]}',
            f"Characters: {json.dumps([{'key': c.key, 'name': c.name, 'role': c.role} for c in chars])}\n"
            f"Scenes: {json.dumps(payload)}",
            temperature=0.5,
        )
        by_scene = {s.get("scene_number"): s for s in (result or {}).get("scenes", []) if isinstance(s, dict)}
        for scene in scenes:
            _default_blocking(scene.cast, scene, key_of)
            planned = {c.get("key"): c for c in by_scene.get(scene.scene_number, {}).get("cast", []) if isinstance(c, dict)}
            for sc_char in scene.cast:
                p = planned.get(key_of[sc_char.character_id])
                if not p:
                    continue
                sc_char.position = str(p.get("position") or sc_char.position)
                sc_char.looks_at = str(p.get("looks_at") or sc_char.looks_at)
                sc_char.action = str(p.get("action") or sc_char.action)
                sc_char.emotion = str(p.get("emotion") or sc_char.emotion)
                if isinstance(p.get("speaks"), bool):
                    sc_char.speaks = p["speaks"]
    return {"stage": "map_interactions"}


# 7. SHOT PLANNER -----------------------------------------------------------------------------

def _shot_slots(scenes: list[Scene]) -> dict[int, list[int]]:
    """Deterministic cost budget: >=1 shot per scene, a 2nd shot only for long scenes, never more
    than MAX_SHOTS total. Durations are snapped to what the video model can render."""
    settings = get_settings()
    durations = allowed_durations()
    longest = durations[-1]
    budget = settings.max_shots - len(scenes)
    slots = {}
    for s in scenes:
        length = max(s.audio_duration + 0.4, 3.0)
        count = 1
        if length > longest and budget > 0:
            count, budget = 2, budget - 1
        per_shot = math.ceil(length / count)
        clip = next((d for d in durations if d >= per_shot), longest)
        slots[s.scene_number] = [clip] * count
    return slots


def plan_shots(state: GraphState) -> GraphState:
    set_status(state["job_id"], "planning_shots")
    job_id = state["job_id"]
    with session() as db:
        scenes = db.query(Scene).filter(Scene.job_id == job_id).order_by(Scene.scene_number).all()
        slots = _shot_slots(scenes)
        payload = [{"scene_number": s.scene_number, "shots": len(slots[s.scene_number]), "location": s.location,
                    "description": s.description, "dialogue": s.dialogue} for s in scenes]
        result = llm_json(
            "You are a cinematographer. For each scene plan exactly the requested number of shots. Each shot: "
            "camera angle (eye-level/low/high/over-the-shoulder), framing (wide/medium/close-up/two-shot), "
            "camera movement (static/slow push-in/pan/dolly/handheld; keep it simple and smooth), and the "
            "single visible action in that shot. Reply as JSON: "
            '{"shots": [{"scene_number": int, "shot_number": int, "camera": str, "framing": str, '
            '"movement": str, "action": str}]}',
            f"Visual style: {state['brief'].get('visual_style')}\nScenes: {json.dumps(payload)}",
            temperature=0.6,
        )
        planned = {(p.get("scene_number"), p.get("shot_number")): p
                   for p in (result or {}).get("shots", []) if isinstance(p, dict)}
        defaults = [
            {"camera": "eye-level", "framing": "medium two-shot", "movement": "slow push-in"},
            {"camera": "eye-level", "framing": "close-up on the speaker", "movement": "static, subtle handheld"},
        ]
        for scene in scenes:
            for old in list(scene.shots):
                scene.shots.remove(old)
            for n, clip in enumerate(slots[scene.scene_number], 1):
                p = planned.get((scene.scene_number, n), {})
                d = defaults[min(n - 1, 1)]
                scene.shots.append(Shot(
                    shot_number=n,
                    camera=str(p.get("camera") or d["camera"]),
                    framing=str(p.get("framing") or d["framing"]),
                    movement=str(p.get("movement") or d["movement"]),
                    action=str(p.get("action") or scene.description),
                    duration_seconds=clip,
                ))
    return {"stage": "plan_shots"}


# 8. PROMPT ENGINE ----------------------------------------------------------------------------

def compose_prompts(shot: Shot, scene: Scene, brief: dict, chars: dict) -> tuple[str, str, str]:
    """Returns (keyframe_prompt, video_prompt, negative_prompt).
    Global style + scene + character refs + interaction + camera, plus a shared negative prompt."""
    cast = scene.cast
    people = []
    blocking = []
    for sc in cast:
        c = chars[sc.character_id]
        people.append(f"{c.name}: {c.appearance}")
        look = "the camera" if sc.looks_at in (None, "", "camera") else next(
            (o.name for o in chars.values() if o.key == sc.looks_at), sc.looks_at)
        blocking.append(f"{c.name} at frame {sc.position}, looking at {look}, {sc.emotion}, {sc.action}")

    count = f"exactly {len(cast)} {'person' if len(cast) == 1 else 'people'} in frame" if cast else "no people"
    style = f"{brief.get('visual_style', '')}, {brief.get('tone', '')} mood"
    keyframe = (
        f"{shot.framing}, {shot.camera} angle. {scene.location}. {count}. "
        f"{' | '.join(people)}. {'; '.join(blocking)}. {shot.action}. "
        f"Style: {style}, photorealistic film still, natural skin texture."
    )
    speakers = [chars[sc.character_id].name for sc in cast if sc.speaks]
    talking = f" {', '.join(speakers)} talking naturally, lips moving." if speakers else ""
    video = (
        f"{shot.movement} camera. {shot.action}.{talking} "
        f"{'; '.join(blocking)}. Keep faces, outfits and {count} consistent. {style}, smooth realistic motion."
    )
    return keyframe, video, NEGATIVE_PROMPT


def build_prompts(state: GraphState) -> GraphState:
    set_status(state["job_id"], "building_prompts")
    with session() as db:
        chars = {c.id: c for c in db.query(Character).filter(Character.job_id == state["job_id"]).all()}
        for scene in db.query(Scene).filter(Scene.job_id == state["job_id"]).all():
            for shot in scene.shots:
                shot.keyframe_prompt, shot.prompt, shot.negative_prompt = compose_prompts(shot, scene, state["brief"], chars)
                shot.status = "pending"
    return {"stage": "build_prompts"}

