import os
import time
import json
import random
import requests
import cloudinary
import cloudinary.uploader
from datetime import datetime, date
from io import BytesIO
import anthropic
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

# ── CONFIG ────────────────────────────────────────────────
ANTHROPIC_API_KEY  = os.environ["ANTHROPIC_API_KEY"]
CLOUDINARY_CLOUD   = os.environ["CLOUDINARY_CLOUD"]
CLOUDINARY_KEY     = os.environ["CLOUDINARY_API_KEY"]
CLOUDINARY_SECRET  = os.environ["CLOUDINARY_SECRET"]
BUFFER_TOKEN       = os.environ["BUFFER_TOKEN"]
TELEGRAM_TOKEN     = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID   = os.environ["TELEGRAM_CHAT_ID"]

# Buffer channels
BUFFER_FB_CHANNEL  = "6a0b3f9e090476fb9932d776"
BUFFER_IG_CHANNEL  = "6a0b4005090476fb9932d92e"
BUFFER_LI_CHANNEL  = "6a0bf7b7090476fb99360b4e"  # Gundrux company page

# Blog sources to scrape topics from
BLOG_SOURCES = [
    "https://webdoux.com/blog/",
    "https://backlinko.com/blog",
    "https://ahrefs.com/blog/",
    "https://moz.com/blog",
    "https://www.semrush.com/blog/",
]

CUSTOM_TOPICS_FILE = "custom_topics.txt"
HISTORY_FILE       = "history.json"

cloudinary.config(
    cloud_name=CLOUDINARY_CLOUD,
    api_key=CLOUDINARY_KEY,
    api_secret=CLOUDINARY_SECRET
)

TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

# ── TELEGRAM HELPERS ─────────────────────────────────────
def tg_send(text, reply_markup=None):
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"}
    if reply_markup:
        data["reply_markup"] = json.dumps(reply_markup)
    return requests.post(f"{TELEGRAM_API}/sendMessage", json=data).json()

def tg_send_photo(image_url, caption, reply_markup=None):
    data = {"chat_id": TELEGRAM_CHAT_ID, "photo": image_url, "caption": caption[:1024], "parse_mode": "HTML"}
    if reply_markup:
        data["reply_markup"] = json.dumps(reply_markup)
    return requests.post(f"{TELEGRAM_API}/sendPhoto", json=data).json()

def tg_answer_callback(callback_id, text=""):
    requests.post(f"{TELEGRAM_API}/answerCallbackQuery", json={"callback_query_id": callback_id, "text": text})

def tg_get_updates(offset=0):
    try:
        resp = requests.get(f"{TELEGRAM_API}/getUpdates", params={"offset": offset, "timeout": 25}, timeout=30)
        return resp.json().get("result", [])
    except:
        return []

# ── HISTORY ──────────────────────────────────────────────
def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE) as f:
                return json.load(f)
        except:
            return []
    return []

def save_history(entry):
    history = load_history()
    history.append(entry)
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=2)

# ── TOPIC SCRAPING (MULTI-SOURCE) ────────────────────────
def scrape_topics_from(url):
    try:
        resp = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0 (compatible; Bot)"})
        soup = BeautifulSoup(resp.text, "html.parser")
        titles = []
        # Try article/h2/h3
        for tag in soup.find_all(["h2", "h3", "h1", "a"]):
            text = tag.get_text(strip=True)
            if 25 < len(text) < 130 and not text.lower().startswith(("subscribe", "sign up", "log in", "menu")):
                titles.append(text)
        return titles[:15]
    except Exception as e:
        print(f"Scrape {url} failed: {e}")
        return []

def scrape_all_sources():
    all_topics = []
    for url in BLOG_SOURCES:
        topics = scrape_topics_from(url)
        print(f"  {url} -> {len(topics)} topics")
        all_topics.extend(topics)
    return all_topics

DEFAULT_TOPICS = [
    "SEO tips for small businesses in 2026",
    "WordPress speed optimization guide",
    "Social media content strategy for brands",
    "Google ranking factors you must know",
    "On-page SEO checklist for beginners",
    "WordPress plugins every business needs",
    "Instagram growth tips for digital agencies",
    "Local SEO strategies that actually work",
    "Content marketing for B2B companies",
    "Technical SEO basics explained",
    "How to use AI for content creation",
    "Common WordPress mistakes to avoid",
    "How to grow a brand on Instagram",
    "Core Web Vitals explained simply",
    "Voice search optimization tips",
    "AI automation for digital marketing agencies",
    "Best AI tools for SEO in 2026",
    "How to do keyword research with AI",
    "Schema markup for better rankings",
    "Link building strategies that work today",
]

