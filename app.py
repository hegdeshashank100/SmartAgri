import os
from flask import Flask, request, jsonify, render_template, redirect, url_for, session, flash, send_from_directory
from flask_pymongo import PyMongo
import io
import base64
import re
import requests
import bcrypt
import secrets
import logging
from PIL import Image
from googleapiclient.discovery import build  # YouTube API
from functools import wraps
from datetime import datetime, timedelta
from dotenv import load_dotenv
from hedera import Client, AccountId, PrivateKey, TopicCreateTransaction, TopicMessageSubmitTransaction
from bson.objectid import ObjectId
import smtplib
from email.mime.text import MIMEText

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__)

# SECRET KEY (for session management)
app.secret_key = os.getenv("FLASK_SECRET_KEY", secrets.token_hex(16))  # Fallback to random key if not in .env

# MongoDB Config
app.config["MONGO_URI"] = "mongodb://localhost:27017/smartagri"
mongo = PyMongo(app)

# Define MongoDB collections
users_collection = mongo.db.users
sessions_collection = mongo.db.sessions
ratings_collection = mongo.db.ratings  # Collection for star ratings
comments_collection = mongo.db.comments  # Collection for comments
crop_data_collection = mongo.db.crop_growth_analysis  # Collection for daily crop data and predictive analysis
irrigation_plans_collection = mongo.db.irrigation_plans
blockchain_records_collection = mongo.db.blockchain_records  # Collection for blockchain records
posts_collection = mongo.db.posts  # Collection for forum posts

# Google API Key (Used for Gemini & YouTube)
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")

# OpenWeather API Key
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY", "")

# Email Configuration
EMAIL_ADDRESS = os.getenv('EMAIL_ADDRESS', '')
EMAIL_PASSWORD = os.getenv('EMAIL_PASSWORD', '')

# Configure Gemini AI
import google.generativeai as genai
genai.configure(api_key=GOOGLE_API_KEY)

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Supported Languages with "none" added
LANGUAGES = {
    "none": "Auto",
    "en": "English",
    "kn": "Kannada",
    "hi": "Hindi",
    "sp": "Spanish",
    "te": "Telugu"
}

# Global variable for Hedera topic ID
global_topic_id = None

# Middleware to check active session before each request
@app.before_request
def check_session():
    if "user" in session:
        email = session["user"]
        user_session = mongo.db.sessions.find_one({"email": email})

        if not user_session:
            session.clear()
            flash("Your session has expired. Please log in again.", "error")
            return redirect(url_for("login"))

        # Check if session is expired
        expiry_time = user_session.get("expiry")
        if expiry_time and datetime.utcnow() > expiry_time:
            mongo.db.sessions.delete_many({"email": email})  # Remove expired session
            session.clear()
            flash("Your session has expired. Please log in again.", "error")
            return redirect(url_for("login"))

# Middleware to require login
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user" not in session:
            flash("Please log in to access this page.", "warning")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function

# Function to clean AI response text
def clean_text(text):
    text = re.sub(r"\*\*|\*", "", text)  # Remove **bold** and *italic* symbols
    text = text.replace("\n", "<br>")  # Convert new lines to HTML breaks
    return text

# Function to fetch YouTube video link for plant disease treatment
def get_youtube_video(query):
    try:
        youtube = build("youtube", "v3", developerKey=GOOGLE_API_KEY)
        search_response = youtube.search().list(
            q=query,
            part="snippet",
            maxResults=1,
            type="video"
        ).execute()

        if search_response.get("items", []):
            video_id = search_response["items"][0]["id"]["videoId"]
            return f"https://www.youtube.com/watch?v={video_id}"
        return "No relevant video found."
    except Exception as e:
        return f"Error fetching video: {str(e)}"

# Function to analyze plant disease (Image)
def analyze_disease_image(image_data, language="en"):
    try:
        model = genai.GenerativeModel("gemini-1.5-flash")
        encoded_image = base64.b64encode(image_data).decode("utf-8")

        response = model.generate_content([
            {"role": "user", "parts": [{"inline_data": {"mime_type": "image/jpeg", "data": encoded_image}}]},
            {"role": "user", "parts": [{"text": f"Identify the plant disease and provide its name, causes, and treatment. Respond in {LANGUAGES[language]}."}]}
        ])

        raw_text = response.text if hasattr(response, "text") else "No response from AI."
        cleaned_text = clean_text(raw_text)
        disease_name = cleaned_text.split("<br>")[0]
        youtube_video = get_youtube_video(disease_name + " disease treatment")

        return cleaned_text + f"<br><br>📺 Watch this video: <a href='{youtube_video}' target='_blank'>{youtube_video}</a>"
    except Exception as e:
        return f"Error processing image: {str(e)}"

