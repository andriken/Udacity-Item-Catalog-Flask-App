import sys
from sqlalchemy import String, Column, Integer, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy import create_engine
from flask import jsonify

Base = declarative_base()


class User(Base):
    __tablename__ = 'user'

    name = Column(String(), nullable=False)
    email = Column(String())
    picture = Column(String())
    id = Column(Integer, primary_key=True)
    category = relationship('Category', backref='user')
    categoryitems = relationship('CategoryItem', backref='user')


class Category(Base):
    __tablename__ = 'category'

    id = Column(Integer, primary_key=True)
    title = Column(String(), nullable=False, unique=True)
    categoryitems = relationship('CategoryItem', backref='category')
    user_id = Column(Integer, ForeignKey('user.id'))

    @property
    def serializeCategory(self):
        return {
            'id': self.id,
            'title': self.title
            }

    @property
    def serializeCatalog(self):
        return {
            'id': self.id,
            'title': self.title,
            'Items': [{
                'cat_id': i.category_id,
                'description': i.description,
                'id': i.id,
                'title': i.title
                } for i in self.categoryitems]
            }

    @property
    def serializeCategoryItems(self):
        items = []
        for item in self.categoryitems:
            items.append({
                'id': item.id,
                'title': item.title,
                'description': item.description,
                'cat_id': self.id
                })
        return items


class CategoryItem(Base):
    __tablename__ = 'category_item'

    id = Column(Integer, primary_key=True)
    title = Column(String(80), nullable=False)
    description = Column(String(250))
    category_id = Column(Integer, ForeignKey('category.id'))
    user_id = Column(Integer, ForeignKey('user.id'))

    @property
    def serializeCategoryItem(self):
        return {
            'id': self.id,
            'title': self.title,
            'description': self.description,
            'cat_id': self.id
            }


engine = create_engine('sqlite:///catalog.db')
Base.metadata.create_all(engine)
