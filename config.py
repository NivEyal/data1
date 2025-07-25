"""
הגדרות האפליקציה
"""

# הגדרות בסיסיות
APP_TITLE = "יועץ פיננסי חכם"
APP_ICON = "💰"

# הגדרות OpenAI
OPENAI_MODEL = "gpt-4o-mini"

# הגדרות בנקים נתמכים
SUPPORTED_BANKS = {
    "הפועלים": "hapoalim",
    "לאומי": "leumi", 
    "דיסקונט": "discount"
}

# הגדרות סיווג פיננסי
THRESHOLDS = {
    "GREEN_MAX": 1.0,
    "YELLOW_MAX": 2.0
}

# הגדרות ברירת מחדל
DEFAULT_INCOME = 15000