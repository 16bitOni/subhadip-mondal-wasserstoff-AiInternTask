import os
import base64
import json
import logging
import re
import email
from typing import List, Dict, Any, Optional, Generator, Tuple
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logger = logging.getLogger(__name__)

# Gmail API configuration
SCOPES = ['https://www.googleapis.com/auth/gmail.modify']
CREDENTIALS_FILE = os.getenv('GMAIL_API_CREDENTIALS_FILE', 'config/credentials.json')
TOKEN_FILE = os.getenv('GMAIL_API_TOKEN_FILE', 'config/token.json')
EMAIL_LIMIT = int(os.getenv('EMAIL_LIMIT', '10'))

class GmailService:
    """Service for interacting with Gmail API"""
    
    def __init__(self):
        self.creds = None
        self.service = None
        self.user_id = 'me'
    
    def authenticate(self) -> bool:
        """
        Authenticate with the Gmail API
        
        Returns:
            bool: True if authentication was successful, False otherwise
        """
        try:
            # Check if token.json exists and is valid
            if os.path.exists(TOKEN_FILE):
                self.creds = Credentials.from_authorized_user_info(
                    json.load(open(TOKEN_FILE)), SCOPES
                )
            
            # If credentials don't exist or are invalid, refresh them
            if not self.creds or not self.creds.valid:
                if self.creds and self.creds.expired and self.creds.refresh_token:
                    self.creds.refresh(Request())
                else:
                    # Create a new OAuth flow
                    flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
                    self.creds = flow.run_local_server(port=0)
                
                # Save the credentials for the next run
                with open(TOKEN_FILE, 'w') as token:
                    token.write(self.creds.to_json())
            
            # Build the Gmail API service
            self.service = build('gmail', 'v1', credentials=self.creds)
            logger.info("Gmail API authentication successful")
            return True
            
        except Exception as e:
            logger.error(f"Error authenticating with Gmail API: {str(e)}")
            return False
    
    def get_emails(self, query: str = '', max_results: int = EMAIL_LIMIT) -> List[Dict[str, Any]]:
        """
        Get emails from the Gmail inbox
        
        Args:
            query: Gmail search query (default: '')
            max_results: Maximum number of emails to fetch (default: from env var)
            
        Returns:
            List[Dict[str, Any]]: List of email dictionaries
        """
        if not self.service:
            if not self.authenticate():
                raise Exception("Failed to authenticate with Gmail API")
        
        try:
            # Get list of message IDs
            results = self.service.users().messages().list(
                userId=self.user_id, q=query, maxResults=max_results
            ).execute()
            
            messages = results.get('messages', [])
            
            if not messages:
                logger.info("No emails found")
                return []
            
            # Get full message details for each ID
            emails = []
            for message in messages:
                email_data = self.get_email_by_id(message['id'])
                if email_data:
                    emails.append(email_data)
            
            return emails
            
        except HttpError as error:
            logger.error(f"Error retrieving emails: {str(error)}")
            return []
    
    def get_email_by_id(self, email_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a specific email by its ID
        
        Args:
            email_id: Gmail message ID
            
        Returns:
            Optional[Dict[str, Any]]: Email data dictionary or None if not found
        """
        if not self.service:
            if not self.authenticate():
                raise Exception("Failed to authenticate with Gmail API")
        
        try:
            # Get the full message
            message = self.service.users().messages().get(
                userId=self.user_id, id=email_id, format='full'
            ).execute()
            
            # Process the message
            headers = {header['name']: header['value'] for header in message['payload']['headers']}
            
            # Get thread ID
            thread_id = message.get('threadId', '')
            
            # Extract email metadata
            sender = headers.get('From', '')
            recipients = headers.get('To', '')
            cc = headers.get('Cc', '')
            bcc = headers.get('Bcc', '')
            subject = headers.get('Subject', '(No Subject)')
            message_id = headers.get('Message-ID', '')
            date_str = headers.get('Date', '')
            
            # Parse date
            try:
                # Try to parse the date from the email header
                # This is complex due to various date formats used in emails
                date_str = re.sub(r'\s+\(.*\)', '', date_str)  # Remove timezone name in parentheses
                date_formats = [
                    '%a, %d %b %Y %H:%M:%S %z',
                    '%d %b %Y %H:%M:%S %z',
                    '%a, %d %b %Y %H:%M:%S',
                    '%d %b %Y %H:%M:%S'
                ]
                
                received_at = None
                for fmt in date_formats:
                    try:
                        received_at = datetime.strptime(date_str, fmt)
                        break
                    except ValueError:
                        continue
                
                if not received_at:
                    received_at = datetime.utcnow()
            except Exception:
                received_at = datetime.utcnow()
            
            # Get email body
            body_text, body_html = self._get_email_body(message)
            
            # Get attachments
            attachments = self._get_email_attachments(message)
            
            # Construct email data dictionary
            email_data = {
                'id': email_id,
                'thread_id': thread_id,
                'message_id': message_id,
                'sender': sender,
                'recipients': [r.strip() for r in recipients.split(',')] if recipients else [],
                'cc': [r.strip() for r in cc.split(',')] if cc else [],
                'bcc': [r.strip() for r in bcc.split(',')] if bcc else [],
                'subject': subject,
                'body_text': body_text,
                'body_html': body_html,
                'received_at': received_at,
                'is_read': 'UNREAD' not in message.get('labelIds', []),
                'is_important': 'IMPORTANT' in message.get('labelIds', []),
                'attachments': attachments,
            }
            
            return email_data
            
        except HttpError as error:
            logger.error(f"Error retrieving email {email_id}: {str(error)}")
            return None
    
    def _get_email_body(self, message: Dict[str, Any]) -> Tuple[str, str]:
        """
        Extract plain text and HTML body from a Gmail message
        
        Args:
            message: Gmail message dictionary
            
        Returns:
            Tuple[str, str]: (plain_text_body, html_body)
        """
        body_text = ""
        body_html = ""
        
        def extract_body(part):
            nonlocal body_text, body_html
            
            if part.get('mimeType') == 'text/plain':
                data = part.get('body', {}).get('data', '')
                if data:
                    text = base64.urlsafe_b64decode(data).decode('utf-8', errors='replace')
                    body_text = text
            elif part.get('mimeType') == 'text/html':
                data = part.get('body', {}).get('data', '')
                if data:
                    html = base64.urlsafe_b64decode(data).decode('utf-8', errors='replace')
                    body_html = html
            
            # Check for nested parts (multipart messages)
            if 'parts' in part:
                for sub_part in part['parts']:
                    extract_body(sub_part)
        
        # Start with the message payload
        payload = message['payload']
        
        if 'parts' in payload:
            for part in payload['parts']:
                extract_body(part)
        else:
            # Handle single-part messages
            mimeType = payload.get('mimeType', '')
            if mimeType == 'text/plain':
                data = payload.get('body', {}).get('data', '')
                if data:
                    body_text = base64.urlsafe_b64decode(data).decode('utf-8', errors='replace')
            elif mimeType == 'text/html':
                data = payload.get('body', {}).get('data', '')
                if data:
                    body_html = base64.urlsafe_b64decode(data).decode('utf-8', errors='replace')
        
        return body_text, body_html
    
    def _get_email_attachments(self, message: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Extract attachments from a Gmail message
        
        Args:
            message: Gmail message dictionary
            
        Returns:
            List[Dict[str, Any]]: List of attachment dictionaries
        """
        attachments = []
        
        def extract_attachments(part):
            if 'filename' in part and part['filename']:
                # This part is an attachment
                attachment_id = part['body'].get('attachmentId')
                if attachment_id:
                    # Only process if it has an attachment ID
                    filename = part['filename']
                    mimeType = part.get('mimeType', 'application/octet-stream')
                    size = int(part['body'].get('size', 0))
                    
                    attachments.append({
                        'filename': filename,
                        'content_type': mimeType,
                        'size': size,
                        'attachment_id': attachment_id,
                    })
            
            # Check for nested parts
            if 'parts' in part:
                for sub_part in part['parts']:
                    extract_attachments(sub_part)
        
        # Start with the message payload
        payload = message['payload']
        
        if 'parts' in payload:
            for part in payload['parts']:
                extract_attachments(part)
        
        return attachments
    
    def get_attachment_content(self, email_id: str, attachment_id: str) -> Optional[bytes]:
        """
        Get the content of an attachment
        
        Args:
            email_id: Gmail message ID
            attachment_id: Attachment ID
            
        Returns:
            Optional[bytes]: Attachment binary content or None if not found
        """
        if not self.service:
            if not self.authenticate():
                raise Exception("Failed to authenticate with Gmail API")
        
        try:
            attachment = self.service.users().messages().attachments().get(
                userId=self.user_id, messageId=email_id, id=attachment_id
            ).execute()
            
            if 'data' in attachment:
                return base64.urlsafe_b64decode(attachment['data'])
            return None
            
        except HttpError as error:
            logger.error(f"Error retrieving attachment: {str(error)}")
            return None
    
    def send_email(
        self,
        to: List[str],
        subject: str,
        body: str,
        is_html: bool = False,
        cc: List[str] = None,
        bcc: List[str] = None,
        thread_id: str = None,
    ) -> Optional[str]:
        """
        Send an email using Gmail API
        
        Args:
            to: List of recipient email addresses
            subject: Email subject
            body: Email body
            is_html: Whether the body is HTML format
            cc: List of CC recipients
            bcc: List of BCC recipients
            thread_id: Thread ID to reply to (optional)
            
        Returns:
            Optional[str]: Message ID of the sent email or None if failed
        """
        if not self.service:
            if not self.authenticate():
                raise Exception("Failed to authenticate with Gmail API")
        
        try:
            # Create message
            message = MIMEMultipart()
            message['To'] = ', '.join(to)
            message['Subject'] = subject
            
            if cc:
                message['Cc'] = ', '.join(cc)
            if bcc:
                message['Bcc'] = ', '.join(bcc)
            
            # Add body
            if is_html:
                message.attach(MIMEText(body, 'html'))
            else:
                message.attach(MIMEText(body, 'plain'))
            
            # Encode message
            encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
            
            # Create the message body
            message_body = {'raw': encoded_message}
            
            # Add thread ID if provided
            if thread_id:
                message_body['threadId'] = thread_id
            
            # Send the message
            sent_message = self.service.users().messages().send(
                userId=self.user_id, body=message_body
            ).execute()
            
            logger.info(f"Email sent successfully: {sent_message['id']}")
            return sent_message['id']
            
        except HttpError as error:
            logger.error(f"Error sending email: {str(error)}")
            return None
    
    def reply_to_email(
        self,
        email_id: str,
        body: str,
        is_html: bool = False,
    ) -> Optional[str]:
        """
        Reply to an existing email
        
        Args:
            email_id: Gmail message ID to reply to
            body: Reply body
            is_html: Whether the body is HTML format
            
        Returns:
            Optional[str]: Message ID of the sent reply or None if failed
        """
        if not self.service:
            if not self.authenticate():
                raise Exception("Failed to authenticate with Gmail API")
        
        try:
            # Get the original message
            original = self.get_email_by_id(email_id)
            
            if not original:
                logger.error(f"Could not find original email {email_id} to reply to")
                return None
            
            # Extract necessary information
            to = [original['sender']]  # Reply to sender
            subject = original['subject']
            if not subject.startswith('Re:'):
                subject = f"Re: {subject}"
            
            # Get thread ID
            thread_id = original['thread_id']
            
            # Send the reply
            return self.send_email(
                to=to,
                subject=subject,
                body=body,
                is_html=is_html,
                thread_id=thread_id
            )
            
        except Exception as e:
            logger.error(f"Error replying to email: {str(e)}")
            return None
    
    def forward_email(
        self,
        email_id: str,
        to: List[str],
        additional_body: str = "",
        is_html: bool = False,
    ) -> Optional[str]:
        """
        Forward an existing email
        
        Args:
            email_id: Gmail message ID to forward
            to: List of recipient email addresses
            additional_body: Additional text to include
            is_html: Whether the additional body is HTML format
            
        Returns:
            Optional[str]: Message ID of the forwarded email or None if failed
        """
        if not self.service:
            if not self.authenticate():
                raise Exception("Failed to authenticate with Gmail API")
        
        try:
            # Get the original message
            original = self.get_email_by_id(email_id)
            
            if not original:
                logger.error(f"Could not find original email {email_id} to forward")
                return None
            
            # Extract necessary information
            subject = original['subject']
            if not subject.startswith('Fwd:'):
                subject = f"Fwd: {subject}"
            
            # Create forwarded message content
            forward_content = f"---------- Forwarded message ---------\n"
            forward_content += f"From: {original['sender']}\n"
            forward_content += f"Date: {original['received_at'].strftime('%a, %b %d, %Y at %I:%M %p')}\n"
            forward_content += f"Subject: {original['subject']}\n"
            forward_content += f"To: {', '.join(original['recipients'])}\n\n"
            
            if is_html:
                # For HTML, format accordingly
                forward_content = forward_content.replace('\n', '<br>')
            
            # Combine additional body and original content
            if additional_body:
                body = f"{additional_body}\n\n{forward_content}{original['body_text']}"
            else:
                body = f"{forward_content}{original['body_text']}"
            
            # Send the forwarded email
            return self.send_email(
                to=to,
                subject=subject,
                body=body,
                is_html=is_html
            )
            
        except Exception as e:
            logger.error(f"Error forwarding email: {str(e)}")
            return None
    
    def mark_as_read(self, email_id: str) -> bool:
        """
        Mark an email as read
        
        Args:
            email_id: Gmail message ID
            
        Returns:
            bool: True if successful, False otherwise
        """
        if not self.service:
            if not self.authenticate():
                raise Exception("Failed to authenticate with Gmail API")
        
        try:
            # Remove UNREAD label
            self.service.users().messages().modify(
                userId=self.user_id,
                id=email_id,
                body={'removeLabelIds': ['UNREAD']}
            ).execute()
            
            logger.info(f"Email {email_id} marked as read")
            return True
            
        except HttpError as error:
            logger.error(f"Error marking email as read: {str(error)}")
            return False
    
    def mark_as_important(self, email_id: str) -> bool:
        """
        Mark an email as important
        
        Args:
            email_id: Gmail message ID
            
        Returns:
            bool: True if successful, False otherwise
        """
        if not self.service:
            if not self.authenticate():
                raise Exception("Failed to authenticate with Gmail API")
        
        try:
            # Add IMPORTANT label
            self.service.users().messages().modify(
                userId=self.user_id,
                id=email_id,
                body={'addLabelIds': ['IMPORTANT']}
            ).execute()
            
            logger.info(f"Email {email_id} marked as important")
            return True
            
        except HttpError as error:
            logger.error(f"Error marking email as important: {str(error)}")
            return False 