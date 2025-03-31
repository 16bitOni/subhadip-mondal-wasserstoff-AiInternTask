import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import QueuePool
from typing import Generator
import logging
from dotenv import load_dotenv

from .models import Base

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Database configuration
DB_TYPE = os.getenv("DB_TYPE", "sqlite")
DB_NAME = os.getenv("DB_NAME", "email_assistant.db")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "postgres")

def get_connection_string() -> str:
    """Get the database connection string based on configuration"""
    if DB_TYPE.lower() == "sqlite":
        # SQLite connection string
        return f"sqlite:///{DB_NAME}"
    elif DB_TYPE.lower() == "postgres":
        # PostgreSQL connection string
        return f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    else:
        raise ValueError(f"Unsupported database type: {DB_TYPE}")

def get_engine():
    """Create and return a SQLAlchemy engine"""
    connection_string = get_connection_string()
    
    logger.info(f"Connecting to database: {connection_string.split('@')[-1] if '@' in connection_string else connection_string}")
    
    if DB_TYPE.lower() == "sqlite":
        # SQLite specific configuration
        engine = create_engine(
            connection_string,
            connect_args={"check_same_thread": False},
        )
    else:
        # PostgreSQL configuration with connection pooling
        engine = create_engine(
            connection_string,
            poolclass=QueuePool,
            pool_size=5,
            max_overflow=10,
            pool_timeout=30,
            pool_recycle=1800,  # Recycle connections after 30 minutes
        )
    
    return engine

def create_tables():
    """Create all tables defined in models.py"""
    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables created successfully")

def get_session() -> Generator[Session, None, None]:
    """Get a database session"""
    engine = get_engine()
    session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = session_local()
    try:
        yield db
    finally:
        db.close()

def init_db():
    """Initialize the database, creating tables if they don't exist"""
    try:
        create_tables()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize database: {str(e)}")
        raise 