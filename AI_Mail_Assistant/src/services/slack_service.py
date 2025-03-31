import os
import logging
from typing import Dict, Any, Optional
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logger = logging.getLogger(__name__)

# Slack configuration
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
SLACK_CHANNEL = os.getenv("SLACK_CHANNEL")

class SlackService:
    """Service for interacting with Slack API"""
    
    def __init__(self, bot_token: str = None, default_channel: str = None):
        self.bot_token = bot_token or SLACK_BOT_TOKEN
        self.default_channel = default_channel or SLACK_CHANNEL
        
        if not self.bot_token:
            logger.warning("No Slack bot token provided. Slack notifications will not function.")
            self.client = None
        else:
            self.client = WebClient(token=self.bot_token)
    
    def send_notification(
        self,
        message: str,
        channel: str = None,
        title: str = None,
        email_data: Dict[str, Any] = None,
        include_buttons: bool = False
    ) -> bool:
        """
        Send a notification message to Slack
        
        Args:
            message: Message text to send
            channel: Channel to send to (optional, falls back to default)
            title: Message title/header (optional)
            email_data: Email data to include in the message (optional)
            include_buttons: Whether to include action buttons (optional)
            
        Returns:
            bool: True if message was sent successfully, False otherwise
        """
        if not self.client:
            logger.error("Slack client not initialized. Cannot send notification.")
            return False
        
        try:
            # Determine the channel to post to
            target_channel = channel or self.default_channel
            
            if not target_channel:
                logger.error("No Slack channel specified. Cannot send notification.")
                return False
            
            # Create a basic text message if no other options
            if not title and not email_data and not include_buttons:
                response = self.client.chat_postMessage(
                    channel=target_channel,
                    text=message
                )
                logger.info(f"Slack notification sent to channel {target_channel}")
                return True
            
            # Otherwise, create a more complex message with blocks
            blocks = []
            
            # Add title if provided
            if title:
                blocks.append({
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": title,
                        "emoji": True
                    }
                })
            
            # Add message text
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": message
                }
            })
            
            # Add email details if provided
            if email_data:
                email_text = f"*From:* {email_data.get('sender', 'Unknown')}\n"
                email_text += f"*Subject:* {email_data.get('subject', 'No Subject')}\n"
                email_text += f"*Received:* {email_data.get('received_at', 'Unknown')}\n\n"
                
                # Truncate body text if too long
                body_text = email_data.get('body_text', '')
                if len(body_text) > 500:
                    body_text = body_text[:497] + "..."
                
                email_text += body_text
                
                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": email_text
                    }
                })
            
            # Add a divider
            blocks.append({
                "type": "divider"
            })
            
            # Add action buttons if requested
            if include_buttons:
                blocks.append({
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {
                                "type": "plain_text",
                                "text": "View Details",
                                "emoji": True
                            },
                            "value": email_data.get('id', 'unknown') if email_data else "view_details"
                        },
                        {
                            "type": "button",
                            "text": {
                                "type": "plain_text",
                                "text": "Mark Read",
                                "emoji": True
                            },
                            "value": email_data.get('id', 'unknown') if email_data else "mark_read"
                        }
                    ]
                })
            
            # Send the message with blocks
            response = self.client.chat_postMessage(
                channel=target_channel,
                text=message,  # Fallback text
                blocks=blocks
            )
            
            logger.info(f"Rich Slack notification sent to channel {target_channel}")
            return True
            
        except SlackApiError as e:
            logger.error(f"Error sending Slack notification: {str(e)}")
            return False
    
    def notify_about_email(self, email_data: Dict[str, Any], analysis: Dict[str, Any] = None) -> bool:
        """
        Send a notification about a specific email
        
        Args:
            email_data: Email data dictionary
            analysis: Email analysis from LLM (optional)
            
        Returns:
            bool: True if notification was sent successfully, False otherwise
        """
        if not self.client:
            logger.error("Slack client not initialized. Cannot send notification.")
            return False
        
        try:
            # Create the notification title
            title = "📧 New Email Notification"
            
            # Create the message text
            message = f"You've received an email from *{email_data.get('sender', 'Unknown')}*"
            
            # Add priority if available from analysis
            if analysis and 'priority' in analysis:
                priority = analysis.get('priority', 'medium')
                if priority.lower() == 'high':
                    title = "🔴 High Priority Email"
                    message += " (High Priority)"
                elif priority.lower() == 'low':
                    message += " (Low Priority)"
            
            # Add summary if available from analysis
            if analysis and 'summary' in analysis:
                message += f"\n\n*Summary:* {analysis['summary']}"
            
            # Add action items if available from analysis
            if analysis and 'action_items' in analysis and analysis['action_items']:
                message += "\n\n*Action Items:*"
                for item in analysis['action_items']:
                    message += f"\n• {item}"
            
            # Send the notification
            return self.send_notification(
                message=message,
                title=title,
                email_data=email_data,
                include_buttons=True
            )
            
        except Exception as e:
            logger.error(f"Error creating email notification: {str(e)}")
            return False 