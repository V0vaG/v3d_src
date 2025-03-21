from flask import Flask, render_template, redirect, request, url_for, flash, session, jsonify, flash
import json
import os
import requests
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key'

# Set up paths
alias = "v3d"
HOME_DIR = os.path.expanduser("~")
FILES_PATH = os.path.join(HOME_DIR, "script_files", alias)
DATA_DIR = os.path.join(FILES_PATH, "data")
USERS_FILE = os.path.join(DATA_DIR, 'users.json')


# Ensure the directory exists
os.makedirs(DATA_DIR, exist_ok=True)

def is_root_registered():
    return bool(get_root_user())

def load_users():
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, 'r') as file:
            return json.load(file)
    return []

def save_users(users):
    with open(USERS_FILE, 'w') as file:
        json.dump(users, file, indent=4)

def get_root_user():
    users = load_users()
    return users[0] if users else None

def get_managers():
    users = load_users()
    return users[1]["users"] if len(users) > 1 else []

def get_users(manager_username):
    for manager in get_managers():
        if manager['manager_username'] == manager_username:
            return manager['users']
    return []

def save_root_user(username, password):
    password_hash = generate_password_hash(password, method='pbkdf2:sha256')
    users = [{"root_user": username, "password_hash": password_hash}, {"users": []}]
    save_users(users)

def save_manager_user(username, password):
    password_hash = generate_password_hash(password, method='pbkdf2:sha256')
    users = load_users()
    users[1]["users"].append({"manager_username": username, "password_hash": password_hash, "users": []})
    save_users(users)

def save_user(manager_username, username, password):
    password_hash = generate_password_hash(password, method='pbkdf2:sha256')
    users = load_users()
    for manager in users[1]["users"]:
        if manager['manager_username'] == manager_username:
            manager['users'].append({'user': username, 'password_hash': password_hash})
            break
    save_users(users)

def remove_user(manager_username, username):
    users = load_users()
    for manager in users[1]["users"]:
        if manager['manager_username'] == manager_username:
            manager["users"] = [user for user in manager.get("users", []) if user["user"] != username]
            break
    save_users(users)

@app.route('/')
def index():
    if not is_root_registered():
        return redirect(url_for('register', role='root'))
    return redirect(url_for('login'))

@app.route('/remove_user', methods=['POST'])
def remove_user_route():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    manager_username = session['user_id']
    username = request.form['username']
    remove_user(manager_username, username)
    flash('User removed successfully!', 'success')
    return redirect(url_for('manager_dashboard'))

@app.before_request
def check_root_user():
    if not is_root_registered():
        if request.endpoint not in ('register', 'static'):
            return redirect(url_for('register', role='root'))

@app.route('/register/<role>', methods=['GET', 'POST'])
def register(role):
    if role == "root" and is_root_registered():
        return redirect(url_for('login'))

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        confirm_password = request.form['confirm_password']

        if password != confirm_password:
            flash('Passwords do not match!', 'danger')
        else:
            if role == "root":
                save_root_user(username, password)
                flash('Root user registered successfully!', 'success')
                return redirect(url_for('login'))
            elif role == "manager":
                save_manager_user(username, password)
                flash('Manager registered successfully!', 'success')
                return redirect(url_for('root_dashboard'))
            elif role == "user":
                if 'user_id' not in session:
                    return redirect(url_for('login'))
                manager_username = session['user_id']
                save_user(manager_username, username, password)
                flash('User registered successfully!', 'success')
                return redirect(url_for('manager_dashboard'))

    return render_template('register.html', role=role)

@app.route('/login', methods=['GET', 'POST'])
def login():
    root_user = get_root_user()
    manager_users = get_managers()
    
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        if root_user and username == root_user['root_user'] and check_password_hash(root_user['password_hash'], password):
            session['user_id'] = username
            return redirect(url_for('root_dashboard'))
        for manager in manager_users:
            if username == manager['manager_username'] and check_password_hash(manager['password_hash'], password):
                session['user_id'] = username
                return redirect(url_for('main', role='manager', username=username))
            for user in manager['users']:
                if username == user['user'] and check_password_hash(user['password_hash'], password):
                    session['user_id'] = username
                    return redirect(url_for('main', role='user', username=username))
        flash('Invalid username or password.', 'danger')
    return render_template('login.html')


@app.route('/main')
def main():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    username = request.args.get('username')
    role = request.args.get('role')
    return render_template('main.html', username=username, role=role)



@app.route('/root_dashboard')
def root_dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    managers = get_managers()
    return render_template('root_dashboard.html', managers=managers)

@app.route('/manager_dashboard')
def manager_dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    manager_username = session['user_id']
    users = get_users(manager_username)
    return render_template('manager_dashboard.html', users=users)

@app.route('/user_dashboard')
def user_dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user_name = session['user_id']
    users = get_users(user_name)
    return render_template('user_dashboard.html', users=users)

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True, threaded=True)
