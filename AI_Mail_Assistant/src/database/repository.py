import json
import logging
from typing import List, Dict, Any, Optional, Union
from sqlalchemy.orm import Session
from datetime import datetime

from .models import Email, EmailThread, Attachment, EmailAction, UserPreference

# Configure logging
logger = logging.getLogger(__name__)

class EmailRepository:
    """Repository for handling email database operations"""
    
    @staticmethod
    def save_email(
        db: Session,
        email_id: str,
        message_id: str,
        thread_id: str,
        sender: str,
        recipients: List[str],
        subject: str,
        body_text: str,
        body_html: str = None,
        cc: List[str] = None,
        bcc: List[str] = None,
        received_at: datetime = None,
        is_read: bool = False,
        is_important: bool = False,
        attachments: List[Dict[str, Any]] = None,
    ) -> Email:
        """
        Save an email to the database
        
        Args:
            db: Database session
            email_id: Unique identifier for the email
            message_id: Email message ID header
            thread_id: Thread ID for conversation grouping
            sender: Email sender
            recipients: List of recipient email addresses
            subject: Email subject
            body_text: Plain text email body
            body_html: HTML email body (optional)
            cc: List of CC recipients (optional)
            bcc: List of BCC recipients (optional)
            received_at: When the email was received (optional, defaults to now)
            is_read: Whether the email has been read (optional)
            is_important: Whether the email is marked as important (optional)
            attachments: List of attachment dictionaries (optional)
            
        Returns:
            Email: The created or updated Email object
        """
        try:
            # Check if the thread exists, if not create it
            thread = db.query(EmailThread).filter(EmailThread.id == thread_id).first()
            if not thread:
                thread = EmailThread(
                    id=thread_id,
                    subject=subject,
                    created_at=received_at or datetime.utcnow(),
                    updated_at=received_at or datetime.utcnow(),
                )
                db.add(thread)
                db.flush()
            else:
                # Update thread's updated_at timestamp
                thread.updated_at = received_at or datetime.utcnow()
                
            # Check if the email already exists
            email = db.query(Email).filter(Email.id == email_id).first()
            
            if not email:
                # Create a new email
                email = Email(
                    id=email_id,
                    thread_id=thread_id,
                    message_id=message_id,
                    sender=sender,
                    recipients=json.dumps(recipients),
                    cc=json.dumps(cc) if cc else None,
                    bcc=json.dumps(bcc) if bcc else None,
                    subject=subject,
                    body_text=body_text,
                    body_html=body_html,
                    received_at=received_at or datetime.utcnow(),
                    is_read=is_read,
                    is_important=is_important,
                )
                db.add(email)
                db.flush()
                
                # Process attachments if any
                if attachments:
                    for attachment_data in attachments:
                        attachment = Attachment(
                            filename=attachment_data.get('filename'),
                            content_type=attachment_data.get('content_type'),
                            size=attachment_data.get('size', 0),
                            content=attachment_data.get('content'),
                            storage_path=attachment_data.get('storage_path'),
                        )
                        db.add(attachment)
                        db.flush()
                        
                        # Associate attachment with email
                        email.attachments.append(attachment)
                
                db.commit()
                logger.info(f"Email saved successfully: {email_id}")
                return email
            else:
                # Email already exists, just update it
                email.is_read = is_read
                email.is_important = is_important
                db.commit()
                logger.info(f"Email updated successfully: {email_id}")
                return email
                
        except Exception as e:
            db.rollback()
            logger.error(f"Error saving email: {str(e)}")
            raise
    
    @staticmethod
    def get_email_by_id(db: Session, email_id: str) -> Optional[Email]:
        """Get an email by its ID"""
        return db.query(Email).filter(Email.id == email_id).first()
    
    @staticmethod
    def get_emails_by_thread(db: Session, thread_id: str) -> List[Email]:
        """Get all emails in a thread, ordered by received_at"""
        return db.query(Email).filter(Email.thread_id == thread_id).order_by(Email.received_at).all()
    
    @staticmethod
    def get_recent_emails(db: Session, limit: int = 50, offset: int = 0) -> List[Email]:
        """Get recent emails ordered by received_at"""
        return db.query(Email).order_by(Email.received_at.desc()).offset(offset).limit(limit).all()
    
    @staticmethod
    def save_email_action(
        db: Session,
        email_id: str,
        action_type: str,
        action_data: Dict[str, Any] = None,
        is_success: bool = True,
        error_message: str = None,
    ) -> EmailAction:
        """
        Save an action performed on an email
        
        Args:
            db: Database session
            email_id: Email ID the action was performed on
            action_type: Type of action (reply, forward, calendar, slack)
            action_data: JSON-serializable data about the action
            is_success: Whether the action was successful
            error_message: Error message if the action failed
            
        Returns:
            EmailAction: The created EmailAction object
        """
        try:
            action = EmailAction(
                email_id=email_id,
                action_type=action_type,
                action_data=json.dumps(action_data) if action_data else None,
                is_success=is_success,
                error_message=error_message,
            )
            db.add(action)
            db.commit()
            logger.info(f"Email action saved: {action_type} for email {email_id}")
            return action
        except Exception as e:
            db.rollback()
            logger.error(f"Error saving email action: {str(e)}")
            raise
    
    @staticmethod
    def get_email_actions(db: Session, email_id: str) -> List[EmailAction]:
        """Get all actions performed on an email"""
        return db.query(EmailAction).filter(EmailAction.email_id == email_id).order_by(EmailAction.performed_at).all()
    
    @staticmethod
    def mark_email_as_read(db: Session, email_id: str) -> bool:
        """Mark an email as read"""
        try:
            email = db.query(Email).filter(Email.id == email_id).first()
            if email:
                email.is_read = True
                db.commit()
                logger.info(f"Email marked as read: {email_id}")
                return True
            return False
        except Exception as e:
            db.rollback()
            logger.error(f"Error marking email as read: {str(e)}")
            return False
    
    @staticmethod
    def mark_email_as_important(db: Session, email_id: str, important: bool = True) -> bool:
        """Mark an email as important/not important"""
        try:
            email = db.query(Email).filter(Email.id == email_id).first()
            if email:
                email.is_important = important
                db.commit()
                logger.info(f"Email marked as {'important' if important else 'not important'}: {email_id}")
                return True
            return False
        except Exception as e:
            db.rollback()
            logger.error(f"Error marking email importance: {str(e)}")
            return False


class UserPreferenceRepository:
    """Repository for handling user preferences"""
    
    @staticmethod
    def set_preference(db: Session, key: str, value: Union[str, int, float, bool, dict, list]) -> UserPreference:
        """Set a user preference"""
        try:
            # Convert non-string values to JSON
            if not isinstance(value, str):
                value = json.dumps(value)
                
            preference = db.query(UserPreference).filter(UserPreference.key == key).first()
            if preference:
                preference.value = value
            else:
                preference = UserPreference(key=key, value=value)
                db.add(preference)
                
            db.commit()
            logger.info(f"User preference set: {key}")
            return preference
        except Exception as e:
            db.rollback()
            logger.error(f"Error setting user preference: {str(e)}")
            raise
    
    @staticmethod
    def get_preference(db: Session, key: str, default=None) -> Any:
        """Get a user preference"""
        try:
            preference = db.query(UserPreference).filter(UserPreference.key == key).first()
            if not preference:
                return default
                
            value = preference.value
            
            # Try to parse JSON
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return value
        except Exception as e:
            logger.error(f"Error getting user preference: {str(e)}")
            return default