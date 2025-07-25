"""
קובץ הגדרות עבור האפליקציה
"""

# הגדרות OpenAI
OPENAI_MODEL = "gpt-3.5-turbo"

# הגדרות UI
PAGE_TITLE = "מומחה כלכלת המשפחה GPT"
PAGE_ICON = "💰"

# הגדרות בנקים נתמכים
SUPPORTED_BANKS = {
    "הפועלים": "hapoalim",
    "לאומי": "leumi", 
    "דיסקונט": "discount"
}

# הגדרות סיווג פיננסי
CLASSIFICATION_THRESHOLDS = {
    "GREEN_MAX": 1.0,
    "YELLOW_MAX": 2.0
}

# הגדרות ברירת מחדל
DEFAULT_MONTHLY_INCOME = 15000