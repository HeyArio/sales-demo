"""
server.py  —  RAG chatbot + quiz API for the Persian sales course.

Endpoints:
  GET  /                -> serves the demo UI (index.html)
  POST /chat            -> {question} -> grounded answer + sources (timestamps)
  POST /quiz            -> {num_questions} -> generates a multiple-choice quiz
  POST /quiz/grade      -> {answers} -> scores it

Run:
  export MISTRAL_API_KEY=your_key
  python build_index.py knowledge_base.json     # once
  uvicorn server:app --reload --port 8000
Then open http://localhost:8000
"""
import os, json, math, re
from typing import List, Optional
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from mistralai import Mistral

API_KEY = os.environ.get("MISTRAL_API_KEY")
if not API_KEY:
    raise SystemExit("Set MISTRAL_API_KEY first.")

EMBED_MODEL = "mistral-embed"
CHAT_MODEL  = "mistral-small-latest"   # free-tier friendly; bump to mistral-large-latest if you want
TOP_K       = 4

client = Mistral(api_key=API_KEY)
app = FastAPI(title="Sales Course RAG Demo")

# ---- load prebuilt index -------------------------------------------------
with open("index.json", encoding="utf-8") as f:
    INDEX = json.load(f)
ITEMS = INDEX["items"]
for it in ITEMS:                       # precompute norms for cosine sim
    it["_norm"] = math.sqrt(sum(x * x for x in it["vector"])) or 1.0

def cosine(q, qnorm, v, vnorm):
    dot = sum(a * b for a, b in zip(q, v))
    return dot / (qnorm * vnorm)

def embed_query(text: str) -> List[float]:
    resp = client.embeddings.create(model=EMBED_MODEL, inputs=[text])
    return resp.data[0].embedding

def retrieve(query: str, k: int = TOP_K):
    q = embed_query(query)
    qnorm = math.sqrt(sum(x * x for x in q)) or 1.0
    scored = [(cosine(q, qnorm, it["vector"], it["_norm"]), it) for it in ITEMS]
    scored.sort(key=lambda s: s[0], reverse=True)
    return [it for _, it in scored[:k]]

# ---- /chat ---------------------------------------------------------------
class ChatIn(BaseModel):
    question: str

SYSTEM_CHAT = (
    "تو یک دستیار آموزشی برای یک دورهٔ فروش و بازاریابی هستی. "
    "فقط بر اساس «متن دوره» که در اختیارت قرار می‌گیرد پاسخ بده. "
    "اگر پاسخ در متن نبود، صادقانه بگو که در این بخش از دوره مطرح نشده است. "
    "پاسخ را روان، خلاصه و به زبان فارسی بده."
)

@app.post("/chat")
def chat(inp: ChatIn):
    hits = retrieve(inp.question)
    context = "\n\n".join(
        f"[بخش {h['timestamp_range']}]\n{h['text']}" for h in hits
    )
    messages = [
        {"role": "system", "content": SYSTEM_CHAT},
        {"role": "user", "content":
            f"متن دوره:\n{context}\n\nسؤال کاربر: {inp.question}"},
    ]
    resp = client.chat.complete(model=CHAT_MODEL, messages=messages, temperature=0.2)
    answer = resp.choices[0].message.content
    return {
        "answer": answer,
        "sources": [
            {"timestamp_range": h["timestamp_range"],
             "start_seconds": h["start_seconds"],
             "preview": h["text"][:90] + "…"}
            for h in hits
        ],
    }

# ---- /quiz ---------------------------------------------------------------
class QuizIn(BaseModel):
    num_questions: int = 4
    # optional: restrict to a time window of the video (seconds)
    start: Optional[float] = None
    end: Optional[float] = None

def section_text(start, end):
    items = ITEMS
    if start is not None and end is not None:
        items = [it for it in ITEMS if start <= it["start_seconds"] <= end]
        if not items:
            items = ITEMS
    return "\n".join(it["text"] for it in items)

QUIZ_INSTR = """تو یک طراح آزمون آموزشی هستی. بر اساس «متن دوره» زیر، {n} سؤال چهارگزینه‌ای بساز.
خروجی را فقط و فقط به صورت JSON معتبر بده، بدون هیچ متن اضافه، با این ساختار دقیق:
{{
  "questions": [
    {{
      "q": "متن سؤال",
      "options": ["گزینه ۱", "گزینه ۲", "گزینه ۳", "گزینه ۴"],
      "answer_index": 0,
      "explanation": "توضیح کوتاه چرا این گزینه درست است"
    }}
  ]
}}
سؤال‌ها باید فقط از محتوای متن دوره باشند و گزینه‌های نادرست منطقی اما اشتباه باشند."""

def extract_json(text: str) -> dict:
    """Mistral sometimes wraps JSON in ```; strip and parse."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?", "", text).strip()
    text = re.sub(r"```$", "", text).strip()
    start = text.find("{")
    end = text.rfind("}")
    return json.loads(text[start:end + 1])

# we keep the correct answers server-side per generated quiz
_ANSWER_STORE = {}

@app.post("/quiz")
def quiz(inp: QuizIn):
    ctx = section_text(inp.start, inp.end)
    # cap context so we stay light on the free tier
    ctx = ctx[:6000]
    prompt = QUIZ_INSTR.format(n=inp.num_questions)
    messages = [
        {"role": "system", "content": "خروجی فقط JSON معتبر است."},
        {"role": "user", "content": f"{prompt}\n\nمتن دوره:\n{ctx}"},
    ]
    resp = client.chat.complete(
        model=CHAT_MODEL, messages=messages, temperature=0.4,
        response_format={"type": "json_object"},
    )
    data = extract_json(resp.choices[0].message.content)

    quiz_id = os.urandom(6).hex()
    # store answers, strip them from what we send to the client
    answers = [q["answer_index"] for q in data["questions"]]
    explanations = [q.get("explanation", "") for q in data["questions"]]
    _ANSWER_STORE[quiz_id] = {"answers": answers, "explanations": explanations}

    public = {
        "quiz_id": quiz_id,
        "questions": [
            {"q": q["q"], "options": q["options"]} for q in data["questions"]
        ],
    }
    return public

class GradeIn(BaseModel):
    quiz_id: str
    answers: List[int]

@app.post("/quiz/grade")
def grade(inp: GradeIn):
    stored = _ANSWER_STORE.get(inp.quiz_id)
    if not stored:
        return {"error": "quiz not found (server restarted?)"}
    correct = stored["answers"]
    results = []
    score = 0
    for i, (given, right) in enumerate(zip(inp.answers, correct)):
        ok = given == right
        score += ok
        results.append({
            "index": i,
            "correct": ok,
            "answer_index": right,
            "explanation": stored["explanations"][i],
        })
    return {"score": score, "total": len(correct), "results": results}

# ---- serve UI ------------------------------------------------------------
@app.get("/")
def home():
    return FileResponse("index.html")