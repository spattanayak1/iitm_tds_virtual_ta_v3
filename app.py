#!/usr/bin/env python3
"""
Virtual TA API for TDS Course
A Flask-based API that answers student questions using course content and Discourse posts.
"""

import os
import json
import base64
import requests
from datetime import datetime, timedelta
from flask import Flask, request, jsonify
from flask_cors import CORS
import openai
from bs4 import BeautifulSoup
import re
import sqlite3
import logging
from typing import List, Dict, Optional, Tuple
import time

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# Configuration
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
if OPENAI_API_KEY:
    openai.api_key = OPENAI_API_KEY

DATABASE_PATH = 'tds_knowledge.db'

class DiscourseScraperTDS:
    """Scraper for TDS Discourse posts"""
    
    def __init__(self, base_url="https://discourse.onlinedegree.iitm.ac.in"):
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
    
    def scrape_posts_by_date_range(self, start_date: str, end_date: str, category_id: int = None) -> List[Dict]:
        """
        Scrape Discourse posts within a date range
        start_date, end_date: 'YYYY-MM-DD' format
        category_id: TDS category ID if known
        """
        posts = []
        
        try:
            # Convert date strings to datetime objects
            start_dt = datetime.strptime(start_date, '%Y-%m-%d')
            end_dt = datetime.strptime(end_date, '%Y-%m-%d')
            
            # Search for TDS-related topics
            search_terms = ['TDS', 'Tools in Data Science', 'assignment', 'project']
            
            for term in search_terms:
                posts.extend(self._search_posts(term, start_dt, end_dt))
                time.sleep(1)  # Rate limiting
            
            # Remove duplicates based on URL
            unique_posts = {}
            for post in posts:
                unique_posts[post['url']] = post
            
            return list(unique_posts.values())
            
        except Exception as e:
            logger.error(f"Error scraping posts: {e}")
            return []
    
    def _search_posts(self, search_term: str, start_date: datetime, end_date: datetime) -> List[Dict]:
        """Search for posts containing a specific term within date range"""
        posts = []
        
        try:
            # Use Discourse search API
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
                        'posts_count': topic.get('posts_count', 0)
                    }
                    
                    # Fetch full content
                    full_content = self._fetch_topic_content(topic.get('id'))
                    post_data['content'] = full_content
                    
                    posts.append(post_data)
                    
        except Exception as e:
            logger.error(f"Error searching posts for term '{search_term}': {e}")
        
        return posts
    
    def _fetch_topic_content(self, topic_id: int) -> str:
        """Fetch full content of a topic"""
        try:
            topic_url = f"{self.base_url}/t/{topic_id}.json"
            response = self.session.get(topic_url)
            
            if response.status_code == 200:
                data = response.json()
                posts = data.get('post_stream', {}).get('posts', [])
                
                content_parts = []
                for post in posts[:5]:  # Limit to first 5 posts
                    raw_content = post.get('raw', '')
                    if raw_content:
                        content_parts.append(raw_content)
                
                return '\n\n'.join(content_parts)
        except Exception as e:
            logger.error(f"Error fetching topic {topic_id}: {e}")
        
        return ""

class KnowledgeBase:
    """Knowledge base for storing and retrieving course content and Discourse posts"""
    
    def __init__(self, db_path: str = DATABASE_PATH):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Initialize SQLite database"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Create tables
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
        """Add Discourse posts to database"""
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
                    logger.error(f"Error inserting post: {e}")
            
            conn.commit()
    
    def search_relevant_content(self, question: str, limit: int = 5) -> List[Dict]:
        """Search for relevant content based on question keywords"""
        keywords = self._extract_keywords(question)
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Search in discourse posts
            discourse_results = []
            for keyword in keywords:
                cursor.execute('''
                    SELECT title, url, content, excerpt FROM discourse_posts
                    WHERE title LIKE ? OR content LIKE ? OR excerpt LIKE ?
                    LIMIT ?
                ''', (f'%{keyword}%', f'%{keyword}%', f'%{keyword}%', limit))
                
                results = cursor.fetchall()
                for result in results:
                    discourse_results.append({
                        'type': 'discourse',
                        'title': result[0],
                        'url': result[1],
                        'content': result[2][:500],  # Truncate for relevance
                        'excerpt': result[3]
                    })
            
            # Search in course content
            course_results = []
            for keyword in keywords:
                cursor.execute('''
                    SELECT title, content, source FROM course_content
                    WHERE title LIKE ? OR content LIKE ?
                    LIMIT ?
                ''', (f'%{keyword}%', f'%{keyword}%', limit))
                
                results = cursor.fetchall()
                for result in results:
                    course_results.append({
                        'type': 'course',
                        'title': result[0],
                        'content': result[1][:500],
                        'source': result[2]
                    })
        
        # Combine and deduplicate
        all_results = discourse_results + course_results
        return all_results[:limit]
    
    def _extract_keywords(self, text: str) -> List[str]:
        """Extract keywords from question text"""
        # Simple keyword extraction
        stop_words = {'the', 'is', 'at', 'which', 'on', 'a', 'an', 'and', 'or', 'but', 'in', 'with', 'to', 'for', 'of', 'as', 'by'}
        words = re.findall(r'\b\w+\b', text.lower())
        keywords = [word for word in words if word not in stop_words and len(word) > 2]
        return keywords[:5]  # Limit to top 5 keywords

