"""
פרסר דוח נתוני אשראי
"""
import pandas as pd
import pymupdf as fitz
import re
import logging
import numpy as np
from utils.helpers import clean_number, normalize_text


class CreditParser:
    """פרסר דוח נתוני אשראי"""
    
    def __init__(self):
        self.logger = logging.getLogger("credit_parser")
        self.bank_keywords = {
            "בנק", "בע\"מ", "אגוד", "דיסקונט", "לאומי", "הפועלים", "מזרחי",
            "טפחות", "הבינלאומי", "מרכנתיל", "אוצר", "החייל", "ירושלים",
            "איגוד", "מימון", "ישיר", "כרטיסי", "אשראי", "מקס", "פיננסים",
            "כאל", "ישראכרט"
        }
        self.section_patterns = {
            "חשבון עובר ושב": "עו\"ש",
            "הלוואה": "הלוואה", 
            "משכנתה": "משכנתה",
            "מסגרת אשראי מתחדשת": "מסגרת אשראי"
        }
    
    def parse_pdf(self, pdf_bytes, filename="credit_report.pdf"):
        """פרסור PDF של דוח נתוני אשראי"""
        extracted_rows = []
        
        try:
            with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
                current_section = None
                current_entry = None
                
                for page in doc:
                    text = page.get_text("text")
                    lines = text.splitlines()
                    
                    for line in lines:
                        line = normalize_text(line.strip())
                        if not line:
                            continue
                        
                        # זיהוי כותרת סעיף
                        section = self._identify_section(line)
                        if section:
                            if current_entry:
                                self._process_entry(current_entry, current_section, extracted_rows)
                            current_section = section
                            current_entry = None
                            continue
                        
                        # עיבוד שורות בתוך סעיף
                        if current_section:
                            current_entry = self._process_line(line, current_entry, current_section, extracted_rows)
                
                # עיבוד הרשומה האחרונה
                if current_entry:
                    self._process_entry(current_entry, current_section, extracted_rows)
                    
        except Exception as e:
            self.logger.error(f"Error processing credit report: {e}")
            return pd.DataFrame()
        
        return self._create_dataframe(extracted_rows)
    
    def _identify_section(self, line):
        """זיהוי סוג סעיף"""
        for header_keyword, section_name in self.section_patterns.items():
            if header_keyword in line and len(line) < len(header_keyword) + 20:
                return section_name
        return None
    
    def _process_line(self, line, current_entry, current_section, extracted_rows):
        """עיבוד שורה בודדת"""
        # זיהוי מספרים
        number_match = re.match(r"^\s*(-?\d{1,3}(?:,\d{3})*\.?\d*)\s*$", line)
        if number_match:
            if current_entry:
                try:
                    number = float(number_match.group(1).replace(",", ""))
                    current_entry.setdefault('numbers', []).append(number)
                except ValueError:
                    pass
            return current_entry
        
        # זיהוי שם בנק/מוסד
        if self._is_bank_name(line):
            if current_entry:
                self._process_entry(current_entry, current_section, extracted_rows)
            return {'bank': line, 'numbers': []}
        
        return current_entry
    
    def _is_bank_name(self, line):
        """בדיקה אם השורה מכילה שם בנק"""
        cleaned_line = re.sub(r'\s*XX-[\w\d\-]+.*', '', line).strip()
        return any(keyword in cleaned_line for keyword in self.bank_keywords)
    
    def _process_entry(self, entry_data, section, all_rows_list):
        """עיבוד רשומה שלמה"""
        if not entry_data or not entry_data.get('bank') or len(entry_data.get('numbers', [])) < 2:
            return
        
        bank_name = self._clean_bank_name(entry_data['bank'])
        numbers = entry_data['numbers']
        
        # הקצאת ערכים לפי סוג הסעיף
        limit_col, original_col, outstanding_col, unpaid_col = np.nan, np.nan, np.nan, np.nan
        
        if section in ["עו\"ש", "מסגרת אשראי"]:
            limit_col = numbers[0] if len(numbers) > 0 else np.nan
            outstanding_col = numbers[1] if len(numbers) > 1 else np.nan
            unpaid_col = numbers[2] if len(numbers) > 2 else 0.0
        elif section in ["הלוואה", "משכנתה"]:
            original_col = numbers[0] if len(numbers) > 0 else np.nan
            outstanding_col = numbers[1] if len(numbers) > 1 else np.nan
            unpaid_col = numbers[2] if len(numbers) > 2 else 0.0
        
        all_rows_list.append({
            "סוג עסקה": section,
            "שם בנק/מקור": bank_name,
            "גובה מסגרת": limit_col,
            "סכום מקורי": original_col,
            "יתרת חוב": outstanding_col,
            "יתרה שלא שולמה": unpaid_col
        })
    
    def _clean_bank_name(self, bank_name_raw):
        """ניקוי שם בנק"""
        bank_name = re.sub(r'\s*XX-[\w\d\-]+.*', '', bank_name_raw).strip()
        bank_name = re.sub(r'\s+\d{1,3}(?:,\d{3})*$', '', bank_name).strip()
        bank_name = re.sub(r'\s+בע\"מ$', '', bank_name).strip()
        
        # הוספת בע"מ לבנקים
        if any(kw in bank_name for kw in ["בנק", "לאומי", "הפועלים", "דיסקונט"]):
            if not bank_name.endswith("בע\"מ"):
                bank_name += " בע\"מ"
        
        return bank_name
    
    def _create_dataframe(self, extracted_rows):
        """יצירת DataFrame מהנתונים שחולצו"""
        if not extracted_rows:
            return pd.DataFrame()
        
        df = pd.DataFrame(extracted_rows)
        
        # וידוא שכל העמודות קיימות
        required_cols = ["סוג עסקה", "שם בנק/מקור", "גובה מסגרת", "סכום מקורי", "יתרת חוב", "יתרה שלא שולמה"]
        for col in required_cols:
            if col not in df.columns:
                df[col] = np.nan
        
        # המרה לטיפוסים מספריים
        numeric_cols = ["גובה מסגרת", "סכום מקורי", "יתרת חוב", "יתרה שלא שולמה"]
        for col in numeric_cols:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        
        return df[required_cols]