"""
פונקציות עזר כלליות
"""
import re
import logging
from datetime import datetime
import unicodedata


def clean_number(text):
    """ניקוי מספר מטקסט"""
    if not text:
        return None
    
    text = str(text).strip()
    text = re.sub(r'[₪,]', '', text)
    
    # טיפול במספרים שליליים
    if text.startswith('(') and text.endswith(')'):
        text = '-' + text[1:-1]
    if text.endswith('-'):
        text = '-' + text[:-1]
    
    try:
        return float(text) if text else None
    except ValueError:
        logging.debug(f"Could not convert '{text}' to float")
        return None


def parse_date(date_str):
    """פרסור תאריך"""
    if not date_str:
        return None
    
    try:
        return datetime.strptime(date_str.strip(), '%d/%m/%Y').date()
    except ValueError:
        try:
            return datetime.strptime(date_str.strip(), '%d/%m/%y').date()
        except ValueError:
            logging.debug(f"Could not parse date: {date_str}")
            return None


def normalize_text(text):
    """נרמול טקסט"""
    if not text:
        return None
    
    text = str(text).replace('\r', ' ').replace('\n', ' ').strip()
    return unicodedata.normalize('NFC', text)


def format_currency(amount):
    """עיצוב מטבע"""
    return f"{amount:,.0f} ₪" if amount else "0 ₪"


def format_percentage(ratio):
    """עיצוב אחוזים"""
    return f"{ratio:.1%}" if ratio else "0%"