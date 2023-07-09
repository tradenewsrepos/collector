from sqlalchemy import Column, Integer, Text, Boolean, Float, VARCHAR, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import declarative_base


Base = declarative_base()


class Feed(Base):
    __tablename__ = "newsfeedner_feed"

    id = Column("id", Integer, primary_key=True)
    url = Column("url",  VARCHAR(2048), nullable=False)
    name = Column("name",  VARCHAR(200), nullable=False)
    title = Column("title",  VARCHAR(300), nullable=False)
    last_fetched_at = Column(
        "last_fetched_at", DateTime(timezone=True), nullable=False)
    tags = Column("tags",  VARCHAR(256), nullable=False)
    used = Column("used", Boolean, nullable=False)
    parser_name = Column("parser_name", VARCHAR(50), nullable=False)
    available = Column("available", Boolean, nullable=False)
    comment = Column("comment", VARCHAR(128), nullable=False)


class Article(Base):
    __tablename__ = "newsfeedner_article"

    id = Column('id', Integer, primary_key=True)
    id_in_feed = Column("id_in_feed", VARCHAR(400), nullable=False)
    url = Column("url",  VARCHAR(2048), nullable=False)
    title = Column("title", Text, nullable=False)
    title_json = Column('title_json', JSONB, nullable=True)
    published_parsed = Column(
        "published_parsed", DateTime(timezone=True), nullable=False)
    is_entities_parsed = Column("is_entities_parsed", Boolean, nullable=False)
    feed_id = Column('feed_id', Integer,  nullable=False)
    is_text_parsed = Column("is_text_parsed", Boolean, nullable=False)
    text = Column("text", Text, nullable=True)
    sentiment = Column("sentiment", Float, nullable=True)

class ExcludedFilter(Base):
    __tablename__ = "excluded_filter" 
    
    id = Column('id', Integer, primary_key=True) 
    url = Column("url",  VARCHAR(2048), nullable=False)
    title = Column("title", Text, nullable=False) 
    published_parsed = Column(
        "published_parsed", DateTime(timezone=True), nullable=False) 
