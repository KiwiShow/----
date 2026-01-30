from flask import Flask, render_template, request, jsonify
import sqlite3
import os
import datetime

app = Flask(__name__)
DB_PATH = "data.db"
CRAWL_TIME_FILE = "last_crawl_time.txt"

def get_last_crawl_time():
    if os.path.exists(CRAWL_TIME_FILE):
        with open(CRAWL_TIME_FILE, 'r') as f:
            return f.read().strip()
    return None

def update_last_crawl_time():
    # Use UTC+8
    now = (datetime.datetime.utcnow() + datetime.timedelta(hours=8)).strftime('%Y-%m-%d %H:%M:%S')
    with open(CRAWL_TIME_FILE, 'w') as f:
        f.write(now)
    return now

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/')
def index():
    conn = get_db_connection()
    # Check if table exists
    try:
        announcements = conn.execute('SELECT * FROM announcements ORDER BY publish_date DESC, id DESC').fetchall()
        # Get latest crawl time from file, fallback to DB
        latest_crawl_time = get_last_crawl_time()
        if not latest_crawl_time and announcements:
            # Find the max crawled_at
            latest_crawl_time = max(row['crawled_at'] for row in announcements)
    except sqlite3.OperationalError:
        announcements = []
        latest_crawl_time = None
    conn.close()
    return render_template('index.html', announcements=announcements, latest_crawl_time=latest_crawl_time)

@app.route('/scrape', methods=['POST'])
def trigger_scrape():
    import crawler
    try:
        new_records = crawler.run_crawler()
        
        # Get total count and latest crawl time
        conn = get_db_connection()
        total_records = conn.execute('SELECT COUNT(*) FROM announcements').fetchone()[0]
        conn.close()
        
        # Update and get current time
        current_time = update_last_crawl_time()
        
        return jsonify({
            "status": "success",
            "new_count": new_records,
            "total_count": total_records,
            "latest_crawl_time": current_time
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

if __name__ == '__main__':
    app.run(debug=True, port=5001)
