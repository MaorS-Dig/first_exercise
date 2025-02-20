import time
import redis
import os
import subprocess
import requests
from flask import Flask, request, jsonify,render_template,send_from_directory

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

    print(f"✅ File saved to: {saved_path}")  # Debugging log
    return saved_path


@app.route('/video/<filename>')
def serve_video(filename):
    video_directory = "/app/videos/"  

    video_path = os.path.join(video_directory, filename)
    if not os.path.exists(video_path):
        return "File not found", 404

    print(f"📢 Serving video from: {video_path}")  
    return send_from_directory(video_directory, filename)

@app.route('/watch')
def watch_video():
        return render_template("watch.html")


'''
In order to trim a video making a POST request with an mp4 Public file and start+end times is needed.
Can use curl -X POST http://127.0.0.1:8000/trim \
     -H "Content-Type: application/json" \
     -d '{
           "url": "your_video_file.mp4",
           "start": "00:00:30",
           "end": "00:01:00"
         }'
'''
@app.route('/trim', methods=['POST'])
def trim_video():
    data = request.json
    url = data.get('url')
    start = data.get('start')  # Format: HH:MM:SS or seconds
    end = data.get('end')  # Format: HH:MM:SS or seconds
    
    if not url or start is None or end is None:
        return jsonify({"error": "Missing parameters (url, start, end)"}), 400
    
    try:
        response = requests.get(url, stream=True)
        if response.status_code != 200:
            return jsonify({"error": "Failed to fetch video from URL"}), 400
        
        temp_input = "temp_input.mp4"
        temp_output = "temp_output_trimmed.mp4"
        
        
        with open(temp_input, "wb") as f:
            for chunk in response.iter_content(chunk_size=1024):
                f.write(chunk)
        
        
        command = [
            "ffmpeg", "-i", temp_input,
            "-ss", str(start), "-to", str(end),
            "-c", "copy", temp_output
        ]
        
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        if os.path.exists(temp_input):
            os.remove(temp_input)

        if result.returncode != 0:
            return jsonify({"error": "FFmpeg processing failed", "details": result.stderr.decode()}), 500

        save_file(temp_output)  # Save the file in the project root

        # Return the video URL to be displayed on the webpage
        return jsonify({"message": "Processing complete", "redirect_url": "/watch"}), 200
    


    except Exception as e:
        return jsonify({"error": "An error occurred", "details": str(e)}), 500
    finally:
        if os.path.exists(temp_input):
            os.remove(temp_input)


'''
In order to trim a video making a POST request with an mp4 Public file and start+end times is needed.
Can use curl -X POST http://127.0.0.1:8000/extract_audio \
     -H "Content-Type: application/json" \
     -d '{
           "url": "your_video_file.mp4",
           "start": "00:00:30",
           "end": "00:01:00"
         }'
'''
@app.route('/extract_audio', methods=['POST'])
def extract_audio():
    data = request.json
    url = data.get('url')
    start = data.get('start')  # Format: HH:MM:SS or seconds
    end = data.get('end')  # Format: HH:MM:SS or seconds

    if not url or start is None or end is None:
        return jsonify({"error": "Missing parameters (url, start, end)"}), 400

    temp_input = "temp_input.mp4"
    temp_output = "temp_output_audio.mp3"

    try:
        response = requests.get(url, stream=True)
        if response.status_code != 200:
            return jsonify({"error": "Failed to fetch video from URL"}), 400

        with open(temp_input, "wb") as f:
            for chunk in response.iter_content(chunk_size=1024):
                f.write(chunk)

        command = [
            "ffmpeg", "-i", temp_input,
            "-ss", str(start), "-to", str(end),
            "-q:a", "0", "-map", "a", temp_output
        ]

        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode != 0:
            return jsonify({"error": "FFmpeg processing failed", "details": result.stderr.decode()}), 500

        saved_path = save_file(temp_output)  

        return jsonify({"message": "Processing complete", "saved_path": saved_path}), 200

    except Exception as e:
        return jsonify({"error": "An error occurred", "details": str(e)}), 500

    finally:
        if os.path.exists(temp_input):
            os.remove(temp_input)