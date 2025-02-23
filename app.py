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
    os.makedirs(save_directory, exist_ok=True)  # Ensure the folder exists

    saved_path = os.path.join(save_directory, os.path.basename(file_path))
    os.rename(file_path, saved_path)  # Move the file

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


@app.route('/trim', methods=['POST'])
def trim_video():
    data = request.json
    url = data.get('url')
    start = data.get('start')
    end = data.get('end')

    if not url or start is None or end is None:
        return jsonify({"error": "Missing parameters (url, start, end)"}), 400

    try:
        # Fetch the video
        response = requests.get(url, stream=True)
        if response.status_code != 200:
            return jsonify({"error": "Failed to fetch video from URL"}), 400

        temp_input = "temp_input.mp4"
        temp_output = "output_video.mp4"  # Fixed output name

        # Save the fetched video
        with open(temp_input, "wb") as f:
            for chunk in response.iter_content(chunk_size=1024):
                f.write(chunk)

        # Run ffmpeg to trim the video
        command = [
            "ffmpeg", "-i", temp_input,
            "-ss", str(start), "-to", str(end),
            "-c", "copy", temp_output
        ]

        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        # Clean up the temporary input file
        if os.path.exists(temp_input):
            os.remove(temp_input)

        # Check for errors
        if result.returncode != 0:
            return jsonify({"error": "FFmpeg processing failed", "details": result.stderr.decode()}), 500

        # Save the video to the desired directory
        saved_video_path = save_file(temp_output)

        # Redirect to the page that will show the video
        return jsonify({"video_filename": os.path.basename(saved_video_path)})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/extract_audio', methods=['POST'])
def extract_audio():
    data = request.json
    url = data.get('url')
    start = data.get('start')  # Format: HH:MM:SS or seconds
    end = data.get('end')  # Format: HH:MM:SS or seconds

    if not url or start is None or end is None:
        return jsonify({"error": "Missing parameters (url, start, end)"}), 400

    try:
        # Fetch the video file
        response = requests.get(url, stream=True)
        if response.status_code != 200:
            return jsonify({"error": "Failed to fetch video from URL"}), 400

        temp_input = "temp_input.mp4"
        temp_output = f"extracted_audio.mp3"  # Output audio file name

        # Save the fetched video file
        with open(temp_input, "wb") as f:
            for chunk in response.iter_content(chunk_size=1024):
                f.write(chunk)

        # Extract audio from the video
        command = [
            "ffmpeg", "-i", temp_input,
            "-ss", str(start), "-to", str(end),
            "-q:a", "0", "-map", "a", temp_output
        ]

        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        # Clean up temporary video input file
        if os.path.exists(temp_input):
            os.remove(temp_input)

        if result.returncode != 0:
            return jsonify({"error": "FFmpeg processing failed", "details": result.stderr.decode()}), 500

        # Save the audio to the desired directory
        saved_audio_path = save_file(temp_output)

        # Redirect to the page that will show the extracted audio
        return jsonify({"audio_filename": os.path.basename(saved_audio_path)})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/process/<file_type>', methods=['GET'])
def process_page(file_type):
    filename = request.args.get(f'{file_type}_filename')
    if not filename:
        return "File not found", 404

    # Serve video/audio based on the file_type
    if file_type == "video":
        return render_template('trim_video.html', video_filename=filename)
    elif file_type == "audio":
        return render_template('extract_audio.html', audio_filename=filename)
    else:
        return "Invalid file type", 400
