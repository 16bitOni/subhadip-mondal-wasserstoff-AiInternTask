import os
import json
import logging
from typing import List, Dict, Any, Optional, Union
from dotenv import load_dotenv
import openai
from openai.types.chat import ChatCompletionSystemMessageParam
from openai.types.chat import ChatCompletionUserMessageParam
from openai.types.chat import ChatCompletionAssistantMessageParam

# Import langchain components for more complex workflows
from langchain.callbacks.manager import CallbackManager
from langchain.callbacks.streaming_stdout import StreamingStdOutCallbackHandler
from langchain.chains import LLMChain
from langchain.prompts import PromptTemplate
from langchain_openai import ChatOpenAI

# Load environment variables
load_dotenv()

# Configure logging
logger = logging.getLogger(__name__)

# LLM configuration
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-3.5-turbo")

class LLMService:
    """Service for interacting with language models"""
    
    def __init__(self, api_key: str = None, model_name: str = None):
        self.api_key = api_key or OPENAI_API_KEY
        self.model_name = model_name or LLM_MODEL
        
        if not self.api_key:
            logger.warning("No OpenAI API key provided. LLM service will not function properly.")
        
        # Initialize OpenAI client
        self.client = openai.OpenAI(api_key=self.api_key)
        
        # Initialize LangChain components for complex workflows
        callback_manager = CallbackManager([StreamingStdOutCallbackHandler()])
        self.langchain_llm = ChatOpenAI(
            model_name=self.model_name,
            temperature=0.7,
            openai_api_key=self.api_key,
            streaming=False,
            verbose=False,
        )
    
    def understand_email(self, email_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Understand the context and intent of an email using LLM
        
        Args:
            email_data: Dictionary containing email data
            
        Returns:
            Dict[str, Any]: Analysis of the email
        """
        try:
            # Construct a rich prompt for the LLM
            system_prompt = """
            You are an AI assistant that helps analyze emails to understand their context and intent.
            Based on the email information, provide a structured analysis including:
            1. A brief summary of what the email is about (2-3 sentences)
            2. The main intent or purpose of the email (e.g., request, information, scheduling, etc.)
            3. Any key questions or requests that need to be addressed
            4. Any time-sensitive information or deadlines mentioned
            5. Sentiment (positive, neutral, negative)
            6. Priority level (high, medium, low)
            7. Whether this email requires a response
            8. Whether this email is part of an ongoing conversation and needs context from previous emails
            9. Whether web search might be needed to properly respond to this email
            10. Whether calendar actions might be needed (scheduling, etc.)
            
            Your analysis should be provided in a structured JSON format.
            """
            
            # Prepare email content for analysis
            email_content = f"""
            From: {email_data.get('sender', '')}
            To: {', '.join(email_data.get('recipients', []))}
            Subject: {email_data.get('subject', '')}
            Date: {email_data.get('received_at', '')}
            
            {email_data.get('body_text', '')}
            """
            
            # Create message list for the API call
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": email_content}
            ]
            
            # Call the OpenAI API
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                temperature=0.3,  # Lower temperature for more deterministic responses
                max_tokens=800,   # Limit response size
                response_format={"type": "json_object"}  # Request JSON format
            )
            
            # Extract the assistant's message
            result = response.choices[0].message.content
            
            # Parse the JSON response
            analysis = json.loads(result)
            
            logger.info(f"Email analysis completed for '{email_data.get('subject', '')[:30]}...'")
            return analysis
            
        except Exception as e:
            logger.error(f"Error analyzing email: {str(e)}")
            # Return a minimal analysis in case of error
            return {
                "summary": "Error analyzing this email.",
                "intent": "unknown",
                "questions": [],
                "time_sensitive": False,
                "sentiment": "neutral",
                "priority": "medium",
                "requires_response": True,
                "needs_context": False,
                "needs_web_search": False,
                "needs_calendar": False,
                "error": str(e)
            }
    
    def generate_reply(
        self,
        email_data: Dict[str, Any],
        email_analysis: Dict[str, Any],
        email_thread: List[Dict[str, Any]] = None,
        web_search_results: List[Dict[str, Any]] = None,
        calendar_info: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Generate an email reply based on the email content and additional context
        
        Args:
            email_data: Dictionary containing the email data
            email_analysis: Analysis of the email from understand_email
            email_thread: List of previous emails in the thread (optional)
            web_search_results: Results from web search (optional)
            calendar_info: Calendar availability information (optional)
            
        Returns:
            Dict[str, Any]: Generated reply content and metadata
        """
        try:
            # Construct system prompt
            system_prompt = """
            You are an AI email assistant that drafts helpful, professional, and concise email replies.
            Your task is to generate a complete email reply based on the original email and any additional context provided.
            Your reply should:
            1. Be professional and maintain an appropriate tone
            2. Address all questions or requests from the original email
            3. Include any relevant information from the provided context (web search, calendar, etc.)
            4. Be concise and to the point
            5. Use appropriate email formatting
            6. End with an appropriate sign-off
            
            Provide your response as a JSON object with the following fields:
            - "subject": The subject line for the reply
            - "body": The full body of the email
            - "should_send": Boolean indicating if this reply can be automatically sent or needs human review
            - "follow_up_tasks": List of any follow-up tasks that may be needed
            """
            
            # Prepare email content
            email_content = f"""
            ORIGINAL EMAIL:
            From: {email_data.get('sender', '')}
            Subject: {email_data.get('subject', '')}
            Body:
            {email_data.get('body_text', '')}
            
            EMAIL ANALYSIS:
            {json.dumps(email_analysis, indent=2)}
            """
            
            # Add thread context if available
            if email_thread and len(email_thread) > 0:
                thread_content = "PREVIOUS EMAILS IN THREAD:\n"
                for i, prev_email in enumerate(email_thread):
                    thread_content += f"\nEmail {i+1}:\n"
                    thread_content += f"From: {prev_email.get('sender', '')}\n"
                    thread_content += f"Date: {prev_email.get('received_at', '')}\n"
                    thread_content += f"Subject: {prev_email.get('subject', '')}\n"
                    thread_content += f"Body:\n{prev_email.get('body_text', '')[:500]}...\n"
                
                email_content += f"\n\n{thread_content}"
            
            # Add web search results if available
            if web_search_results and len(web_search_results) > 0:
                web_content = "WEB SEARCH RESULTS:\n"
                for i, result in enumerate(web_search_results):
                    web_content += f"\nResult {i+1}:\n"
                    web_content += f"Title: {result.get('title', '')}\n"
                    web_content += f"URL: {result.get('url', '')}\n"
                    web_content += f"Snippet: {result.get('snippet', '')}\n"
                
                email_content += f"\n\n{web_content}"
            
            # Add calendar info if available
            if calendar_info:
                calendar_content = "CALENDAR INFORMATION:\n"
                calendar_content += f"Available time slots: {calendar_info.get('available_slots', [])}\n"
                calendar_content += f"Existing meetings: {calendar_info.get('existing_meetings', [])}\n"
                
                email_content += f"\n\n{calendar_content}"
            
            # Create message list for the API call
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": email_content}
            ]
            
            # Call the OpenAI API
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                temperature=0.7,  # Higher temperature for more creative responses
                max_tokens=1000,  # Allow longer responses for email bodies
                response_format={"type": "json_object"}  # Request JSON format
            )
            
            # Extract the assistant's message
            result = response.choices[0].message.content
            
            # Parse the JSON response
            reply_data = json.loads(result)
            
            logger.info(f"Email reply generated for '{email_data.get('subject', '')[:30]}...'")
            return reply_data
            
        except Exception as e:
            logger.error(f"Error generating email reply: {str(e)}")
            # Return a minimal reply in case of error
            return {
                "subject": f"Re: {email_data.get('subject', '')}",
                "body": "I'll get back to you soon regarding your email.",
                "should_send": False,
                "follow_up_tasks": ["Review email manually due to error in generation"],
                "error": str(e)
            }
    
    def extract_action_items(self, email_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract action items and tasks from an email
        
        Args:
            email_data: Dictionary containing email data
            
        Returns:
            Dict[str, Any]: Dictionary of action items and their details
        """
        try:
            system_prompt = """
            You are an AI assistant that helps extract action items and tasks from emails.
            Look for explicit requests, implied tasks, deadlines, and commitments in the email.
            
            Provide your extraction as a JSON object with the following structure:
            {
              "action_items": [
                {
                  "description": "Brief description of the action item",
                  "deadline": "YYYY-MM-DD" or null if no deadline,
                  "priority": "high/medium/low",
                  "assignee": "Person assigned to the task or 'me' if assigned to recipient",
                  "requires_response": true/false,
                  "status": "pending"
                },
                ...
              ],
              "calendar_items": [
                {
                  "type": "meeting/deadline/reminder",
                  "description": "Description of the calendar item",
                  "date": "YYYY-MM-DD",
                  "time": "HH:MM" or null,
                  "duration_minutes": 30/60/etc. or null,
                  "participants": ["person1@example.com", "person2@example.com"]
                },
                ...
              ]
            }
            
            If no action items or calendar items are found, return empty arrays.
            """
            
            # Prepare email content
            email_content = f"""
            From: {email_data.get('sender', '')}
            To: {', '.join(email_data.get('recipients', []))}
            Subject: {email_data.get('subject', '')}
            Date: {email_data.get('received_at', '')}
            
            {email_data.get('body_text', '')}
            """
            
            # Create message list for the API call
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": email_content}
            ]
            
            # Call the OpenAI API
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                temperature=0.3,  # Lower temperature for more deterministic responses
                max_tokens=800,   # Limit response size
                response_format={"type": "json_object"}  # Request JSON format
            )
            
            # Extract the assistant's message
            result = response.choices[0].message.content
            
            # Parse the JSON response
            extracted_items = json.loads(result)
            
            logger.info(f"Action items extracted from email '{email_data.get('subject', '')[:30]}...'")
            return extracted_items
            
        except Exception as e:
            logger.error(f"Error extracting action items: {str(e)}")
            return {
                "action_items": [],
                "calendar_items": [],
                "error": str(e)
            }
    
    def detect_calendar_events(self, email_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Detect calendar events mentioned in an email
        
        Args:
            email_data: Dictionary containing email data
            
        Returns:
            List[Dict[str, Any]]: List of detected calendar events
        """
        try:
            system_prompt = """
            You are an AI assistant specialized in detecting calendar events in emails.
            Your task is to identify any mentions of meetings, appointments, calls, or deadlines with dates and times.
            Parse the email to extract these details and format them as structured calendar events.
            
            For each event, provide:
            1. Event type (meeting, deadline, etc.)
            2. Event description or title
            3. Date (in YYYY-MM-DD format)
            4. Start time (in HH:MM format, 24-hour)
            5. End time or duration (if available)
            6. Location or meeting link (if available)
            7. Participants (if mentioned)
            8. Any additional notes
            
            Provide your response as a JSON array of event objects.
            If no events are detected, return an empty array.
            """
            
            # Prepare email content
            email_content = f"""
            From: {email_data.get('sender', '')}
            To: {', '.join(email_data.get('recipients', []))}
            Subject: {email_data.get('subject', '')}
            Date: {email_data.get('received_at', '')}
            
            {email_data.get('body_text', '')}
            """
            
            # Create message list for the API call
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": email_content}
            ]
            
            # Call the OpenAI API
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                temperature=0.3,  # Lower temperature for more deterministic responses
                max_tokens=800,   # Limit response size
                response_format={"type": "json_object"}  # Request JSON format
            )
            
            # Extract the assistant's message
            result = response.choices[0].message.content
            
            # Parse the JSON response
            calendar_events = json.loads(result)
            
            # Ensure we return a list
            if isinstance(calendar_events, dict) and 'events' in calendar_events:
                calendar_events = calendar_events['events']
            elif not isinstance(calendar_events, list):
                calendar_events = []
            
            logger.info(f"Calendar events detected in email '{email_data.get('subject', '')[:30]}...'")
            return calendar_events
            
        except Exception as e:
            logger.error(f"Error detecting calendar events: {str(e)}")
            return [] 