class VirtualTA:
    """Main Virtual TA class for answering questions"""
    
    def __init__(self):
        self.knowledge_base = KnowledgeBase()
        self.scraper = DiscourseScraperTDS()
    
    def answer_question(self, question: str, image_base64: Optional[str] = None) -> Dict:
        """Answer a student question"""
        try:
            # Search for relevant content
            relevant_content = self.knowledge_base.search_relevant_content(question)
            
            # Prepare context for AI
            context = self._prepare_context(relevant_content)
            
            # Generate answer using AI
            answer = self._generate_answer(question, context, image_base64)
            
            # Extract relevant links
            links = self._extract_links(relevant_content)
            
            return {
                "answer": answer,
                "links": links
            }
            
        except Exception as e:
            logger.error(f"Error answering question: {e}")
            return {
                "answer": "I apologize, but I encountered an error while processing your question. Please try again or contact the course staff.",
                "links": []
            }
    
    def _prepare_context(self, relevant_content: List[Dict]) -> str:
        """Prepare context from relevant content"""
        context_parts = []
        
        for content in relevant_content:
            if content['type'] == 'discourse':
                context_parts.append(f"Discourse Post: {content['title']}\n{content['content']}")
            elif content['type'] == 'course':
                context_parts.append(f"Course Content: {content['title']}\n{content['content']}")
        
        return '\n\n---\n\n'.join(context_parts)
    
    def _generate_answer(self, question: str, context: str, image_base64: Optional[str] = None) -> str:
        """Generate answer using OpenAI API"""
        if not OPENAI_API_KEY:
            return self._generate_fallback_answer(question, context)
        
        try:
            messages = [
                {
                    "role": "system",
                    "content": """You are a helpful Teaching Assistant for the Tools in Data Science (TDS) course at IIT Madras. 
                    Answer student questions based on the provided context from course materials and Discourse posts. 
                    Be concise, accurate, and helpful. If you're not sure about something, say so.
                    Focus on practical guidance and reference the course materials when appropriate."""
                },
                {
                    "role": "user",
                    "content": f"Context:\n{context}\n\nQuestion: {question}"
                }
            ]
            
            # Add image if provided
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
            logger.error(f"Error generating AI answer: {e}")
            return self._generate_fallback_answer(question, context)
    
    def _generate_fallback_answer(self, question: str, context: str) -> str:
        """Generate a fallback answer when AI is not available"""
        if not context:
            return "I don't have enough information to answer your question. Please check the course materials or ask on the Discourse forum."
        
        # Simple keyword-based response
        if any(word in question.lower() for word in ['assignment', 'homework', 'hw']):
            return "For assignment-related questions, please refer to the course materials and assignment instructions. If you need clarification, check the Discourse forum for similar discussions."
        elif any(word in question.lower() for word in ['deadline', 'due', 'submit']):
            return "Please check the course schedule and assignment pages for submission deadlines. Make sure to submit your work before the specified deadline."
        else:
            return "Based on the available course materials, I suggest reviewing the relevant course content. For specific questions, please check the Discourse forum or contact the course staff."
    
    def _extract_links(self, relevant_content: List[Dict]) -> List[Dict]:
        """Extract relevant links from content"""
        links = []
        
        for content in relevant_content:
            if content['type'] == 'discourse' and content.get('url'):
                links.append({
                    "url": content['url'],
                    "text": content.get('title', 'Discourse Discussion')
                })
        
        return links[:3]  # Limit to top 3 links
    
    def update_knowledge_base(self):
        """Update knowledge base with latest Discourse posts"""
        try:
            # Scrape posts from Jan 1, 2025 to Apr 14, 2025 as specified
            posts = self.scraper.scrape_posts_by_date_range('2025-01-01', '2025-04-14')
            self.knowledge_base.add_discourse_posts(posts)
            logger.info(f"Updated knowledge base with {len(posts)} posts")
        except Exception as e:
            logger.error(f"Error updating knowledge base: {e}")

# Initialize Virtual TA
virtual_ta = VirtualTA()

@app.route('/api/', methods=['POST'])
def answer_question():
    """Main API endpoint for answering questions"""
    try:
        data = request.get_json()
        
        if not data or 'question' not in data:
            return jsonify({"error": "Missing 'question' in request"}), 400
        
        question = data['question']
        image_base64 = data.get('image')
        
        # Process image if provided
        if image_base64:
            try:
                # Validate base64 image
                base64.b64decode(image_base64)
            except Exception:
                return jsonify({"error": "Invalid base64 image"}), 400
        
        # Get answer from Virtual TA
        response = virtual_ta.answer_question(question, image_base64)
        
        return jsonify(response)
        
    except Exception as e:
        logger.error(f"API error: {e}")
        return jsonify({"error": "Internal server error"}), 500

@app.route('/api/update', methods=['POST'])
def update_knowledge():
    """Endpoint to update knowledge base"""
    try:
        virtual_ta.update_knowledge_base()
        return jsonify({"message": "Knowledge base updated successfully"})
    except Exception as e:
        logger.error(f"Update error: {e}")
        return jsonify({"error": "Failed to update knowledge base"}), 500

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({"status": "healthy"})

if __name__ == '__main__':
    # Initialize database and update knowledge base on startup
    try:
        virtual_ta.update_knowledge_base()
    except Exception as e:
        logger.warning(f"Could not update knowledge base on startup: {e}")
    
    # Run the app
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)