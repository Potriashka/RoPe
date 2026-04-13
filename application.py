from flask import Flask, render_template, request, redirect, url_for
import firebase_admin
from firebase_admin import credentials, firestore, storage
from datetime import datetime
import os
from werkzeug.utils import secure_filename

# Initialize Flask app
app = Flask(__name__)
app.secret_key = 'myVerysecretVeryKey361' 

UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'pdf', 'docx', 'txt', 'jpg', 'jpeg', 'png'}  # Modify as per your file types

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Firebase setup
cred = credentials.Certificate('firebase_config.json')
firebase_admin.initialize_app(cred)
db = firestore.client()

# Routes
@app.route('/')
def home():
    # Fetch 5 most recent and 5 most starred IVRs
    recent_ivrs = db.collection('ivrs').order_by('submitted_at', direction=firestore.Query.DESCENDING).limit(9).stream()
    starred_ivrs = db.collection('ivrs').order_by('mark', direction=firestore.Query.DESCENDING).limit(9).stream()
    return render_template('home.html', recent_ivrs=recent_ivrs, starred_ivrs=starred_ivrs)

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/submit', methods=['GET', 'POST'])
def submit_ivr():
    if request.method == 'POST':
        # Retrieve form data
        name = request.form['name']
        description = request.form['description']
        type = request.form['type']
        field = request.form['field']
        year_of_defense = request.form['year_of_defense']
        author = request.form['author']
        group = request.form['group']
        mark = request.form.get('mark', None)
        
        # Retrieve uploaded files (optional picture and IVR file)
        picture = request.files.get('picture')
        file = request.files.get('file')

        # File paths
        file_path = None
        picture_path = None

        # Handle the IVR file upload
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)

        # Handle the picture file upload (optional)
        if picture:
            picture_filename = secure_filename(picture.filename)
            picture_path = os.path.join(app.config['UPLOAD_FOLDER'], picture_filename)
            picture.save(picture_path)

        # Get current timestamp
        current_time = datetime.now().isoformat()

        # Prepare the IVR data to be saved in Firestore
        ivr_data = {
            'name': name,
            'description': description,
            'type': type,
            'field': field,
            'year_of_defense': year_of_defense,
            'author': author,
            'group': group,
            'mark': mark if mark else None,
            'picture': picture_path if picture else None,
            'file': file_path if file else None,
            'submitted_at': current_time
        }

        # Save the IVR data to Firestore (replace this with your actual database logic)
        ivrs_ref = db.collection('ivrs')
        ivrs_ref.add(ivr_data)

        # Redirect to the home page after successful submission
        return redirect(url_for('home'))

    # If the request is GET, return the submission form page
    return render_template('submit.html')

@app.route('/search', methods=['GET'])
def search():
    # Get the search parameters from the URL query string
    name = request.args.get('name', '').strip()
    type = request.args.get('type', '').strip()
    field = request.args.get('field', '').strip()
    year_of_defense = request.args.get('year_of_defense', '').strip()

    # Start with the base query for the 'ivrs' collection
    query = db.collection('ivrs')

    # Add conditions to the query based on the search parameters
    if type:
        query = query.where('type', '==', type)

    if year_of_defense:
        try:
            # Try to convert year to an integer (if possible)
            year_int = int(year_of_defense)
            query = query.where('year_of_defense', '==', year_int)
        except ValueError:
            # If year is not an integer, try matching it as a string
            query = query.where('year_of_defense', '==', year_of_defense)

    # Execute the query to get the results
    ivrs = query.stream()

    # Prepare the results to pass to the template, including the document id
    ivr_list = []
    for ivr in ivrs:
        ivr_data = ivr.to_dict()
        ivr_data['id'] = ivr.id  # Include the document ID in the data
        ivr_list.append(ivr_data)

    # If 'name' was entered, perform the substring check on 'name' field
    if name:
        ivr_list = [ivr for ivr in ivr_list if name.lower() in ivr['name'].lower()]

    # If 'field' was entered, perform the substring check on 'field' field
    if field:
        ivr_list = [ivr for ivr in ivr_list if field.lower() in ivr['field'].lower()]

    return render_template('search.html', ivrs=ivr_list)


@app.route('/tips')
def tips():
    return render_template('tips.html')


@app.route('/ivr/<ivr_id>', methods=['GET'])
def ivr_detail(ivr_id):
    # Retrieve the IVR document by its ID
    ivr_ref = db.collection('ivrs').document(ivr_id)
    ivr = ivr_ref.get()

    if ivr.exists:
        # Pass the IVR data to the template for rendering
        ivr_data = ivr.to_dict()
        return render_template('ivr_detail.html', ivr=ivr_data)
    else:
        return 'IVR not found', 404

def generate_user_id():
    """Generate a unique user ID for each user based on random string"""
    return ''.join(random.choices(string.ascii_letters + string.digits, k=10))

@app.route('/add_star/<string:ivr_id>', methods=['POST'])
def add_star(ivr_id):
    # Get the user ID from cookies, or create one if it doesn't exist
    user_id = request.cookies.get('user_id')

    if not user_id:
        # Generate a new user ID and store it in the cookies
        user_id = generate_user_id()

        resp = make_response(jsonify({"success": False, "message": "New user identified. Please try again to add a star."}))
        resp.set_cookie('user_id', user_id, max_age=30*24*60*60)  # Store user ID in cookies for 30 days
        return resp

    ivr_ref = db.collection('ivrs').document(ivr_id)
    ivr_doc = ivr_ref.get()

    if not ivr_doc.exists:
        return jsonify({"success": False, "message": "IVR not found"}), 404

    ivr_data = ivr_doc.to_dict()

    if 'starred_by' not in ivr_data:
        ivr_data['starred_by'] = []

    if user_id in ivr_data['starred_by']:
        return jsonify({"success": False, "message": "You have already added a star"}), 400

    # Add star
    ivr_data['starred_by'].append(user_id)
    new_star_count = ivr_data.get('stars', 0) + 1
    ivr_ref.update({'stars': new_star_count, 'starred_by': ivr_data['starred_by']})

    return jsonify({"success": True, "new_star_count": new_star_count})

if __name__ == '__main__':
    app.run(debug=True)
