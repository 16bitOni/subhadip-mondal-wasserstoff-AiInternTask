import os
import logging
import json
from typing import List, Dict, Any, Optional, Generator
from datetime import datetime, timedelta
import time
from dotenv import load_dotenv

from ..database import get_session, EmailRepository, UserPreferenceRepository
from ..services import GmailService, LLMService, SlackService, CalendarService, SearchService

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Email processing configuration
EMAIL_FETCH_INTERVAL = int(os.getenv("EMAIL_FETCH_INTERVAL", "300"))  # In seconds
EMAIL_LIMIT = int(os.getenv("EMAIL_LIMIT", "10"))
AUTO_REPLY_ENABLED = os.getenv("AUTO_REPLY_ENABLED", "false").lower() == "true"
AUTO_FORWARD_ENABLED = os.getenv("AUTO_FORWARD_ENABLED", "false").lower() == "true"

class EmailProcessor:
    """Controller for processing emails with AI assistance"""
    
    def __init__(self):
        # Initialize services
        self.gmail_service = GmailService()
        self.llm_service = LLMService()
        self.slack_service = SlackService()
        self.calendar_service = CalendarService()
        self.search_service = SearchService()
        
        # Authenticate with Gmail
        if not self.gmail_service.authenticate():
            raise Exception("Failed to authenticate with Gmail API")
        
        logger.info("Email Processor initialized successfully")
    
    def process_inbox(self, limit: int = EMAIL_LIMIT) -> List[Dict[str, Any]]:
        """
        Process emails from the inbox
        
        Args:
            limit: Maximum number of emails to process
            
        Returns:
            List[Dict[str, Any]]: List of processed email data
        """
        # Get recent emails
        query = "is:unread"  # Process unread emails
        emails = self.gmail_service.get_emails(query=query, max_results=limit)
        
        if not emails:
            logger.info("No new emails to process")
            return []
        
        processed_emails = []
        
        # Process each email
        for email_data in emails:
            try:
                # Process email
                processed_data = self.process_email(email_data)
                processed_emails.append(processed_data)
                
                # Mark as read in Gmail
                self.gmail_service.mark_as_read(email_data['id'])
                
            except Exception as e:
                logger.error(f"Error processing email {email_data.get('id', '')}: {str(e)}")
        
        return processed_emails
    
    def process_email(self, email_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process a single email
        
        Args:
            email_data: Email data dictionary
            
        Returns:
            Dict[str, Any]: Processed email data with analysis and actions
        """
        try:
            # Get database session
            db = next(get_session())
            
            # Save email to database
            EmailRepository.save_email(
                db=db,
                email_id=email_data['id'],
                message_id=email_data['message_id'],
                thread_id=email_data['thread_id'],
                sender=email_data['sender'],
                recipients=email_data['recipients'],
                subject=email_data['subject'],
                body_text=email_data['body_text'],
                body_html=email_data['body_html'],
                cc=email_data['cc'],
                bcc=email_data['bcc'],
                received_at=email_data['received_at'],
                is_read=False,
                is_important=email_data['is_important'],
                attachments=[
                    {
                        'filename': attachment['filename'],
                        'content_type': attachment['content_type'],
                        'size': attachment['size'],
                    } for attachment in email_data.get('attachments', [])
                ]
            )
            
            # Analyze email with LLM
            analysis = self.llm_service.understand_email(email_data)
            
            # Handle high priority emails
            if analysis.get('priority', '').lower() == 'high':
                logger.info(f"High priority email detected: {email_data['subject']}")
                
                # Send notification to Slack for high priority
                self.slack_service.notify_about_email(email_data, analysis)
                
                # Mark as important in Gmail
                self.gmail_service.mark_as_important(email_data['id'])
                
                # Mark as important in database
                EmailRepository.mark_email_as_important(db, email_data['id'], True)
            
            # Extract action items and calendar events
            action_items = self.llm_service.extract_action_items(email_data)
            calendar_events = self.llm_service.detect_calendar_events(email_data)
            
            # Check if we need to gather additional info to respond
            web_search_results = None
            if analysis.get('needs_web_search', False):
                # Generate search query based on email content
                search_query = f"email question: {email_data['subject']} {analysis.get('questions', [''])[0]}"
                web_search_results = self.search_service.search(search_query, num_results=3)
            
            # Check if we need to get calendar information
            calendar_info = None
            if analysis.get('needs_calendar', False) or calendar_events:
                # Get calendar information for next week
                upcoming_events = self.calendar_service.list_upcoming_events(max_results=5)
                free_slots = self.calendar_service.get_free_slots(
                    duration_minutes=30,
                    time_zone='UTC'  # Use appropriate time zone
                )
                
                calendar_info = {
                    'existing_meetings': upcoming_events,
                    'available_slots': free_slots
                }
            
            # Get thread context if needed
            email_thread = None
            if analysis.get('needs_context', False):
                # Get other emails in the same thread
                email_thread = EmailRepository.get_emails_by_thread(db, email_data['thread_id'])
            
            # Generate reply if needed
            reply_data = None
            if analysis.get('requires_response', False):
                reply_data = self.llm_service.generate_reply(
                    email_data,
                    analysis,
                    email_thread,
                    web_search_results,
                    calendar_info
                )
                
                # Auto-reply if enabled and LLM indicates it's safe to auto-send
                if AUTO_REPLY_ENABLED and reply_data.get('should_send', False):
                    reply_id = self.gmail_service.reply_to_email(
                        email_id=email_data['id'],
                        body=reply_data['body'],
                        is_html=False
                    )
                    
                    if reply_id:
                        logger.info(f"Auto-replied to email: {email_data['subject']}")
                        
                        # Save action to database
                        EmailRepository.save_email_action(
                            db=db,
                            email_id=email_data['id'],
                            action_type='reply',
                            action_data={
                                'reply_id': reply_id,
                                'subject': reply_data['subject'],
                                'auto_sent': True
                            },
                            is_success=True
                        )
            
            # Create calendar events if needed and calendar has events
            if calendar_events and len(calendar_events) > 0:
                for event in calendar_events:
                    try:
                        # Check if event has required fields
                        if 'type' in event and event['type'].lower() == 'meeting' and 'date' in event:
                            # Convert date and time strings to datetime
                            event_date = datetime.fromisoformat(event['date']) if '-' in event['date'] else None
                            
                            if event_date:
                                start_time = None
                                end_time = None
                                
                                # Parse time if available
                                if 'start_time' in event:
                                    hours, minutes = map(int, event['start_time'].split(':'))
                                    start_time = event_date.replace(hour=hours, minute=minutes)
                                    
                                    # Calculate end time based on duration
                                    duration = event.get('duration_minutes', 60)
                                    end_time = start_time + timedelta(minutes=duration)
                                
                                if start_time and end_time:
                                    # Create event
                                    self.calendar_service.create_event(
                                        summary=event.get('description', 'Meeting'),
                                        start_time=start_time,
                                        end_time=end_time,
                                        description=event.get('description', ''),
                                        location=event.get('location', ''),
                                        attendees=event.get('participants', []),
                                        send_notifications=True
                                    )
                                    
                                    logger.info(f"Created calendar event: {event.get('description', 'Meeting')}")
                                    
                                    # Save action to database
                                    EmailRepository.save_email_action(
                                        db=db,
                                        email_id=email_data['id'],
                                        action_type='calendar',
                                        action_data=event,
                                        is_success=True
                                    )
                    except Exception as e:
                        logger.error(f"Error creating calendar event: {str(e)}")
            
            # Combine all data for return
            processed_data = {
                'email': email_data,
                'analysis': analysis,
                'action_items': action_items,
                'calendar_events': calendar_events,
                'web_search_results': web_search_results,
                'reply': reply_data
            }
            
            return processed_data
            
        except Exception as e:
            logger.error(f"Error processing email: {str(e)}")
            return {
                'email': email_data,
                'error': str(e)
            }
    
    def run_processing_loop(self, interval: int = EMAIL_FETCH_INTERVAL) -> None:
        """
        Run email processing in a loop at specified intervals
        
        Args:
            interval: Time between processing runs in seconds
        """
        logger.info(f"Starting email processing loop with interval of {interval} seconds")
        
        while True:
            try:
                logger.info("Processing emails...")
                processed_emails = self.process_inbox()
                
                logger.info(f"Processed {len(processed_emails)} emails")
                
                # Sleep until next processing interval
                logger.info(f"Sleeping for {interval} seconds...")
                time.sleep(interval)
                
            except KeyboardInterrupt:
                logger.info("Keyboard interrupt received. Stopping loop.")
                break
            except Exception as e:
                logger.error(f"Error in processing loop: {str(e)}")
                # Sleep before retrying to avoid rapid error loops
                time.sleep(10)
    
    def process_specific_email(self, email_id: str) -> Optional[Dict[str, Any]]:
        """
        Process a specific email by ID
        
        Args:
            email_id: Gmail message ID
            
        Returns:
            Optional[Dict[str, Any]]: Processed email data or None if not found
        """
        try:
            # Get the email
            email_data = self.gmail_service.get_email_by_id(email_id)
            
            if not email_data:
                logger.error(f"Email not found: {email_id}")
                return None
            
            # Process it
            return self.process_email(email_data)
            
        except Exception as e:
            logger.error(f"Error processing specific email {email_id}: {str(e)}")
            return None 