def load_topics():
    print("Scraping topics from blog sources...")
    topics = scrape_all_sources()
    if os.path.exists(CUSTOM_TOPICS_FILE):
        with open(CUSTOM_TOPICS_FILE) as f:
            custom = [l.strip() for l in f if l.strip() and not l.startswith("#")]
            topics.extend(custom)
            print(f"  Custom topics: {len(custom)}")
    if len(topics) < 10:
        topics.extend(DEFAULT_TOPICS)
    # Dedupe + filter already-posted
    history = load_history()
    posted = {h.get("topic", "").lower() for h in history if h.get("status") == "approved"}
    fresh = [t for t in set(topics) if t.lower() not in posted]
    print(f"  Total fresh topics: {len(fresh)}")
    return fresh if fresh else list(set(topics))

def pick_topic():
    topics = load_topics()
    return random.choice(topics) if topics else random.choice(DEFAULT_TOPICS)

# ── CLAUDE HAIKU ──────────────────────────────────────────
def generate_content(topic):
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        messages=[{
            "role": "user",
            "content": (
                f"You are a social media expert for Gundrux, a digital marketing agency "
                f"specializing in AI SEO, WordPress, social media growth, and AI automation.\n\n"
                f"Topic: {topic}\n\n"
                f"Return pure JSON only with these keys:\n"
                f"1. title: punchy title max 8 words in English\n"
                f"2. points: exactly 5 actionable tips in English max 12 words each\n"
                f"3. caption: 2-3 engaging lines for social media in English\n"
                f"4. hashtags: 15 relevant hashtags as single string starting with #\n"
                f"5. category: pick one: SEO TIPS / WORDPRESS / SOCIAL MEDIA / AI MARKETING / CONTENT GROWTH\n\n"
                f"Pure JSON only. No markdown."
            )
        }]
    )
    raw = message.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw.strip())

# ── HTML TEMPLATES (3 ROTATING) ──────────────────────────
def template_dark_indigo(c):
    return TEMPLATE_DARK_INDIGO.format(**c)

def template_split_purple(c):
    return TEMPLATE_SPLIT_PURPLE.format(**c)

def template_minimal_neon(c):
    return TEMPLATE_MINIMAL_NEON.format(**c)

TEMPLATES = [template_dark_indigo, template_split_purple, template_minimal_neon]

