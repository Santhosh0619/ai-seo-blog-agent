"""Structured outputs the LLM must return (validated by Pydantic)."""
from typing import Literal

from pydantic import BaseModel

Level = Literal["low", "medium", "high"]


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
    sections: list[Section]
    faqs: list[FAQ]
    internal_links: list[InternalLink]
    images: list[ImageIdea]
    cta: CTA
    secondary_keywords_used: list[str]
