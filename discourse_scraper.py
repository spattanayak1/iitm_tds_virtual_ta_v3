#!/usr/bin/env python3
"""
Standalone Discourse Scraper for TDS Course
This script scrapes Discourse posts from a specified date range and saves them to a database.
"""

import requests
import json
import sqlite3
import time
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
import argparse
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DiscourseScraperTDS:
    """Standalone scraper for TDS Discourse posts"""
    
    def __init__(self, base_url="https://discourse.onlinedegree.iitm.ac.in"):
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
    
    def scrape_discourse_posts(self, start_date: str, end_date: str, output_file: str = 'tds_posts.json'):
        """
        Scrape Discourse posts within a date range and save to file
        Args:
            start_date: Start date in 'YYYY-MM-DD' format
            end_date: End date in 'YYYY-MM-DD' format
            output_file: Output JSON file path
        """
        logger.info(f"Scraping posts from {start_date} to {end_date}")
        
        posts = []
        
        try:
            # Convert dates
            start_dt = datetime.strptime(start_date, '%Y-%m-%d')
            end_dt = datetime.strptime(end_date, '%Y-%m-%d')
            
            # Search terms related to TDS
            search_terms = [
                'TDS', 'Tools in Data Science', 'assignment', 'project', 
                'homework', 'week', 'lecture', 'python', 'data science',
                'GA1', 'GA2', 'GA3', 'GA4', 'GA5', 'quiz', 'exam'
            ]
            
            for term in search_terms:
                logger.info(f"Searching for: {term}")
                term_posts = self._search_posts_by_term(term, start_dt, end_dt)
                posts.extend(term_posts)
                time.sleep(2)  # Rate limiting
            
            # Remove duplicates based on URL
            unique_posts = {}
            for post in posts:
                if post.get('url'):
                    unique_posts[post['url']] = post
            
            final_posts = list(unique_posts.values())
            logger.info(f"Found {len(final_posts)} unique posts")
            
            # Save to JSON file
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(final_posts, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Saved {len(final_posts)} posts to {output_file}")
            return final_posts
            
        except Exception as e:
            logger.error(f"Error during scraping: {e}")
            return []
    
    def _search_posts_by_term(self, search_term: str, start_date: datetime, end_date: datetime):
        """Search for posts containing a specific term"""
        posts = []
        page = 1
        
        while page <= 5:  # Limit to 5 pages per search term
            try:
                logger.info(f"  Searching page {page} for '{search_term}'")
                
                # Use Discourse search API
                search_url = f"{self.base_url}/search.json"
                params = {
                    'q': f"{search_term} after:{start_date.strftime('%Y-%m-%d')} before:{end_date.strftime('%Y-%m-%d')}",
                    'page': page
                }
                
                response = self.session.get(search_url, params=params, timeout=30)
                
                if response.status_code != 200:
                    logger.warning(f"Search failed with status {response.status_code}")
                    break
                
                data = response.json()
                topics = data.get('topics', [])
                
                if not topics:
                    logger.info(f"  No more results for '{search_term}' on page {page}")
                    break
                
                for topic in topics:
                    post_data = self._extract_topic_data(topic)
                    if post_data:
                        posts.append(post_data)
                
                page += 1
                time.sleep(1)  # Rate limiting between pages
                
            except Exception as e:
                logger.error(f"Error searching for '{search_term}' page {page}: {e}")
                break
        
        return posts
    
    def _extract_topic_data(self, topic):
        """Extract data from a topic"""
        try:
            topic_id = topic.get('id')
            slug = topic.get('slug', '')
            
            post_data = {
                'id': topic_id,
                'title': topic.get('title', ''),
                'url': f"{self.base_url}/t/{slug}/{topic_id}",
                'created_at': topic.get('created_at', ''),
                'last_posted_at': topic.get('last_posted_at', ''),
                'category_name': topic.get('category_name', ''),
                'posts_count': topic.get('posts_count', 0),
                'views': topic.get('views', 0),
                'excerpt': topic.get('excerpt', ''),
                'tags': topic.get('tags', [])
            }
            
            # Fetch full content
            content = self._fetch_topic_content(topic_id)
            post_data['content'] = content
            
            return post_data
            
        except Exception as e:
            logger.error(f"Error extracting topic data: {e}")
            return None
    
    def _fetch_topic_content(self, topic_id):
        """Fetch full content of a topic"""
        try:
            topic_url = f"{self.base_url}/t/{topic_id}.json"
            response = self.session.get(topic_url, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                posts = data.get('post_stream', {}).get('posts', [])
                
                content_parts = []
                for post in posts[:10]:  # Limit to first 10 posts per topic
                    raw_content = post.get('raw', '')
                    username = post.get('username', 'Unknown')
                    created_at = post.get('created_at', '')
                    
                    if raw_content:
                        post_content = f"[{username} - {created_at}]\n{raw_content}"
                        content_parts.append(post_content)
                
                return '\n\n---\n\n'.join(content_parts)
                
        except Exception as e:
            logger.error(f"Error fetching content for topic {topic_id}: {e}")
        
        return ""
    
    def save_to_database(self, posts, db_path='tds_knowledge.db'):
        """Save posts to SQLite database"""
        try:
            with sqlite3.connect(db_path) as conn:
                cursor = conn.cursor()
                
                # Create table if not exists
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS discourse_posts (
                        id INTEGER PRIMARY KEY,
                        title TEXT,
                        url TEXT UNIQUE,
                        content TEXT,
                        created_at TEXT,
                        last_posted_at TEXT,
                        category_name TEXT,
                        posts_count INTEGER,
                        views INTEGER,
                        excerpt TEXT,
                        tags TEXT
                    )
                ''')
                
                # Insert posts
                for post in posts:
                    try:
                        cursor.execute('''
                            INSERT OR REPLACE INTO discourse_posts 
                            (id, title, url, content, created_at, last_posted_at, 
                             category_name, posts_count, views, excerpt, tags)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (
                            post.get('id'),
                            post.get('title', ''),
                            post.get('url', ''),
                            post.get('content', ''),
                            post.get('created_at', ''),
                            post.get('last_posted_at', ''),
                            post.get('category_name', ''),
                            post.get('posts_count', 0),
                            post.get('views', 0),
                            post.get('excerpt', ''),
                            json.dumps(post.get('tags', []))
                        ))
                    except Exception as e:
                        logger.error(f"Error inserting post {post.get('id')}: {e}")
                
                conn.commit()
                logger.info(f"Saved {len(posts)} posts to database")
                
        except Exception as e:
            logger.error(f"Error saving to database: {e}")

def main():
    parser = argparse.ArgumentParser(description='Scrape TDS Discourse posts')
    parser.add_argument('--start-date', required=True, help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end-date', required=True, help='End date (YYYY-MM-DD)')
    parser.add_argument('--output', default='tds_posts.json', help='Output JSON file')
    parser.add_argument('--database', default='tds_knowledge.db', help='SQLite database file')
    parser.add_argument('--base-url', default='https://discourse.onlinedegree.iitm.ac.in', 
                       help='Discourse base URL')
    
    args = parser.parse_args()
    
    scraper = DiscourseScraperTDS(base_url=args.base_url)
    
    # Scrape posts
    posts = scraper.scrape_discourse_posts(args.start_date, args.end_date, args.output)
    
    # Save to database
    if posts:
        scraper.save_to_database(posts, args.database)
        print(f"Successfully scraped {len(posts)} posts from {args.start_date} to {args.end_date}")
    else:
        print("No posts were scraped")

if __name__ == '__main__':
    main()