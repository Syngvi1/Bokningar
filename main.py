import os
import pandas as pd
from flask_sqlalchemy import SQLAlchemy
from flask import Flask, render_template, request, redirect, session, make_response, url_for
from datetime import datetime
import calendar
import secrets
import pdfkit
from xhtml2pdf import pisa
from io import BytesIO
import re

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)

# Set the base directory where the app is located
basedir = os.path.abspath(os.path.dirname(__file__))

# Use os.path.join to construct the correct path to the Excel file
file_path = os.path.join(basedir, 'Gymnasium.xlsx')

# Configure the SQLite database
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{os.path.join(basedir, 'data.db')}'  # Points to current directory
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

class SchoolContact(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    school_name = db.Column(db.String(150), nullable=False)
    address = db.Column(db.String(200), nullable=False)
    city = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(50), nullable=False)
    local = db.Column(db.String(50), nullable=True)
    equipment = db.Column(db.String(50), nullable=True)
    limitations = db.Column(db.String(50), nullable=True)
    rules = db.Column(db.Text, nullable=True)
    date = db.Column(db.String(50), nullable=True)  # Store date as string
    time_slot = db.Column(db.String(50), nullable=True)



# Create the tables
with app.app_context():
    db.create_all()

@app.route('/')
def index():
    return render_template('index.html')

def load_schools_from_excel():
    try:
        # Load the Excel file
        df = pd.read_excel(file_path)
        
        # Convert 'LÄN' to string and ensure it's padded with leading zeros (if necessary)
        df['LÄN'] = df['LÄN'].astype(str).str.zfill(2)

        # Filter rows where the 'KOMMUNKOD' starts with the specified values
        län_filter = df['LÄN'].astype(str).str.startswith(('18','05','20','17','03','14','04','19'))
        filtered_df = df[län_filter]

        # Remove duplicate addresses
        filtered_df = filtered_df.drop_duplicates(subset=['BESÖKSADRESS'])

        # Get booked schools from the database (by address)
        booked_schools = {contact.address for contact in SchoolContact.query.all()}

        # Remove schools that have already been booked
        available_schools_df = filtered_df[~filtered_df['BESÖKSADRESS'].isin(booked_schools)]

        # Select the relevant columns
        schools = available_schools_df[['SKOLENHETENS NAMN', 'LÄNSNAMN', 'BESÖKSADRESS', 'BESÖKSPOSTORT', 'TELENR', 'EPOST', 'WEBB', 'REKTORS NAMN', 'EKONOMIPROGRAMMET', 'ESTETISKA PROGRAMMET','HUMANISTISKA PROGRAMMET','NATURVETENSKAPSPROGRAMMET','SAMHÄLLSVETENSKAPSPROGRAMMET','TEKNIKPROGRAMMET']]
        
        return schools.to_dict(orient='records')  # Convert to a list of dictionaries
    except FileNotFoundError:
        return []



@app.route('/schools')
def school_list():
    schools_data = load_schools_from_excel()
    return render_template('school_list.html', schools=schools_data)

from flask import session, redirect

@app.route('/booking-details/<school_name>', methods=['GET', 'POST'])
def booking_details(school_name):
    if request.method == 'POST':
        # Collect the data from the form
        address = request.form.get('address')
        city = request.form.get('city')
        phone = request.form.get('phone')
        local = request.form.get('local')
        equipment = request.form.get('equipment')
        limitations = request.form.get('limitations')
        rules = request.form.get('rules')

        # Store the form data in the session
        session['school_data'] = {
            'school_name': school_name,
            'address': address,
            'city': city,
            'phone': phone,
            'local': local,
            'equipment': equipment,
            'limitations': limitations,
            'rules': rules
        }

        # Redirect to the calendar page
        return redirect(f'/choose-date/{school_name}')
    address = request.args.get('address')
    city = request.args.get('city')
    phone = request.args.get('phone')

    # For GET requests, render the booking details form
    return render_template(
        'booking_details.html',
          school_name=school_name, 
          address=address, 
          city=city, 
          phone=phone
    )


