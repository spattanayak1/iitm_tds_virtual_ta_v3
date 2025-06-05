import os
import json
import base64
import requests
from datetime import datetime
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict
import openai
import sqlite3
import logging
import re
import time

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# FastAPI setup
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# OpenAI config
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
if OPENAI_API_KEY:
    openai.api_key = OPENAI_API_KEY

DATABASE_PATH = 'tds_knowledge.db'

# ----- Models -----
class QuestionRequest(BaseModel):
    question: str
    image: Optional[str] = None

# ----- Classes -----

class DiscourseScraperTDS:
    def __init__(self, base_url="https://discourse.onlinedegree.iitm.ac.in"):
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0'
        })

    def scrape_posts_by_date_range(self, start_date: str, end_date: str) -> List[Dict]:
        posts = []
        try:
            start_dt = datetime.strptime(start_date, '%Y-%m-%d')
            end_dt = datetime.strptime(end_date, '%Y-%m-%d')
            search_terms = ['TDS', 'Tools in Data Science', 'assignment', 'project']
            for term in search_terms:
                posts.extend(self._search_posts(term, start_dt, end_dt))
                time.sleep(1)
            unique_posts = {post['url']: post for post in posts}
            return list(unique_posts.values())
        except Exception as e:
            logger.error(f"Error scraping posts: {e}")
            return []

    def _search_posts(self, search_term: str, start_date: datetime, end_date: datetime) -> List[Dict]:
        posts = []
        try:
            search_url = f"{self.base_url}/search.json"
            params = {
                'q': f"{search_term} after:{start_date.strftime('%Y-%m-%d')} before:{end_date.strftime('%Y-%m-%d')}",
                'page': 1
            }
            response = self.session.get(search_url, params=params)
            if response.status_code == 200:
                data = response.json()
                for topic in data.get('topics', []):
                    post_data = {
                        'title': topic.get('title', ''),
                        'url': f"{self.base_url}/t/{topic.get('slug', '')}/{topic.get('id', '')}",
                        'created_at': topic.get('created_at', ''),
                        'excerpt': topic.get('excerpt', ''),
                        'category_name': topic.get('category_name', ''),
                        'posts_count': topic.get('posts_count', 0),
                        'content': self._fetch_topic_content(topic.get('id'))
                    }
                    posts.append(post_data)
        except Exception as e:
            logger.error(f"Error searching posts: {e}")
        return posts

    def _fetch_topic_content(self, topic_id: int) -> str:
        try:
            topic_url = f"{self.base_url}/t/{topic_id}.json"
            response = self.session.get(topic_url)
            if response.status_code == 200:
                data = response.json()
                posts = data.get('post_stream', {}).get('posts', [])
                content_parts = [post.get('raw', '') for post in posts[:5]]
                return '\n\n'.join(content_parts)
        except Exception as e:
            logger.error(f"Error fetching topic {topic_id}: {e}")
        return ""


