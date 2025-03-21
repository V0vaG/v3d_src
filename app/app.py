from flask import Flask, render_template, redirect, request, url_for, flash, session, jsonify, flash, send_from_directory, send_file
import json
import os
import requests
import tempfile
import zipfile
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import shutil
from io import BytesIO


app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key'

# Set up paths
alias = "v3d"
HOME_DIR = os.path.expanduser("~")
FILES_PATH = os.path.join(HOME_DIR, "script_files", alias)
DATA_DIR = os.path.join(FILES_PATH, "data")
STL_DIR = os.path.join(FILES_PATH, "stl")
USERS_FILE = os.path.join(DATA_DIR, 'users.json')


# Ensure the directory exists
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(STL_DIR, exist_ok=True)

@app.route('/stl_files/<path:filename>')
def stl_files(filename):
    return send_from_directory(STL_DIR, filename)

def is_root_registered():
    return bool(get_root_user())

def load_users():
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, 'r') as f:
            return json.load(f)
    return []

def save_users(users):
    with open(USERS_FILE, 'w') as f:
        json.dump(users, f, indent=4)

def add_user(username, password, role):
    users = load_users()
    password_hash = generate_password_hash(password)
    users.append({
        "user": username,
        "role": role,
        "password_hash": password_hash
    })
    save_users(users)

def remove_user(username):
    users = load_users()
    users = [u for u in users if u['user'] != username]
    save_users(users)

def find_user(username):
    users = load_users()
    return next((u for u in users if u['user'] == username), None)



def get_root_user():
    users = load_users()
    return users[0] if users else None

def get_managers():
    users = load_users()
    return [u for u in users if u['role'] == 'manager']


def get_users(manager_username=None):
    users = load_users()
    return [u for u in users if u['role'] == 'user']


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
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        confirm = request.form['confirm_password']

        if password != confirm:
            flash("Passwords do not match", "danger")
            return redirect(request.url)

        existing = find_user(username)
        if existing:
            flash("User already exists", "danger")
            return redirect(request.url)

        add_user(username, password, role)
        flash(f"{role.capitalize()} user registered successfully!", "success")
        return redirect(url_for('login'))

    return render_template('register.html', role=role)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        user = find_user(username)
        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = username
            session['role'] = user['role']

            # Redirect everyone (root/manager/user) to main page with role and username
            return redirect(url_for('main', username=username, role=user['role']))

        flash("Invalid username or password", "danger")

    return render_template('login.html')


@app.route('/main')
def main():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    username = request.args.get('username')
    role = request.args.get('role')

    try:
        stl_folders = [
            f for f in os.listdir(STL_DIR)
            if os.path.isdir(os.path.join(STL_DIR, f))
        ]
    except FileNotFoundError:
        stl_folders = []

    return render_template('main.html', username=username, role=role, stl_folders=stl_folders)

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

    subfolder = request.args.get('folder', '')

    stl_folders = list_stl_folders_only(subfolder)
    stl_root_folders = list_stl_root_folders()

    return render_template(
        'manager_dashboard.html',
        users=users,
        username=manager_username,
        role='manager',
        current_folder=subfolder,
        stl_folders=stl_folders,
        stl_root_folders=stl_root_folders
    )


@app.route('/user_dashboard')
def user_dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    username = session['user_id']

    try:
        stl_folders = [
            f for f in os.listdir(STL_DIR)
            if os.path.isdir(os.path.join(STL_DIR, f))
        ]
    except FileNotFoundError:
        stl_folders = []

    return render_template('user_dashboard.html', username=username, role='user', stl_folders=stl_folders)


@app.route('/logout')
def logout():
    session.pop('user_id', None)
    return redirect(url_for('login'))

def list_stl_folders_only(subfolder=""):
    path = os.path.join(STL_DIR, subfolder)
    path = os.path.normpath(path)

    if not path.startswith(STL_DIR):
        return []

    try:
        return [
            {
                "name": item,
                "subpath": os.path.relpath(os.path.join(subfolder, item), start=""),
            }
            for item in os.listdir(path)
            if os.path.isdir(os.path.join(path, item))
        ]
    except FileNotFoundError:
        return []

def list_stl_root_folders():
    try:
        return [
            item for item in os.listdir(STL_DIR)
            if os.path.isdir(os.path.join(STL_DIR, item))
        ]
    except FileNotFoundError:
        return []



