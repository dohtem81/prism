from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from services.worker.app.infra.settings import settings

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)