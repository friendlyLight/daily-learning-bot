import requests
import time
import json
import os
import re
import hashlib
from datetime import datetime

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
    articles_data = []
    for article in articles:
        articles_data.append(
            {
                "title": article.get("title", ""),
                "description": article.get("description", ""),
                "source": article.get("source", {}).get("name", ""),
                "url": article.get("url", ""),
                "published": article.get("publishedAt", ""),
            }
        )

    # Create prompt for Gemini
    prompt = f"""
        You are a highly skilled IT analyst. Your task is to process and distill a list of {len(articles)} technology news articles related to **AI**, **Automation**, and **Cybersecurity**.

        Here’s what I need:

        🔹 Only include **highly relevant** and **high-impact** articles.
        🔹 Skip generic or low-signal news (like company PR fluff, funding rounds unless strategic, minor product updates).
        🔹 Categorize each article into one of: **AI**, **Automation**, or **Security**.
        🔹 If unclear, choose the most relevant category — do not duplicate across multiple sections.

        ### Format:

        - Group the content into these sections in this order:
        - ## AI
        - ## Automation
        - ## Security

        - For each article under the correct category, summarize like this:

        **[Article Title](URL)**  
        _Summary in 1–2 sentences_  
        <i>Source: SourceName</i>

        ### Focus:
        - Focus on **emerging trends**, **important research**, **market shifts**, **security threats**, **regulatory updates**, or **significant product developments**.
        - If there are no good articles in a category, say "**No major updates today.**"

        ---

        Here are the raw articles:

        {json.dumps(articles_data, indent=2)}

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


def send_to_telegram(message):
    """Send message to Telegram with proper Markdown handling"""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

    # Clean and escape problematic characters for Telegram's Markdown
    # Escape special characters that could interfere with Markdown parsing
    def clean_markdown(text):
        # Escape special characters that break Telegram markdown
        special_chars = [
            "_",
            "*",
            "[",
            "]",
            "(",
            ")",
            "~",
            "`",
            ">",
            "#",
            "+",
            "-",
            "=",
            "|",
            "{",
            "}",
            ".",
            "!",
        ]
        for char in special_chars:
            # Don't escape if it's part of a markdown link structure
            if char in ["[", "]", "(", ")"]:
                continue
            text = text.replace(char, "\\" + char)

        # Fix links - Telegram requires a protocol (http/https) for URLs
        import re

        # Find markdown links
        link_pattern = r"\[([^\]]+)\]\(([^)]+)\)"

        def fix_link(match):
            link_text = match.group(1)
            url = match.group(2)

            # Ensure URL has protocol
            if not (url.startswith("http://") or url.startswith("https://")):
                url = "https://" + url

            return f"[{link_text}]({url})"

        text = re.sub(link_pattern, fix_link, text)
        return text

    # Process message to ensure compatibility with Telegram's Markdown
    # For the title we'll use bold without markdown
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    header = f"🔍 AI & TECH NEWS MARKET ANALYSIS\n<code>{timestamp}</code>\n\n"

    # For the analysis content, we'll use HTML mode instead of Markdown
    # Convert basic markdown to HTML
    content = message.replace(header, "")

    # Replace markdown headers with HTML
    content = re.sub(r"## (.*?)(\n|$)", r"<b>\1</b>\n", content)
    content = re.sub(r"# (.*?)(\n|$)", r"<b>\1</b>\n", content)

    # Replace markdown bold with HTML bold
    content = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", content)
    content = re.sub(r"\*(.*?)\*", r"<b>\1</b>", content)

    # Replace markdown italic with HTML italic
    content = re.sub(r"_(.*?)_", r"<i>\1</i>", content)

    # Replace markdown links with HTML links
    content = re.sub(r"\[(.*?)\]\((.*?)\)", r'<a href="\2">\1</a>', content)

    # Create the full message with HTML formatting
    html_message = header + content

    # Telegram messages have character limits, split if necessary
    max_length = 4096  # Telegram's max message length

    if len(html_message) <= max_length:
        messages = [html_message]
    else:
        # Simple splitting by finding paragraph boundaries
        messages = []
        current_message = ""
        paragraphs = html_message.split("\n\n")

        for paragraph in paragraphs:
            if len(current_message) + len(paragraph) + 2 <= max_length:
                if current_message:
                    current_message += "\n\n" + paragraph
                else:
                    current_message = paragraph
            else:
                messages.append(current_message)
                current_message = paragraph

        if current_message:
            messages.append(current_message)

    # Send each message part
    for i, msg_part in enumerate(messages):
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": msg_part,
            "parse_mode": "HTML",  # Using HTML instead of Markdown
            "disable_web_page_preview": True,  # Set to False if you want link previews
        }

        response = requests.post(url, data=payload)
        if response.status_code != 200:
            raise Exception(f"Telegram Error: {response.status_code}, {response.text}")

        # Slight delay to avoid rate limits
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
        send_to_telegram(f"🔍 AI & TECH NEWS MARKET ANALYSIS\n\n{analysis}")

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
