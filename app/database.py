"""
MetaForge Database Module — SQLite + SQLAlchemy

Provides persistent storage for:
- Users (registration, login, profiles)
- Projects (meta-analysis projects with studies data)
- API Usage tracking (quota management)
- Sessions (JWT token management)
"""

import os
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Float, Boolean, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "metaforge.db")

engine = create_engine(f"sqlite:///{DB_PATH}", echo=False, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(120), unique=True, nullable=False, index=True)
    password_hash = Column(String(128), nullable=False)
    plan = Column(String(20), default="free")  # free, starter, professional, enterprise
    api_calls_today = Column(Integer, default=0)
    api_calls_limit = Column(Integer, default=50)  # Free: 50/day
    projects_limit = Column(Integer, default=3)     # Free: 3 projects
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login = Column(DateTime, nullable=True)

    projects = relationship("Project", back_populates="owner", cascade="all, delete-orphan")
    usage_records = relationship("APIUsage", back_populates="user", cascade="all, delete-orphan")


class Project(Base):
    __tablename__ = "projects"

    id = Column(String(36), primary_key=True)  # UUID
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String(200), nullable=False)
    studies_json = Column(Text, nullable=False)  # JSON string of studies data
    settings_json = Column(Text, default="{}")   # JSON string of settings
    result_json = Column(Text, nullable=True)     # Cached analysis results
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    owner = relationship("User", back_populates="projects")


class APIUsage(Base):
    __tablename__ = "api_usage"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    endpoint = Column(String(100), nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)
    response_ms = Column(Float, default=0.0)

    user = relationship("User", back_populates="usage_records")


class ShareToken(Base):
    __tablename__ = "share_tokens"

    id = Column(Integer, primary_key=True, autoincrement=True)
    token = Column(String(36), unique=True, nullable=False, index=True)
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=True)
    view_count = Column(Integer, default=0)


def init_db():
    """Create all tables."""
    Base.metadata.create_all(bind=engine)


def get_db():
    """Get a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Plan limits configuration
PLAN_LIMITS = {
    "free": {
        "api_calls_per_day": 50,
        "projects": 3,
        "max_studies_per_project": 10,
        "export_formats": ["csv"],
    },
    "starter": {
        "api_calls_per_day": 500,
        "projects": 20,
        "max_studies_per_project": 50,
        "export_formats": ["csv", "json"],
    },
    "professional": {
        "api_calls_per_day": 5000,
        "projects": 100,
        "max_studies_per_project": 500,
        "export_formats": ["csv", "json", "pdf"],
    },
    "enterprise": {
        "api_calls_per_day": -1,  # Unlimited
        "projects": -1,
        "max_studies_per_project": -1,
        "export_formats": ["csv", "json", "pdf"],
    },
}
