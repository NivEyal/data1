"""
מנתח פיננסי
"""
from config import THRESHOLDS


class FinancialAnalyzer:
    """מחלקה לניתוח פיננסי וסיווג מצב"""
    
    def __init__(self):
        self.green_threshold = THRESHOLDS["GREEN_MAX"]
        self.yellow_threshold = THRESHOLDS["YELLOW_MAX"]
    
    def calculate_debt_to_income_ratio(self, total_debts, annual_income):
        """חישוב יחס חוב להכנסה"""
        if annual_income <= 0:
            return float('inf')
        return total_debts / annual_income
    
    def classify_financial_status(self, debt_to_income_ratio, has_collection=None, can_raise_funds=None):
        """סיווג מצב פיננסי"""
        # ירוק - יחס נמוך
        if debt_to_income_ratio < self.green_threshold:
            return {
                'status': 'ירוק',
                'color': 'success',
                'message': '🟢 מצב פיננסי תקין! יחס החוב להכנסה נמוך ובטוח.',
                'recommendations': [
                    'המשך בניהול פיננסי אחראי',
                    'שקול הגדלת חיסכון או השקעות',
                    'בדוק אפשרויות לשיפור תנאי אשראי'
                ]
            }
        
        # אדום - יחס גבוה מאוד
        elif debt_to_income_ratio > self.yellow_threshold:
            return {
                'status': 'אדום',
                'color': 'error',
                'message': '🔴 מצב פיננסי מאתגר. יחס החוב להכנסה גבוה מאוד.',
                'recommendations': [
                    'פנה לייעוץ מקצועי בהקדם',
                    'בחן אפשרויות לגיוס כספים',
                    'הפסק לצבור חוב חדש',
                    'שקול פנייה לארגון "פעמונים"'
                ]
            }
        
        # צהוב - תלוי בנסיבות נוספות
        else:
            if has_collection is True:
                return {
                    'status': 'אדום',
                    'color': 'error',
                    'message': '🔴 מצב פיננסי מאתגר. קיימים הליכי גבייה.',
                    'recommendations': [
                        'פנה לייעוץ משפטי בהקדם',
                        'נהל משא ומתן עם הנושים',
                        'בחן אפשרויות להסדר חוב'
                    ]
                }
            elif has_collection is False and can_raise_funds is True:
                return {
                    'status': 'צהוב',
                    'color': 'warning',
                    'message': '🟡 מצב פיננסי דורש תשומת לב. יש פוטנציאל לשיפור.',
                    'recommendations': [
                        'גייס את הכספים הזמינים',
                        'בנה תוכנית להחזר חובות',
                        'צמצם הוצאות לא חיוניות',
                        'שקול הגדלת הכנסות'
                    ]
                }
            elif has_collection is False and can_raise_funds is False:
                return {
                    'status': 'אדום',
                    'color': 'error',
                    'message': '🔴 מצב פיננסי מאתגר. אין יכולת גיוס כספים.',
                    'recommendations': [
                        'פנה לייעוץ מקצועי בהקדם',
                        'בחן מקורות הכנסה נוספים',
                        'שקול מכירת נכסים',
                        'פנה לעזרה משפחתית'
                    ]
                }
            else:
                # צריך עוד מידע
                return None
    
    def needs_additional_questions(self, debt_to_income_ratio):
        """בדיקה אם צריך שאלות נוספות"""
        return self.green_threshold <= debt_to_income_ratio <= self.yellow_threshold
    
    def calculate_fund_raising_amount(self, total_debts):
        """חישוב סכום נדרש לגיוס (50% מהחוב)"""
        return total_debts * 0.5