# Function to analyze plant disease (Text Description)
def analyze_disease_description(description, language="en"):
    try:
        model = genai.GenerativeModel("gemini-1.5-flash")
        
        # Step 1: Detect the language of the description
        detection_prompt = f"Detect the language of this text: '{description}'. Return only the language code (e.g., 'en', 'kn', 'hi', 'sp', 'te')."
        detection_response = model.generate_content([{"role": "user", "parts": [{"text": detection_prompt}]}])
        detected_lang = detection_response.text.strip() if hasattr(detection_response, "text") else "en"
        logger.debug(f"Detected language of description: {detected_lang}")

        # Step 2: Determine the response language
        if language == "none":  # If "Auto" is selected
            response_lang = detected_lang if detected_lang in LANGUAGES else "en"
            logger.debug(f"Language set to 'Auto'; responding in detected language: {response_lang}")
        else:
            response_lang = language if language in LANGUAGES else "en"
            logger.debug(f"User-selected language: {response_lang}")
        
        # Step 3: Generate response in the determined language
        prompt = (
            f"Based on this description: '{description}', identify the plant disease and provide its name, causes, and treatment. "
            f"Respond only in {LANGUAGES[response_lang]}, do not include any other language."
        )
        response = model.generate_content([{"role": "user", "parts": [{"text": prompt}]}])

        raw_text = response.text if hasattr(response, "text") else f"No response from AI in {LANGUAGES[response_lang]}."
        cleaned_text = clean_text(raw_text)
        disease_name = cleaned_text.split("<br>")[0] if "<br>" in cleaned_text else cleaned_text
        youtube_video = get_youtube_video(disease_name + " disease treatment")

        return cleaned_text + f"<br><br>📺 Watch this video: <a href='{youtube_video}' target='_blank'>{youtube_video}</a>"
    except Exception as e:
        return f"Error processing description: {str(e)}"

# Function to analyze crop growth from image
def analyze_crop_growth_image(image_data):
    try:
        model = genai.GenerativeModel("gemini-1.5-flash")
        encoded_image = base64.b64encode(image_data).decode("utf-8")

        prompt = (
            "Analyze this crop image and provide a growth report including current growth stage, health status (healthy, stressed, or poor), "
            "and any recommendations. Respond in English."
        )
        response = model.generate_content([
            {"role": "user", "parts": [{"inline_data": {"mime_type": "image/jpeg", "data": encoded_image}}]},
            {"role": "user", "parts": [{"text": prompt}]}
        ])

        raw_text = response.text if hasattr(response, "text") else "No analysis available."
        cleaned_text = clean_text(raw_text)
        return cleaned_text
    except Exception as e:
        return f"Error analyzing crop growth: {str(e)}"

# Function to send email
def send_email(to_email, subject, body):
    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['From'] = EMAIL_ADDRESS
    msg['To'] = to_email

    try:
        with smtplib.SMTP('smtp.gmail.com', 587) as server:
            server.starttls()
            server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
            server.send_message(msg)
        logger.debug(f"Email sent to {to_email}")
    except Exception as e:
        logger.error(f"Email sending error: {str(e)}")

def get_weather(lat, lon):
    logger.debug(f"Fetching weather for lat: {lat}, lon: {lon}")
    try:
        url = f"https://api.openweathermap.org/data/2.5/forecast?lat={lat}&lon={lon}&appid={OPENWEATHER_API_KEY}&units=metric"
        logger.debug(f"Requesting URL: {url}")
        response = requests.get(url)
        data = response.json()

        logger.debug(f"API Response Status: {response.status_code}")
        logger.debug(f"API Response Data: {data}")

        if response.status_code == 200:
            location = data["city"]["name"]
            forecast = []
            daily_data = {}
            for entry in data["list"]:
                date = datetime.fromtimestamp(entry["dt"]).strftime("%Y-%m-%d")
                if date not in daily_data and len(daily_data) < 7:  # Limit to 7 days
                    chance_of_rain = entry.get("pop", 0) * 100
                    daily_data[date] = {
                        "date": date,
                        "temperature": entry["main"]["temp"],
                        "humidity": entry["main"]["humidity"],
                        "wind_speed": entry["wind"]["speed"],
                        "description": entry["weather"][0]["description"],
                        "icon": f"https://openweathermap.org/img/wn/{entry['weather'][0]['icon']}@2x.png",
                        "chance_of_rain": round(chance_of_rain, 1)
                    }
            forecast = list(daily_data.values())
            logger.debug(f"Forecast Data: {forecast}")
            return {"location": location, "forecast": forecast}
        else:
            error_message = data.get("message", "Unknown error")
            logger.error(f"API Error: {error_message}")
            return {"error": f"Unable to fetch weather details: {error_message}"}
    except Exception as e:
        logger.error(f"Exception occurred: {str(e)}")
        return {"error": f"Error fetching weather: {str(e)}"}

# Routes
@app.route("/")
def index():
    if "user" not in session:
        return redirect(url_for("login"))

    recent_comments = list(comments_collection.find().sort("timestamp", -1).limit(3))
    feedback_list = []
    for comment in recent_comments:
        email = comment["email"]
        user_rating = ratings_collection.find_one({"email": email}, sort=[("timestamp", -1)])
        feedback_list.append({
            "email": email,
            "comment": comment["comment"],
            "rating": user_rating["rating"] if user_rating else None,
            "timestamp": comment["timestamp"]
        })

    return render_template("index.html", feedback_list=feedback_list)

