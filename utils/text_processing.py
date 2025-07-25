"""
פונקציות עזר לעיבוד טקסט
"""
import unicodedata
import re
import logging
from datetime import datetime


def clean_number(text):
    """ניקוי מספר מטקסט"""
    if text is None:
        return None
    
    text = str(text).strip()
    text = re.sub(r'[₪,]', '', text)
    
    # טיפול במספרים שליליים
    if text.startswith('(') and text.endswith(')'):
        text = '-' + text[1:-1]
    if text.endswith('-'):
        text = '-' + text[:-1]
    
    try:
        return float(text)
    except ValueError:
        logging.warning(f"Could not convert '{text}' to float.")
        return None


def parse_date(date_str):
    """פרסור תאריך"""
    if date_str is None:
        return None
    
    try:
        return datetime.strptime(date_str.strip(), '%d/%m/%Y')
    except ValueError:
        try:
            return datetime.strptime(date_str.strip(), '%d/%m/%y')
        except ValueError:
            logging.warning(f"Could not parse date: {date_str}")
            return None


def normalize_text(text):
    """נרמול טקסט"""
    if text is None:
        return None
    return unicodedata.normalize('NFC', str(text))


def reverse_hebrew_text(text):
    """היפוך טקסט עברי"""
    if not text:
        return text
    
    words = text.split()
    reversed_words = [word[::-1] for word in words]
    return ' '.join(reversed_words[::-1])