# Template 1: Dark Indigo with icons
TEMPLATE_DARK_INDIGO = """<!DOCTYPE html><html><head><meta charset="UTF-8">
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800;900&display=swap');
*{{margin:0;padding:0;box-sizing:border-box;}}
body{{width:1080px;height:1080px;overflow:hidden;font-family:'Inter',sans-serif;}}
.post{{width:1080px;height:1080px;background:linear-gradient(135deg,#0D0D1A 0%,#0A0A14 60%,#0D0A1F 100%);position:relative;overflow:hidden;display:flex;flex-direction:column;justify-content:space-between;padding:48px 56px;}}
.grid{{position:absolute;inset:0;background-image:linear-gradient(rgba(99,102,241,0.05) 1px,transparent 1px),linear-gradient(90deg,rgba(99,102,241,0.05) 1px,transparent 1px);background-size:80px 80px;pointer-events:none;}}
.watermark{{position:absolute;bottom:-30px;left:-20px;font-size:220px;font-weight:900;color:rgba(99,102,241,0.06);letter-spacing:-8px;pointer-events:none;z-index:1;white-space:nowrap;}}
.glow1{{position:absolute;top:-150px;left:-150px;width:600px;height:600px;background:radial-gradient(circle,rgba(99,102,241,0.18) 0%,transparent 70%);}}
.glow2{{position:absolute;bottom:-150px;right:-100px;width:500px;height:500px;background:radial-gradient(circle,rgba(139,92,246,0.12) 0%,transparent 70%);}}
.icon-box{{position:absolute;z-index:1;opacity:0.15;width:56px;height:56px;border-radius:14px;display:flex;align-items:center;justify-content:center;}}
.top-bar{{display:flex;justify-content:space-between;align-items:center;position:relative;z-index:10;}}
.logo img{{height:34px;object-fit:contain;}}
.tag{{background:rgba(99,102,241,0.2);border:1px solid rgba(99,102,241,0.5);color:#A5B4FC;font-size:15px;font-weight:700;letter-spacing:2px;padding:8px 20px;border-radius:100px;}}
.main{{position:relative;z-index:10;flex:1;display:flex;flex-direction:column;justify-content:center;}}
.category{{font-size:15px;font-weight:700;color:#6366F1;letter-spacing:3px;text-transform:uppercase;margin-bottom:14px;display:flex;align-items:center;gap:10px;}}
.category::before{{content:'';display:block;width:28px;height:2px;background:#6366F1;}}
.title{{font-size:72px;font-weight:900;color:#FFFFFF;line-height:1.05;letter-spacing:-2px;margin-bottom:24px;}}
.title .hl{{background:linear-gradient(90deg,#818CF8,#C084FC);-webkit-background-clip:text;-webkit-text-fill-color:transparent;}}
.divider{{width:60px;height:3px;background:linear-gradient(90deg,#6366F1,transparent);margin-bottom:24px;}}
.points{{display:flex;flex-direction:column;gap:14px;}}
.point{{display:flex;align-items:flex-start;gap:16px;}}
.point-num{{min-width:38px;height:38px;background:linear-gradient(135deg,#6366F1,#8B5CF6);border-radius:10px;display:flex;align-items:center;justify-content:center;font-size:15px;font-weight:800;color:white;flex-shrink:0;margin-top:4px;box-shadow:0 0 16px rgba(99,102,241,0.4);}}
.point-text{{font-size:30px;font-weight:500;color:#CBD5E1;line-height:1.35;}}
.bottom{{display:flex;justify-content:space-between;align-items:center;position:relative;z-index:10;border-top:1px solid rgba(255,255,255,0.07);padding-top:20px;}}
.domain{{font-size:22px;font-weight:800;color:#6366F1;}}
.services{{font-size:17px;color:#475569;}}
</style></head><body>
<div class="post">
  <div class="grid"></div><div class="glow1"></div><div class="glow2"></div>
  <div class="watermark">GUNDRUX</div>
  <div class="icon-box" style="top:100px;right:65px;background:linear-gradient(45deg,#f09433,#dc2743,#bc1888);"><svg width="30" height="30" viewBox="0 0 24 24" fill="white"><path d="M12 2.163c3.204 0 3.584.012 4.85.07 3.252.148 4.771 1.691 4.919 4.919.058 1.265.069 1.645.069 4.849 0 3.205-.012 3.584-.069 4.849-.149 3.225-1.664 4.771-4.919 4.919-1.266.058-1.644.07-4.85.07-3.204 0-3.584-.012-4.849-.07-3.26-.149-4.771-1.699-4.919-4.92-.058-1.265-.07-1.644-.07-4.849 0-3.204.013-3.583.07-4.849.149-3.227 1.664-4.771 4.919-4.919 1.266-.057 1.645-.069 4.849-.069zM12 0C8.741 0 8.333.014 7.053.072 2.695.272.273 2.69.073 7.052.014 8.333 0 8.741 0 12c0 3.259.014 3.668.072 4.948.2 4.358 2.618 6.78 6.98 6.98C8.333 23.986 8.741 24 12 24c3.259 0 3.668-.014 4.948-.072 4.354-.2 6.782-2.618 6.979-6.98.059-1.28.073-1.689.073-4.948 0-3.259-.014-3.667-.072-4.947-.196-4.354-2.617-6.78-6.979-6.98C15.668.014 15.259 0 12 0zm0 5.838a6.162 6.162 0 100 12.324 6.162 6.162 0 000-12.324zM12 16a4 4 0 110-8 4 4 0 010 8zm6.406-11.845a1.44 1.44 0 100 2.881 1.44 1.44 0 000-2.881z"/></svg></div>
  <div class="icon-box" style="top:195px;right:165px;background:#1877F2;"><svg width="30" height="30" viewBox="0 0 24 24" fill="white"><path d="M24 12.073c0-6.627-5.373-12-12-12s-12 5.373-12 12c0 5.99 4.388 10.954 10.125 11.854v-8.385H7.078v-3.47h3.047V9.43c0-3.007 1.792-4.669 4.533-4.669 1.312 0 2.686.235 2.686.235v2.953H15.83c-1.491 0-1.956.925-1.956 1.874v2.25h3.328l-.532 3.47h-2.796v8.385C19.612 23.027 24 18.062 24 12.073z"/></svg></div>
  <div class="icon-box" style="top:305px;right:70px;background:#FF0000;"><svg width="30" height="30" viewBox="0 0 24 24" fill="white"><path d="M23.495 6.205a3.007 3.007 0 00-2.088-2.088c-1.87-.501-9.396-.501-9.396-.501s-7.507-.01-9.396.501A3.007 3.007 0 00.527 6.205a31.247 31.247 0 00-.522 5.805 31.247 31.247 0 00.522 5.783 3.007 3.007 0 002.088 2.088c1.868.502 9.396.502 9.396.502s7.506 0 9.396-.502a3.007 3.007 0 002.088-2.088 31.247 31.247 0 00.5-5.783 31.247 31.247 0 00-.5-5.805zM9.609 15.601V8.408l6.264 3.602z"/></svg></div>
  <div class="icon-box" style="top:410px;right:175px;background:#0A66C2;"><svg width="30" height="30" viewBox="0 0 24 24" fill="white"><path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433a2.062 2.062 0 01-2.063-2.065 2.064 2.064 0 112.063 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z"/></svg></div>
  <div class="icon-box" style="top:510px;right:70px;background:#fff;"><svg width="30" height="30" viewBox="0 0 24 24"><path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4"/><path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/><path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"/><path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/></svg></div>
  <div class="icon-box" style="top:610px;right:175px;background:linear-gradient(135deg,#6366F1,#8B5CF6);"><svg width="30" height="30" viewBox="0 0 24 24" fill="white"><path d="M22.2819 9.8211a5.9847 5.9847 0 0 0-.5157-4.9108 6.0462 6.0462 0 0 0-6.5098-2.9A6.0651 6.0651 0 0 0 4.9807 4.1818a5.9847 5.9847 0 0 0-3.9977 2.9 6.0462 6.0462 0 0 0 .7427 7.0966 5.98 5.98 0 0 0 .511 4.9107 6.051 6.051 0 0 0 6.5146 2.9001A5.9847 5.9847 0 0 0 13.2599 24a6.0557 6.0557 0 0 0 5.7718-4.2058 5.9894 5.9894 0 0 0 3.9977-2.9001 6.0557 6.0557 0 0 0-.7475-7.0729z"/></svg></div>
  <div class="icon-box" style="top:150px;right:265px;background:linear-gradient(135deg,#10B981,#059669);"><svg width="30" height="30" viewBox="0 0 24 24" fill="white"><path d="M15.5 14h-.79l-.28-.27A6.471 6.471 0 0 0 16 9.5 6.5 6.5 0 1 0 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z"/></svg></div>
  <div class="icon-box" style="top:370px;right:275px;background:linear-gradient(135deg,#F59E0B,#D97706);"><svg width="30" height="30" viewBox="0 0 24 24" fill="white"><path d="M3.5 18.49l6-6.01 4 4L22 6.92l-1.41-1.41-7.09 7.97-4-4L2 16.99l1.5 1.5z"/></svg></div>
  <div class="icon-box" style="top:560px;right:270px;background:#21759B;"><svg width="30" height="30" viewBox="0 0 24 24" fill="white"><path d="M12 2C6.486 2 2 6.486 2 12s4.486 10 10 10 10-4.486 10-10S17.514 2 12 2zm0 1.542c2.282 0 4.368.813 6 2.148L5.69 18c-1.335-1.632-2.148-3.718-2.148-6C3.542 7.144 7.144 3.542 12 3.542z"/></svg></div>
  <div class="top-bar">
    <div class="logo"><img src="https://gundrux.in/wp-content/uploads/2026/03/cropped-cropped-ChatGPT_Image_Mar_21__2026__02_13_51_PM-removebg-preview-1-250x42.png" /></div>
    <div class="tag">{category}</div>
  </div>
  <div class="main">
    <div class="category">{category}</div>
    <div class="title">{title_line1}<br><span class="hl">{title_line2}</span></div>
    <div class="divider"></div>
    <div class="points">
      <div class="point"><div class="point-num">01</div><div class="point-text">{p1}</div></div>
      <div class="point"><div class="point-num">02</div><div class="point-text">{p2}</div></div>
      <div class="point"><div class="point-num">03</div><div class="point-text">{p3}</div></div>
      <div class="point"><div class="point-num">04</div><div class="point-text">{p4}</div></div>
      <div class="point"><div class="point-num">05</div><div class="point-text">{p5}</div></div>
    </div>
  </div>
  <div class="bottom">
    <div class="domain">gundrux.in</div>
    <div class="services">AI SEO · AEO · GEO · Brand Growth</div>
  </div>
</div></body></html>"""

