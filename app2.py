import os
import re
from dotenv import load_dotenv
from flask import Flask, request, jsonify, render_template
import requests
import json
import sqlite3
from flask_cors import CORS
from openai import OpenAI

load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_API_KEY)

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=True)

# Set API key
UNSPLASH_ACCESS_KEY = os.getenv("UNSPLASH_ACCESS_KEY")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
# ---------------------
# OpenAI API features
# ---------------------

# Chat history storage
messages = [{"role": "assistant", "content": "How can I help?"}]

# A function that displays chat history
def display_chat_history(messages):
    for message in messages:
        print(f"{message['role'].capitalize()}: {message['content']}")

# Get assistant response
def get_assistant_response(messages):
    try:
        r = client.chat.completions.create(
            model="gpt-4",
            messages=[{"role": m["role"], "content": m["content"]} for m in messages],
        )
        response = r.choices[0].message.content
        return response
    except Exception as e:
        return f"Error: {str(e)}"

# Chat interface
@app.route('/query', methods=['POST'])
def query():
    try:
        data = request.json
        prompt = data.get("prompt", "")
        messages.append({"role": "user", "content": prompt})  # Add user input to chat history
        
        # Get the assistant response and add it to the chat history
        response = get_assistant_response(messages)
        messages.append({"role": "assistant", "content": response})
        
        # Return to full chat history
        return jsonify({
            "status": "success",
            "data": {
                "chat_history": messages
            }
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})


# ---------------------
# Unsplash API 
# ---------------------
@app.route('/image', methods=['GET'])
def get_image():
    topic = request.args.get('topic', 'biology')
    try:
        url = f"https://api.unsplash.com/search/photos?query={topic}&client_id={UNSPLASH_ACCESS_KEY}"
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            if data['results']:
                return jsonify({"url": data['results'][0]['urls']['regular']})
        return jsonify({"error": "No image found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ---------------------
# YouTube API 
# ---------------------
def fetch_video(topic):
    url = f"https://www.googleapis.com/youtube/v3/search?part=snippet&type=video&q={topic}&key={YOUTUBE_API_KEY}"
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        if data['items']:
            # Extract the video ID and generate an embedded link
            video_id = data['items'][0]['id']['videoId']
            embed_url = f"https://www.youtube.com/embed/{video_id}"
            return embed_url
    return None

# ---------------------
# SQLite 
# ---------------------
def init_db():
    conn = sqlite3.connect("quiz.db")
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS user_results (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT,
        topic TEXT,
        score INTEGER
    )
    """)
    conn.commit()
    conn.close()

@app.route('/quiz', methods=['GET'])
def get_quiz():
    topic = request.args.get('topic', 'biology')
    num_questions = int(request.args.get('num_questions', 3))
    dynamic_questions = generate_quiz(topic, num_questions)
    return jsonify({"topic": topic, "questions": dynamic_questions})

def parse_quiz_from_text(text):
    
    questions = []
    lines = text.split("\n")
    question = None
    options = []
    correct_answer = None

    for line in lines:
        # matching problem
        if re.match(r"^\d+\.", line.strip()):
            if question:  # Save the previous question
                questions.append({
                    "question": question,
                    "options": options,
                    "answer": correct_answer
                })
            question = line.strip()
            options = []
            correct_answer = None

        elif re.match(r"^[A-D]\.", line.strip()):  # Matching option
            option_text = line.strip()
            if "[Correct]" in option_text:  # Check to see if there is a correct answer mark
                correct_answer = option_text.split("[Correct]")[0].strip()  # Extract the correct answer
                option_text = correct_answer  # Remove [Correct] from options
            options.append(option_text)
  
    if question:
        questions.append({
            "question": question,
            "options": options,
            "answer": correct_answer
        })

    return questions

def generate_quiz(topic, num_questions=3):
    try:
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are an assistant helping teachers create quiz questions for students aged 10 to 12."},
                {"role": "user", "content": f"Create {num_questions} multiple-choice quiz questions about {topic}. Each question should have 4 options, and the correct one should be marked."}
            ]
        )
        quiz_content = response.choices[0].message.content
        try:
            return json.loads(quiz_content)
        except json.JSONDecodeError:
            return parse_quiz_from_text(quiz_content)
    except Exception as e:
        print(f"Error in generate_quiz: {e}")
        return {"error": str(e)}


@app.route('/quiz', methods=['POST'])
def submit_quiz():
    try:
        data = request.json
        username = data.get('username', 'Anonymous')
        topic = data.get('topic', 'biology')
        answers = data.get('answers', {})
        correct_answers = {"question1": "A", "question2": "C"}  # Sample correct answer
        score = sum(1 for q, a in answers.items() if correct_answers.get(q) == a)

        conn = sqlite3.connect("quiz.db")
        cursor = conn.cursor()
        cursor.execute("INSERT INTO user_results (username, topic, score) VALUES (?, ?, ?)",
                       (username, topic, score))
        conn.commit()
        conn.close()

        return jsonify({"status": "success", "score": score})
    except sqlite3.Error as db_error:
        return jsonify({"status": "error", "message": f"Database error: {db_error}"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@app.route('/video', methods=['GET'])
def get_video():
    topic = request.args.get('topic', 'biology')
    embed_url = fetch_video(topic)
    if embed_url:
        return jsonify({"url": embed_url})
    else:
        return jsonify({"error": "No video found"}), 404

@app.route('/')
def home():
    # Render the index.html template
    return render_template("index2.html")

@app.route('/api')
def api_info():
    # Return JSON information
    return jsonify({
        "message": "Welcome to the BioQuest API!",
        "endpoints": {
            "/chat": "POST - Interact with the chatbox.",
            "/quiz": "GET/POST - Generate or submit quiz results.",
            "/image": "GET - Get an image related to a topic.",
            "/video": "GET - Get a video related to a topic."
        }
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
