from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, Text, DateTime, ForeignKey
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class Company(Base):
    __tablename__ = 'companies'

    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键ID')
    name = Column(String(256), nullable=False, index=True, comment='公司名称')
    basic_info = Column(Text, default='', comment='公司基本信息')
    intro = Column(Text, default='', comment='公司介绍')
    business_registration = Column(Text, default='', comment='工商信息')
    created_at = Column(DateTime, default=datetime.utcnow, comment='创建时间')
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment='更新时间')

    jobs = relationship('Job', back_populates='company')


class Job(Base):
    __tablename__ = 'jobs'

    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键ID')
    title = Column(String(256), nullable=False, index=True, comment='岗位名称')
    company_id = Column(Integer, ForeignKey('companies.id'), comment='关联公司ID')
    company_name = Column(String(256), default='', index=True, comment='公司名称（冗余字段，方便直接查看）')

    salary_raw = Column(String(64), default='', comment='原始薪资（如 15k-25k*15薪 / 面议 / 300-500/天）')
    salary_type = Column(String(16), default='', comment='薪资类型：月薪/日薪/时薪/面议')

    experience_raw = Column(String(32), default='', comment='经验要求')
    education_raw = Column(String(16), default='', comment='学历要求')

    description = Column(Text, default='', comment='岗位描述')
    location_raw = Column(String(128), default='', comment='工作地点')
    benefits = Column(Text, default='', comment='福利待遇')

    url = Column(String(512), nullable=False, unique=True, comment='岗位详情页URL')
    hr_name = Column(String(64), default='', comment='HR姓名')
    created_at = Column(DateTime, default=datetime.utcnow, comment='创建时间')
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment='更新时间')

    company = relationship('Company', back_populates='jobs')