@app.route('/upload_stl', methods=['POST'])
def upload_stl():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    folder = request.form.get('folder')
    file = request.files.get('file')

    if not file or not folder:
        flash('Please select a folder and choose a file.', 'danger')
        return redirect(url_for('manager_dashboard'))

    filename = secure_filename(file.filename)
    if not filename.lower().endswith('.zip'):
        flash('Upload only ZIP files.', 'danger')
        return redirect(url_for('manager_dashboard'))

    # Define target paths
    upload_path = os.path.join(STL_DIR, folder)
    os.makedirs(upload_path, exist_ok=True)

    zip_path = os.path.join(upload_path, filename)
    extract_folder_name = os.path.splitext(filename)[0]
    extract_path = os.path.join(upload_path, extract_folder_name)

    file.save(zip_path)

    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            os.makedirs(extract_path, exist_ok=True)
            zip_ref.extractall(extract_path)
        os.remove(zip_path)
        flash(f'"{filename}" uploaded and extracted to folder "{extract_folder_name}".', 'success')
    except zipfile.BadZipFile:
        os.remove(zip_path)
        flash('Invalid ZIP file. Upload failed.', 'danger')

    return redirect(url_for('manager_dashboard'))


@app.route('/create_stl_folder', methods=['POST'])
def create_stl_folder():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    folder_name = request.form.get('folder_name', '').strip()

    if not folder_name:
        flash("Folder name cannot be empty.", "danger")
        return redirect(url_for('manager_dashboard'))

    # Sanitize folder name to avoid path traversal
    safe_name = secure_filename(folder_name)
    new_folder_path = os.path.join(STL_DIR, safe_name)

    try:
        os.makedirs(new_folder_path, exist_ok=False)
        flash(f'Folder "{safe_name}" created successfully!', "success")
    except FileExistsError:
        flash(f'Folder "{safe_name}" already exists.', "danger")
    except Exception as e:
        flash(f'Error creating folder: {e}', "danger")

    return redirect(url_for('manager_dashboard'))

@app.route('/folder/<path:folder_name>')
def view_folder(folder_name):
    folder_path = os.path.join(STL_DIR, folder_name)
    folder_path = os.path.normpath(folder_path)

    if not folder_path.startswith(STL_DIR):
        flash("Invalid folder path.", "danger")
        return redirect(url_for('main'))

    folders_with_data = []

    try:
        subfolders = [
            f for f in os.listdir(folder_path)
            if os.path.isdir(os.path.join(folder_path, f))
        ]

        for sub in subfolders:
            subfolder_path = os.path.join(folder_path, sub)
            files = os.listdir(subfolder_path)

            # Find image
            image_file = next((f for f in files if f.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp'))), None)
            image_url = url_for('stl_files', filename=os.path.join(folder_name, sub, image_file)) if image_file else None

            # Read README.txt
            readme_path = os.path.join(subfolder_path, "README.txt")
            description = ""
            if os.path.isfile(readme_path):
                with open(readme_path, 'r', encoding='utf-8') as f:
                    description = f.read().strip()

            folders_with_data.append({
                'name': sub,
                'image': image_url,
                'description': description
            })

    except FileNotFoundError:
        folders_with_data = []

    return render_template(
        'folder.html',
        current_folder=folder_name,
        folders=folders_with_data
    )


@app.route('/download_folder/<path:folder_path>')
def download_folder(folder_path):
    abs_path = os.path.normpath(os.path.join(STL_DIR, folder_path))

    if not abs_path.startswith(STL_DIR) or not os.path.isdir(abs_path):
        flash("Invalid folder path.", "danger")
        return redirect(url_for('main'))

    try:
        # Create a temporary directory to store the zip
        temp_dir = tempfile.mkdtemp()
        folder_name = os.path.basename(abs_path)
        zip_base = os.path.join(temp_dir, folder_name)

        # Create the zip file
        zip_path = shutil.make_archive(zip_base, 'zip', abs_path)

        # Send the zip file as download
        return send_file(
            zip_path,
            as_attachment=True,
            download_name=f"{folder_name}.zip",
            mimetype='application/zip'
        )

    except Exception as e:
        flash(f"Error creating zip: {e}", "danger")
        return redirect(url_for('main'))


if __name__ == '__main__':
    app.run(debug=True, threaded=True)