# Template 2: Split Purple
TEMPLATE_SPLIT_PURPLE = """<!DOCTYPE html><html><head><meta charset="UTF-8">
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800;900&display=swap');
*{{margin:0;padding:0;box-sizing:border-box;}}
body{{width:1080px;height:1080px;overflow:hidden;font-family:'Inter',sans-serif;}}
.post{{width:1080px;height:1080px;background:#08080F;position:relative;overflow:hidden;}}
.left{{position:absolute;top:0;left:0;width:60%;height:100%;background:linear-gradient(180deg,#0A0A14 0%,#15102B 100%);padding:48px 56px;display:flex;flex-direction:column;justify-content:space-between;z-index:5;}}
.right{{position:absolute;top:0;right:0;width:42%;height:100%;background:linear-gradient(135deg,#1E1B4B 0%,#312E81 100%);padding:60px 40px;display:flex;flex-direction:column;justify-content:center;z-index:4;}}
.right::before{{content:'';position:absolute;top:0;left:-40px;width:80px;height:100%;background:linear-gradient(90deg,transparent,#15102B);}}
.glow{{position:absolute;top:-200px;left:-100px;width:600px;height:600px;background:radial-gradient(circle,rgba(139,92,246,0.25) 0%,transparent 70%);}}
.logo img{{height:36px;}}
.tag{{display:inline-block;background:rgba(192,132,252,0.2);border:1px solid rgba(192,132,252,0.5);color:#E9D5FF;font-size:14px;font-weight:700;letter-spacing:2px;padding:8px 18px;border-radius:100px;margin-top:20px;width:fit-content;}}
.title{{font-size:64px;font-weight:900;color:white;line-height:1.05;letter-spacing:-2px;margin-top:40px;}}
.title .hl{{background:linear-gradient(90deg,#C084FC,#F0ABFC);-webkit-background-clip:text;-webkit-text-fill-color:transparent;}}
.bottom-left{{margin-top:30px;}}
.domain{{font-size:24px;font-weight:800;color:#C084FC;}}
.services{{font-size:16px;color:#94A3B8;margin-top:6px;}}
.points-header{{font-size:16px;font-weight:700;color:#C084FC;letter-spacing:3px;text-transform:uppercase;margin-bottom:20px;}}
.divider{{width:50px;height:3px;background:linear-gradient(90deg,#C084FC,transparent);margin-bottom:30px;}}
.point{{display:flex;align-items:flex-start;gap:14px;margin-bottom:24px;}}
.point-num{{font-size:34px;font-weight:900;color:#C084FC;line-height:1;flex-shrink:0;min-width:50px;}}
.point-text{{font-size:22px;font-weight:500;color:#E2E8F0;line-height:1.4;}}
</style></head><body>
<div class="post">
  <div class="glow"></div>
  <div class="left">
    <div>
      <div class="logo"><img src="https://gundrux.in/wp-content/uploads/2026/03/cropped-cropped-ChatGPT_Image_Mar_21__2026__02_13_51_PM-removebg-preview-1-250x42.png" /></div>
      <div class="tag">{category}</div>
      <div class="title">{title_line1}<br><span class="hl">{title_line2}</span></div>
    </div>
    <div class="bottom-left">
      <div class="domain">gundrux.in</div>
      <div class="services">AI SEO · AEO · GEO · Brand Growth</div>
    </div>
  </div>
  <div class="right">
    <div class="points-header">KEY TIPS</div>
    <div class="divider"></div>
    <div class="point"><div class="point-num">01</div><div class="point-text">{p1}</div></div>
    <div class="point"><div class="point-num">02</div><div class="point-text">{p2}</div></div>
    <div class="point"><div class="point-num">03</div><div class="point-text">{p3}</div></div>
    <div class="point"><div class="point-num">04</div><div class="point-text">{p4}</div></div>
    <div class="point"><div class="point-num">05</div><div class="point-text">{p5}</div></div>
  </div>
</div></body></html>"""

