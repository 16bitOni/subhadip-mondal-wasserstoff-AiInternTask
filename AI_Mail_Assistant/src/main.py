#!/usr/bin/env python3
import os
import argparse
import logging
from dotenv import load_dotenv

from database import init_db
from controllers import EmailProcessor
from utils import setup_logging

# Load environment variables
load_dotenv()

# Configure logging
logger = setup_logging(__name__)

def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description='AI Email Assistant')
    parser.add_argument(
        '--mode', 
        type=str, 
        choices=['daemon', 'process-inbox', 'process-email'],
        default='daemon', 
        help='Operating mode (default: daemon)'
    )
    parser.add_argument(
        '--email-id', 
        type=str, 
        help='Process a specific email by ID (use with --mode=process-email)'
    )
    parser.add_argument(
        '--interval', 
        type=int, 
        default=int(os.getenv("EMAIL_FETCH_INTERVAL", "300")),
        help='Interval in seconds between email checks (default: from .env or 300)'
    )
    parser.add_argument(
        '--limit', 
        type=int, 
        default=int(os.getenv("EMAIL_LIMIT", "10")),
        help='Maximum number of emails to process in one batch (default: from .env or 10)'
    )
    
    return parser.parse_args()

def run_in_daemon_mode(interval: int, limit: int):
    """Run the application in daemon mode, processing emails periodically"""
    logger.info(f"Starting in daemon mode with interval={interval}s and limit={limit}")
    processor = EmailProcessor()
    processor.run_processing_loop(interval)

def process_inbox_once(limit: int):
    """Process the inbox once and exit"""
    logger.info(f"Processing inbox (one-time) with limit={limit}")
    processor = EmailProcessor()
    emails = processor.process_inbox(limit)
    logger.info(f"Processed {len(emails)} emails")
    
    return emails

def process_specific_email(email_id: str):
    """Process a specific email by ID"""
    if not email_id:
        logger.error("No email ID provided")
        return None
    
    logger.info(f"Processing specific email: {email_id}")
    processor = EmailProcessor()
    result = processor.process_specific_email(email_id)
    
    if result:
        logger.info(f"Successfully processed email {email_id}")
    else:
        logger.error(f"Failed to process email {email_id}")
    
    return result

def main():
    """Main entry point for the application"""
    try:
        # Parse command line arguments
        args = parse_args()
        
        # Initialize database
        logger.info("Initializing database...")
        init_db()
        
        # Run in the specified mode
        if args.mode == 'daemon':
            run_in_daemon_mode(args.interval, args.limit)
        elif args.mode == 'process-inbox':
            process_inbox_once(args.limit)
        elif args.mode == 'process-email':
            if not args.email_id:
                logger.error("Email ID is required for process-email mode")
                return
            process_specific_email(args.email_id)
        else:
            logger.error(f"Unknown mode: {args.mode}")
    
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received. Shutting down...")
    except Exception as e:
        logger.exception(f"Unhandled exception: {str(e)}")
        
if __name__ == "__main__":
    main()
