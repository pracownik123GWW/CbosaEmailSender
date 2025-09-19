#!/usr/bin/env python3
"""
Moduł zarządzania bazą danych dla CBOSA Bot
Używa SQLAlchemy do komunikacji z PostgreSQL
"""

import os
import logging
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from sqlalchemy import BigInteger, create_engine, Column, String, Integer, DateTime, Boolean, JSON, Text, ForeignKey, Enum as SqlEnum
from sqlalchemy.orm import sessionmaker, Session, relationship, declarative_base, joinedload
from sqlalchemy.exc import IntegrityError

from models import DateRangeEnum, JudgementStatusEnum

Base = declarative_base()

class User(Base):
    """Model użytkownika subskrybującego newsletter"""
    __tablename__ = 'users'
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    email = Column(String(255), unique=True, nullable=False)
    first_name = Column(String(255))
    last_name = Column(String(255))
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=datetime.now(timezone.utc), onupdate=datetime.now(timezone.utc), nullable=False)
    
    # Relacje
    subscriptions = relationship("UserSubscription", back_populates="user")
    email_logs = relationship("EmailLog", back_populates="user")

class SearchConfiguration(Base):
    __tablename__ = 'search_configurations'

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    short_name = Column(String(255), unique=True, nullable=False)
    description = Column(Text)
    max_results = Column(Integer, default=50, nullable=False)
    date_range = Column(SqlEnum(DateRangeEnum, name="date_range_enum"), 
                        nullable=False, 
                        default=DateRangeEnum.YESTERDAY)
    config = Column(JSON, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=datetime.now(timezone.utc), onupdate=datetime.now(timezone.utc), nullable=False)

    # Relacje
    subscriptions = relationship("UserSubscription", back_populates="search_config")
    execution_logs = relationship("ExecutionLog", back_populates="search_config")
    
    @property
    def effective_from(self):
        return self.date_range.compute_range()[0]

    @property
    def effective_to(self):
        return self.date_range.compute_range()[1]

class UserSubscription(Base):
    """Model subskrypcji użytkownika do określonej konfiguracji wyszukiwania"""
    __tablename__ = 'user_subscriptions'
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    search_config_id = Column(BigInteger, ForeignKey('search_configurations.id', ondelete='CASCADE'), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.now(timezone.utc), nullable=False)
    
    # Relacje
    user = relationship("User", back_populates="subscriptions")
    search_config = relationship("SearchConfiguration", back_populates="subscriptions")

class ExecutionLog(Base):
    """Model logu wykonania bota"""
    __tablename__ = 'execution_logs'
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    search_config_id = Column(BigInteger, ForeignKey('search_configurations.id', ondelete='CASCADE'), nullable=False)
    status = Column(String(50), nullable=False)
    started_at = Column(DateTime, default=datetime.now(timezone.utc), nullable=False)
    completed_at = Column(DateTime)
    cases_found = Column(Integer)
    cases_analyzed = Column(Integer)
    emails_sent = Column(Integer)
    error_message = Column(Text)
    execution_details = Column(JSON)
    
    # Relacje
    search_config = relationship("SearchConfiguration", back_populates="execution_logs")
    email_logs = relationship("EmailLog", back_populates="execution_log")