# Template 3: Minimal Neon
TEMPLATE_MINIMAL_NEON = """<!DOCTYPE html><html><head><meta charset="UTF-8">
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800;900&display=swap');
*{{margin:0;padding:0;box-sizing:border-box;}}
body{{width:1080px;height:1080px;overflow:hidden;font-family:'Inter',sans-serif;}}
.post{{width:1080px;height:1080px;background:#08080C;position:relative;overflow:hidden;display:flex;flex-direction:column;justify-content:space-between;padding:48px 56px;}}
.grid{{position:absolute;inset:0;background-image:linear-gradient(rgba(34,211,238,0.04) 1px,transparent 1px),linear-gradient(90deg,rgba(34,211,238,0.04) 1px,transparent 1px);background-size:60px 60px;}}
.glow1{{position:absolute;top:-200px;right:-100px;width:500px;height:500px;background:radial-gradient(circle,rgba(34,211,238,0.15) 0%,transparent 70%);}}
.glow2{{position:absolute;bottom:-200px;left:-100px;width:600px;height:600px;background:radial-gradient(circle,rgba(99,102,241,0.12) 0%,transparent 70%);}}
.watermark{{position:absolute;right:-30px;top:50%;transform:translateY(-50%) rotate(-90deg);font-size:200px;font-weight:900;color:rgba(34,211,238,0.04);letter-spacing:-6px;pointer-events:none;}}
.top-bar{{display:flex;justify-content:space-between;align-items:center;position:relative;z-index:10;}}
.logo img{{height:34px;}}
.tag{{background:rgba(34,211,238,0.15);border:1px solid rgba(34,211,238,0.4);color:#67E8F9;font-size:15px;font-weight:700;letter-spacing:2px;padding:8px 20px;border-radius:8px;}}
.main{{position:relative;z-index:10;flex:1;display:flex;flex-direction:column;justify-content:center;}}
.bar{{display:flex;align-items:center;gap:14px;margin-bottom:18px;}}
.bar-line{{width:50px;height:3px;background:#22D3EE;}}
.bar-text{{font-size:15px;font-weight:700;color:#22D3EE;letter-spacing:3px;text-transform:uppercase;}}
.title{{font-size:74px;font-weight:900;color:#FFFFFF;line-height:1.05;letter-spacing:-2px;margin-bottom:30px;}}
.title .hl{{color:#22D3EE;text-shadow:0 0 30px rgba(34,211,238,0.4);}}
.points{{display:flex;flex-direction:column;gap:18px;}}
.point{{display:flex;align-items:flex-start;gap:18px;}}
.point-bar{{min-width:6px;height:42px;background:#22D3EE;flex-shrink:0;margin-top:4px;box-shadow:0 0 15px rgba(34,211,238,0.5);}}
.point-text{{font-size:30px;font-weight:500;color:#E2E8F0;line-height:1.35;}}
.bottom{{display:flex;justify-content:space-between;align-items:center;position:relative;z-index:10;padding-top:24px;border-top:1px solid rgba(34,211,238,0.15);}}
.domain{{font-size:24px;font-weight:800;color:#22D3EE;text-shadow:0 0 20px rgba(34,211,238,0.4);}}
.services{{font-size:17px;color:#64748B;}}
</style></head><body>
<div class="post">
  <div class="grid"></div><div class="glow1"></div><div class="glow2"></div>
  <div class="watermark">GUNDRUX</div>
  <div class="top-bar">
    <div class="logo"><img src="https://gundrux.in/wp-content/uploads/2026/03/cropped-cropped-ChatGPT_Image_Mar_21__2026__02_13_51_PM-removebg-preview-1-250x42.png" /></div>
    <div class="tag">{category}</div>
  </div>
  <div class="main">
    <div class="bar"><div class="bar-line"></div><div class="bar-text">{category}</div></div>
    <div class="title">{title_line1}<br><span class="hl">{title_line2}</span></div>
    <div class="points">
      <div class="point"><div class="point-bar"></div><div class="point-text">{p1}</div></div>
      <div class="point"><div class="point-bar"></div><div class="point-text">{p2}</div></div>
      <div class="point"><div class="point-bar"></div><div class="point-text">{p3}</div></div>
      <div class="point"><div class="point-bar"></div><div class="point-text">{p4}</div></div>
      <div class="point"><div class="point-bar"></div><div class="point-text">{p5}</div></div>
    </div>
  </div>
  <div class="bottom">
    <div class="domain">gundrux.in</div>
    <div class="services">AI SEO · AEO · GEO · Brand Growth</div>
  </div>
</div></body></html>"""

