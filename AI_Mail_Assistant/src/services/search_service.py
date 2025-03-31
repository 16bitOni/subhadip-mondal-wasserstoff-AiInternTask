import os
import logging
import requests
import json
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv
from bs4 import BeautifulSoup

# Load environment variables
load_dotenv()

# Configure logging
logger = logging.getLogger(__name__)

# Web Search API configuration
GOOGLE_SEARCH_API_KEY = os.getenv("GOOGLE_SEARCH_API_KEY")
GOOGLE_SEARCH_ENGINE_ID = os.getenv("GOOGLE_SEARCH_ENGINE_ID")

class SearchService:
    """Service for performing web searches and fetching information"""
    
    def __init__(self, api_key: str = None, search_engine_id: str = None):
        self.api_key = api_key or GOOGLE_SEARCH_API_KEY
        self.search_engine_id = search_engine_id or GOOGLE_SEARCH_ENGINE_ID
        
        if not self.api_key or not self.search_engine_id:
            logger.warning("Google Search API credentials not provided. Web search will not function.")
    
    def google_search(self, query: str, num_results: int = 5) -> List[Dict[str, Any]]:
        """
        Perform a Google search via the Custom Search JSON API
        
        Args:
            query: Search query string
            num_results: Number of results to fetch (max 10)
            
        Returns:
            List[Dict[str, Any]]: List of search results
        """
        if not self.api_key or not self.search_engine_id:
            logger.error("Google Search API credentials not provided.")
            return []
        
        try:
            # Limit to 10 results max (API limitation for free tier)
            num_results = min(num_results, 10)
            
            # Build URL for the Custom Search JSON API
            url = f"https://www.googleapis.com/customsearch/v1"
            params = {
                'q': query,
                'key': self.api_key,
                'cx': self.search_engine_id,
                'num': num_results
            }
            
            # Make the request
            response = requests.get(url, params=params)
            response.raise_for_status()  # Raise an exception for HTTP errors
            
            # Parse the response
            search_results = response.json()
            
            # Extract relevant information from search results
            results = []
            if 'items' in search_results:
                for item in search_results['items']:
                    results.append({
                        'title': item.get('title', ''),
                        'link': item.get('link', ''),
                        'snippet': item.get('snippet', ''),
                        'source': 'Google Search'
                    })
            
            logger.info(f"Google search for '{query}' returned {len(results)} results")
            return results
            
        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP error during Google search: {str(e)}")
            return []
        except requests.exceptions.RequestException as e:
            logger.error(f"Request error during Google search: {str(e)}")
            return []
        except Exception as e:
            logger.error(f"Error during Google search: {str(e)}")
            return []
    
    def fallback_search(self, query: str, num_results: int = 5) -> List[Dict[str, Any]]:
        """
        Fallback search method using a public API that doesn't require authentication
        
        Args:
            query: Search query string
            num_results: Number of results to fetch
            
        Returns:
            List[Dict[str, Any]]: List of search results
        """
        try:
            # Use DuckDuckGo API (doesn't require authentication)
            encoded_query = requests.utils.quote(query)
            url = f"https://api.duckduckgo.com/?q={encoded_query}&format=json"
            
            response = requests.get(url)
            response.raise_for_status()
            
            data = response.json()
            
            results = []
            
            # Add the abstract if available
            if data.get('Abstract'):
                results.append({
                    'title': data.get('Heading', 'Information'),
                    'link': data.get('AbstractURL', ''),
                    'snippet': data.get('Abstract', ''),
                    'source': 'DuckDuckGo Abstract'
                })
            
            # Add related topics
            for topic in data.get('RelatedTopics', [])[:num_results]:
                if 'Text' in topic and 'FirstURL' in topic:
                    results.append({
                        'title': topic.get('Text', '').split(' - ')[0] if ' - ' in topic.get('Text', '') else topic.get('Text', ''),
                        'link': topic.get('FirstURL', ''),
                        'snippet': topic.get('Text', ''),
                        'source': 'DuckDuckGo'
                    })
            
            logger.info(f"Fallback search for '{query}' returned {len(results)} results")
            return results
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Request error during fallback search: {str(e)}")
            return []
        except Exception as e:
            logger.error(f"Error during fallback search: {str(e)}")
            return []
    
    def search(self, query: str, num_results: int = 5) -> List[Dict[str, Any]]:
        """
        Perform a web search, falling back to alternative methods if primary fails
        
        Args:
            query: Search query string
            num_results: Number of results to fetch
            
        Returns:
            List[Dict[str, Any]]: List of search results
        """
        # Try Google Search first if credentials are available
        if self.api_key and self.search_engine_id:
            results = self.google_search(query, num_results)
            if results:
                return results
        
        # Fall back to alternative search if Google fails or credentials missing
        return self.fallback_search(query, num_results)
    
    def fetch_webpage_content(self, url: str, max_length: int = 5000) -> Optional[str]:
        """
        Fetch and extract content from a webpage
        
        Args:
            url: URL of the webpage to fetch
            max_length: Maximum length of content to return
            
        Returns:
            Optional[str]: Extracted text content or None if failed
        """
        try:
            # Add user agent to avoid being blocked
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            
            # Fetch the page
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            
            # Parse the HTML
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Remove script and style elements
            for script in soup(['script', 'style']):
                script.extract()
            
            # Get the text
            text = soup.get_text(separator='\n')
            
            # Clean up the text
            lines = (line.strip() for line in text.splitlines())
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            text = '\n'.join(chunk for chunk in chunks if chunk)
            
            # Truncate if needed
            if len(text) > max_length:
                text = text[:max_length] + "..."
            
            logger.info(f"Successfully fetched content from {url}")
            return text
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Request error fetching {url}: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Error fetching {url}: {str(e)}")
            return None 