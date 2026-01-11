# app.py
from flask import Flask, request, jsonify
from models import Notification, db, User, Task, Quote, Rating
from functools import wraps
import jwt
import datetime
import os
from flask_cors import CORS
from math import radians, sin, cos, sqrt, atan2
from werkzeug.utils import secure_filename
from flask import send_from_directory
from sqlalchemy.orm import joinedload

app = Flask(__name__)
CORS(app, origins="*")

# Add this after CORS(app, origins="*")
@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Headers', 
                         'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 
                         'GET,PUT,POST,DELETE,OPTIONS')
    return response

basedir = os.path.abspath(os.path.dirname(__file__))

instance_path = os.path.join(basedir, "instance")
os.makedirs(instance_path, exist_ok=True)  # ✅ ensure folder exists

db_path = os.path.join(instance_path, "wave.db")

app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{db_path}"

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'wave-secret-key-for-dev-only'

db.init_app(app)

UPLOAD_FOLDER = os.path.join(basedir, 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB max

# Create uploads folder if not exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def create_tables():
    with app.app_context():
        db.create_all()
        print("✅ Tables created!")

create_tables()

# Add this helper function at the top (after imports)
def create_notification(user_id, message):
    from models import Notification  # Avoid circular import
    notif = Notification(user_id=user_id, message=message)
    db.session.add(notif)

def haversine_distance(lat1, lon1, lat2, lon2):
    R = 6371.0
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * atan2(sqrt(a), sqrt(1-a))
    return R * c

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        auth_header = request.headers.get('Authorization')
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]
        if not token:
            return jsonify({"error": "Token is missing!"}), 401
        try:
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=["HS256"])
            current_user_id = data['user_id']
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "Token has expired!"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"error": "Token is invalid!"}), 401
        return f(current_user_id, *args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(current_user_id, *args, **kwargs):
        user = User.query.get(current_user_id)
        if not user or not user.is_admin:
            return jsonify({"error": "Admin only"}), 403
        return f(current_user_id, *args, **kwargs)
    return decorated

@app.route('/')
def hello():
    return "Wave Backend is live! ✅"

# Serve uploaded images
@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# === AUTH ROUTES ===
@app.route('/api/auth/register', methods=['POST'])
def register():
    data = request.get_json()
    required_fields = ['username', 'email', 'password', 'role']
    if not all(field in data for field in required_fields):
        return jsonify({"error": "Username, email, password, and role are required"}), 400

    if data['role'] not in ['user', 'seeker']:
        return jsonify({"error": "Role must be 'user' or 'seeker'"}), 400

    if User.query.filter_by(email=data['email']).first():
        return jsonify({"error": "Email already registered"}), 400
    if User.query.filter_by(username=data['username']).first():
        return jsonify({"error": "Username already taken"}), 400

    new_user = User(
        username=data['username'],
        email=data['email'],
        role=data['role'],
        work_platform=data.get('work_platform'),
        is_admin=data['email'] == "wavecommunnity@gmail.com"
    )
    new_user.set_password(data['password'])
    db.session.add(new_user)
    db.session.commit()
    return jsonify({"message": "User registered!", "user": new_user.to_dict()}), 201

@app.route('/api/auth/login', methods=['POST'])
def login():
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')
    if not email or not password:
        return jsonify({"error": "Email and password required"}), 400

    user = User.query.filter_by(email=email).first()
    if not user or not user.check_password(password):
        return jsonify({"error": "Invalid email or password"}), 401

    token = jwt.encode({
        'user_id': user.id,
        'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=24)
    }, app.config['SECRET_KEY'], algorithm='HS256')

    return jsonify({
        "message": "Login successful",
        "token": token,
        "user": user.to_dict()
    }), 200

@app.route('/api/tasks/mine', methods=['GET'])
@token_required
def get_my_tasks(current_user_id):
    tasks = Task.query.options(
        joinedload(Task.quotes),
        joinedload(Task.ratings)
    ).filter_by(poster_id=current_user_id).all()
    return jsonify([task.to_dict() for task in tasks]), 200

@app.route('/me', methods=['GET'])
@token_required
def get_current_user(current_user_id):
    user = User.query.get(current_user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404
    return jsonify(user.to_dict()), 200

@app.route('/users', methods=['GET'])
def get_users():
    users = User.query.all()
    return jsonify([user.to_dict() for user in users]), 200

# === TASK ROUTES ===
@app.route('/api/tasks', methods=['POST'])
@token_required
def create_task(current_user_id):
    data = request.get_json()
    required = ['title', 'description', 'category', 'latitude', 'longitude']
    if not all(k in data for k in required):
        return jsonify({"error": "title, description, category, latitude, and longitude are required"}), 400

    new_task = Task(
        title=data['title'],
        description=data['description'],
        category=data['category'],
        latitude=data['latitude'],
        longitude=data['longitude'],
        reward=data.get('reward', ''),
        poster_id=current_user_id,
        status='open'
    )
    db.session.add(new_task)
    db.session.commit()
    return jsonify(new_task.to_dict()), 201





    tasks = Task.query.filter_by(status='open').all()
    return jsonify([task.to_dict() for task in tasks]), 200

@app.route('/api/admin/users', methods=['GET'])
@token_required
@admin_required
def admin_users(current_user_id):
    users = User.query.all()
    return jsonify([u.to_dict() for u in users])

@app.route('/api/admin/tasks', methods=['GET'])
@token_required
@admin_required
def admin_tasks(current_user_id):
    tasks = Task.query.all()
    return jsonify([t.to_dict() for t in tasks])

@app.route('/profile/location', methods=['PUT'])
@token_required
def update_location(current_user_id):
    data = request.get_json()
    if 'latitude' not in data or 'longitude' not in data:
        return jsonify({"error": "latitude and longitude are required"}), 400

    user = User.query.get(current_user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404

    user.latitude = data['latitude']
    user.longitude = data['longitude']
    db.session.commit()

    return jsonify({
        "message": "Location updated",
        "user": user.to_dict()
    }), 200

# === QUOTE-BASED NEGOTIATION ===
@app.route('/api/tasks/<int:task_id>/quote', methods=['POST'])
@token_required
def submit_quote(current_user_id, task_id):
    data = request.get_json()
    charges = data.get('charges')
    hours = data.get('hours')
    mobile = data.get('mobile')
    
    if charges is None or hours is None or not mobile:
        return jsonify({"error": "Charges, hours, and mobile are required"}), 400
        
    task = Task.query.filter_by(id=task_id, status='open').first()
    if not task:
        return jsonify({"error": "Task not found or no longer open"}), 404

    existing = Quote.query.filter_by(task_id=task_id, helper_id=current_user_id).first()
    if existing:
        db.session.delete(existing)


    quote = Quote(
        task_id=task_id,
        helper_id=current_user_id,
        charges=float(charges),
        hours=float(hours),
        mobile=mobile
    )
    db.session.add(quote)
    db.session.commit()
    return jsonify(quote.to_dict()), 201

# In app.py (add this route)
@app.route('/api/profile/upload', methods=['POST'])
@token_required
def upload_profile_image(current_user_id):
    if 'image' not in request.files:
        return jsonify({"error": "No image provided"}), 400

    file = request.files['image']
    if file.filename == '':
        return jsonify({"error": "No image selected"}), 400

    if file and allowed_file(file.filename):
        filename = f"profile_{current_user_id}_{secure_filename(file.filename)}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        user = User.query.get(current_user_id)
        user.image_url = f"/uploads/{filename}"
        db.session.commit()
        
        return jsonify({"image_url": user.image_url}), 200

    return jsonify({"error": "Invalid file type. Use PNG, JPG, JPEG, or GIF"}), 400

@app.route('/api/quotes/<int:quote_id>/accept', methods=['POST'])
@token_required
def accept_quote(current_user_id, quote_id):
    quote = Quote.query.get(quote_id)
    if not quote:
        return jsonify({"error": "Quote not found"}), 404
        
    task = quote.task
    if task.poster_id != current_user_id:
        return jsonify({"error": "Only the task poster can accept quotes"}), 403

    # Decline all other quotes
    other_quotes = Quote.query.filter_by(task_id=task.id).filter(Quote.id != quote_id)
    for q in other_quotes:
        q.status = 'declined'
        create_notification(
            q.helper_id,
            f"Your quotation for '{task.title}' was declined."
        )
    
    
    # Accept selected quote
    quote.status = 'accepted'
    task.helper_id = quote.helper_id
    task.charges = quote.charges
    task.hours = quote.hours
    task.status = 'accepted'
    db.session.commit()
    create_notification(
        quote.helper_id,
        f"Your work for '{task.title}' was assigned!"
    )
    db.session.commit()

    return jsonify({
        "message": "Quote accepted",
        "task": task.to_dict(),
        "accepted_quote": quote.to_dict()
    }), 200

@app.route('/api/notifications', methods=['GET'])
@token_required
def get_notifications(current_user_id):
    notifs = Notification.query.filter_by(user_id=current_user_id).order_by(Notification.created_at.desc()).all()
    return jsonify([n.to_dict() for n in notifs]), 200

@app.route('/api/notifications/<int:notification_id>/read', methods=['POST'])
@token_required
def mark_notification_read(current_user_id, notification_id):
    notif = Notification.query.filter_by(id=notification_id, user_id=current_user_id).first()
    if not notif:
        return jsonify({"error": "Notification not found"}), 404
    notif.is_read = True
    db.session.commit()
    return jsonify({"message": "Notification marked as read"}), 200

@app.route('/api/profile/<int:user_id>', methods=['GET'])
def get_profile(user_id):
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404

    # Get completed tasks counts
    completed_tasks_as_helper = Task.query.filter_by(helper_id=user_id, status='completed').count()
    completed_tasks_as_seeker = Task.query.filter_by(poster_id=user_id, status='completed').count()

    # Get ratings received
    ratings_received = Rating.query.filter_by(ratee_id=user_id).all()
    # ✅ Use 'score' instead of 'rating'
    avg_rating = round(sum(r.score for r in ratings_received) / len(ratings_received), 1) if ratings_received else 0

    return jsonify({
        "user": user.to_dict(),
        "completed_tasks_as_helper": completed_tasks_as_helper,
        "completed_tasks_as_seeker": completed_tasks_as_seeker,
        "total_ratings": len(ratings_received),
        "average_rating": avg_rating,
        "ratings": [r.to_dict() for r in ratings_received]
    }), 200

# Add to your existing routes in app.py

@app.route('/api/tasks/assigned', methods=['GET'])
@token_required
def get_assigned_tasks(current_user_id):
    """Get tasks assigned to current user as helper"""
    tasks = Task.query.filter_by(helper_id=current_user_id).all()
    return jsonify([task.to_dict() for task in tasks]), 200

# ✅ SINGLE complete_task route (removed duplicate)
@app.route('/api/tasks/<int:task_id>/complete', methods=['POST'])
@token_required
def complete_task(current_user_id, task_id):
    task = Task.query.filter_by(id=task_id).first()
    if not task:
        return jsonify({"error": "Task not found"}), 404
    
    # Only helper or poster can mark as complete
    if current_user_id not in [task.helper_id, task.poster_id]:
        return jsonify({"error": "You're not authorized to complete this task"}), 403

    task.status = 'completed'
    db.session.commit()
    return jsonify(task.to_dict()), 200

# Profile image upload route

@app.route('/api/rating', methods=['POST'])
@token_required
def create_rating(current_user_id):
    data = request.get_json()
    task_id = data.get('task_id')
    ratee_id = data.get('ratee_id')
    score = data.get('score')
    comment = data.get('comment', '')

    if not all([task_id, ratee_id, score]):
        return jsonify({"error": "task_id, ratee_id, and score are required"}), 400
    if not (1 <= score <= 5):
        return jsonify({"error": "Score must be between 1 and 5"}), 400

    task = Task.query.get(task_id)
    if not task or task.status != 'completed':
        return jsonify({"error": "Task not found or not completed"}), 400

    # Ensure rater was part of the task
    if current_user_id not in [task.poster_id, task.helper_id]:
        return jsonify({"error": "You were not part of this task"}), 403

    # Ensure ratee is the other participant
    if ratee_id not in [task.poster_id, task.helper_id] or ratee_id == current_user_id:
        return jsonify({"error": "You can only rate the other participant"}), 400

    # Prevent duplicate rating
    existing = Rating.query.filter_by(
        task_id=task_id,
        rater_id=current_user_id,
        ratee_id=ratee_id
    ).first()
    if existing:
        return jsonify({"error": "You already rated this user for this task"}), 400

    rating = Rating(
        task_id=task_id,
        rater_id=current_user_id,
        ratee_id=ratee_id,
        score=score,
        comment=comment
    )
    db.session.add(rating)
    db.session.commit()
    return jsonify(rating.to_dict()), 201

# === TASK MANAGEMENT ===
# In app.py - Replace your delete_task route with this:
# In app.py - REPLACE your current delete_task route
@app.route('/api/tasks/<int:task_id>', methods=['DELETE'])
@token_required
def delete_task(current_user_id, task_id):
    try:
        task = Task.query.filter_by(id=task_id, poster_id=current_user_id).first()
        if not task:
            return jsonify({"error": "Task not found or you don't own it"}), 404
        if task.status != 'open':
            return jsonify({"error": "Only open tasks can be deleted"}), 400

        # Delete related quotes and ratings FIRST
        Quote.query.filter_by(task_id=task_id).delete()
        Rating.query.filter_by(task_id=task_id).delete()
        
        db.session.delete(task)
        db.session.commit()
        return jsonify({"message": "Task deleted successfully"}), 200
    except Exception as e:
        db.session.rollback()
        print(f"Error deleting task {task_id}: {str(e)}")  # Check Flask console for real error
        return jsonify({"error": "Failed to delete task"}), 500

# === IMAGE UPLOAD ROUTE ===
@app.route('/api/tasks/<int:task_id>/image', methods=['POST'])
@token_required
def upload_task_image(current_user_id, task_id):
    task = Task.query.filter_by(id=task_id, poster_id=current_user_id).first()
    if not task:
        return jsonify({"error": "Task not found or you don't own it"}), 404

    if 'image' not in request.files:
        return jsonify({"error": "No image provided"}), 400

    file = request.files['image']
    if file.filename == '':
        return jsonify({"error": "No image selected"}), 400

    if file and allowed_file(file.filename):
        filename = f"task_{task_id}_{secure_filename(file.filename)}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        task.image_url = f"/uploads/{filename}"
        db.session.commit()
        return jsonify({"message": "Image uploaded", "image_url": task.image_url}), 200

    return jsonify({"error": "Invalid file type. Use PNG, JPG, JPEG, or GIF"}), 400

# Add this route AFTER your other task routes
@app.route('/api/tasks/completed/<int:user_id>', methods=['GET'])
def get_completed_tasks(user_id):
    """Get tasks where user was helper and status=completed"""
    try:
        tasks = Task.query.filter_by(helper_id=user_id, status='completed').all()
        return jsonify([task.to_dict() for task in tasks]), 200
    except Exception as e:
        print(f"Error fetching completed tasks: {e}")
        return jsonify({"error": "Failed to fetch completed tasks"}), 500

# === MAP ROUTE ===
@app.route('/api/map/tasks', methods=['GET'])
@token_required
def get_map_tasks(current_user_id):
    user = User.query.get(current_user_id)
    if not user or user.latitude is None or user.longitude is None:
        return jsonify({"error": "Your location is not set"}), 400

    try:
        radius = float(request.args.get('radius', 5.0))
        if radius < 0.1 or radius > 50:
            return jsonify({"error": "Radius must be between 0.1 and 50 km"}), 400
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid radius"}), 400

    all_tasks = Task.query.filter_by(status='open').all()
    nearby_tasks = []

    for task in all_tasks:
        dist = haversine_distance(
            user.latitude, user.longitude,
            task.latitude, task.longitude
        )
        if dist <= radius:
            nearby_tasks.append({
                "id": task.id,
                "title": task.title,
                "category": task.category,
                "reward": task.reward,
                "latitude": task.latitude,
                "longitude": task.longitude,
                "distance_km": round(dist, 2)
            })

    return jsonify(nearby_tasks), 200

if __name__ == '__main__':
    app.run()