def render_image(content_data):
    words = content_data["title"].split()
    mid = max(1, len(words) // 2)
    points = content_data["points"]
    while len(points) < 5:
        points.append("Stay consistent and track your results daily")

    data = {
        "category": content_data.get("category", "DIGITAL MARKETING"),
        "title_line1": " ".join(words[:mid]),
        "title_line2": " ".join(words[mid:]),
        "p1": points[0], "p2": points[1], "p3": points[2],
        "p4": points[3], "p5": points[4]
    }

    # Rotate template based on day + time
    hour = datetime.now().hour
    template_idx = hour % 3
    template_fn = TEMPLATES[template_idx]
    html = template_fn(data)

    with open("/tmp/post_render.html", "w") as f:
        f.write(html)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1080, "height": 1080})
        page.goto("file:///tmp/post_render.html")
        page.wait_for_timeout(3000)
        img_bytes = page.screenshot(full_page=False)
        browser.close()
    return img_bytes, template_idx

def upload_cloudinary(image_bytes, topic):
    slug = topic[:25].replace(" ", "_").replace("/", "-")
    result = cloudinary.uploader.upload(
        image_bytes,
        folder="social_posts",
        public_id=f"{date.today()}_{slug}_{int(time.time())}",
        resource_type="image"
    )
    return result["secure_url"]

