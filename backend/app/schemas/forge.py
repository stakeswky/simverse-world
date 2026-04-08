from pydantic import BaseModel


class ForgeStartRequest(BaseModel):
    """Initiate a new forge session."""
    name: str  # Q1: resident name


class ForgeStartResponse(BaseModel):
    forge_id: str
    step: int  # current step (1)
    question: str  # next question to display


class ForgeAnswerRequest(BaseModel):
    """Submit an answer for the current step."""
    forge_id: str
    answer: str


class ForgeAnswerResponse(BaseModel):
    forge_id: str
    step: int  # step just completed
    next_step: int | None  # next step, or None if done
    question: str | None  # next question, or None if done
    ability_md: str | None = None
    persona_md: str | None = None
    soul_md: str | None = None


class ForgeStatusResponse(BaseModel):
    forge_id: str
    status: str  # "collecting" | "generating" | "done" | "error"
    step: int
    name: str
    answers: dict[str, str]
    ability_md: str
    persona_md: str
    soul_md: str
    star_rating: int
    district: str
    resident_id: str | None  # set when status == "done"
    error: str | None = None


# --- Deep forge (pipeline) schemas ---

class DeepStartRequest(BaseModel):
    character_name: str
    raw_text: str = ""
    user_material: str = ""


class DeepStartResponse(BaseModel):
    forge_id: str
    mode: str
    status: str


class DeepStatusResponse(BaseModel):
    forge_id: str
    status: str
    current_stage: str
    mode: str
    character_name: str
