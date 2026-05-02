from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, Text, DateTime, ForeignKey
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class Company(Base):
    __tablename__ = 'companies'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(256), nullable=False, index=True)
    basic_info = Column(Text, default='')
    intro = Column(Text, default='')
    business_registration = Column(Text, default='')
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    jobs = relationship('Job', back_populates='company')


class Job(Base):
    __tablename__ = 'jobs'

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(256), nullable=False, index=True)
    company_id = Column(Integer, ForeignKey('companies.id'))
    company_name = Column(String(256), default='', index=True)

    salary_raw = Column(String(64), default='')
    salary_min = Column(Float, nullable=True)
    salary_max = Column(Float, nullable=True)
    salary_type = Column(String(16), default='')
    salary_periods = Column(Integer, nullable=True)

    experience_raw = Column(String(32), default='')
    experience_normalized = Column(String(16), default='')
    education_raw = Column(String(16), default='')
    education_normalized = Column(String(16), default='')

    description = Column(Text, default='')
    location_raw = Column(String(128), default='')
    province = Column(String(32), default='')
    city = Column(String(32), default='')
    district = Column(String(32), default='')
    benefits = Column(Text, default='')

    url = Column(String(512), nullable=False, unique=True)
    hr_name = Column(String(64), default='')
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    company = relationship('Company', back_populates='jobs')