@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'static'), 'favicon.ico', mimetype='image/vnd.microsoft.icon')

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name")
        email = request.form.get("email")
        password = request.form.get("password")

        existing_user = mongo.db.users.find_one({"email": email})
        if existing_user:
            flash("Email already registered. Please log in.", "warning")
            return redirect(url_for("login"))

        hashed_password = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
        mongo.db.users.insert_one({"name": name, "email": email, "password": hashed_password})
        flash("Registration successful! Please log in.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")

        user = mongo.db.users.find_one({"email": email})
        if not user or not bcrypt.checkpw(password.encode("utf-8"), user["password"]):
            flash("Invalid email or password. Try again!", "error")
            return redirect(url_for("login"))
        
        app.permanent_session_lifetime = timedelta(days=1)
        session_token = secrets.token_hex(32)
        expiry_time = datetime.utcnow() + timedelta(days=1)

        mongo.db.sessions.update_one(
            {"email": email},
            {"$set": {"session_token": session_token, "expiry": expiry_time}},
            upsert=True
        )

        session["user"] = email
        session.permanent = True
        flash("Login successful!", "success")
        logger.debug("Redirecting to index...")
        return redirect(url_for("index"))

    return render_template("login.html")

@app.route("/logout")
def logout():
    if "user" in session:
        email = session["user"]
        mongo.db.sessions.delete_many({"email": email})
        session.clear()
        flash("You have been logged out.", "info")
    return redirect(url_for("login"))

@app.route("/submit_rating", methods=["POST"])
@login_required
def submit_rating():
    data = request.get_json()
    rating = data.get("rating")

    if not rating or not isinstance(rating, int) or rating < 1 or rating > 5:
        return jsonify({"success": False, "message": "Invalid rating"}), 400

    rating_entry = {"email": session["user"], "rating": rating, "timestamp": datetime.utcnow()}
    ratings_collection.insert_one(rating_entry)
    return jsonify({"success": True, "message": "Rating submitted successfully"})

@app.route("/submit_comment", methods=["POST"])
@login_required
def submit_comment():
    data = request.get_json()
    comment = data.get("comment")

    if not comment or len(comment) > 500:
        return jsonify({"success": False, "message": "Invalid comment"}), 400

    comment_entry = {"email": session["user"], "comment": comment, "timestamp": datetime.utcnow()}
    comments_collection.insert_one(comment_entry)
    return jsonify({"success": True, "message": "Comment submitted successfully"})

@app.route("/chatbot", methods=["POST"])
@login_required
def agriculture_chatbot():
    logger.debug("Received request to /chatbot")
    try:
        data = request.json
        logger.debug(f"Request data: {data}")
        user_query = data.get("query")
        selected_language = data.get("language", "none")

        if not user_query:
            return jsonify({"error": "Please enter a question"}), 400

        model = genai.GenerativeModel("gemini-1.5-flash")
        detection_prompt = f"Detect the language of this text: '{user_query}'. Return only the language code (e.g., 'en', 'kn', 'hi', 'sp', 'te')."
        detection_response = model.generate_content([{"role": "user", "parts": [{"text": detection_prompt}]}])
        detected_lang = detection_response.text.strip() if hasattr(detection_response, "text") else "en"
        logger.debug(f"Detected language: {detected_lang}")

        if selected_language == "none":
            response_lang = detected_lang if detected_lang in LANGUAGES else "en"
            logger.debug(f"Selected language is 'none'; using detected language: {response_lang}")
        else:
            response_lang = selected_language if selected_language in LANGUAGES else "en"
            logger.debug(f"Selected language provided: {response_lang}")

        chat_prompt = (
            f"Agriculture expert chatbot. Answer this question: '{user_query}'. "
            f"Respond only in {LANGUAGES[response_lang]}, do not include any other language."
        )
        response = model.generate_content([{"role": "user", "parts": [{"text": chat_prompt}]}])

        raw_text = response.text if hasattr(response, "text") else f"No response from AI in {LANGUAGES[response_lang]}."
        cleaned_text = clean_text(raw_text)
        logger.debug(f"Response: {cleaned_text}")
        
        return jsonify({
            "response": cleaned_text,
            "detected_language": detected_lang,
            "response_language": response_lang,
            "reset_language_to": "none"
        })
    except Exception as e:
        logger.error(f"Error: {str(e)}")
        return jsonify({"error": f"Error processing request: {str(e)}"}), 500

@app.route("/disease_detection")
@login_required
def disease_detection():
    return render_template("disease_detection.html", languages=LANGUAGES)

