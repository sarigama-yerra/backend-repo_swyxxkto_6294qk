import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Dict, Optional, List
from database import create_document, get_documents

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class Expressions(BaseModel):
    neutral: Optional[float] = 0
    happy: Optional[float] = 0
    sad: Optional[float] = 0
    angry: Optional[float] = 0
    fearful: Optional[float] = 0
    disgusted: Optional[float] = 0
    surprised: Optional[float] = 0

class StoryRequest(BaseModel):
    image_data: str = Field(..., description="Base64 data URL of captured image")
    mood: str = Field(..., description="Primary detected mood")
    expressions: Dict[str, float] = Field(..., description="Expression scores map")
    prompt_hint: Optional[str] = Field(None, description="Optional user hint for the story")

class StoryResponse(BaseModel):
    id: str
    mood: str
    story: str
    illustration: str


@app.get("/")
def read_root():
    return {"message": "Mood Story Generator API is running"}


@app.get("/api/hello")
def hello():
    return {"message": "Hello from the backend API!"}


@app.get("/test")
def test_database():
    """Test endpoint to check if database is available and accessible"""
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }
    try:
        from database import db
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
            response["database_name"] = db.name if hasattr(db, 'name') else "✅ Connected"
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️  Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"
    return response


def _generate_rule_based_story(mood: str, hint: Optional[str], scores: Dict[str, float]) -> str:
    mood = (mood or "neutral").lower()
    templates = {
        "happy": (
            "Sunlight spilled across the scene like a promise kept. With a grin that could start a parade, "
            "you stepped into a day that felt tailor‑made—small wins humming in the background, "
            "good news waiting just around the corner. {hint}"
        ),
        "sad": (
            "The world moved softly, as if it knew to speak in whispers today. Even through the gray, "
            "there was kindness—warm tea, a gentle song, a friend who stays. Your heart carried rain, "
            "but it also carried flowers waiting to bloom. {hint}"
        ),
        "angry": (
            "The air crackled—electric, decisive. Your fire didn’t destroy; it forged. Today you chose "
            "to build boundaries like bright lines on a map, turning heat into momentum and motion into change. {hint}"
        ),
        "fearful": (
            "Shadows stretched long, but courage walked beside you, quiet and steady. Each careful step "
            "rewrote a small fear into a fearless line. Your breath became an anchor, and the unknown grew smaller. {hint}"
        ),
        "disgusted": (
            "Clarity arrived like a clean breeze through a cluttered room. You saw what didn’t belong, "
            "and chose better—cleaner intentions, truer paths, a standard that honored your spirit. {hint}"
        ),
        "surprised": (
            "A sudden spark—like confetti popped in slow motion. The unexpected turned into delight, "
            "and the story bent toward wonder. You followed curiosity and found a door you didn’t know you needed. {hint}"
        ),
        "neutral": (
            "Balanced and unhurried, the day unfolded like neat pages in a journal. Quiet details glowed— "
            "a steady rhythm, a tidy list, a calm horizon. In the middle of ordinary, you found peace. {hint}"
        ),
    }
    base = templates.get(mood, templates["neutral"]) 
    hint_text = ("" if not hint else f"\n\nA note from you: {hint.strip()}")
    # Add a small footer based on the strongest alternate expressions
    sorted_scores = sorted(scores.items(), key=lambda x: x[1] or 0, reverse=True)
    tone = ", ".join([k for k, v in sorted_scores[:3]]) if sorted_scores else mood
    footer = f"\n\nMood palette today: {tone}."
    return (base.format(hint=hint_text) + footer).strip()


@app.post("/api/generate-story", response_model=StoryResponse)
def generate_story(req: StoryRequest):
    if not req.image_data.startswith("data:image/"):
        raise HTTPException(status_code=400, detail="image_data must be a data URL starting with data:image/")

    story_text = _generate_rule_based_story(req.mood, req.prompt_hint, req.expressions)

    # Choose a simple illustration key for the frontend
    mood_map = {
        "happy": "sunny",
        "sad": "rainy",
        "angry": "flame",
        "fearful": "moon",
        "disgusted": "leaf",
        "surprised": "spark",
        "neutral": "cloud",
    }
    illustration_key = mood_map.get(req.mood.lower(), "cloud")

    # Persist to MongoDB
    try:
        data_to_save = {
            "image_data": req.image_data,
            "mood": req.mood,
            "expressions": req.expressions,
            "story": story_text,
            "illustration": illustration_key,
        }
        inserted_id = create_document("storyentry", data_to_save)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to store story: {str(e)[:120]}")

    return StoryResponse(id=inserted_id, mood=req.mood, story=story_text, illustration=illustration_key)


@app.get("/api/stories")
def list_stories(limit: int = 10) -> List[dict]:
    try:
        docs = get_documents("storyentry", {}, limit)
        # sanitize ObjectId
        for d in docs:
            if "_id" in d:
                d["id"] = str(d.pop("_id"))
        return docs
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch stories: {str(e)[:120]}")


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