# ── BUFFER POSTING ───────────────────────────────────────
def post_buffer(image_url, caption, channel_id, platform):
    query = """
    mutation CreatePost($input: CreatePostInput!) {
      createPost(input: $input) {
        ... on PostActionSuccess { post { id status } }
        ... on MutationError { message }
      }
    }
    """
    metadata = {}
    if platform == "facebook":
        metadata = {"facebook": {"type": "post"}}
    elif platform == "instagram":
        metadata = {"instagram": {"type": "post", "shouldShareToFeed": True}}
    elif platform == "linkedin":
        metadata = {"linkedin": {"type": "post"}}

    variables = {
        "input": {
            "channelId": channel_id,
            "text": caption,
            "schedulingType": "automatic",
            "mode": "addToQueue",
            "assets": [{"image": {"url": image_url}}],
            "metadata": metadata
        }
    }
    resp = requests.post(
        "https://api.buffer.com/graphql",
        json={"query": query, "variables": variables},
        headers={"Authorization": f"Bearer {BUFFER_TOKEN}", "Content-Type": "application/json"}
    )
    return resp.json()

def publish_post(image_url, caption):
    results = {}
    print("  Posting Facebook...")
    results["facebook"] = post_buffer(image_url, caption, BUFFER_FB_CHANNEL, "facebook")
    print("  Posting Instagram...")
    results["instagram"] = post_buffer(image_url, caption, BUFFER_IG_CHANNEL, "instagram")
    print("  Posting LinkedIn...")
    results["linkedin"] = post_buffer(image_url, caption, BUFFER_LI_CHANNEL, "linkedin")
    return results

# ── MAIN BOT FLOW ─────────────────────────────────────────
pending = {}  # post_id -> {topic, content, image_url, caption}

def generate_one_post():
    topic = pick_topic()
    print(f"\nTopic: {topic}")
    content = generate_content(topic)
    caption = f"{content['caption']}\n\n{content['hashtags']}"
    image_bytes, tpl_idx = render_image(content)
    image_url = upload_cloudinary(image_bytes, topic)
    return {
        "topic": topic,
        "content": content,
        "image_url": image_url,
        "caption": caption,
        "template": tpl_idx,
        "created_at": datetime.now().isoformat()
    }

def send_for_approval(post_id, post):
    pending[post_id] = post
    preview = (
        f"📋 <b>Post #{post_id}</b>\n"
        f"📌 <b>Topic:</b> {post['topic']}\n"
        f"🎨 <b>Template:</b> {post['template']+1}\n\n"
        f"📝 <b>Caption:</b>\n{post['caption'][:400]}...\n\n"
        f"👇 Tap a button below:"
    )
    markup = {
        "inline_keyboard": [
            [
                {"text": "✅ Approve & Post", "callback_data": f"approve_{post_id}"},
                {"text": "❌ Reject", "callback_data": f"reject_{post_id}"}
            ],
            [
                {"text": "✏️ Edit Caption", "callback_data": f"edit_{post_id}"},
                {"text": "🔄 Regenerate", "callback_data": f"regen_{post_id}"}
            ]
        ]
    }
    tg_send_photo(post['image_url'], preview, markup)

