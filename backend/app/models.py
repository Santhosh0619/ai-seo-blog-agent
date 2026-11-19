"""Request and structured outputs (validated by Pydantic)."""
import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

Level = Literal["low", "medium", "high"]
TONES = ("friendly", "professional", "expert", "casual")


class BlogRequest(BaseModel):
    """What the user fills in. The user's Gemini key is NOT part of this body (it travels in a header)."""
    topic: str = Field(min_length=3, max_length=120)
    site_url: str = Field(default="", max_length=200)
    country: str = Field(default="us", max_length=2)
    language: str = Field(default="en", max_length=2)
    audience: str = Field(default="", max_length=120)
    tone: str = Field(default="friendly", max_length=20)
    notes: str = Field(default="", max_length=1500)
    author: str = Field(default="", max_length=60)
    word_target: int = Field(default=1400, ge=800, le=2200)

    @field_validator("topic", "audience", "notes", "author", "site_url")
    @classmethod
    def _strip(cls, v: str) -> str:
        return re.sub(r"[ \t]+", " ", v).strip()

    @field_validator("country", "language")
    @classmethod
    def _code(cls, v: str) -> str:
        v = v.strip().lower()
        if not re.fullmatch(r"[a-z]{2}", v):
            raise ValueError("two-letter code expected")
        return v

    @field_validator("tone")
    @classmethod
    def _tone(cls, v: str) -> str:
        return v if v in TONES else "friendly"


class Seeds(BaseModel):
    seeds: list[str]
    audience_guess: str


class KeywordInsight(BaseModel):
    keyword: str
    intent: Literal["informational", "commercial", "transactional", "navigational"]
    relevance: Level
    competition: Level
    volume_band: Level
    note: str


class OutlineSection(BaseModel):
    h2: str
    h3s: list[str]


class Plan(BaseModel):
    primary_keyword: str
    secondary_keywords: list[str]
    reasoning: str
    topic: str
    angle: str
    slug: str
    audience: str
    search_intent: str
    insights: list[KeywordInsight]
    outline: list[OutlineSection]


class Subsection(BaseModel):
    heading: str
    paragraphs: list[str]
    bullets: list[str]


class Section(BaseModel):
    heading: str
    paragraphs: list[str]
    bullets: list[str]
    subsections: list[Subsection]


class FAQ(BaseModel):
    question: str
    answer: str


class InternalLink(BaseModel):
    anchor: str
    url: str
    reason: str


class ImageIdea(BaseModel):
    description: str
    alt: str
    placement: str
    query: str


class SourceRef(BaseModel):
    title: str
    url: str


class CTA(BaseModel):
    heading: str
    text: str
    button_text: str


class BlogPost(BaseModel):
    seo_title: str
    meta_description: str
    slug: str
    h1: str
    intro: list[str]
    takeaways: list[str]
    sections: list[Section]
    faqs: list[FAQ]
    internal_links: list[InternalLink]
    images: list[ImageIdea]
    sources: list[SourceRef]
    cta: CTA
    secondary_keywords_used: list[str]
