import os
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from storage.models import Base, Company, Job
from storage.cleaner import clean_salary


def get_db_url():
    return os.environ.get('DATABASE_URL', 'sqlite:///jobs.db')


def get_engine():
    return create_engine(get_db_url(), echo=False)


def init_db():
    engine = get_engine()
    Base.metadata.create_all(engine)
    return engine


def get_session(engine=None):
    if engine is None:
        engine = get_engine()
    return Session(engine)


def get_or_create_company(session, name: str, basic_info='', intro='', business_registration='') -> Company:
    if not name:
        return None
    company = session.query(Company).filter(Company.name == name).first()
    if company:
        if basic_info and len(basic_info) > len(company.basic_info or ''):
            company.basic_info = basic_info
        if intro and len(intro) > len(company.intro or ''):
            company.intro = intro
        if business_registration and len(business_registration) > len(company.business_registration or ''):
            company.business_registration = business_registration
        return company
    company = Company(
        name=name, basic_info=basic_info or '',
        intro=intro or '', business_registration=business_registration or ''
    )
    session.add(company)
    session.flush()
    return company


def insert_job(session, job_data: dict, keyword: str = ''):
    url = job_data.get('网址', '')
    if not url:
        return None

    existing = session.query(Job).filter(Job.url == url).first()
    if existing:
        return None

    company_name = job_data.get('公司名称', '')
    company = get_or_create_company(
        session,
        name=company_name,
        basic_info=job_data.get('公司基本信息', ''),
        intro=job_data.get('公司介绍', ''),
        business_registration=job_data.get('工商信息', ''),
    )

    salary_type = clean_salary(job_data.get('薪资', '')).get('type', '')

    job = Job(
        title=job_data.get('岗位名称', ''),
        company_id=company.id if company else None,
        company_name=company_name,
        keyword=keyword,
        salary=job_data.get('薪资', ''),
        salary_type=salary_type,
        experience=job_data.get('经验', ''),
        education=job_data.get('学历', ''),
        description=job_data.get('岗位描述', ''),
        location=job_data.get('工作地点', ''),
        benefits=job_data.get('福利', ''),
        hr_name=job_data.get('HR', ''),
        url=url,
    )
    session.add(job)
    session.flush()
    return job