class EmailLog(Base):
    """Model logu wysłanych emaili"""
    __tablename__ = 'email_logs'
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    execution_log_id = Column(BigInteger, ForeignKey('execution_logs.id', ondelete='CASCADE'), nullable=False)
    user_id = Column(BigInteger, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    email = Column(String(255), nullable=False)
    status = Column(String(50), nullable=False)  # 'sent', 'failed', 'bounced'
    brevo_message_id = Column(String(255))
    sent_at = Column(DateTime, default=datetime.now(timezone.utc), nullable=False)
    error_message = Column(Text)
    
    # Relacje
    execution_log = relationship("ExecutionLog", back_populates="email_logs")
    user = relationship("User", back_populates="email_logs")

class PendingJudgment(Base):
    __tablename__ = "pending_judgments"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    signature = Column(String(255), nullable=False, unique=True)
    url = Column(String(500), nullable=False)
    search_config_id = Column(BigInteger, ForeignKey("search_configurations.id"), nullable=False)
    found_date = Column(DateTime, default=datetime.now(timezone.utc), nullable=False)
    last_checked = Column(DateTime)
    status = Column(
        SqlEnum(JudgementStatusEnum, name="judgment_status_enum"),
        nullable=False,
        server_default=JudgementStatusEnum.NO_JUSTIFICATION.value
    )

class DatabaseManager:
    """Menedżer bazy danych"""
    
    def __init__(self):
        self.database_url = os.getenv('DATABASE_URL')
        if not self.database_url:
            raise ValueError("DATABASE_URL nie jest ustawione")
        
        self.engine = create_engine(
            self.database_url,
            pool_pre_ping=True,        # ping przed użyciem połączenia – usuwa „stale connections”
            pool_recycle=1800,         # recykling co 30 min (ustaw < idle-timeout po stronie serwera)
            pool_size=5,
            max_overflow=10,
            connect_args={
                "sslmode": "require",      # jeśli Twój dostawca wymaga SSL
                "keepalives": 1,           # TCP keepalive (psycopg2)
                "keepalives_idle": 30,
                "keepalives_interval": 10,
                "keepalives_count": 3,
            }
        )
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        self.logger = logging.getLogger(__name__)
        
    def init_database(self):
        """Zainicjalizuj tabele bazy danych"""
        try:
            Base.metadata.create_all(bind=self.engine)
            self.logger.info("✅ Tabele bazy danych zostały zainicjalizowane")
        except Exception as e:
            self.logger.error(f"❌ Błąd podczas inicjalizacji bazy danych: {e}")
            raise
    
    def get_session(self) -> Session:
        """Uzyskaj sesję bazy danych"""
        return self.SessionLocal()
    
    # Metody dla użytkowników
    def get_user(self, user_id: int) -> Optional[User]:
        """Pobierz użytkownika po ID"""
        with self.get_session() as session:
            return session.query(User).filter(User.id == user_id).first()
    
    def get_user_by_email(self, email: str) -> Optional[User]:
        """Pobierz użytkownika po emailu"""
        with self.get_session() as session:
            return session.query(User).filter(User.email == email).first()
    
    def create_user(self, email: str, first_name: str, last_name: str) -> User:
        with self.get_session() as session:
            user = User(email=email, first_name=first_name, last_name=last_name)
            session.add(user)
            session.commit()
            session.refresh(user)
            return user
    
    def get_all_active_users(self) -> List[User]:
        """Pobierz wszystkich aktywnych użytkowników"""
        with self.get_session() as session:
            return session.query(User).filter(User.is_active.is_(True)).all()
    
    # Metody dla konfiguracji wyszukiwania
    def get_search_configuration(self, config_id: int) -> Optional[SearchConfiguration]:
        """Pobierz konfigurację wyszukiwania po ID"""
        with self.get_session() as session:
            return session.query(SearchConfiguration).filter(SearchConfiguration.id == config_id).first()
    
    def get_all_active_search_configurations(self) -> List[SearchConfiguration]:
        """Pobierz wszystkie aktywne konfiguracje wyszukiwania"""
        with self.get_session() as session:
            return session.query(SearchConfiguration).filter(SearchConfiguration.is_active).all()
    
    def get_all_active_subscriptions(self):
        with self.get_session() as session:
            return (
                session.query(UserSubscription)
                .options(
                    joinedload(UserSubscription.user),
                    joinedload(UserSubscription.search_config)
                )
                .filter(UserSubscription.is_active)
                .all()
            )
    
    def create_search_configuration(
    self,
    short_name: str,
    description: str,
    config: Dict[str, Any],
    max_results: int = 50,
    date_range: DateRangeEnum = DateRangeEnum.YESTERDAY
    ) -> SearchConfiguration:
        with self.get_session() as session:
            config_obj = SearchConfiguration(
                short_name=short_name,
                description=description,
                config=config,
                max_results=max_results,
                date_range=date_range
            )
            session.add(config_obj)
            session.commit()
            session.refresh(config_obj)
            return config_obj
    
    # Metody dla subskrypcji
    def get_user_subscriptions(self, user_id: int) -> List[UserSubscription]:
        """Pobierz subskrypcje użytkownika"""
        with self.get_session() as session:
            return session.query(UserSubscription).filter(
                UserSubscription.user_id == user_id,
                UserSubscription.is_active.is_(True)
            ).all()
    
    def get_subscriptions_for_config(self, search_config_id: int) -> List[UserSubscription]:
        """Pobierz subskrypcje dla określonej konfiguracji"""
        with self.get_session() as session:
            return session.query(UserSubscription).filter(
                UserSubscription.search_config_id == search_config_id,
                UserSubscription.is_active.is_(True)
            ).all()
    
    def create_user_subscription(self, user_id: int, search_config_id: int) -> UserSubscription:
        """Utwórz nową subskrypcję"""
        with self.get_session() as session:
            subscription = UserSubscription(
                user_id=user_id,
                search_config_id=search_config_id
            )
            session.add(subscription)
            session.commit()
            session.refresh(subscription)
            return subscription
    
    # Metody dla logów wykonania
    def create_execution_log(self, search_config_id: int, status: str = 'started') -> ExecutionLog:
        """Utwórz nowy log wykonania"""
        with self.get_session() as session:
            log = ExecutionLog(
                search_config_id=search_config_id,
                status=status
            )
            session.add(log)
            session.commit()
            session.refresh(log)
            return log
    
    def update_execution_log(self, log_id: int, **updates) -> Optional[ExecutionLog]:
        """Zaktualizuj log wykonania"""
        with self.get_session() as session:
            log = session.query(ExecutionLog).filter(ExecutionLog.id == log_id).first()
            if log:
                for key, value in updates.items():
                    setattr(log, key, value)
                session.commit()
                session.refresh(log)
            return log
    
    def get_recent_execution_logs(self, limit: int = 10) -> List[ExecutionLog]:
        """Pobierz najnowsze logi wykonania"""
        with self.get_session() as session:
            return session.query(ExecutionLog).order_by(ExecutionLog.started_at.desc()).limit(limit).all()
    
    # Metody dla logów emaili
    def create_email_log(self, execution_log_id: int, user_id: int, email: str, status: str, 
                        brevo_message_id: Optional[str] = None, error_message: Optional[str] = None) -> EmailLog:
        """Utwórz nowy log emaila"""
        with self.get_session() as session:
            log = EmailLog(
                execution_log_id=execution_log_id,
                user_id=user_id,
                email=email,
                status=status,
                brevo_message_id=brevo_message_id,
                error_message=error_message
            )
            session.add(log)
            session.commit()
            session.refresh(log)
            return log
    
    def get_email_logs_for_execution(self, execution_log_id: int) -> List[EmailLog]:
        """Pobierz logi emaili dla określonego wykonania"""
        with self.get_session() as session:
            return session.query(EmailLog).filter(EmailLog.execution_log_id == execution_log_id).all()
    
    def get_pending_for_config(self, search_config_id: int) -> List[PendingJudgment]:
        """Zwraca pendingi NO_JUSTIFICATION dla danej konfiguracji."""
        with self.get_session() as session:
            return (
                session.query(PendingJudgment)
                .filter(
                    PendingJudgment.search_config_id == search_config_id,
                    PendingJudgment.status == JudgementStatusEnum.NO_JUSTIFICATION.value,
                )
                .order_by(PendingJudgment.found_date.asc())
                .all()
            )
        
    def mark_pending_as_processed(self, pending_id: int) -> Optional[PendingJudgment]:
        """Ustawia status PROCESSED i last_checked=now."""
        with self.get_session() as session:
            pj = session.query(PendingJudgment).filter(PendingJudgment.id == pending_id).first()
            if not pj:
                return None
            pj.status = JudgementStatusEnum.PROCESSED.value
            pj.last_checked = datetime.now(timezone.utc)
            session.commit()
            session.refresh(pj)
            return pj
        
    def pending_signature_exists(self, signature: str) -> bool:
        """Szybkie sprawdzenie, czy sygnatura już jest w pending_judgments."""
        with self.get_session() as session:
            return session.query(PendingJudgment.id)\
                .filter(PendingJudgment.signature == signature)\
                .first() is not None
    
    def add_pending_judgment(
        self,
        *,
        signature: str,
        url: str,
        search_config_id: int,
        status: JudgementStatusEnum = JudgementStatusEnum.NO_JUSTIFICATION.value,
        found_date: Optional[datetime] = None,
    ) -> PendingJudgment:
        """
        Prosty INSERT (bez upsertu).
        Jeśli w bazie jest UNIQUE na 'signature' i trafi się duplikat — poleci IntegrityError.
        """
        with self.get_session() as session:
            pj = PendingJudgment(
                signature=signature,
                url=url,
                search_config_id=search_config_id,
                status=status,
                found_date=found_date or datetime.now(timezone.utc),
            )
            session.add(pj)
            try:
                session.commit()
            except IntegrityError as e:
                session.rollback()
                raise ValueError(f"Sygnatura już istnieje: {signature}") from e

            session.refresh(pj)
            return pj
    
    def touch_pending_no_justification(self, pending_id: int) -> Optional[PendingJudgment]:
        """Ustawia status NO_JUSTIFICATION (pozostaje taki sam) i aktualizuje last_checked=now."""
        with self.get_session() as session:
            pj = session.query(PendingJudgment).filter(PendingJudgment.id == pending_id).first()
            if not pj:
                return None
            pj.status = JudgementStatusEnum.NO_JUSTIFICATION.value
            pj.last_checked = datetime.now(timezone.utc)
            session.commit()
            session.refresh(pj)
            return pj