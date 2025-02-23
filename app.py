import time
import redis
import os
import subprocess
import requests
from flask import *

app = Flask(__name__)
cache = redis.Redis(host='redis', port=6379)

def get_hit_count():
    retries = 5
    while True:
        try:
            return cache.incr('hits')
        except redis.exceptions.ConnectionError as exc:
            if retries == 0:
                raise exc
            retries -= 1
            time.sleep(0.5)

@app.route('/')
def hello():
    count = get_hit_count()
    return render_template('index.html', count=count)


def save_file(file_path):
    save_directory = "/app/videos/"  # Define a fixed directory inside the container
    os.makedirs(save_directory, exist_ok=True)  

    saved_path = os.path.join(save_directory, os.path.basename(file_path))
    os.rename(file_path, saved_path) 


    print(f"✅ File saved to: {saved_path}")  
    return file_path


@app.route('/video/<filename>')
def serve_video(filename):
    video_directory = "/app/videos/"  

    video_path = os.path.join(video_directory, filename)
    if not os.path.exists(video_path):
        return "File not found", 404

    print(f"📢 Serving video from: {video_path}")  
    return send_from_directory(video_directory, filename)


@app.route('/process', methods=['POST'])
def process_file():

    data = request.json
    action = data.get('action')
    url = data.get('url')
    start = data.get('start')
    end = data.get('end')

    if not action or not url or start is None or end is None:
        return jsonify({"error": "Missing parameters (action, url, start, end)"}), 400

    if action not in ['trim', 'extract_audio']:
        return jsonify({"error": "Invalid action type"}), 400

    try:
        # Fetch the video
        response = requests.get(url, stream=True)
        if response.status_code != 200:
            return jsonify({"error": "Failed to fetch video from URL"}), 400

        temp_input = "temp_input.mp4"
        if action == "trim":
            temp_output = "output_video.mp4"  # Fixed output name for trimming
        elif action == "extract_audio":
            temp_output = "extracted_audio.mp3"  # Output name for audio extraction


        # Save the fetched video
        with open(temp_input, "wb") as f:
            for chunk in response.iter_content(chunk_size=1024):
                f.write(chunk)

        # Run ffmpeg based on the action type
        if action == "trim":
            command = [
                "ffmpeg", "-i", temp_input,
                "-ss", str(start), "-to", str(end),
                "-c", "copy", temp_output
            ]
        elif action == "extract_audio":
            command = [
                "ffmpeg", "-i", temp_input,
                "-ss", str(start), "-to", str(end),
                "-q:a", "0", "-map", "a", temp_output
            ]


        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        # Clean up the temporary input file
        if os.path.exists(temp_input):
            os.remove(temp_input)

        # Check for errors
        if result.returncode != 0:
            return jsonify({"error": "FFmpeg processing failed", "details": result.stderr.decode()}), 500

        # Save the video or audio to the desired directory
        saved_file_path = save_file(temp_output)

        # Return the result with the filename
        if action == "trim":
            return jsonify({"video_filename": os.path.basename(saved_file_path)})
        elif action == "extract_audio":
            return jsonify({"audio_filename": os.path.basename(saved_file_path)})


    except Exception as e:
        return jsonify({"error": str(e)}), 500



@app.route('/trim_video/<video_filename>')
def trim_video_page(video_filename):
    return render_template('trim_video.html', video_filename=video_filename)


@app.route('/extract_audio/<audio_filename>')
def extract_audio_page(audio_filename):
    return render_template('extract_audio.html', audio_filename=audio_filename)
