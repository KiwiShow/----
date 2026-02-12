import requests
from bs4 import BeautifulSoup
import sqlite3
import time
import random
import datetime
import re
from urllib.parse import urljoin

# Configuration
BASE_URL = "https://www.pbc.gov.cn/zhengcehuobisi/125207/125213/125431/5492845/b0da893b-1.html"
HOST_URL = "https://www.pbc.gov.cn"
DB_PATH = "data.db"
MAX_PAGES = 10
TIMEOUT = 15
MAX_CONSECUTIVE_DUPLICATES = 3  # Stop crawling after finding this many existing items in a row

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

DATE_PATTERN = re.compile(r'(\d{4}[-年]\d{1,2}[-月]\d{1,2}[日]?)')

def get_current_time_str():
    """Returns current UTC+8 time string."""
    return (datetime.datetime.utcnow() + datetime.timedelta(hours=8)).strftime('%Y-%m-%d %H:%M:%S')

def init_db():
    """Initialize the SQLite database."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS announcements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT,
                link TEXT UNIQUE,
                content TEXT,
                publish_date TEXT,
                crawled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()
        print("Database initialized.")
    except sqlite3.Error as e:
        print(f"Database error: {e}")
    finally:
        if conn:
            conn.close()

def get_soup(url):
    """Helper to fetch URL and return BeautifulSoup object."""
    try:
        response = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        response.encoding = 'utf-8' # Force UTF-8 for Chinese characters
        if response.status_code == 200:
            return BeautifulSoup(response.text, 'html.parser')
        else:
            print(f"Failed to fetch {url}: Status {response.status_code}")
            return None
    except requests.RequestException as e:
        print(f"Error fetching {url}: {e}")
        return None

def format_table(table):
    """Formats HTML table to text with aligned columns."""
    rows = []
    for tr in table.find_all('tr'):
        cells = [cell.get_text(strip=True) for cell in tr.find_all(['td', 'th'])]
        rows.append(cells)
    
    if not rows:
        return ""
    
    # Helper to calculate visual width (East Asian Width approximation)
    def get_width(s):
        return sum(2 if ord(c) > 127 else 1 for c in s)
    
    # Calculate max width for each column
    num_cols = max(len(r) for r in rows) if rows else 0
    col_widths = [0] * num_cols
    
    for row in rows:
        for i, cell in enumerate(row):
            if i < num_cols:
                w = get_width(cell)
                if w > col_widths[i]:
                    col_widths[i] = w
    
    # Format table rows
    table_lines = []
    for row in rows:
        line_parts = []
        for i, cell in enumerate(row):
            if i < num_cols:
                # Padding: target width - current width + 4 spaces
                padding = " " * (col_widths[i] - get_width(cell) + 4)
                line_parts.append(cell + padding)
        table_lines.append("".join(line_parts).rstrip())
    
    return "\n" + "\n".join(table_lines) + "\n"

def scrape_detail(url):
    """Scrape title, content, and date from a detail page."""
    soup = get_soup(url)
    if not soup:
        return None, None

    # Try to find content - PBOC pages usually have a main content area
    content_div = soup.find('div', {'id': 'zoom'}) or soup.find('div', class_='content')
    
    content = ""
    if content_div:
        # Remove script and style tags
        for script in content_div(["script", "style"]):
            script.decompose()

        # Process tables: convert to formatted text
        for table in content_div.find_all('table'):
            formatted_table = format_table(table)
            table.replace_with(formatted_table)

        content = content_div.get_text(separator='\n', strip=True)
    
    # Try to find date
    date = "Unknown"
    
    # Priority 0: Check specifically for span id="shijian"
    shijian_span = soup.find('span', id='shijian')
    if shijian_span:
        date = shijian_span.get_text(strip=True)

    # Priority 1: Check header info area
    if date == "Unknown":
        info_row = soup.find('td', class_='hui12')
        if info_row:
            match = DATE_PATTERN.search(info_row.get_text())
            if match:
                date = match.group(1)
            
    # Priority 2: Check last few lines of content
    if date == "Unknown" and content:
        lines = content.split('\n')
        for line in reversed(lines[-5:]): # Check last 5 lines
            match = DATE_PATTERN.search(line)
            if match:
                date = match.group(1)
                break
                
    return content, date

def is_duplicate(cursor, url):
    """Check if URL already exists in database."""
    cursor.execute("SELECT id FROM announcements WHERE link = ?", (url,))
    return cursor.fetchone() is not None

def extract_list_date(a_tag):
    """Try to extract date from list item context."""
    list_date = None
    if a_tag.parent:
        parent_text = a_tag.parent.get_text(separator=' ', strip=True)
        match = DATE_PATTERN.search(parent_text)
        if match:
            list_date = match.group(1)
    
    if not list_date and a_tag.parent and a_tag.parent.parent:
        grandparent_text = a_tag.parent.parent.get_text(separator=' ', strip=True)
        match = DATE_PATTERN.search(grandparent_text)
        if match:
            list_date = match.group(1)
    return list_date

def get_next_page(soup, current_url):
    """Find the next page URL."""
    # Try finding by text
    next_link_tag = soup.find('a', string=re.compile(r'下一页|Next'))
    
    if not next_link_tag:
         # Try text content search if direct match fails
         for a in soup.find_all('a'):
             if "下一页" in a.get_text():
                 next_link_tag = a
                 break
    
    if next_link_tag:
        href = next_link_tag.get('href') or next_link_tag.get('tagname')
        if href and href != '#':
            return urljoin(current_url, href)
    
    return None

def run_crawler():
    """Main crawler function."""
    init_db()
    print(f"Starting crawl of {BASE_URL}...")
    
    links_found = 0
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    current_url = BASE_URL
    page_count = 0
    consecutive_duplicates = 0
    stop_crawling = False
    
    try:
        while current_url and page_count < MAX_PAGES and not stop_crawling:
            page_count += 1
            print(f"Scraping page {page_count}: {current_url}")
            
            soup = get_soup(current_url)
            if not soup:
                break
                
            # Extract items
            # Find all links, but filter relevant ones first to avoid processing nav links
            all_links = soup.find_all('a')
            
            for a_tag in all_links:
                href = a_tag.get('href')
                if not href:
                    continue
                    
                full_url = urljoin(current_url, href)
                title = a_tag.get_text(strip=True)
                
                # Filter: must be a sub-page and have meaningful title length
                # Basic heuristics to identify article links
                is_article = (
                    "index.html" in full_url 
                    and len(title) > 5 
                    and BASE_URL.split('/')[-2] in full_url
                )
                
                if is_article:
                    if is_duplicate(cursor, full_url):
                        print(f"Skipping existing: {title}")
                        consecutive_duplicates += 1
                        if consecutive_duplicates >= MAX_CONSECUTIVE_DUPLICATES:
                            print(f"Stopping crawl: Found {MAX_CONSECUTIVE_DUPLICATES} consecutive duplicates.")
                            stop_crawling = True
                            break
                        continue
                    else:
                        consecutive_duplicates = 0  # Reset counter on new item

                    # Process new item
                    list_date = extract_list_date(a_tag)
                    print(f"Scraping: {title} (List Date: {list_date})")
                    
                    content, detail_date = scrape_detail(full_url)
                    final_date = list_date if list_date else detail_date
                    
                    if content:
                        cursor.execute('''
                            INSERT INTO announcements (title, link, content, publish_date, crawled_at)
                            VALUES (?, ?, ?, ?, ?)
                        ''', (title, full_url, content, final_date, get_current_time_str()))
                        conn.commit()
                        links_found += 1
                        time.sleep(random.uniform(0.5, 1.5))

            if stop_crawling:
                break

            # Pagination
            next_page_link = get_next_page(soup, current_url)
            if next_page_link and next_page_link != current_url:
                current_url = next_page_link
                time.sleep(random.uniform(1, 2))
            else:
                print("No next page found or reached end.")
                break
                
    except Exception as e:
        print(f"Crawler error: {e}")
    finally:
        conn.close()
        print(f"Crawl finished. Added {links_found} new records.")
        
    return links_found

if __name__ == "__main__":
    run_crawler()
