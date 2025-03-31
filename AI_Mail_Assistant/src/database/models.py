from sqlalchemy import Column, String, Integer, DateTime, Text, Boolean, ForeignKey, Table
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime

Base = declarative_base()

# Association table for email attachments
email_attachments = Table(
    'email_attachments',
    Base.metadata,
    Column('email_id', String, ForeignKey('emails.id')),
    Column('attachment_id', Integer, ForeignKey('attachments.id'))
)

class EmailThread(Base):
    """Model representing an email thread (conversation)"""
    __tablename__ = 'email_threads'
    
    id = Column(String, primary_key=True)
    subject = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    emails = relationship("Email", back_populates="thread")
    
    def __repr__(self):
        return f"<EmailThread(id='{self.id}', subject='{self.subject}')>"


class Email(Base):
    """Model representing an individual email"""
    __tablename__ = 'emails'
    
    id = Column(String, primary_key=True)
    thread_id = Column(String, ForeignKey('email_threads.id'))
    message_id = Column(String, nullable=True)
    sender = Column(String, nullable=False)
    recipients = Column(Text, nullable=False)  # Stored as JSON string
    cc = Column(Text, nullable=True)  # Stored as JSON string
    bcc = Column(Text, nullable=True)  # Stored as JSON string
    subject = Column(String, nullable=True)
    body_text = Column(Text, nullable=True)
    body_html = Column(Text, nullable=True)
    received_at = Column(DateTime, nullable=False)
    is_read = Column(Boolean, default=False)
    is_important = Column(Boolean, default=False)
    
    # Relationships
    thread = relationship("EmailThread", back_populates="emails")
    attachments = relationship("Attachment", secondary=email_attachments, back_populates="emails")
    actions = relationship("EmailAction", back_populates="email")
    
    def __repr__(self):
        return f"<Email(id='{self.id}', subject='{self.subject}', sender='{self.sender}')>"


class Attachment(Base):
    """Model representing an email attachment"""
    __tablename__ = 'attachments'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    filename = Column(String, nullable=False)
    content_type = Column(String, nullable=False)
    size = Column(Integer, nullable=False)
    content = Column(Text, nullable=True)  # For small attachments or references
    storage_path = Column(String, nullable=True)  # For file system storage
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    emails = relationship("Email", secondary=email_attachments, back_populates="attachments")
    
    def __repr__(self):
        return f"<Attachment(id={self.id}, filename='{self.filename}', type='{self.content_type}')>"


class EmailAction(Base):
    """Model representing actions taken on an email"""
    __tablename__ = 'email_actions'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    email_id = Column(String, ForeignKey('emails.id'))
    action_type = Column(String, nullable=False)  # e.g., 'reply', 'forward', 'calendar', 'slack'
    action_data = Column(Text, nullable=True)  # JSON data of the action
    performed_at = Column(DateTime, default=datetime.utcnow)
    is_success = Column(Boolean, default=True)
    error_message = Column(Text, nullable=True)
    
    # Relationships
    email = relationship("Email", back_populates="actions")
    
    def __repr__(self):
        return f"<EmailAction(id={self.id}, type='{self.action_type}', success={self.is_success})>"


class UserPreference(Base):
    """Model for storing user preferences"""
    __tablename__ = 'user_preferences'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    key = Column(String, nullable=False, unique=True)
    value = Column(Text, nullable=True)
    
    def __repr__(self):
        return f"<UserPreference(key='{self.key}', value='{self.value}')>" 