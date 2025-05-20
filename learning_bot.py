import requests
import time
import json
import os
import re
import hashlib
from datetime import datetime
from newspaper import Article

# ===== CONFIGURATION =====

NEWS_API_KEY = os.getenv("NEWS_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

MAX_ARTICLES = 30  # Max number of articles to analyze and send

# Model to use - options include: "gemini-2.0-flash", "gemini-2.0-pro", "gemini-1.5-flash", "gemini-1.5-pro"
GEMINI_MODEL = "gemini-2.0-flash-lite"

# Keywords to search (in lowercase)
KEYWORD_GROUPS = [
    [
        "AI",
        "Artificial Intelligence",
        "ChatGPT",
        "LLM",
        "Large Language Models",
        "deepseek",
        "Claude",
        "GPT-4",
        "GPT-5",
        "Anthropic",
        "OpenAI",
    ],
    [
        "Automation",
        "automation tools",
        "RPA",
        "Robotic Process Automation",
        "Cybersecurity",
        "cyber security",
        "infosec",
        "hacked",
        "data breach",
        "zero-day",
        "network security",
        "phishing",
        "malware",
        "ransomware",
    ],
]

# ===== FUNCTIONS =====


def load_processed_urls():
    path = "processed_urls.txt"
    if not os.path.exists(path):
        return set()
    with open(path, "r") as f:
        return set(line.strip() for line in f.readlines())


def fetch_full_article(url):
    try:
        article = Article(url)
        article.download()
        article.parse()
        return article.text
    except Exception as e:
        print(f"❌ Failed to fetch full content from {url}: {str(e)}")
        return None


def save_processed_urls(urls):
    with open("processed_urls.txt", "a") as f:
        for url in urls:
            f.write(url + "\n")


def fetch_articles_by_keywords(keywords):
    """Fetch news articles from News API for a given list of keywords"""
    url = "https://newsapi.org/v2/everything"
    headers = {"X-Api-Key": NEWS_API_KEY}
    query = " OR ".join(keywords)

    params = {
        "q": query,
        "language": "en",
        "sortBy": "publishedAt",
        "pageSize": MAX_ARTICLES,
    }

    print(f"📊 Fetching articles with keywords: {query}")
    response = requests.get(url, headers=headers, params=params)
    if response.status_code != 200:
        raise Exception(f"News API Error: {response.status_code}, {response.text}")

    data = response.json()
    return data.get("articles", [])


def analyze_with_gemini(articles):
    """Send articles to Gemini API for analysis using the official Google genai library"""
    if not articles:
        return "No articles found to analyze."

    try:
        # Import the Google genai library
        from google import genai
        from google.genai import types
    except ImportError:
        raise Exception(
            "Google genai library not installed. Install it with: pip install google-generativeai"
        )

    # Prepare articles data for Gemini
    enriched_articles = []

    print("📰 Enriching articles with full content...")

    for article in articles:
        full_text = fetch_full_article(article["url"])
        enriched_articles.append(
            {
                "title": article.get("title", ""),
                "description": article.get("description", ""),
                "source": article.get("source", {}).get("name", ""),
                "url": article.get("url", ""),
                "published": article.get("publishedAt", ""),
                "image": article.get("urlToImage", ""),
                "content": full_text or "",
            }
        )

    # Create prompt for Gemini
    prompt = f"""
        You're a tech news analyst. Your job is to extract deep insights from a list of articles about AI, automation, and cybersecurity.

        ### Task:
        - Categorize each article as: **AI**, **Automation**, or **Security**.
        - Read the full content to summarize **key developments**, **implications**, or **industry trends**.
        - Provide only 1–2 impactful sentences per article.
        - Add the link in markdown `[Title](url)` and show source.
        - If a category has no important news, write “No major updates today.”

        ### Format:

        ## AI  
        **[Article Title](URL)**  
        _Summary_  
        <i>Source: SourceName</i>

        ## Automation  
        ...

        ## Security  
        ...

        Here are the articles (with full content included):

        {json.dumps(articles, indent=2)}

        Only output in markdown as per the structure above. Do not add anything else.
        """

    print("🤖 Sending to Gemini API for analysis...")

    # Create a client instance
    client = genai.Client(api_key=GEMINI_API_KEY)

    # Set generation config
    generation_config = types.GenerateContentConfig(
        temperature=0.2, top_k=40, top_p=0.95, max_output_tokens=8192
    )

    # Call Gemini API using the official client
    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,  # Using the configured model
            contents=prompt,
            config=generation_config,
        )

        # Get the text from the response
        analysis = response.text
        print("✅ Analysis received from Gemini")
        return analysis
    except Exception as e:
        raise Exception(f"Gemini API Error: {str(e)}")


