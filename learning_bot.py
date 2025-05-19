# learning_bot.py

import os
import requests
from datetime import datetime
import feedparser

# Load secrets from GitHub Actions environment
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")


def get_today_task():
    task_schedule = {
        1: "Learn about the OSI model and how each layer interacts.",
        2: "Install and explore Zabbix. Try to monitor local CPU usage.",
        3: "Write a Bash script to ping a host and log downtime.",
        4: "Learn prompt engineering basics. Try zero-shot vs few-shot examples in ChatGPT.",
    }
    start_date = datetime(2025, 5, 18)
    day_number = (datetime.now() - start_date).days + 1
    return task_schedule.get(day_number, "🎉 You're done or no task set for today!")


def get_news():
    feeds = [
        "https://feeds.arstechnica.com/arstechnica/technology-lab",
        "https://www.reddit.com/r/sysadmin/.rss",
        "https://www.reddit.com/r/devops/.rss",
        "https://www.reddit.com/r/LLM/.rss",
    ]
    headlines = []
    for url in feeds:
        feed = feedparser.parse(url)
        for entry in feed.entries[:2]:
            headlines.append(f"• {entry.title} - {entry.link}")
    return headlines[:6]


def send_to_telegram(task, news_list):
    message = f"📚 *Today's Learning Goal:*\n{task}\n\n🗞️ *Tech News:*\n"
    for news in news_list:
        message += f"{news}\n"

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown"}
    response = requests.post(url, data=data)
    print("Sent message:", response.text)


if __name__ == "__main__":
    task = get_today_task()
    news = get_news()
    send_to_telegram(task, news)
