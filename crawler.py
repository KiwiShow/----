import requests
from bs4 import BeautifulSoup
import sqlite3
import time
import random
import datetime
from urllib.parse import urljoin

# Configuration
BASE_URL = "https://www.pbc.gov.cn/zhengcehuobisi/125207/125213/125431/5492845/b0da893b-1.html"
HOST_URL = "https://www.pbc.gov.cn"
DB_PATH = "data.db"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

def init_db():
    """Initialize the SQLite database."""
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
    conn.close()
    print("Database initialized.")

def get_soup(url):
    """Helper to fetch URL and return BeautifulSoup object."""
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.encoding = 'utf-8' # Force UTF-8 for Chinese characters
        if response.status_code == 200:
            return BeautifulSoup(response.text, 'html.parser')
        else:
            print(f"Failed to fetch {url}: Status {response.status_code}")
            return None
    except Exception as e:
        print(f"Error fetching {url}: {e}")
        return None

def scrape_detail(url):
    """Scrape title, content, and date from a detail page."""
    soup = get_soup(url)
    if not soup:
        return None, None, None

    # Try to find content - PBOC pages usually have a main content area
    # Adjust selectors based on typical government site structures
    # Often id="zoom" or class="content"
    content_div = soup.find('div', {'id': 'zoom'}) or soup.find('div', class_='content')
    
    content = ""
    if content_div:
        # Remove script and style tags
        for script in content_div(["script", "style"]):
            script.decompose()

        # Process tables: convert to formatted text
        for table in content_div.find_all('table'):
            rows = []
            for tr in table.find_all('tr'):
                cells = [cell.get_text(strip=True) for cell in tr.find_all(['td', 'th'])]
                rows.append(cells)
            
            if not rows:
                continue
            
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
                        # Padding: target width - current width
                        padding = " " * (col_widths[i] - get_width(cell) + 4) # 4 spaces extra padding
                        line_parts.append(cell + padding)
                table_lines.append("".join(line_parts).rstrip())
            
            formatted_table = "\n" + "\n".join(table_lines) + "\n"
            table.replace_with(formatted_table)

        content = content_div.get_text(separator='\n', strip=True)
    
    # Try to find date - often in a specific span or div with class 'hui12' or similar
    # Or parsed from the bottom right
    date = "Unknown"
    
    # Common pattern for date in title area or bottom
    # Strategy: Look for text matching date pattern YYYY-MM-DD
    import re
    date_pattern = re.compile(r'(\d{4}[-年]\d{1,2}[-月]\d{1,2}[日]?)')
    
    # Priority 0: Check specifically for span id="shijian"
    shijian_span = soup.find('span', id='shijian')
    if shijian_span:
        date = shijian_span.get_text(strip=True)

    # Check the whole page text for date if not found in specific location
    # Priority: Header info area
    info_row = soup.find('td', class_='hui12') # Common in older gov sites
    if info_row:
        match = date_pattern.search(info_row.get_text())
        if match:
            date = match.group(1)
            
    # If not found, try searching in the last few lines of content (often the "signature" date)
    if date == "Unknown" and content:
        lines = content.split('\n')
        for line in reversed(lines[-5:]): # Check last 5 lines
            match = date_pattern.search(line)
            if match:
                date = match.group(1)
                break
                
    return content, date

def run_crawler():
    init_db()
    print(f"Starting crawl of {BASE_URL}...")
    
    import re
    date_pattern_str = r'(\d{4}[-年]\d{1,2}[-月]\d{1,2}[日]?)'
    date_pattern = re.compile(date_pattern_str)
    
    links_found = 0
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    current_url = BASE_URL
    page_count = 0
    stop_crawling = False  # Flag to control when to stop completely
    
    while current_url and page_count < 10 and not stop_crawling: # Safety limit
        page_count += 1
        print(f"Scraping page {page_count}: {current_url}")
        
        soup = get_soup(current_url)
        if not soup:
            break
            
        # Extract items
        for a_tag in soup.find_all('a'):
            href = a_tag.get('href')
            if not href:
                continue
                
            full_url = urljoin(current_url, href)
            title = a_tag.get_text(strip=True)
            
            # Filter: URL must be a sub-page (roughly) and Title must not be empty
            if "index.html" in full_url and len(title) > 5 and BASE_URL.split('/')[-2] in full_url:
                
                cursor.execute("SELECT id FROM announcements WHERE link = ?", (full_url,))
                if cursor.fetchone():
                    print(f"Skipping existing: {title}")
                    continue

                # Try to extract date from list
                list_date = None
                if a_tag.parent:
                    parent_text = a_tag.parent.get_text(separator=' ', strip=True)
                    match = date_pattern.search(parent_text)
                    if match:
                        list_date = match.group(1)
                
                if not list_date and a_tag.parent and a_tag.parent.parent:
                    grandparent_text = a_tag.parent.parent.get_text(separator=' ', strip=True)
                    match = date_pattern.search(grandparent_text)
                    if match:
                        list_date = match.group(1)
                
                print(f"Scraping: {title} (List Date: {list_date})")
                content, detail_date = scrape_detail(full_url)
                final_date = list_date if list_date else detail_date
                
                if content:
                    utc_plus_8_time = (datetime.datetime.utcnow() + datetime.timedelta(hours=8)).strftime('%Y-%m-%d %H:%M:%S')
                    cursor.execute('''
                        INSERT INTO announcements (title, link, content, publish_date, crawled_at)
                        VALUES (?, ?, ?, ?, ?)
                    ''', (title, full_url, content, final_date, utc_plus_8_time))
                    conn.commit()
                    links_found += 1
                    time.sleep(random.uniform(0.5, 1.5))

        # If we decided to stop, break the outer loop too
        if stop_crawling:
            break

        # Find Next Page
        next_page_link = None
        # Try finding by text
        next_link_tag = soup.find('a', string=re.compile(r'下一页|Next'))
        
        if not next_link_tag:
             # Try text content
             for a in soup.find_all('a'):
                 if "下一页" in a.get_text():
                     next_link_tag = a
                     break
        
        if next_link_tag:
            href = next_link_tag.get('href')
            if not href:
                # Try 'tagname' attribute (common in PBOC pagination)
                href = next_link_tag.get('tagname')
            
            print(f"Found next page link tag: {next_link_tag}, href: {href}")
            if href and href != '#':
                next_page_link = urljoin(current_url, href)
        else:
            print("Debug: Pagination links found:")
            # Print last few links to check encoding/text
            for a in soup.find_all('a')[-10:]:
                print(f" - {a.get_text(strip=True)}: {a.get('href')}")
        
        if next_page_link and next_page_link != current_url:
            current_url = next_page_link
            time.sleep(random.uniform(1, 2))
        else:
            print("No next page found or reached end.")
            break

    conn.close()
    print(f"Crawl finished. Added {links_found} new records.")
    return links_found

if __name__ == "__main__":
    run_crawler()