def format_articles_basic(articles):
    """Format articles as a simple markdown list"""
    if not articles:
        return "No relevant news articles found."

    lines = ["📰 *Latest AI / Automation / Cybersecurity News:*"]
    for i, article in enumerate(articles, 1):
        title = article.get("title", "No title")
        url = article.get("url", "")
        source = article.get("source", {}).get("name", "")
        lines.append(f"\n*{i}. {title}* \n_Source: {source}_\n[Read more]({url})")

    return "\n".join(lines)


def send_to_telegram(message, image_url=None):
    """Send message (and optionally an image) to Telegram using HTML formatting."""
    base_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

    # Step 1: Send the image first (if available)
    if image_url:
        photo_payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "photo": image_url,
            "caption": "🖼️ Top Headline Image",
        }
        photo_response = requests.post(f"{base_url}/sendPhoto", data=photo_payload)
        if photo_response.status_code != 200:
            print(f"⚠️ Failed to send image: {photo_response.text}")

    # Step 2: Prepare HTML-formatted text
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    header = f"🔍 <b>AI & TECH NEWS MARKET ANALYSIS</b>\n<code>{timestamp}</code>\n\n"

    # Convert markdown-ish Gemini output to HTML
    content = message
    content = re.sub(r"## (.*?)(\n|$)", r"<b>\1</b>\n", content)
    content = re.sub(r"# (.*?)(\n|$)", r"<b>\1</b>\n", content)
    content = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", content)
    content = re.sub(r"_(.*?)_", r"<i>\1</i>", content)
    content = re.sub(r"\[(.*?)\]\((.*?)\)", r'<a href="\2">\1</a>', content)

    html_message = header + content

    # Step 3: Split message if too long
    max_length = 4096
    if len(html_message) <= max_length:
        parts = [html_message]
    else:
        parts = []
        current = ""
        for paragraph in html_message.split("\n\n"):
            if len(current) + len(paragraph) + 2 <= max_length:
                current += "\n\n" + paragraph if current else paragraph
            else:
                parts.append(current)
                current = paragraph
        if current:
            parts.append(current)

    # Step 4: Send all parts
    for i, msg in enumerate(parts):
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": msg,
            "parse_mode": "HTML",
            "disable_web_page_preview": False,
        }
        response = requests.post(f"{base_url}/sendMessage", data=payload)
        if response.status_code != 200:
            print(f"❌ Failed to send message part {i+1}: {response.text}")
        time.sleep(1)


def save_analysis(analysis, articles):
    """Save the analysis and articles to a file for reference"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    directory = "news_analysis"

    # Create directory if it doesn't exist
    if not os.path.exists(directory):
        os.makedirs(directory)

    # Save the full analysis
    with open(f"{directory}/analysis_{timestamp}.md", "w", encoding="utf-8") as f:
        f.write("# AI, Automation and Cybersecurity News Analysis\n\n")
        f.write(f"*Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*\n\n")
        f.write("## Analysis\n\n")
        f.write(analysis)
        f.write("\n\n## Raw Articles Data\n\n")
        f.write(
            json.dumps(
                [
                    {
                        "title": article.get("title", ""),
                        "description": article.get("description", ""),
                        "source": article.get("source", {}).get("name", ""),
                        "url": article.get("url", ""),
                        "published": article.get("publishedAt", ""),
                    }
                    for article in articles
                ],
                indent=2,
            )
        )

    print(f"📄 Analysis saved to {directory}/analysis_{timestamp}.md")


# ===== MAIN FUNCTION =====


def main():
    try:
        print("🔍 Starting news analysis process...")

        all_articles = []
        seen_urls = set()
        processed_urls = load_processed_urls()

        for group in KEYWORD_GROUPS:
            articles = fetch_articles_by_keywords(group)
            for article in articles:
                url = article.get("url")
                if url and url not in seen_urls and url not in processed_urls:
                    seen_urls.add(url)
                    all_articles.append(article)

        if not all_articles:
            print("❌ No new articles found.")
            return

        print(f"✅ Total unique articles collected: {len(all_articles)}")

        # Limit to MAX_ARTICLES total
        all_articles = all_articles[:MAX_ARTICLES]

        analysis = analyze_with_gemini(all_articles)
        save_analysis(analysis, all_articles)

        print("📤 Sending analysis to Telegram...")
        # Pick top article that has an image
        top_image = next(
            (a.get("urlToImage") for a in all_articles if a.get("urlToImage")), None
        )
        send_to_telegram(analysis, image_url=top_image)

        save_processed_urls([article.get("url") for article in all_articles])
        print("✅ Process completed successfully!")

    except Exception as e:
        error_message = f"❌ Error: {str(e)}"
        print(error_message)
        try:
            send_to_telegram(f"⚠️ NEWS ANALYSIS ERROR\n\n{error_message}")
        except Exception as te:
            print(f"Could not send error message to Telegram: {str(te)}")


# Run the script
if __name__ == "__main__":
    main()
