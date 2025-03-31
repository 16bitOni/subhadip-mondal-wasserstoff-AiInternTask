import os
import json
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta, time
import pytz
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logger = logging.getLogger(__name__)

# Calendar API configuration
CALENDAR_SCOPES = ['https://www.googleapis.com/auth/calendar']
CREDENTIALS_FILE = os.getenv('GMAIL_API_CREDENTIALS_FILE', 'config/credentials.json')
TOKEN_FILE = os.getenv('GMAIL_API_TOKEN_FILE', 'config/token.json')
CALENDAR_ID = os.getenv('CALENDAR_ID', 'primary')

class CalendarService:
    """Service for interacting with Google Calendar API"""
    
    def __init__(self, calendar_id: str = None):
        self.calendar_id = calendar_id or CALENDAR_ID
        self.creds = None
        self.service = None
    
    def authenticate(self) -> bool:
        """
        Authenticate with the Google Calendar API
        
        Returns:
            bool: True if authentication was successful, False otherwise
        """
        try:
            # Reuse credentials from Gmail API if possible
            if os.path.exists(TOKEN_FILE):
                self.creds = Credentials.from_authorized_user_info(
                    json.load(open(TOKEN_FILE)), CALENDAR_SCOPES
                )
            
            # If credentials don't exist or are invalid, fail
            # (we're assuming Gmail authentication happened first)
            if not self.creds or not self.creds.valid:
                if self.creds and self.creds.expired and self.creds.refresh_token:
                    self.creds.refresh(Request())
                else:
                    logger.error("Calendar authentication failed. No valid credentials.")
                    return False
            
            # Build the Calendar API service
            self.service = build('calendar', 'v3', credentials=self.creds)
            logger.info("Google Calendar API authentication successful")
            return True
            
        except Exception as e:
            logger.error(f"Error authenticating with Google Calendar API: {str(e)}")
            return False
    
    def list_upcoming_events(self, max_results: int = 10, time_min: datetime = None) -> List[Dict[str, Any]]:
        """
        List upcoming calendar events
        
        Args:
            max_results: Maximum number of events to fetch
            time_min: Start time (defaults to now)
            
        Returns:
            List[Dict[str, Any]]: List of upcoming events
        """
        if not self.service:
            if not self.authenticate():
                raise Exception("Failed to authenticate with Google Calendar API")
        
        try:
            # Set default time_min to now if not provided
            if time_min is None:
                time_min = datetime.utcnow()
            
            # Format time for API
            time_min_str = time_min.isoformat() + 'Z'  # 'Z' indicates UTC time
            
            # Call the Calendar API
            events_result = self.service.events().list(
                calendarId=self.calendar_id,
                timeMin=time_min_str,
                maxResults=max_results,
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            
            events = events_result.get('items', [])
            
            # Process events into a cleaner format
            processed_events = []
            for event in events:
                start = event['start'].get('dateTime', event['start'].get('date'))
                end = event['end'].get('dateTime', event['end'].get('date'))
                
                processed_events.append({
                    'id': event['id'],
                    'summary': event.get('summary', 'No Title'),
                    'description': event.get('description', ''),
                    'start': start,
                    'end': end,
                    'attendees': [attendee.get('email') for attendee in event.get('attendees', [])],
                    'location': event.get('location', ''),
                    'organizer': event.get('organizer', {}).get('email', 'Unknown'),
                    'link': event.get('htmlLink', '')
                })
            
            logger.info(f"Retrieved {len(processed_events)} upcoming events")
            return processed_events
            
        except HttpError as error:
            logger.error(f"Error retrieving calendar events: {str(error)}")
            return []
    
    def get_free_slots(
        self,
        start_date: datetime = None,
        end_date: datetime = None,
        working_hours: tuple = (9, 17),  # 9AM to 5PM
        duration_minutes: int = 30,
        time_zone: str = 'UTC'
    ) -> List[Dict[str, Any]]:
        """
        Find free time slots in calendar
        
        Args:
            start_date: Start date (defaults to today)
            end_date: End date (defaults to 7 days from start)
            working_hours: Tuple of (start_hour, end_hour) in 24h format
            duration_minutes: Minimum duration of free slot in minutes
            time_zone: Time zone to use
            
        Returns:
            List[Dict[str, Any]]: List of available time slots
        """
        if not self.service:
            if not self.authenticate():
                raise Exception("Failed to authenticate with Google Calendar API")
        
        try:
            # Set default dates if not provided
            if start_date is None:
                start_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            
            if end_date is None:
                end_date = start_date + timedelta(days=7)
            
            # Get timezone
            tz = pytz.timezone(time_zone)
            
            # Get busy periods from calendar
            body = {
                "timeMin": start_date.isoformat() + 'Z',
                "timeMax": end_date.isoformat() + 'Z',
                "items": [{"id": self.calendar_id}]
            }
            
            free_busy_request = self.service.freebusy().query(body=body).execute()
            busy_periods = free_busy_request['calendars'][self.calendar_id]['busy']
            
            # Convert busy periods to datetime objects
            busy_ranges = []
            for period in busy_periods:
                start = datetime.fromisoformat(period['start'].replace('Z', '+00:00'))
                end = datetime.fromisoformat(period['end'].replace('Z', '+00:00'))
                busy_ranges.append((start, end))
            
            # Generate available slots
            free_slots = []
            current_date = start_date
            
            while current_date < end_date:
                # Get working hours for this day
                work_start = tz.localize(
                    datetime.combine(current_date.date(), time(working_hours[0], 0))
                )
                work_end = tz.localize(
                    datetime.combine(current_date.date(), time(working_hours[1], 0))
                )
                
                # Convert to UTC for comparison
                work_start = work_start.astimezone(pytz.UTC)
                work_end = work_end.astimezone(pytz.UTC)
                
                # Skip if we're past working hours for today
                if datetime.now(pytz.UTC) > work_end:
                    current_date += timedelta(days=1)
                    continue
                
                # Start from current time if it's today and within working hours
                if current_date.date() == datetime.now().date():
                    if datetime.now(pytz.UTC) > work_start:
                        slot_start = datetime.now(pytz.UTC).replace(
                            minute=(datetime.now().minute // 30) * 30,
                            second=0,
                            microsecond=0
                        ) + timedelta(minutes=30)  # Start from next 30-min boundary
                    else:
                        slot_start = work_start
                else:
                    slot_start = work_start
                
                # Find free slots for this day
                while slot_start < work_end:
                    slot_end = slot_start + timedelta(minutes=duration_minutes)
                    
                    # Check if slot overlaps with any busy period
                    is_free = True
                    for busy_start, busy_end in busy_ranges:
                        if (slot_start < busy_end) and (slot_end > busy_start):
                            is_free = False
                            # Move slot_start to the end of this busy period
                            slot_start = busy_end
                            break
                    
                    # If slot is free, add it to results
                    if is_free:
                        # Convert to local time for output
                        local_start = slot_start.astimezone(tz)
                        local_end = slot_end.astimezone(tz)
                        
                        free_slots.append({
                            'start': local_start.isoformat(),
                            'end': local_end.isoformat(),
                            'duration_minutes': duration_minutes
                        })
                        
                        # Move to next slot
                        slot_start = slot_end
                    
                # Move to next day
                current_date += timedelta(days=1)
            
            logger.info(f"Found {len(free_slots)} free time slots")
            return free_slots
            
        except HttpError as error:
            logger.error(f"Error finding free time slots: {str(error)}")
            return []
    
    def create_event(
        self,
        summary: str,
        start_time: datetime,
        end_time: datetime,
        description: str = '',
        location: str = '',
        attendees: List[str] = None,
        send_notifications: bool = True
    ) -> Optional[Dict[str, Any]]:
        """
        Create a calendar event
        
        Args:
            summary: Event title
            start_time: Start time
            end_time: End time
            description: Event description (optional)
            location: Event location (optional)
            attendees: List of attendee email addresses (optional)
            send_notifications: Whether to send notifications to attendees
            
        Returns:
            Optional[Dict[str, Any]]: Created event data or None if failed
        """
        if not self.service:
            if not self.authenticate():
                raise Exception("Failed to authenticate with Google Calendar API")
        
        try:
            # Format attendees list
            formatted_attendees = None
            if attendees:
                formatted_attendees = [{'email': email} for email in attendees]
            
            # Create event body
            event_body = {
                'summary': summary,
                'description': description,
                'start': {
                    'dateTime': start_time.isoformat(),
                    'timeZone': start_time.tzinfo.zone if start_time.tzinfo else 'UTC',
                },
                'end': {
                    'dateTime': end_time.isoformat(),
                    'timeZone': end_time.tzinfo.zone if end_time.tzinfo else 'UTC',
                }
            }
            
            # Add optional fields
            if location:
                event_body['location'] = location
            
            if formatted_attendees:
                event_body['attendees'] = formatted_attendees
            
            # Create the event
            event = self.service.events().insert(
                calendarId=self.calendar_id,
                body=event_body,
                sendUpdates='all' if send_notifications else 'none'
            ).execute()
            
            logger.info(f"Calendar event created: {event.get('htmlLink')}")
            
            # Return processed event data
            return {
                'id': event['id'],
                'summary': event['summary'],
                'description': event.get('description', ''),
                'start': event['start']['dateTime'],
                'end': event['end']['dateTime'],
                'location': event.get('location', ''),
                'attendees': [attendee.get('email') for attendee in event.get('attendees', [])],
                'link': event.get('htmlLink', '')
            }
            
        except HttpError as error:
            logger.error(f"Error creating calendar event: {str(error)}")
            return None 