def run_one_cycle():
    tg_send(f"🤖 <b>Generating new post...</b>\n⏰ {datetime.now().strftime('%H:%M %d %b %Y')}")
    try:
        post = generate_one_post()
        post_id = int(time.time()) % 100000
        send_for_approval(post_id, post)
        tg_send("✅ Post ready! Approve, edit, reject or regenerate above.")
    except Exception as e:
        tg_send(f"❌ Error generating post: {e}")
        print(f"Error: {e}")

def handle_callbacks(timeout=10800):
    """Poll Telegram for button clicks. Timeout = max wait in seconds (3 hours default)"""
    offset = 0
    waiting_edit = {}
    start = time.time()

    while time.time() - start < timeout:
        try:
            updates = tg_get_updates(offset)
            for update in updates:
                offset = update["update_id"] + 1

                if "callback_query" in update:
                    cb = update["callback_query"]
                    data = cb["data"]
                    tg_answer_callback(cb["id"])

                    if data.startswith("approve_"):
                        post_id = int(data.split("_")[1])
                        post = pending.get(post_id)
                        if post:
                            tg_send(f"⏳ Publishing post #{post_id} to Facebook + Instagram + LinkedIn...")
                            try:
                                results = publish_post(post["image_url"], post["caption"])
                                tg_send(f"✅ Published successfully!\n\nFB: ok\nIG: ok\nLI: ok")
                                save_history({
                                    "post_id": post_id,
                                    "topic": post["topic"],
                                    "caption": post["caption"],
                                    "image_url": post["image_url"],
                                    "status": "approved",
                                    "results": results,
                                    "timestamp": datetime.now().isoformat()
                                })
                                del pending[post_id]
                                return  # Done after approve
                            except Exception as e:
                                tg_send(f"❌ Publishing failed: {e}")

                    elif data.startswith("reject_"):
                        post_id = int(data.split("_")[1])
                        if post_id in pending:
                            save_history({
                                "post_id": post_id,
                                "topic": pending[post_id]["topic"],
                                "status": "rejected",
                                "timestamp": datetime.now().isoformat()
                            })
                            del pending[post_id]
                        tg_send(f"🗑️ Post #{post_id} rejected.")
                        return

                    elif data.startswith("edit_"):
                        post_id = int(data.split("_")[1])
                        waiting_edit[post_id] = True
                        tg_send(f"✏️ Send your new caption for post #{post_id}:")

                    elif data.startswith("regen_"):
                        post_id = int(data.split("_")[1])
                        old = pending.get(post_id)
                        if old:
                            tg_send(f"🔄 Regenerating post #{post_id}...")
                            try:
                                new_post = generate_one_post()
                                del pending[post_id]
                                send_for_approval(post_id, new_post)
                            except Exception as e:
                                tg_send(f"❌ Regen failed: {e}")

                elif "message" in update:
                    msg = update["message"]
                    text = msg.get("text", "")
                    for post_id in list(waiting_edit.keys()):
                        if waiting_edit.get(post_id) and pending.get(post_id):
                            pending[post_id]["caption"] = text
                            del waiting_edit[post_id]
                            markup = {"inline_keyboard": [[
                                {"text": "✅ Approve & Post", "callback_data": f"approve_{post_id}"},
                                {"text": "❌ Reject", "callback_data": f"reject_{post_id}"}
                            ]]}
                            tg_send_photo(pending[post_id]["image_url"],
                                        f"✏️ Updated caption for post #{post_id}:\n\n{text[:400]}",
                                        markup)
                            break

            time.sleep(2)
        except Exception as e:
            print(f"Poll error: {e}")
            time.sleep(5)

def main():
    print(f"Bot starting at {datetime.now()}")
    tg_send(f"🚀 <b>Gundrux Bot Active</b>\n⏰ {datetime.now().strftime('%H:%M %d %b %Y')}\n📊 Generating today's post...")
    run_one_cycle()
    handle_callbacks(timeout=10800)  # Wait 3 hours for response
    print("Cycle done.")

if __name__ == "__main__":
    main()