@app.route('/choose-date/<school_name>', methods=['GET', 'POST'])
def choose_date(school_name):
    if request.method == 'POST':
        selected_date = request.form.get('selected-date')
        selected_time_slot = request.form.get('selected-time-slot')

        school_data = session.get('school_data', {})

        school_contact = SchoolContact(
            school_name=school_data['school_name'],
            address=school_data['address'],
            city=school_data['city'],
            phone=school_data['phone'],
            local=school_data['local'],
            equipment=school_data['equipment'],
            limitations=school_data['limitations'],
            rules=school_data['rules'],
            date=selected_date,
            time_slot=selected_time_slot
        )

        db.session.add(school_contact)
        db.session.commit()

        session.pop('school_data', None)
        return redirect('/kontacted-schools')

    # Generate the calendar for the current month
    now = datetime.now()  # Current date and time
    year = request.args.get('year', now.year, type=int)
    month = request.args.get('month', now.month, type=int)

    cal = calendar.Calendar(calendar.SUNDAY)
    week = cal.monthdayscalendar(year, month)

    # Define two time slots
    time_slots = ['08:00-09:00', '13:00-14:00']

    # Prepare days in HTML format
    days_html = ""
    for week in week:
        days_html += "<tr>"
        for day in week:
            if day == 0:
                days_html += '<td class="empty"></td>'
            else:
                # Get the current date
                date_obj = datetime(year, month, day)
                weekday = date_obj.weekday()  # Monday = 0, Sunday = 6

                days_html += f'<td class="selectable-day" data-date="{year}-{month:02d}-{day:02d}">'
                days_html += f'<div class="date-number">{day}</div>'
                
                # Check if the date is today or in the future
                if date_obj >= now:
                    # Only show time slots if it's not a weekend (weekday < 5 means Monday to Friday)
                    if weekday < 5:
                        for slot in time_slots:
                            days_html += f'<div class="time-slot available" data-date="{year}-{month:02d}-{day:02d}" data-time="{slot}">{slot}</div>'
                days_html += '</td>'
        days_html += "</tr>"

    prev_month = month - 1 if month > 1 else 12
    prev_year = year if month > 1 else year - 1
    next_month = month + 1 if month < 12 else 1
    next_year = year if month < 12 else year + 1

    return render_template(
        'calendar.html',
        school_name=school_name,
        days_html=days_html,
        time_slots=time_slots,
        month=calendar.month_name[month],
        year=year,
        prev_month=prev_month,
        prev_year=prev_year,
        next_month=next_month,
        next_year=next_year
    )







@app.route('/kontakt', methods=['POST'])
def kontakt():
    # Extract the data from the form
    school_name = request.form['school_name']
    address = request.form['address']
    city = request.form['city']
    phone = request.form['phone']

    # Create a new SchoolContact instance
    new_contact = SchoolContact(
        school_name=school_name,
        address=address,
        city=city,
        phone=phone,

    )

    # Add the new contact to the database within an application context
    with app.app_context():
        db.session.add(new_contact)
        db.session.commit()

    return redirect('/schools')

@app.route('/kontacted-schools')
def kontacted_schools():
    contacts = SchoolContact.query.all()  # Retrieve all kontacted schools
    return render_template('kontacted_schools.html', contacts=contacts)

@app.route('/delete-booking/<int:id>', methods=['POST'])
def delete_booking(id):
    booking_to_delete = SchoolContact.query.get_or_404(id)

    try:
        db.session.delete(booking_to_delete)
        db.session.commit()
        return redirect('/kontacted-schools')  # Redirect back to the bookings page after deletion
    except:
        return 'There was a problem deleting that booking'
    
@app.route('/edit-booking/<int:id>', methods=['GET', 'POST'])
def edit_booking(id):
    booking = SchoolContact.query.get_or_404(id)  # Fetch the booking by ID
    if request.method == 'POST':
        # Update the booking with form data
        booking.school_name = request.form['school-name']
        booking.address = request.form['address']
        booking.phone = request.form['phone']
        booking.local = request.form.get('local')  # Optional field
        booking.equipment = request.form.get('equipment')  # Optional field
        booking.limitations = request.form.get('limitations')  # Optional field
        booking.rules = request.form.get('rules')  # Optional field
        booking.date = request.form['date']
        booking.time_slot = request.form['time-slot']

        # Save the changes to the database
        db.session.commit()

        # Redirect back to the list of contacted schools
        return redirect(url_for('kontacted_schools'))

    # Render the edit_booking.html template for GET requests
    return render_template('edit_booking.html', booking=booking)





@app.route('/scorecard/<int:id>', methods=['GET'])
def scorecard(id):
    # Get the booking details by ID
    contact = SchoolContact.query.get_or_404(id)
    
    return render_template('scorecard.html', contact=contact)


@app.route('/download-scorecard/<int:id>', methods=['GET'])
def download_scorecard(id):
    # Get the booking details by ID
    contact = SchoolContact.query.get_or_404(id)
    
    # Render the HTML template as a string
    rendered_html = render_template('scorecard.html', contact=contact)
    
    # Create a PDF from the HTML
    pdf = BytesIO()
    pisa_status = pisa.CreatePDF(BytesIO(rendered_html.encode('utf-8')), dest=pdf)
    
    if pisa_status.err:
        return 'Error creating PDF', 500
    
    # Create a clean filename based on the school name (remove special characters)
    school_name = re.sub(r'[^a-zA-Z0-9]', '_', contact.school_name)  # Replace any non-alphanumeric characters with an underscore
    
    # Return the PDF as a downloadable file with the school name as the filename
    response = make_response(pdf.getvalue())
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = f'attachment; filename={school_name}_scorecard.pdf'
    
    return response


if __name__ == '__main__':
    app.run(debug=True)
