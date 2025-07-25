"""
מנתח פיננסי - לוגיקת הסיווג והחישובים
"""
from config import CLASSIFICATION_THRESHOLDS


class FinancialAnalyzer:
    """מחלקה לניתוח פיננסי וסיווג מצב"""
    
    def __init__(self):
        self.green_threshold = CLASSIFICATION_THRESHOLDS["GREEN_MAX"]
        self.yellow_threshold = CLASSIFICATION_THRESHOLDS["YELLOW_MAX"]
    
    def calculate_debt_to_income_ratio(self, total_debts, annual_income):
        """חישוב יחס חוב להכנסה"""
        if annual_income <= 0:
            return float('inf')
        return total_debts / annual_income
    
    def classify_financial_status(self, debt_to_income_ratio, collection_proceedings=None, can_raise_funds=None):
        """סיווג מצב פיננסי"""
        if debt_to_income_ratio < self.green_threshold:
            return "ירוק"
        
        elif debt_to_income_ratio <= self.yellow_threshold:
            if collection_proceedings is True:
                return "אדום"
            elif collection_proceedings is False:
                if can_raise_funds is True:
                    return "צהוב"
                elif can_raise_funds is False:
                    return "אדום"
                else:
                    return None  # צריך עוד מידע
            else:
                return None  # צריך עוד מידע
        
        else:  # ratio > 2
            return "אדום"
    
    def get_classification_color_and_message(self, classification):
        """קבלת צבע והודעה לסיווג"""
        messages = {
            "ירוק": ("success", "🟢 מצב פיננסי תקין! יחס החוב להכנסה נמוך ובטוח."),
            "צהוב": ("warning", "🟡 מצב פיננסי דורש תשומת לב. מומלץ לשקול צעדים לשיפור."),
            "אדום": ("error", "🔴 מצב פיננסי מאתגר. מומלץ מאוד לפנות לייעוץ מקצועי.")
        }
        return messages.get(classification, ("info", "מצב לא ידוע"))
    
    def needs_collection_question(self, debt_to_income_ratio):
        """בדיקה אם צריך לשאול על הליכי גבייה"""
        return self.green_threshold <= debt_to_income_ratio <= self.yellow_threshold
    
    def needs_funds_question(self, debt_to_income_ratio, collection_proceedings):
        """בדיקה אם צריך לשאול על יכולת גיוס כספים"""
        return (self.green_threshold <= debt_to_income_ratio <= self.yellow_threshold and 
                collection_proceedings is False)
    
    def calculate_fund_raising_amount(self, total_debts):
        """חישוב סכום נדרש לגיוס (50% מהחוב)"""
        return total_debts * 0.5