class KnowledgeBase:
    def __init__(self, db_path: str = DATABASE_PATH):
        self.db_path = db_path
        self.init_database()

    def init_database(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS discourse_posts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT,
                    url TEXT UNIQUE,
                    content TEXT,
                    created_at TEXT,
                    category_name TEXT,
                    excerpt TEXT,
                    posts_count INTEGER
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS course_content (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT,
                    content TEXT,
                    source TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            conn.commit()

    def add_discourse_posts(self, posts: List[Dict]):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            for post in posts:
                try:
                    cursor.execute('''
                        INSERT OR REPLACE INTO discourse_posts 
                        (title, url, content, created_at, category_name, excerpt, posts_count)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        post.get('title', ''),
                        post.get('url', ''),
                        post.get('content', ''),
                        post.get('created_at', ''),
                        post.get('category_name', ''),
                        post.get('excerpt', ''),
                        post.get('posts_count', 0)
                    ))
                except Exception as e:
                    logger.error(f"DB insert error: {e}")
            conn.commit()

    def search_relevant_content(self, question: str, limit: int = 5) -> List[Dict]:
        keywords = self._extract_keywords(question)
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            discourse_results, course_results = [], []
            for keyword in keywords:
                cursor.execute('''
                    SELECT title, url, content, excerpt FROM discourse_posts
                    WHERE title LIKE ? OR content LIKE ? OR excerpt LIKE ?
                    LIMIT ?
                ''', (f'%{keyword}%',)*3 + (limit,))
                discourse_results.extend([
                    {
                        'type': 'discourse',
                        'title': r[0],
                        'url': r[1],
                        'content': r[2][:500],
                        'excerpt': r[3]
                    } for r in cursor.fetchall()
                ])
                cursor.execute('''
                    SELECT title, content, source FROM course_content
                    WHERE title LIKE ? OR content LIKE ?
                    LIMIT ?
                ''', (f'%{keyword}%', f'%{keyword}%', limit))
                course_results.extend([
                    {
                        'type': 'course',
                        'title': r[0],
                        'content': r[1][:500],
                        'source': r[2]
                    } for r in cursor.fetchall()
                ])
        return (discourse_results + course_results)[:limit]

    def _extract_keywords(self, text: str) -> List[str]:
        stop_words = {'the', 'is', 'at', 'which', 'on', 'a', 'an', 'and', 'or', 'but', 'in', 'with', 'to', 'for', 'of', 'as', 'by'}
        words = re.findall(r'\b\w+\b', text.lower())
        return [w for w in words if w not in stop_words and len(w) > 2][:5]


class VirtualTA:
    def __init__(self):
        self.knowledge_base = KnowledgeBase()
        self.scraper = DiscourseScraperTDS()

    def answer_question(self, question: str, image_base64: Optional[str] = None) -> Dict:
        try:
            relevant = self.knowledge_base.search_relevant_content(question)
            context = self._prepare_context(relevant)
            answer = self._generate_answer(question, context, image_base64)
            links = self._extract_links(relevant)
            return {"answer": answer, "links": links}
        except Exception as e:
            logger.error(f"Answer error: {e}")
            return {
                "answer": "I encountered an error while processing your question. Please try again.",
                "links": []
            }

    def _prepare_context(self, content: List[Dict]) -> str:
        return '\n\n---\n\n'.join([
            f"{c['type'].capitalize()} Content: {c['title']}\n{c['content']}"
            for c in content
        ])

    def _generate_answer(self, question: str, context: str, image_base64: Optional[str] = None) -> str:
        if not OPENAI_API_KEY:
            return self._generate_fallback_answer(question, context)
        try:
            messages = [
                {
                    "role": "system",
                    "content": """You are a helpful Teaching Assistant for the TDS course at IIT Madras. Be concise and helpful."""
                },
                {
                    "role": "user",
                    "content": f"Context:\n{context}\n\nQuestion: {question}"
                }
            ]
            if image_base64:
                messages[-1]["content"] = [
                    {"type": "text", "text": f"Context:\n{context}\n\nQuestion: {question}"},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}}
                ]
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=messages,
                max_tokens=300,
                temperature=0.7
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"OpenAI error: {e}")
            return self._generate_fallback_answer(question, context)

    def _generate_fallback_answer(self, question: str, context: str) -> str:
        if not context:
            return "I don't have enough info to answer that."
        if 'assignment' in question.lower():
            return "For assignment help, refer to course materials or Discourse discussions."
        return "Please check course content or Discourse discussions related to your question."

    def _extract_links(self, content: List[Dict]) -> List[Dict]:
        return [{"url": c["url"], "text": c.get("title", "Discussion")} for c in content if c["type"] == "discourse"][:3]

    def update_knowledge_base(self):
        posts = self.scraper.scrape_posts_by_date_range('2025-01-01', '2025-04-14')
        self.knowledge_base.add_discourse_posts(posts)
        logger.info(f"Added {len(posts)} posts to DB")

# ----- Init -----
virtual_ta = VirtualTA()

# ----- Routes -----
@app.post("/api/")
async def answer(request: QuestionRequest):
    try:
        if not request.question:
            raise HTTPException(status_code=400, detail="Missing 'question'")
        if request.image:
            try:
                base64.b64decode(request.image)
            except Exception:
                raise HTTPException(status_code=400, detail="Invalid base64 image")
        response = virtual_ta.answer_question(request.question, request.image)
        return response
    except Exception as e:
        logger.error(f"API error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.post("/api/update")
async def update_knowledge():
    try:
        virtual_ta.update_knowledge_base()
        return {"message": "Knowledge base updated"}
    except Exception as e:
        logger.error(f"Update error: {e}")
        raise HTTPException(status_code=500, detail="Failed to update")

@app.get("/health")
async def health_check():
    return {"status": "healthy"}