@app.route("/upload", methods=["POST"])
@login_required
def upload_image_or_description():
    language = request.form.get("language", "en")

    if "image" in request.files and request.files["image"].filename != "":
        image = request.files["image"]
        img = Image.open(image)
        img_bytes = io.BytesIO()
        if img.mode == "RGBA":
            img = img.convert("RGB")
        img.save(img_bytes, format="JPEG")
        img_data = img_bytes.getvalue()
        result = analyze_disease_image(img_data, language)
        return jsonify({"disease_info": result})

    elif "description" in request.form and request.form["description"].strip() != "":
        description = request.form["description"]
        result = analyze_disease_description(description, language)
        return jsonify({"disease_info": result})

    return jsonify({"error": "Please provide an image or a description"}), 400

@app.route("/weather_forecast")
@login_required
def weather_page():
    return render_template("weather.html")

@app.route("/weather", methods=["POST"])
@login_required
def weather():
    data = request.json
    if not data:
        return jsonify({"error": "No data provided"}), 400

    lat = data.get("latitude")
    lon = data.get("longitude")

    if not lat or not lon:
        return jsonify({"error": "Latitude and Longitude are required"}), 400

    weather_data = get_weather(lat, lon)
    return jsonify(weather_data)

@app.route("/cropgrowthanalysis")
@login_required
def crop_growth_analysis():
    records = crop_data_collection.find({"email": session["user"]}).sort("timestamp", -1)
    formatted_records = []
    for record in records:
        photo_data = record.get("photo_data")
        if photo_data:
            encoded_photo = base64.b64encode(photo_data).decode('utf-8')
            formatted_records.append({
                "date": record.get("date", record.get("timestamp", datetime.utcnow())).strftime('%Y-%m-%d'),
                "activity": record.get("activity", "N/A"),
                "growth_report": record.get("growth_report", "N/A"),
                "photo": encoded_photo
            })
        else:
            formatted_records.append({
                "date": record.get("timestamp", datetime.utcnow()).strftime('%Y-%m-%d'),
                "activity": "N/A",
                "growth_report": "N/A",
                "photo": None
            })
    return render_template("cropgrowthanalysis.html", records=formatted_records)

