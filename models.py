# models.py
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

db = SQLAlchemy()

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))
    role = db.Column(db.String(20), nullable=False)  
    skills = db.Column(db.String(100))
    image_url = db.Column(db.String(255), nullable=True)
    mobile = db.Column(db.String(20))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)
    work_platform = db.Column(db.String(50))
    is_admin = db.Column(db.Boolean, default=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.username,
            "email": self.email,
            "role": self.role,
            "skills": self.skills,
            "image_url": self.image_url,
            "mobile": self.mobile,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "work_platform": self.work_platform,
            "is_admin": self.is_admin,
        }

class Rating(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey('task.id'), nullable=False)
    rater_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)  # who gave the rating
    ratee_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)  # who received the rating
    score = db.Column(db.Integer, nullable=False)  # 1 to 5
    comment = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    task = db.relationship('Task', backref=db.backref('ratings', lazy=True))
    rater = db.relationship('User', foreign_keys=[rater_id])
    ratee = db.relationship('User', foreign_keys=[ratee_id])

    def to_dict(self):
        return {
            "id": self.id,
            "task_id": self.task_id,
            "rater_id": self.rater_id,
            "ratee_id": self.ratee_id,
            "rater_name": self.rater.username if self.rater else None,
            "ratee_name": self.ratee.username if self.ratee else None,
            "score": self.score,
            "comment": self.comment,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }

class Quote(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey('task.id'), nullable=False)
    helper_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    charges = db.Column(db.Float, nullable=False)
    hours = db.Column(db.Float, nullable=False)
    mobile = db.Column(db.String(20), nullable=False)
    status = db.Column(db.String(20), default="pending")  # pending, accepted, declined
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    task = db.relationship('Task', backref=db.backref('quotes', lazy=True))
    helper = db.relationship('User', foreign_keys=[helper_id])

    def to_dict(self):
        return {
            "id": self.id,
            "task_id": self.task_id,
            "helper_id": self.helper_id,
            "helper_name": self.helper.username if self.helper else None,
            "charges": self.charges,
            "hours": self.hours,
            "mobile": self.mobile,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }

class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    message = db.Column(db.String(255), nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref=db.backref('notifications', lazy=True))

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "message": self.message,
            "is_read": self.is_read,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }

class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(50), nullable=False)
    reward = db.Column(db.String(100))
    status = db.Column(db.String(20), default="open")  # open → quoted → accepted → completed
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    poster_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    helper_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    charges = db.Column(db.Float)  # Set after quote acceptance
    hours = db.Column(db.Float)    # Set after quote acceptance
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)
    image_url = db.Column(db.String(255))

    def to_dict(self):
        result = {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "category": self.category,
            "reward": self.reward,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "status": self.status,
            "poster_id": self.poster_id,
            "helper_id": self.helper_id,
            "charges": self.charges,
            "hours": self.hours,
            "image_url": self.image_url,
        }
        
        result["quotes"] = [q.to_dict() for q in self.quotes]
        result["ratings"] = [r.to_dict() for r in self.ratings]
    
        return result
