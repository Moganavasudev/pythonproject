from flask import Flask, render_template, request, redirect, url_for, session, send_file, flash
from pymongo import MongoClient
from werkzeug.security import generate_password_hash, check_password_hash
import os
from bson import ObjectId
import pdfkit
import io
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'your-secret-key'  # Change this to a secure secret key

# MongoDB connection
client = MongoClient('mongodb://localhost:27017/')
db = client['portfolio_db']

# PDF Configuration
if os.name == 'nt':  # For Windows
    path_wkhtmltopdf = r'C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe'
    config = pdfkit.configuration(wkhtmltopdf=path_wkhtmltopdf)
else:  # For Linux/Unix/MacOS
    config = pdfkit.configuration()

# PDF Options
pdf_options = {
    'page-size': 'A4',
    'margin-top': '0.75in',
    'margin-right': '0.75in',
    'margin-bottom': '0.75in',
    'margin-left': '0.75in',
    'encoding': "UTF-8",
    'no-outline': None,
    'enable-local-file-access': None
}

@app.route('/')
def home():
    if 'user_id' in session:
        return redirect(url_for('builder'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        
        user = db.users.find_one({'email': email})
        if user and check_password_hash(user['password'], password):
            session['user_id'] = str(user['_id'])
            flash('Successfully logged in!', 'success')
            return redirect(url_for('builder'))
        flash('Invalid email or password', 'danger')
        return redirect(url_for('login'))
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        
        if db.users.find_one({'email': email}):
            flash('Email already exists', 'danger')
            return redirect(url_for('register'))
        
        hashed_password = generate_password_hash(password)
        db.users.insert_one({
            'email': email,
            'password': hashed_password,
            'portfolios': []
        })
        flash('Registration successful! Please login.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    flash('Successfully logged out!', 'success')
    return redirect(url_for('login'))

@app.route('/builder')
def builder():
    if 'user_id' not in session:
        flash('Please login first', 'warning')
        return redirect(url_for('login'))
    return render_template('builder.html')

@app.route('/create_portfolio', methods=['GET', 'POST'])
def create_portfolio():
    if 'user_id' not in session:
        flash('Please login first', 'warning')
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        portfolio_id = str(ObjectId())
        portfolio_data = {
            'id': portfolio_id,
            'name': request.form['name'],
            'title': request.form['title'],
            'about': request.form['about'],
            'skills': request.form.getlist('skills'),
            'experience': request.form.getlist('experience'),
            'education': request.form.getlist('education'),
            'projects': request.form.getlist('projects'),
            'contact': {
                'email': request.form['contact_email'],
                'phone': request.form['contact_phone'],
                'linkedin': request.form['linkedin']
            },
            'created_at': datetime.now()
        }
        
        db.users.update_one(
            {'_id': ObjectId(session['user_id'])},
            {'$push': {'portfolios': portfolio_data}}
        )
        flash('Portfolio created successfully!', 'success')
        return redirect(url_for('view_portfolio', portfolio_id=portfolio_id))
    
    return render_template('create_portfolio.html')

@app.route('/view_portfolios')
def view_portfolios():
    if 'user_id' not in session:
        flash('Please login first', 'warning')
        return redirect(url_for('login'))
    
    user = db.users.find_one({'_id': ObjectId(session['user_id'])})
    if not user or 'portfolios' not in user or not user['portfolios']:
        flash('No portfolios found. Create your first portfolio!', 'info')
        return redirect(url_for('create_portfolio'))
    
    # Sort portfolios by creation date, newest first
    portfolios = sorted(user['portfolios'], key=lambda x: x['created_at'], reverse=True)
    return render_template('view_portfolios.html', portfolios=portfolios)

@app.route('/view_portfolio/<portfolio_id>')
def view_portfolio(portfolio_id):
    if 'user_id' not in session:
        flash('Please login first', 'warning')
        return redirect(url_for('login'))
    
    user = db.users.find_one({'_id': ObjectId(session['user_id'])})
    if not user or 'portfolios' not in user:
        flash('No portfolios found', 'warning')
        return redirect(url_for('create_portfolio'))
    
    portfolio = next((p for p in user['portfolios'] if p['id'] == portfolio_id), None)
    if not portfolio:
        flash('Portfolio not found', 'warning')
        return redirect(url_for('view_portfolios'))
    
    return render_template('view_portfolio.html', portfolio=portfolio)

@app.route('/download_portfolio/<portfolio_id>')
def download_portfolio(portfolio_id):
    if 'user_id' not in session:
        flash('Please login first', 'warning')
        return redirect(url_for('login'))
    
    user = db.users.find_one({'_id': ObjectId(session['user_id'])})
    portfolio = next((p for p in user['portfolios'] if p['id'] == portfolio_id), None)
    
    if not portfolio:
        flash('Portfolio not found', 'warning')
        return redirect(url_for('view_portfolios'))
    
    try:
        # Generate PDF from the portfolio template
        rendered = render_template('portfolio_pdf.html', portfolio=portfolio)
        
        try:
            # Try with configuration first
            pdf = pdfkit.from_string(rendered, False, options=pdf_options, configuration=config)
        except Exception as e:
            # If configuration fails, try without it
            pdf = pdfkit.from_string(rendered, False, options=pdf_options)
        
        # Create a response with the PDF
        return send_file(
            io.BytesIO(pdf),
            download_name=f"{portfolio['name']}_portfolio.pdf",
            as_attachment=True,
            mimetype='application/pdf'
        )
    except Exception as e:
        flash(f'Error generating PDF. Please make sure wkhtmltopdf is installed. Error: {str(e)}', 'danger')
        return redirect(url_for('view_portfolio', portfolio_id=portfolio_id))

@app.route('/delete_portfolio/<portfolio_id>')
def delete_portfolio(portfolio_id):
    if 'user_id' not in session:
        flash('Please login first', 'warning')
        return redirect(url_for('login'))
    
    db.users.update_one(
        {'_id': ObjectId(session['user_id'])},
        {'$pull': {'portfolios': {'id': portfolio_id}}}
    )
    flash('Portfolio deleted successfully!', 'success')
    return redirect(url_for('view_portfolios'))

if __name__ == '__main__':
    app.run(debug=True) 