@app.route("/daily-crop-analysis", methods=["POST"])
@login_required
def daily_crop_analysis():
    logger.debug("Received request to /daily-crop-analysis")
    try:
        if "cropPhoto" not in request.files:
            return jsonify({"success": False, "message": "No photo uploaded"}), 400
        photo = request.files["cropPhoto"]
        activity = request.form.get("activity", "No activity recorded")

        if photo.filename == "":
            return jsonify({"success": False, "message": "No photo selected"}), 400

        # Save photo and analyze
        img = Image.open(photo)
        img_bytes = io.BytesIO()
        if img.mode == "RGBA":
            img = img.convert("RGB")
        img.save(img_bytes, format="JPEG")
        img_data = img_bytes.getvalue()
        growth_report = analyze_crop_growth_image(img_data)

        # Store in MongoDB
        record = {
            "email": session["user"],
            "photo_data": img_data,
            "activity": activity,
            "date": datetime.utcnow(),
            "growth_report": growth_report
        }
        crop_data_collection.insert_one(record)

        # Send report email
        user = users_collection.find_one({"email": session["user"]})
        if user:
            subject = f"Crop Growth Report - {datetime.utcnow().strftime('%Y-%m-%d')}"
            body = f"Dear {user['name']},\n\nHere is your daily crop growth report:\n{growth_report}\n\nActivity: {activity}\n\nBest,\nSmartAgri Team"
            send_email(user["email"], subject, body)

        return jsonify({"success": True, "message": "Record saved and report sent"})
    except Exception as e:
        logger.error(f"Error in daily crop analysis: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500

# Daily reminder check (to be run via scheduler)
def check_daily_reminders():
    logger.debug("Running daily reminder check")
    today = datetime.utcnow().date()
    users = users_collection.find()
    for user in users:
        last_record = crop_data_collection.find_one({"email": user["email"]}, sort=[("date", -1)])
        if last_record and last_record.get("date", datetime.utcnow().date()) == today:
            continue  # Skip if photo was uploaded today
        send_email(user["email"], "Crop Monitoring Reminder", "Reminder: No photo uploaded today. Please upload your crop photo.")

@app.route("/analyze_crop_growth", methods=["POST"])
@login_required
def analyze_crop_growth():
    logger.debug("Received request to /analyze_crop_growth")
    try:
        data = request.json
        logger.debug(f"Request data: {data}")
        if not data:
            return jsonify({"error": "No data provided"}), 400

        required_fields = ["crop_type", "location"]
        for field in required_fields:
            if field not in data or not data[field]:
                return jsonify({"error": f"Missing required field: {field}"}), 400

        crop_type = data["crop_type"]
        location = data["location"]
        planting_date = data.get("planting_date", "Not provided")
        soil_quality = data.get("soil_quality", "Not provided")

        planting_date_str = "Not provided"
        planting_date_obj = None
        if planting_date != "Not provided":
            try:
                planting_date = planting_date.replace("/", "-")
                planting_date_obj = datetime.strptime(planting_date, "%d-%m-%Y")
                planting_date_str = planting_date_obj.strftime("%Y-%m-%d")
            except ValueError:
                return jsonify({"error": "Invalid planting date format. Use DD-MM-YYYY or DD/MM/YYYY."}), 400

        current_date = datetime(2025, 3, 25)
        next_month_date = current_date + timedelta(days=30)
        next_month_date_str = next_month_date.strftime("%Y-%m-%d")

        days_since_planting = 0
        days_to_next_month = 30
        if planting_date_obj:
            days_since_planting = (current_date - planting_date_obj).days
            if days_since_planting < 0:
                return jsonify({"error": "Planting date cannot be in the future."}), 400
            days_to_next_month = days_since_planting + 30

        weather_url = f"http://api.openweathermap.org/data/2.5/weather?q={location}&appid={OPENWEATHER_API_KEY}&units=metric"
        weather_response = requests.get(weather_url)
        if weather_response.status_code != 200 or "main" not in weather_response.json():
            return jsonify({"error": "Invalid location or weather API error"}), 400
        
        weather_data = weather_response.json()
        current_temperature = weather_data["main"]["temp"]
        current_humidity = weather_data["main"]["humidity"]
        current_weather_conditions = weather_data["weather"][0]["description"]

        prompt = (
            f"As an agriculture expert, predict {crop_type} growth accurately:\n"
            f"- Crop Type: {crop_type}\n"
            f"- Location: {location}\n"
            f"- Planting Date: {planting_date_str}\n"
            f"- Soil Quality: {soil_quality}\n"
            f"- Current Date: 2025-03-25\n"
            f"- Prediction Date: {next_month_date_str}\n"
            f"- Days Since Planting: {days_since_planting} days\n"
            f"- Total Days to Prediction: {days_to_next_month} days\n"
            f"- Current Temperature: {current_temperature}C\n"
            f"- Current Humidity: {current_humidity}%\n"
            f"- Current Weather: {current_weather_conditions}\n"
            f"Crop-specific growth guidelines:\n"
            f"- Arecanut: 20-50 cm/year (0-2 years), 50-100 cm/year (2+ years), max 2000 cm\n"
            f"- Wheat: 0.5-0.7 cm/day (first 60 days), then slows, max 100 cm\n"
            f"Calculate height for {next_month_date_str} based on total days from planting:\n"
            f"1. Use growth rates for {crop_type} (or reasonable estimate if unknown).\n"
            f"2. Adjust height: +5% for loamy soil, -10% if outside optimal season.\n"
            f"3. Optimal seasons: Arecanut (May-Jun), Wheat (Oct-Dec).\n"
            f"Return exactly five lines in this format:\n"
            f"Growth Status: [Optimal, Poor, or Needs Attention]\n"
            f"Reason: [one sentence, max 10 words]\n"
            f"Best Planting Period: [e.g., May to June]\n"
            f"Height Next Month: [e.g., 367 cm]\n"
            f"Next Month Status: [e.g., bearing fruit]\n"
            f"If planting date is 'Not provided', assume today (2025-03-25).\n"
            f"Ensure height is realistic, in cm, and never below 10 cm.\n"
            f"Use only letters, numbers, spaces, hyphens, and 'cm'."
        )

        model = genai.GenerativeModel("gemini-1.5-flash")
        response = model.generate_content([{"role": "user", "parts": [{"text": prompt}]}])
        
        raw_text = response.text if hasattr(response, "text") else (
            "Growth Status: Needs Attention\n"
            "Reason: No AI response\n"
            "Best Planting Period: Unknown\n"
            "Height Next Month: 100 cm\n"
            "Next Month Status: unknown"
        )
        logger.debug(f"Gemini Raw Response: {raw_text}")

        lines = raw_text.split("\n")
        growth_status = "Needs Attention"
        growth_reason = "No reason provided"
        best_planting_period = "Unknown"
        height_next_month = "100 cm"
        next_month_status = "unknown"
        
        for line in lines:
            line = line.strip()
            if line.startswith("Growth Status:"):
                growth_status = line.replace("Growth Status:", "").strip()
            elif line.startswith("Reason:"):
                growth_reason = line.replace("Reason:", "").strip()
            elif line.startswith("Best Planting Period:"):
                best_planting_period = line.replace("Best Planting Period:", "").strip()
            elif line.startswith("Height Next Month:"):
                height_next_month = line.replace("Height Next Month:", "").strip()
            elif line.startswith("Next Month Status:"):
                next_month_status = line.replace("Next Month Status:", "").strip()

        valid_statuses = ["Optimal", "Poor", "Needs Attention"]
        if growth_status not in valid_statuses:
            growth_status = "Needs Attention"
            growth_reason = "AI returned invalid status"

        if not best_planting_period or len(best_planting_period.split()) < 3:
            best_planting_period = "Unknown" if crop_type not in ["Arecanut", "Wheat"] else (
                "May to June" if crop_type == "Arecanut" else "October to November"
            )

        if not height_next_month.endswith("cm") or not any(c.isdigit() for c in height_next_month):
            height_next_month = "100 cm"
            growth_reason = "AI failed to provide valid height"
        else:
            try:
                height_value = float(height_next_month.replace("cm", "").strip())
                if height_value < 10:
                    height_next_month = "10 cm"
                    growth_reason = "Height adjusted to minimum 10 cm"
            except ValueError:
                height_next_month = "100 cm"
                growth_reason = "Invalid height format"

        if not next_month_status:
            next_month_status = "unknown"

        growth_status = re.sub(r"[^a-zA-Z0-9\s\-]", "", growth_status)
        growth_reason = re.sub(r"[^a-zA-Z0-9\s\-]", "", growth_reason)
        best_planting_period = re.sub(r"[^a-zA-Z0-9\s\-]", "", best_planting_period)
        height_next_month = re.sub(r"[^a-zA-Z0-9\s\-cm]", "", height_next_month)
        next_month_status = re.sub(r"[^a-zA-Z0-9\s\-]", "", next_month_status)

        logger.debug(f"Parsed - Growth Status: {growth_status}, Reason: {growth_reason}, "
                     f"Best Planting Period: {best_planting_period}, Height Next Month: {height_next_month}, "
                     f"Next Month Status: {next_month_status}")

        crop_record = {
            "email": session["user"],
            "crop_type": crop_type,
            "location": location,
            "planting_date": planting_date_str,
            "soil_quality": soil_quality,
            "weather_conditions": current_weather_conditions,
            "temperature": current_temperature,
            "humidity": current_humidity,
            "growth_status": growth_status,
            "growth_reason": growth_reason,
            "best_planting_period": best_planting_period,
            "height_next_month": height_next_month,
            "next_month_status": next_month_status,
            "days_since_planting": days_since_planting,
            "days_to_next_month": days_to_next_month,
            "timestamp": datetime.utcnow()
        }
        crop_data_collection.insert_one(crop_record)

        return jsonify({"message": "Crop growth data saved successfully!", "data": crop_record})
    except Exception as e:
        logger.error(f"Error: {str(e)}")
        return jsonify({"error": f"Error processing request: {str(e)}"}), 500

@app.route("/irrigation_plan", methods=["GET", "POST"])
@login_required
def irrigation_plan():
    logger.debug("Received request to /irrigation_plan")
    if request.method == "GET":
        return render_template("irrigation_plan.html")

    try:
        data = request.json
        logger.debug(f"Request data: {data}")
        if not data:
            return jsonify({"error": "No data provided"}), 400

        required_fields = ["crop_type", "location"]
        for field in required_fields:
            if field not in data or not data[field]:
                return jsonify({"error": f"Missing required field: {field}"}), 400

        crop_type = data["crop_type"]
        location = data["location"]
        planting_date = data.get("planting_date", "Not provided")
        growth_stage = data.get("growth_stage", "Not provided")

        planting_date_str = "Not provided"
        if planting_date != "Not provided":
            try:
                planting_date = planting_date.replace("/", "-")
                planting_date_obj = datetime.strptime(planting_date, "%d-%m-%Y")
                planting_date_str = planting_date_obj.strftime("%Y-%m-%d")
            except ValueError:
                return jsonify({"error": "Invalid planting date format. Use DD-MM-YYYY or DD/MM/YYYY."}), 400

        weather_url = f"http://api.openweathermap.org/data/2.5/weather?q={location}&appid={OPENWEATHER_API_KEY}&units=metric"
        weather_response = requests.get(weather_url).json()

        if "main" not in weather_response:
            return jsonify({"error": "Invalid location"}), 400

        temperature = weather_response["main"]["temp"]
        humidity = weather_response["main"]["humidity"]
        weather_conditions = weather_response["weather"][0]["description"]

        prompt = (
            f"As an irrigation expert, create a plan for this crop:\n"
            f"- Crop Type: {crop_type}\n"
            f"- Location: {location}\n"
            f"- Planting Date: {planting_date_str}\n"
            f"- Growth Stage: {growth_stage}\n"
            f"- Current Temperature: {temperature}C\n"
            f"- Current Humidity: {humidity}%\n"
            f"- Current Weather: {weather_conditions}\n"
            f"For {location} (Bangalore, India):\n"
            f"- Typical October: 25-28C, moderate rain\n"
            f"- Typical November: 20-25C, dry\n"
            f"- Typical December: 18-23C, dry\n"
            f"Return exactly three lines in this format:\n"
            f"Irrigation Frequency: [e.g., daily, weekly]\n"
            f"Water Amount: [e.g., X liters per hectare]\n"
            f"Reason: [one sentence, max 10 words]\n"
            f"Base plan on current weather and typical seasonal conditions.\n"
            f"Use only letters, numbers, spaces, and hyphens."
        )

        model = genai.GenerativeModel("gemini-1.5-flash")
        response = model.generate_content([{"role": "user", "parts": [{"text": prompt}]}])
        
        raw_text = response.text if hasattr(response, "text") else "Irrigation Frequency: weekly\nWater Amount: 5000 liters per hectare\nReason: Default irrigation plan"
        logger.debug(f"Gemini Raw Response: {raw_text}")

        lines = raw_text.split("\n")
        irrigation_frequency = "weekly"
        water_amount = "5000 liters per hectare"
        reason = "Default irrigation plan"
        
        for line in lines:
            line = line.strip()
            if line.startswith("Irrigation Frequency:"):
                irrigation_frequency = line.replace("Irrigation Frequency:", "").strip()
            elif line.startswith("Water Amount:"):
                water_amount = line.replace("Water Amount:", "").strip()
            elif line.startswith("Reason:"):
                reason = line.replace("Reason:", "").strip()

        irrigation_frequency = re.sub(r"[^a-zA-Z0-9\s\-]", "", irrigation_frequency)
        water_amount = re.sub(r"[^a-zA-Z0-9\s\-]", "", water_amount)
        reason = re.sub(r"[^a-zA-Z0-9\s\-]", "", reason)

        irrigation_record = {
            "email": session["user"],
            "crop_type": crop_type,
            "location": location,
            "planting_date": planting_date_str,
            "growth_stage": growth_stage,
            "temperature": temperature,
            "humidity": humidity,
            "weather_conditions": weather_conditions,
            "irrigation_frequency": irrigation_frequency,
            "water_amount": water_amount,
            "reason": reason,
            "timestamp": datetime.utcnow()
        }
        irrigation_plans_collection.insert_one(irrigation_record)

        return jsonify({"message": "Irrigation plan saved successfully!", "data": irrigation_record})
    except Exception as e:
        logger.error(f"Error: {str(e)}")
        return jsonify({"error": f"Error processing request: {str(e)}"}), 500

@app.route("/forum")
@login_required
def forum():
    return render_template("forum.html")

@app.route("/submit_crop_data", methods=["POST"])
@login_required
def submit_crop_data():
    global global_topic_id
    try:
        # Initialize Hedera testnet client
        client = Client.forTestnet()

        # Load credentials from environment
        account_id = os.getenv("HEDERA_ACCOUNT_ID")
        private_key = os.getenv("HEDERA_PRIVATE_KEY")

        if not account_id or not private_key:
            return jsonify({"status": "error", "message": "Missing Hedera credentials"}), 500

        client.setOperator(AccountId.fromString(account_id), PrivateKey.fromString(private_key))

        # Create new topic only if one hasn't been created
        if not global_topic_id:
            tx_response = TopicCreateTransaction().execute(client)
            receipt = tx_response.getReceipt(client)
            global_topic_id = receipt.topicId

        # Extract crop data
        data = request.form.get('crop_data')
        if not data:
            return jsonify({"status": "error", "message": "No crop data provided"}), 400

        # Submit message to Hedera topic
        TopicMessageSubmitTransaction() \
            .setTopicId(global_topic_id) \
            .setMessage(data.encode()) \
            .execute(client)

        # Log record in MongoDB
        blockchain_record = {
            "email": session["user"],
            "data": data,
            "timestamp": datetime.utcnow(),
            "topic_id": str(global_topic_id)
        }
        mongo.db.blockchain_records.insert_one(blockchain_record)

        return jsonify({"status": "success", "message": "Data submitted to blockchain"})
    except Exception as e:
        logger.error(f"Blockchain error: {str(e)}")
        return jsonify({"status": "error", "message": f"Blockchain error: {str(e)}"}), 500

# New route to save a post to MongoDB with AI fact-checking
@app.route('/post', methods=['POST'])
@login_required
def post():
    logger.debug("Accessing /post route. Session user: %s", session.get("user", "No session"))
    try:
        content = request.form.get('content')
        if not content:
            return jsonify({"status": "error", "message": "No content provided"}), 400

        # AI fact-checking for agriculture relevance and factual accuracy
        logger.debug("Performing AI fact-check on: %s", content)
        model = genai.GenerativeModel("gemini-1.5-flash")
        response = model.generate_content(
            f"Is this statement related to agriculture and factually correct? Consider crop water requirements (e.g., wheat needs 20-30 cm per season is correct). Statement: {content}. Respond with 'true' or 'false'."
        )
        is_fact_checked = response.text.strip().lower() == 'true'
        logger.debug("AI fact-check result: %s", is_fact_checked)

        if is_fact_checked:
            # Store in MongoDB
            post_id = posts_collection.insert_one({
                'content': content,
                'timestamp': datetime.utcnow(),
                'votes': {'likes': 0, 'dislikes': 0},
                'email': session['user'],
                'comments': []
            }).inserted_id
            logger.debug("Post saved to MongoDB with ID: %s", str(post_id))
            return jsonify({"status": "success", "message": "Post saved"})
        else:
            # Send email notification
            user_email = session['user']
            subject = "Incorrect or Non-Agriculture Information in Forum Post"
            body = f"Dear user,\n\nThe post you submitted ('{content}') was flagged as either incorrect or not related to agriculture by our AI fact-checking system. Please review and resubmit accurate agriculture-related information.\n\nBest,\nSmartAgri Team"
            send_email(user_email, subject, body)
            logger.debug("Email sent to %s for incorrect post", user_email)
            return jsonify({"status": "error", "message": "Post rejected due to incorrect or non-agriculture content. Notification sent."})
    except Exception as e:
        logger.error("Error in /post: %s", str(e), exc_info=True)
        return jsonify({"status": "error", "message": f"Server error: {str(e)}"}), 500

@app.route('/posts', methods=['GET'])
@login_required
def get_posts():
    logger.debug("Accessing /posts route. Session user: %s", session.get("user", "No session"))
    try:
        search_query = request.args.get('search', '').lower()
        logger.debug("Search query: %s", search_query)
        posts_cursor = posts_collection.find().sort('timestamp', -1)
        if search_query:
            posts_cursor = posts_collection.find({'content': {'$regex': search_query, '$options': 'i'}}).sort('timestamp', -1)
        logger.debug("Posts cursor raw: %s", list(posts_cursor.clone()))  # Clone to avoid cursor exhaustion
        posts = [{
            '_id': str(post['_id']),
            'content': post['content'],
            'likes': post['votes'].get('likes', 0),
            'dislikes': post['votes'].get('dislikes', 0),
            'timestamp': post['timestamp'].isoformat(),
            'email': post.get('email', 'anonymous'),
            'comments': post.get('comments', [])
        } for post in posts_cursor]
        logger.debug("Returning posts: %s", posts)
        return jsonify(posts)
    except Exception as e:
        logger.error("Error in /posts: %s", str(e), exc_info=True)
        return jsonify({"error": f"Server error: {str(e)}"}), 500

# New route to handle voting (like/dislike) on a post
@app.route('/vote', methods=['POST'])
@login_required
def vote():
    logger.debug("Accessing /vote route. Session user: %s", session.get("user"))
    try:
        post_id = request.form.get('postId')
        action = request.form.get('action')  # 'like' or 'dislike'
        if not post_id or action not in ['like', 'dislike']:
            return jsonify({'status': 'error', 'message': 'Invalid vote data'}), 400

        update_field = f'votes.{action}s'  # e.g., 'votes.likes' or 'votes.dislikes'
        post = posts_collection.find_one_and_update(
            {'_id': ObjectId(post_id)},
            {'$inc': {update_field: 1}},  # Increment the specific vote type
            return_document=True
        )
        if post:
            return jsonify({'status': 'success', 'message': 'Vote updated'})
        return jsonify({'status': 'error', 'message': 'Post not found'}), 404
    except Exception as e:
        logger.error("Error in /vote: %s", str(e), exc_info=True)
        return jsonify({'status': 'error', 'message': str(e)}), 500

# New route to add a comment to a post
@app.route('/comment', methods=['POST'])
@login_required
def comment():
    logger.debug("Accessing /comment route. Session user: %s", session.get("user"))
    try:
        post_id = request.form.get('postId')
        content = request.form.get('content')
        if not post_id or not content:
            return jsonify({'status': 'error', 'message': 'Post ID and content are required'}), 400

        comment_data = {
            'content': content,
            'email': session["user"],
            'timestamp': datetime.utcnow()
        }
        posts_collection.update_one(
            {'_id': ObjectId(post_id)},
            {'$push': {'comments': comment_data}}
        )
        logger.debug("Comment added to post %s: %s", post_id, comment_data)
        return jsonify({'status': 'success', 'message': 'Comment added'})
    except Exception as e:
        logger.error("Comment error: %s", str(e), exc_info=True)
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/comments', methods=['GET'])
def get_comments():
    post_id = request.args.get('post_id')
    if not post_id:
        return jsonify({'status': 'error', 'message': 'Post ID required'}), 400
    try:
        comments = list(comments_collection.find({'post_id': post_id}).sort('timestamp', -1))
        for comment in comments:
            comment['_id'] = str(comment['_id'])
        return jsonify(comments)
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

# New route to delete a post
@app.route('/delete_post', methods=['POST'])
@login_required
def delete_post():
    post_id = request.form.get('postId')
    if not post_id:
        return jsonify({'status': 'error', 'message': 'Post ID is required'}), 400
    try:
        post = posts_collection.find_one({'_id': ObjectId(post_id), 'email': session["user"]})
        if not post:
            return jsonify({'status': 'error', 'message': 'Post not found or unauthorized'}), 404
        posts_collection.delete_one({'_id': ObjectId(post_id)})
        return jsonify({'status': 'success', 'message': 'Post deleted successfully'})
    except Exception as e:
        logger.error(f"Delete post error: {str(e)}", exc_info=True)
        return jsonify({'status': 'error', 'message': str(e)}), 500

if __name__ == "__main__":
    # Schedule daily reminder check (use a scheduler like APScheduler in production)
    check_daily_reminders()
    print(f"Server running at http://127.0.0.1:5000")
    app.run(debug=True)