# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime
import logging
import unicodedata
import re
import io
import traceback
import numpy as np

# PDF Parsing libraries
import pymupdf as fitz # PyMuPDF, Hapoalim & Credit Report
import pdfplumber # Leumi & Discount

from openai import OpenAI

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- OpenAI Client Setup ---
try:
    client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
except Exception as e:
    st.error(f"שגיאה בטעינת מפתח OpenAI: {e}. הצ'אטבוט עשוי לא לפעול כראוי.")
    client = None

# --- Helper Functions (Copied from previous combined version) ---
def clean_number_general(text):
    if text is None: return None
    text = str(text).strip()
    text = re.sub(r'[₪,]', '', text)
    if text.startswith('(') and text.endswith(')'): text = '-' + text[1:-1]
    if text.endswith('-'): text = '-' + text[:-1]
    try: return float(text)
    except ValueError: logging.warning(f"Could not convert '{text}' to float."); return None

def parse_date_general(date_str):
    if date_str is None: return None
    try: return datetime.strptime(date_str.strip(), '%d/%m/%Y')
    except ValueError:
        try: return datetime.strptime(date_str.strip(), '%d/%m/%y')
        except ValueError: logging.warning(f"Could not parse date: {date_str}"); return None

def normalize_text_general(text):
    if text is None: return None
    return unicodedata.normalize('NFC', str(text))

# --- HAPOALIM PARSER (Copied) ---
def extract_transactions_from_pdf_hapoalim(pdf_content_bytes, filename_for_logging="hapoalim_pdf"):
    transactions = []
    try:
        doc = fitz.open(stream=pdf_content_bytes, filetype="pdf")
    except Exception as e:
        logging.error(f"Hapoalim: Failed to open/process PDF {filename_for_logging}: {e}", exc_info=True)
        return pd.DataFrame() # Return empty DataFrame on error

    date_pattern_end = re.compile(r"(\d{1,2}/\d{1,2}/\d{4})\s*$")
    balance_pattern_start = re.compile(r"^\s*(₪?-?[\d,]+\.\d{2})")

    for page_num, page in enumerate(doc):
        lines = page.get_text("text", sort=True).splitlines()
        for line_num, line_text in enumerate(lines):
            original_line = line_text
            line_normalized = normalize_text_general(line_text.strip())
            if not line_normalized: continue

            date_match = date_pattern_end.search(original_line)
            if date_match:
                date_str = date_match.group(1)
                parsed_date = parse_date_general(date_str)
                if not parsed_date: continue

                balance_match = balance_pattern_start.search(original_line)
                if balance_match:
                    balance_str = balance_match.group(1)
                    balance = clean_number_general(balance_str)
                    if balance is not None:
                        transactions.append({
                            'Date': parsed_date,
                            'Balance': balance,
                            # 'SourceFile': filename_for_logging, # Optional
                            # 'LineText': original_line.strip()   # Optional
                        })
    doc.close()
    if not transactions:
        return pd.DataFrame()

    df = pd.DataFrame(transactions)
    df['Date'] = pd.to_datetime(df['Date'])
    df['Balance'] = pd.to_numeric(df['Balance'])
    # df = df.sort_values(by=['Date', 'SourceFile', 'LineText']) # Sorting simplified
    df = df.sort_values(by=['Date'])
    df = df.drop_duplicates(subset='Date', keep='last').reset_index(drop=True)
    return df[['Date', 'Balance']]


# --- LEUMI PARSER (Copied and adapted) ---
def clean_transaction_amount_leumi(text):
    if text is None or pd.isna(text) or text == '': return None
    text = str(text).strip().replace('₪', '').replace(',', '')
    if '.' not in text: return None
    text = text.lstrip('\u200b')
    try:
        if text.count('.') > 1:
            parts = text.split('.')
            text = parts[0] + '.' + "".join(parts[1:])
        val = float(text)
        if abs(val) > 1_000_000: return None
        return val
    except ValueError: return None

def clean_number_leumi(text): # Keep specific if needed, or unify with general
    return clean_number_general(text)

def parse_date_leumi(date_str): # Keep specific if needed, or unify with general
    if date_str is None or pd.isna(date_str) or not isinstance(date_str, str): return None
    date_str = date_str.strip()
    if not date_str: return None
    try: return datetime.strptime(date_str, '%d/%m/%Y').date()
    except ValueError:
        try: return datetime.strptime(date_str, '%d/%m/%y').date()
        except ValueError: return None

def normalize_text_leumi(text): # Keep specific for Hebrew reversal
    if text is None or pd.isna(text): return None
    text = str(text).replace('\r', ' ').replace('\n', ' ')
    text = unicodedata.normalize('NFC', text.strip())
    if any('\u0590' <= char <= '\u05EA' for char in text):
       words = text.split()
       reversed_text = ' '.join(words[::-1])
       return reversed_text
    return text

def parse_leumi_transaction_line_extracted_order_v2(line_text, previous_balance):
    line = line_text.strip()
    if not line: return None
    pattern = re.compile(
        r"^([\-\u200b\d,\.]+)\s+"
        r"(\d{1,3}(?:,\d{3})*\.\d{2})?\s*"
        r"(\S+)\s+"
        r"(.*?)\s+"
        r"(\d{1,2}/\d{1,2}/\d{2,4})\s+"
        r"(\d{1,2}/\d{1,2}/\d{2,4})$"
    )
    match = pattern.match(line)
    if not match: return None
    balance_str, amount_str, _, _, date_str, _ = match.groups()
    current_balance = clean_number_leumi(balance_str)
    parsed_date = parse_date_leumi(date_str)
    if parsed_date is None or current_balance is None: return None
    amount = clean_transaction_amount_leumi(amount_str)
    debit = None; credit = None
    if amount is not None and amount != 0 and previous_balance is not None:
        balance_diff = current_balance - previous_balance
        tolerance = 0.02
        if abs(balance_diff + amount) < tolerance: debit = amount
        elif abs(balance_diff - amount) < tolerance: credit = amount
    elif amount is None: return None # Need amount to confirm it's a transaction for balance logic
    
    return {'Date': parsed_date, 'Balance': current_balance, 'Debit': debit, 'Credit': credit}


def extract_leumi_transactions_line_by_line(pdf_content_bytes, filename_for_logging="leumi_pdf"):
    transactions_data = []
    try:
        with pdfplumber.open(io.BytesIO(pdf_content_bytes))as pdf:
            previous_balance = None; first_transaction_processed = False
            for page in pdf.pages:
                text = page.extract_text(x_tolerance=2, y_tolerance=2, layout=True)
                if not text: continue
                for line_text in text.splitlines():
                    parsed_data = parse_leumi_transaction_line_extracted_order_v2(line_text.strip(), previous_balance)
                    if parsed_data:
                        current_balance = parsed_data['Balance']
                        if not first_transaction_processed:
                            previous_balance = current_balance
                            first_transaction_processed = True
                        else:
                            if parsed_data['Debit'] is not None or parsed_data['Credit'] is not None:
                                transactions_data.append({'Date': parsed_data['Date'], 'Balance': current_balance})
                                previous_balance = current_balance
                            else: # Balance line or mismatch, update previous_balance
                                previous_balance = current_balance
    except Exception as e:
        logging.error(f"Leumi: Failed to process PDF {filename_for_logging}: {e}", exc_info=True)
        return pd.DataFrame()
    if not transactions_data: return pd.DataFrame()
    df = pd.DataFrame(transactions_data)
    df['Date'] = pd.to_datetime(df['Date'])
    df = df.sort_values(by='Date').groupby('Date')['Balance'].last().reset_index()
    return df[['Date', 'Balance']]


# --- DISCOUNT PARSER (Copied and adapted) ---
def parse_discont_transaction_line(line_text): # Simplified for balance trend
    line = line_text.strip()
    if not line: return None
    date_pattern = re.compile(r"(\d{1,2}/\d{1,2}/\d{2,4})\s+(\d{1,2}/\d{1,2}/\d{2,4})$")
    date_match = date_pattern.search(line)
    if not date_match: return None
    parsed_date = parse_date_general(date_match.group(1)) # Transaction date
    if not parsed_date: return None
    line_before_dates = line[:date_match.start()].strip()
    balance_amount_pattern = re.compile(r"^([₪\-,\d]+\.\d{2})\s+([₪\-,\d]+\.\d{2})")
    balance_amount_match = balance_amount_pattern.search(line_before_dates)
    if not balance_amount_match: return None
    balance = clean_number_general(balance_amount_match.group(1))
    if balance is None: return None
    return {'Date': parsed_date, 'Balance': balance}

def extract_and_parse_discont_pdf(pdf_content_bytes, filename_for_logging="discount_pdf"):
    transactions = []
    try:
        with pdfplumber.open(io.BytesIO(pdf_content_bytes)) as pdf:
            for page in pdf.pages:
                text = page.extract_text(x_tolerance=2, y_tolerance=2)
                if text:
                    for line_text in text.splitlines():
                        parsed = parse_discont_transaction_line(line_text)
                        if parsed: transactions.append(parsed)
    except Exception as e:
        logging.error(f"Discount: Failed to process PDF {filename_for_logging}: {e}", exc_info=True)
        return pd.DataFrame()
    if not transactions: return pd.DataFrame()
    df = pd.DataFrame(transactions)
    df['Date'] = pd.to_datetime(df['Date'])
    df = df.sort_values(by='Date').groupby('Date')['Balance'].last().reset_index()
    return df[['Date', 'Balance']]


# --- CREDIT REPORT PARSER (Copied) ---
# (Using the full extract_credit_data_final_v13 and its helpers:
#  COLUMN_HEADER_WORDS_CR, BANK_KEYWORDS_CR, process_entry_final_cr)

COLUMN_HEADER_WORDS_CR = {
    "שם", "מקור", "מידע", "מדווח", "מזהה", "עסקה", "מספר", "עסקאות",
    "גובה", "מסגרת", "מסגרות", "סכום", "הלוואות", "מקורי", "יתרת", "חוב",
    "יתרה", "שלא", "שולמה", "במועד"
}
BANK_KEYWORDS_CR = {"בנק", "בע\"מ", "אגוד", "דיסקונט", "לאומי", "הפועלים", "מזרחי",
                 "טפחות", "הבינלאומי", "מרכנתיל", "אוצר", "החייל", "ירושלים",
                 "איגוד", "מימון", "ישיר", "כרטיסי", "אשראי", "מקס", "פיננסים",
                 "כאל", "ישראכרט"}

def process_entry_final_cr(entry_data, section, all_rows_list):
    if not entry_data or not entry_data.get('bank') or len(entry_data.get('numbers', [])) < 2: return

    bank_name_raw = entry_data['bank']
    bank_name_cleaned = re.sub(r'\s*XX-[\w\d\-]+.*', '', bank_name_raw).strip()
    bank_name_cleaned = re.sub(r'\s+\d{1,3}(?:,\d{3})*$', '', bank_name_cleaned).strip()
    bank_name_cleaned = re.sub(r'\s+בע\"מ$', '', bank_name_cleaned).strip()
    bank_name_final = bank_name_cleaned if bank_name_cleaned else bank_name_raw

    is_likely_bank = any(kw in bank_name_final for kw in ["בנק", "לאומי", "הפועלים", "דיסקונט", "מזרחי", "הבינלאומי", "מרכנתיל", "ירושלים", "איגוד"])
    # is_non_bank_entity = any(kw in bank_name_final for kw in ["מימון ישיר", "מקס איט", "כרטיסי אשראי", "כאל", "ישראכרט"]) # Less crucial for simple name ending

    if is_likely_bank and not bank_name_final.endswith("בע\"מ"):
        bank_name_final += " בע\"מ"
    # Simplified: if any of the specific non-bank entities that DO end with בע"מ are present, add it
    elif any(kw in bank_name_final for kw in ["מקס איט פיננסים", "מימון ישיר נדל\"ן ומשכנתאות"]) and not bank_name_final.endswith("בע\"מ"):
         bank_name_final += " בע\"מ"


    numbers = entry_data['numbers']
    num_count = len(numbers)
    limit_col, original_col, outstanding_col, unpaid_col = np.nan, np.nan, np.nan, np.nan

    if num_count >= 2:
        val1 = numbers[0]; val2 = numbers[1]; val3 = numbers[2] if num_count >= 3 else 0.0

        if section in ["עו\"ש", "מסגרת אשראי"]:
            limit_col = val1; outstanding_col = val2; unpaid_col = val3
        elif section in ["הלוואה", "משכנתה"]:
            if num_count >= 3:
                 if val1 < 50 and val1 == int(val1) and num_count >= 4: # num_transactions heuristic
                      original_col = numbers[1]; outstanding_col = numbers[2]; unpaid_col = numbers[3]
                 else:
                     original_col = val1; outstanding_col = val2; unpaid_col = val3
            elif num_count == 2:
                 original_col = val1; outstanding_col = val2; unpaid_col = 0.0
        else:
            original_col = val1; outstanding_col = val2; unpaid_col = val3

        all_rows_list.append({
            "סוג עסקה": section, "שם בנק/מקור": bank_name_final,
            "גובה מסגרת": limit_col, "סכום מקורי": original_col,
            "יתרת חוב": outstanding_col, "יתרה שלא שולמה": unpaid_col
        })

def extract_credit_data_final_v13(pdf_content_bytes, filename_for_logging="credit_report_pdf"):
    extracted_rows = []
    try:
        with fitz.open(stream=pdf_content_bytes, filetype="pdf") as doc:
            current_section = None; current_entry = None
            last_line_was_id = False; potential_bank_continuation_candidate = False
            section_patterns = { "חשבון עובר ושב": "עו\"ש", "הלוואה": "הלוואה", "משכנתה": "משכנתה", "מסגרת אשראי מתחדשת": "מסגרת אשראי"}
            number_line_pattern = re.compile(r"^\s*(-?\d{1,3}(?:,\d{3})*\.?\d*)\s*$")

            for page in doc:
                lines = page.get_text("text").splitlines()
                for line_text in lines:
                    line = line_text.strip()
                    if not line: potential_bank_continuation_candidate = False; continue
                    is_section_header = False
                    for header_keyword, section_name in section_patterns.items():
                        if header_keyword in line and len(line) < len(header_keyword) + 20 and line.count(' ') < 5:
                            if current_entry and not current_entry.get('processed', False): process_entry_final_cr(current_entry, current_section, extracted_rows)
                            current_section = section_name; current_entry = None; last_line_was_id = False; potential_bank_continuation_candidate = False; is_section_header = True; break
                    if is_section_header: continue
                    if line.startswith("סה\"כ"):
                        if current_entry and not current_entry.get('processed', False): process_entry_final_cr(current_entry, current_section, extracted_rows)
                        current_entry = None; last_line_was_id = False; potential_bank_continuation_candidate = False; continue
                    if current_section:
                        number_match = number_line_pattern.match(line)
                        is_id_line = line.startswith("XX-") and len(line) > 5
                        is_noise_line = any(word == line for word in COLUMN_HEADER_WORDS_CR) or line in [':', '.'] or (len(line)<3 and not line.isdigit())
                        if number_match:
                            if current_entry:
                                try:
                                    number = float(number_match.group(1).replace(",", ""))
                                    num_list = current_entry.get('numbers', [])
                                    if last_line_was_id and len(num_list) >= 2:
                                        if not current_entry.get('processed', False): process_entry_final_cr(current_entry, current_section, extracted_rows)
                                        current_entry = {'bank': current_entry['bank'], 'numbers': [number], 'processed': False}
                                    elif len(num_list) < 4: current_entry['numbers'].append(number)
                                except ValueError: pass
                            last_line_was_id = False; potential_bank_continuation_candidate = False; continue
                        elif is_id_line: last_line_was_id = True; potential_bank_continuation_candidate = False; continue
                        elif is_noise_line: last_line_was_id = False; potential_bank_continuation_candidate = False; continue
                        else:
                             cleaned_line = re.sub(r'\s*XX-[\w\d\-]+.*|\d+$', '', line).strip()
                             is_potential_bank = any(kw in cleaned_line for kw in BANK_KEYWORDS_CR) or len(cleaned_line) > 6
                             common_continuations = ["לישראל", "בע\"מ", "ומשכנתאות", "נדל\"ן", "דיסקונט", "הראשון", "פיננסים"]
                             is_continuation = potential_bank_continuation_candidate and current_entry and not current_entry.get('numbers') and any(cleaned_line.startswith(cont) for cont in common_continuations)
                             if is_continuation and cleaned_line:
                                 current_entry['bank'] = (current_entry['bank'] + " " + cleaned_line).replace(" בע\"מ בע\"מ", " בע\"מ")
                                 potential_bank_continuation_candidate = True
                             elif is_potential_bank:
                                 if current_entry and not current_entry.get('processed', False): process_entry_final_cr(current_entry, current_section, extracted_rows)
                                 current_entry = {'bank': line, 'numbers': [], 'processed': False}
                                 potential_bank_continuation_candidate = True
                             else: potential_bank_continuation_candidate = False
                             last_line_was_id = False
            if current_entry and not current_entry.get('processed', False): process_entry_final_cr(current_entry, current_section, extracted_rows)
    except Exception as e:
        logging.error(f"CreditReport: FATAL ERROR processing {filename_for_logging}: {e}", exc_info=True)
        return pd.DataFrame()
    if not extracted_rows: return pd.DataFrame()
    df = pd.DataFrame(extracted_rows)
    final_cols = ["סוג עסקה", "שם בנק/מקור", "גובה מסגרת", "סכום מקורי", "יתרת חוב", "יתרה שלא שולמה"]
    for col in final_cols:
        if col not in df.columns: df[col] = np.nan
    df = df[final_cols]
    for col in ["גובה מסגרת", "סכום מקורי", "יתרת חוב", "יתרה שלא שולמה"]:
        if col in df.columns: df[col] = pd.to_numeric(df[col], errors='coerce')
    return df


# --- Initialize Session State ---
if 'app_stage' not in st.session_state: st.session_state.app_stage = "welcome" # welcome, file_upload, questionnaire, summary
if 'questionnaire_stage' not in st.session_state: st.session_state.questionnaire_stage = 0
if 'answers' not in st.session_state: st.session_state.answers = {}
if 'classification_details' not in st.session_state: st.session_state.classification_details = {}
if 'chat_messages' not in st.session_state: st.session_state.chat_messages = []
# DataFrames for parsed files
if 'df_bank_uploaded' not in st.session_state: st.session_state.df_bank_uploaded = pd.DataFrame()
if 'df_credit_uploaded' not in st.session_state: st.session_state.df_credit_uploaded = pd.DataFrame()
if 'bank_type_selected' not in st.session_state: st.session_state.bank_type_selected = "ללא דוח בנק"
if 'total_debt_from_credit_report' not in st.session_state: st.session_state.total_debt_from_credit_report = None


def reset_all_data():
    st.session_state.app_stage = "welcome"
    st.session_state.questionnaire_stage = 0
    st.session_state.answers = {}
    st.session_state.classification_details = {}
    st.session_state.chat_messages = []
    st.session_state.df_bank_uploaded = pd.DataFrame()
    st.session_state.df_credit_uploaded = pd.DataFrame()
    st.session_state.bank_type_selected = "ללא דוח בנק"
    st.session_state.total_debt_from_credit_report = None


st.set_page_config(layout="wide", page_title="יועץ פיננסי משולב", page_icon="🧩")
st.title("🧩 יועץ פיננסי משולב: שאלון וניתוח דוחות")

# --- Sidebar ---
with st.sidebar:
    st.header("אפשרויות")
    if st.button("התחל מחדש את כל התהליך", key="reset_sidebar_button"):
        reset_all_data()
        st.rerun()
    st.markdown("---")
    st.caption("© כל הזכויות שמורות. כלי זה נועד למטרות אבחון ראשוני ואינו מהווה ייעוץ פיננסי.")


# --- Main Application Flow ---

if st.session_state.app_stage == "welcome":
    st.header("ברוכים הבאים ליועץ הפיננסי המשולב!")
    st.markdown("""
    כלי זה יעזור לך לקבל תמונה על מצבך הפיננסי באמצעות שילוב של:
    1.  **העלאת דוחות**: דוח בנק ודוח נתוני אשראי (אופציונלי, אך מומלץ לניתוח מדויק).
    2.  **שאלון פיננסי**: למילוי פרטים נוספים על הכנסות, הוצאות ומצבך הכללי.

    בסיום התהליך תקבל סיכום, סיווג פיננסי ראשוני, ויזואליזציות ואפשרות לשוחח עם יועץ וירטואלי.
    """)
    if st.button("התחל בהעלאת קבצים (מומלץ)", key="start_with_files"):
        st.session_state.app_stage = "file_upload"
        st.rerun()
    if st.button("התחל ישירות עם השאלון הפיננסי", key="start_with_questionnaire"):
        st.session_state.app_stage = "questionnaire"
        st.session_state.questionnaire_stage = 0 # Start questionnaire from beginning
        st.rerun()

elif st.session_state.app_stage == "file_upload":
    st.header("שלב 1: העלאת דוחות")
    
    bank_type_options = ["ללא דוח בנק", "הפועלים", "דיסקונט", "לאומי"]
    st.session_state.bank_type_selected = st.selectbox("בחר סוג דוח בנק:", bank_type_options, 
                                                       index=bank_type_options.index(st.session_state.bank_type_selected), 
                                                       key="bank_type_selector_main")

    uploaded_bank_file = None
    if st.session_state.bank_type_selected != "ללא דוח בנק":
        uploaded_bank_file = st.file_uploader(f"העלה דוח בנק ({st.session_state.bank_type_selected})", type="pdf", key="bank_pdf_uploader_main")

    uploaded_credit_file = st.file_uploader("העלה דוח נתוני אשראי (קובץ PDF)", type="pdf", key="credit_pdf_uploader_main")

    if st.button("עבד קבצים והמשך לשאלון", key="process_files_button"):
        with st.spinner("מעבד קבצים..."):
            # Process Bank File
            st.session_state.df_bank_uploaded = pd.DataFrame() # Reset
            if uploaded_bank_file is not None and st.session_state.bank_type_selected != "ללא דוח בנק":
                bank_file_bytes = uploaded_bank_file.getvalue()
                parser_func = None
                if st.session_state.bank_type_selected == "הפועלים": parser_func = extract_transactions_from_pdf_hapoalim
                elif st.session_state.bank_type_selected == "לאומי": parser_func = extract_leumi_transactions_line_by_line
                elif st.session_state.bank_type_selected == "דיסקונט": parser_func = extract_and_parse_discont_pdf
                
                if parser_func:
                    st.session_state.df_bank_uploaded = parser_func(bank_file_bytes, uploaded_bank_file.name)
                
                if st.session_state.df_bank_uploaded.empty:
                    st.warning(f"לא הצלחנו לחלץ נתונים מדוח הבנק ({st.session_state.bank_type_selected}).")
                else:
                    st.success(f"דוח בנק ({st.session_state.bank_type_selected}) עובד בהצלחה!")

            # Process Credit File
            st.session_state.df_credit_uploaded = pd.DataFrame() # Reset
            st.session_state.total_debt_from_credit_report = None # Reset
            if uploaded_credit_file is not None:
                credit_file_bytes = uploaded_credit_file.getvalue()
                st.session_state.df_credit_uploaded = extract_credit_data_final_v13(credit_file_bytes, uploaded_credit_file.name)
                if st.session_state.df_credit_uploaded.empty:
                    st.warning("לא הצלחנו לחלץ נתונים מדוח האשראי.")
                else:
                    st.success("דוח נתוני אשראי עובד בהצלחה!")
                    if 'יתרת חוב' in st.session_state.df_credit_uploaded.columns:
                        st.session_state.total_debt_from_credit_report = st.session_state.df_credit_uploaded['יתרת חוב'].sum()
                        st.info(f"סך יתרת החוב שחושבה מדוח האשראי: {st.session_state.total_debt_from_credit_report:,.0f} ₪")

        st.session_state.app_stage = "questionnaire"
        st.session_state.questionnaire_stage = 0 # Start questionnaire
        st.rerun()
    
    if st.button("דלג על העלאת קבצים והמשך לשאלון", key="skip_files_button"):
        st.session_state.app_stage = "questionnaire"
        st.session_state.questionnaire_stage = 0 # Start questionnaire
        st.rerun()


elif st.session_state.app_stage == "questionnaire":
    st.header("שלב 2: שאלון פיננסי")
    # --- Questionnaire Stages (Copied and adapted from previous "Questionnaire Only" app) ---
    q_stage = st.session_state.questionnaire_stage

    # Stage 0 of Questionnaire: Initial Questions
    if q_stage == 0:
        st.subheader("חלק א': שאלות פתיחה")
        # ... (copy paste from Stage 0 of questionnaire app, ensure keys are unique if needed or reuse)
        st.session_state.answers['q1_unusual_event'] = st.text_area("1. האם קרה משהו חריג שבגללו פנית?", value=st.session_state.answers.get('q1_unusual_event', ''), key="q_s0_q1")
        st.session_state.answers['q2_other_funding'] = st.text_area("2. האם יש מקורות מימון אחרים שבדקת?", value=st.session_state.answers.get('q2_other_funding', ''), key="q_s0_q2")
        st.session_state.answers['q3_existing_loans_bool'] = st.radio("3. האם קיימות הלוואות נוספות (לא משכנתא)?", ("כן", "לא"), index=("לא","כן").index(st.session_state.answers.get('q3_existing_loans_bool', 'לא')), key="q_s0_q3_bool")
        if st.session_state.answers['q3_existing_loans_bool'] == "כן":
            st.session_state.answers['q3_loan_repayment_amount'] = st.number_input("מה גובה ההחזר החודשי עליהן?", min_value=0, value=st.session_state.answers.get('q3_loan_repayment_amount', 0), key="q_s0_q3_amount")
        else: st.session_state.answers['q3_loan_repayment_amount'] = 0
        st.session_state.answers['q4_financially_balanced_bool'] = st.radio("4. האם אתם מאוזנים כלכלית כרגע?", ("כן", "בערך", "לא"), index=("כן","בערך","לא").index(st.session_state.answers.get('q4_financially_balanced_bool', 'כן')), key="q_s0_q4_bool")
        st.session_state.answers['q4_situation_change_next_year'] = st.text_area("האם המצב צפוי להשתנות בשנה הקרובה?", value=st.session_state.answers.get('q4_situation_change_next_year', ''), key="q_s0_q4_change")
        
        if st.button("הבא", key="q_s0_next"):
            st.session_state.questionnaire_stage += 1
            st.rerun()

    # Stage 1 of Questionnaire: Income
    elif q_stage == 1:
        st.subheader("חלק ב': הכנסות (נטו חודשי)")
        st.session_state.answers['income_employee'] = st.number_input("הכנסתך:", min_value=0, value=st.session_state.answers.get('income_employee', 0), key="q_s1_inc_emp")
        st.session_state.answers['income_partner'] = st.number_input("הכנסת בן/בת הזוג:", min_value=0, value=st.session_state.answers.get('income_partner', 0), key="q_s1_inc_partner")
        st.session_state.answers['income_other'] = st.number_input("הכנסות נוספות (קצבאות וכו'):", min_value=0, value=st.session_state.answers.get('income_other', 0), key="q_s1_inc_other")
        total_net_income = sum(st.session_state.answers.get(k,0) for k in ['income_employee','income_partner','income_other'])
        st.session_state.answers['total_net_income'] = total_net_income
        st.metric("סך הכנסות נטו:", f"{total_net_income:,.0f} ₪")
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("הקודם", key="q_s1_prev"): st.session_state.questionnaire_stage -= 1; st.rerun()
        with col2:
            if st.button("הבא", key="q_s1_next"): st.session_state.questionnaire_stage += 1; st.rerun()

    # Stage 2 of Questionnaire: Fixed Expenses
    elif q_stage == 2:
        st.subheader("חלק ג': הוצאות קבועות חודשיות")
        st.session_state.answers['expense_rent_mortgage'] = st.number_input("שכירות/משכנתא:", min_value=0, value=st.session_state.answers.get('expense_rent_mortgage', 0), key="q_s2_exp_rent")
        default_debt_repayment = st.session_state.answers.get('q3_loan_repayment_amount', 0)
        st.session_state.answers['expense_debt_repayments'] = st.number_input("החזרי הלוואות (לא משכנתא):", min_value=0, value=st.session_state.answers.get('expense_debt_repayments', default_debt_repayment), key="q_s2_exp_debt")
        st.session_state.answers['expense_alimony_other'] = st.number_input("מזונות/הוצאות קבועות גדולות אחרות:", min_value=0, value=st.session_state.answers.get('expense_alimony_other', 0), key="q_s2_exp_alimony")
        total_fixed_expenses = sum(st.session_state.answers.get(k,0) for k in ['expense_rent_mortgage','expense_debt_repayments','expense_alimony_other'])
        st.session_state.answers['total_fixed_expenses'] = total_fixed_expenses
        st.metric("סך הוצאות קבועות:", f"{total_fixed_expenses:,.0f} ₪")
        monthly_balance = st.session_state.answers.get('total_net_income', 0) - total_fixed_expenses
        st.session_state.answers['monthly_balance'] = monthly_balance
        st.metric("מאזן חודשי (הכנסות פחות קבועות):", f"{monthly_balance:,.0f} ₪")
        if monthly_balance < 0: st.warning("ההוצאות הקבועות גבוהות מההכנסות.")

        col1, col2 = st.columns(2)
        with col1:
            if st.button("הקודם", key="q_s2_prev"): st.session_state.questionnaire_stage -= 1; st.rerun()
        with col2:
            if st.button("הבא", key="q_s2_next"): st.session_state.questionnaire_stage += 1; st.rerun()

    # Stage 3 of Questionnaire: Total Debts & Arrears
    elif q_stage == 3:
        st.subheader("חלק ד': חובות ופיגורים")
        # If total debt was calculated from credit report, use it as default
        default_total_debt = st.session_state.total_debt_from_credit_report if st.session_state.total_debt_from_credit_report is not None else st.session_state.answers.get('total_debt_amount', 0)
        if st.session_state.total_debt_from_credit_report is not None:
            st.info(f"סך יתרת החוב שחושבה מדוח האשראי שהועלה הוא: {st.session_state.total_debt_from_credit_report:,.0f} ₪. ניתן לעדכן אם יש חובות נוספים שלא מופיעים בדוח.")

        st.session_state.answers['total_debt_amount'] = st.number_input(
            "מה היקף החובות הכולל שלך (ללא משכנתא)?",
            min_value=0, value=default_total_debt, step=100, key="q_s3_total_debt"
        )
        st.session_state.answers['arrears_collection_proceedings'] = st.radio(
            "האם קיימים פיגורים בתשלומים או הליכי גבייה נגדך?",
            ("כן", "לא"), index=("לא","כן").index(st.session_state.answers.get('arrears_collection_proceedings', 'לא')), key="q_s3_arrears")

        col1, col2 = st.columns(2)
        with col1:
            if st.button("הקודם", key="q_s3_prev"): st.session_state.questionnaire_stage -= 1; st.rerun()
        with col2:
            if st.button("המשך לסיכום וסיווג", key="q_s3_next_finish"):
                # Calculate Debt-to-Income Ratio
                total_debt = st.session_state.answers.get('total_debt_amount', 0)
                annual_income = st.session_state.answers.get('total_net_income', 0) * 12
                st.session_state.answers['annual_income'] = annual_income
                st.session_state.answers['debt_to_income_ratio'] = (total_debt / annual_income) if annual_income > 0 else (float('inf') if total_debt > 0 else 0)
                
                # Classification logic
                ratio = st.session_state.answers['debt_to_income_ratio']
                if ratio < 1:
                    st.session_state.classification_details = {'classification': "ירוק", 'description': "סך החוב נמוך מההכנסה השנתית.", 'color': "green"}
                    st.session_state.app_stage = "summary" # Go to main summary
                elif 1 <= ratio <= 2:
                    st.session_state.classification_details = {'classification': "צהוב (בבדיקה)", 'description': "סך החוב בגובה ההכנסה של 1-2 שנים.", 'color': "orange"}
                    st.session_state.questionnaire_stage = 100 # Special stage for mid-tier questions in questionnaire
                else: # ratio > 2
                    st.session_state.classification_details = {'classification': "אדום", 'description': "סך החוב בגובה ההכנסה של שנתיים או יותר.", 'color': "red"}
                    st.session_state.app_stage = "summary" # Go to main summary
                st.rerun()

    # Stage 100 of Questionnaire: Intermediate questions for Yellow classification
    elif q_stage == 100:
        st.subheader("שאלות הבהרה נוספות (לאחר חישוב יחס חוב/הכנסה)")
        st.warning(f"יחס החוב להכנסה שלך הוא {st.session_state.answers.get('debt_to_income_ratio', 0):.2f}. ({st.session_state.classification_details.get('description')})")
        
        collection_proceedings = st.session_state.answers.get('arrears_collection_proceedings', 'לא')
        st.write(f"ציינת ש {'קיימים' if collection_proceedings == 'כן' else 'לא קיימים'} נגדך הליכי גבייה.")

        if collection_proceedings == "כן":
            st.session_state.classification_details.update({'classification': "אדום", 'description': st.session_state.classification_details.get('description','') + " קיימים הליכי גבייה.", 'color': "red"})
            if st.button("המשך לסיכום", key="q_s100_to_summary_red"):
                st.session_state.app_stage = "summary"; st.rerun()
        else:
            st.session_state.answers['can_raise_50_percent'] = st.radio(
                f"האם תוכל לגייס 50% מהחוב ({st.session_state.answers.get('total_debt_amount', 0) * 0.5:,.0f} ₪) ממקורות תמיכה תוך זמן סביר?",
                ("כן", "לא"), index=("לא","כן").index(st.session_state.answers.get('can_raise_50_percent', 'לא')), key="q_s100_q_raise_funds")
            if st.button("המשך לסיכום", key="q_s100_to_summary_yellow_check"):
                if st.session_state.answers['can_raise_50_percent'] == "כן":
                    st.session_state.classification_details.update({'classification': "צהוב", 'description': st.session_state.classification_details.get('description','') + " אין הליכי גבייה ויכולת לגייס 50% מהחוב.", 'color': "orange"})
                else:
                    st.session_state.classification_details.update({'classification': "אדום", 'description': st.session_state.classification_details.get('description','') + " אין הליכי גבייה אך אין יכולת לגייס 50% מהחוב.", 'color': "red"})
                st.session_state.app_stage = "summary"; st.rerun()
        
        if st.button("חזור לשלב הקודם בשאלון", key="q_s100_prev"):
            st.session_state.questionnaire_stage = 3; st.rerun()

elif st.session_state.app_stage == "summary":
    st.header("שלב 3: סיכום, ויזואליזציות וייעוץ")

    # Display calculated metrics from questionnaire
    st.subheader("📊 סיכום נתונים (משאלון וקבצים)")
    col1, col2, col3 = st.columns(3)
    total_net_income_ans = st.session_state.answers.get('total_net_income', 0)
    total_debt_amount_ans = st.session_state.answers.get('total_debt_amount', 0)
    annual_income_ans = st.session_state.answers.get('annual_income', 0)
    debt_to_income_ratio_ans = st.session_state.answers.get('debt_to_income_ratio', 0)
    
    with col1:
        st.metric("💰 סך חובות (ללא משכנתא)", f"{total_debt_amount_ans:,.0f} ₪")
        if st.session_state.total_debt_from_credit_report is not None and st.session_state.total_debt_from_credit_report != total_debt_amount_ans:
             st.caption(f"(מדוח אשראי: {st.session_state.total_debt_from_credit_report:,.0f} ₪)")
    with col2:
        st.metric("📈 הכנסה שנתית (משאלון)", f"{annual_income_ans:,.0f} ₪")
    with col3:
        st.metric("⚖️ יחס חוב להכנסה", f"{debt_to_income_ratio_ans:.2%}")

    # Display classification
    classification = st.session_state.classification_details.get('classification', "לא נקבע")
    description = st.session_state.classification_details.get('description', "")
    color = st.session_state.classification_details.get('color', "gray")
    st.subheader("סיווג והמלצה ראשונית:")
    if color == "green": st.success(f"🟢 **סיווג: {classification}**")
    elif color == "orange": st.warning(f"🟡 **סיווג: {classification}**")
    elif color == "red": st.error(f"🔴 **סיווג: {classification}**")
    st.markdown(f"*{description}*")
    # ... (add more detailed recommendations based on classification as before)

    st.markdown("---")
    st.subheader("🎨 ויזואליזציות")
    # Visualization 1: Debt Breakdown from Credit Report (Pie Chart)
    if not st.session_state.df_credit_uploaded.empty and 'סוג עסקה' in st.session_state.df_credit_uploaded.columns and 'יתרת חוב' in st.session_state.df_credit_uploaded.columns:
        debt_summary = st.session_state.df_credit_uploaded.groupby("סוג עסקה")["יתרת חוב"].sum().reset_index()
        debt_summary = debt_summary[debt_summary['יתרת חוב'] > 0]
        if not debt_summary.empty:
            fig_debt_pie = px.pie(debt_summary, values='יתרת חוב', names='סוג עסקה', title='פירוט יתרות חוב (מדוח אשראי)', color_discrete_sequence=px.colors.qualitative.Pastel)
            fig_debt_pie.update_traces(textposition='inside', textinfo='percent+label')
            st.plotly_chart(fig_debt_pie, use_container_width=True)
    
    # Visualization 2: Debt vs. Income (Bar Chart) - Using data from questionnaire/final calculation
    if total_debt_amount_ans > 0 and annual_income_ans > 0 :
        comparison_data = pd.DataFrame({'קטגוריה': ['סך חובות', 'הכנסה שנתית'], 'סכום': [total_debt_amount_ans, annual_income_ans]})
        fig_debt_income_bar = px.bar(comparison_data, x='קטגוריה', y='סכום', title='השוואת סך חובות להכנסה שנתית', color='קטגוריה', text_auto=True)
        st.plotly_chart(fig_debt_income_bar, use_container_width=True)

    # Visualization 3: Bank Balance Trend (Line Chart)
    if not st.session_state.df_bank_uploaded.empty:
        st.subheader(f"מגמת יתרת חשבון בנק ({st.session_state.bank_type_selected})")
        df_bank_plot = st.session_state.df_bank_uploaded.dropna(subset=['Date', 'Balance'])
        if not df_bank_plot.empty:
            fig_balance_trend = px.line(df_bank_plot, x='Date', y='Balance', title=f'מגמת יתרת חשבון', markers=True)
            st.plotly_chart(fig_balance_trend, use_container_width=True)

    # Display DataFrames (optional)
    with st.expander("הצג נתונים שחולצו מדוחות שהועלו"):
        if not st.session_state.df_credit_uploaded.empty:
            st.write("נתוני אשראי מחולצים:")
            st.dataframe(st.session_state.df_credit_uploaded.style.format("{:,.0f}", subset=pd.IndexSlice[:, ['גובה מסגרת', 'סכום מקורי', 'יתרת חוב', 'יתרה שלא שולמה']]))
        if not st.session_state.df_bank_uploaded.empty:
            st.write(f"נתוני יתרות בנק מחולצים ({st.session_state.bank_type_selected}):")
            st.dataframe(st.session_state.df_bank_uploaded.style.format({"Balance": '{:,.2f}'}))
        if st.session_state.df_credit_uploaded.empty and st.session_state.df_bank_uploaded.empty:
            st.write("לא הועלו או עובדו קבצים.")
    
    st.markdown("---")
    # --- Chatbot Interface ---
    st.header("💬 צ'אט עם יועץ פיננסי וירטואלי")
    if client:
        # Prepare context for chatbot
        financial_context = "סיכום המצב הפיננסי של המשתמש:\n"
        financial_context += f"- סך הכנסות נטו חודשיות (משאלון): {st.session_state.answers.get('total_net_income', 0):,.0f} ₪\n"
        financial_context += f"- סך הוצאות קבועות חודשיות (משאלון): {st.session_state.answers.get('total_fixed_expenses', 0):,.0f} ₪\n"
        financial_context += f"- מאזן חודשי (משאלון): {st.session_state.answers.get('monthly_balance', 0):,.0f} ₪\n"
        financial_context += f"- סך חובות (ללא משכנתא, לאחר שאלון ואולי עדכון מדוח): {total_debt_amount_ans:,.0f} ₪\n"
        if st.session_state.total_debt_from_credit_report is not None:
            financial_context += f"  - מתוכם, סך יתרת חוב מדוח אשראי: {st.session_state.total_debt_from_credit_report:,.0f} ₪\n"
            if not st.session_state.df_credit_uploaded.empty:
                financial_context += "  - פירוט חובות מדוח אשראי:\n"
                for _, row in st.session_state.df_credit_uploaded.iterrows():
                    financial_context += f"    - {row['סוג עסקה']} ב{row['שם בנק/מקור']}: יתרת חוב {row['יתרת חוב']:,.0f} ₪ (שולם בפיגור: {row['יתרה שלא שולמה']:,.0f} ₪)\n"

        financial_context += f"- הכנסה שנתית: {annual_income_ans:,.0f} ₪\n"
        financial_context += f"- יחס חוב להכנסה: {debt_to_income_ratio_ans:.2%}\n"
        financial_context += f"- סיווג מצב: {classification} ({description})\n"
        financial_context += "\nתשובות נוספות מהשאלון:\n"
        for key, value in st.session_state.answers.items():
            # Avoid re-listing already summarized numeric data, focus on qualitative answers
            if key not in ['total_net_income', 'total_fixed_expenses', 'monthly_balance', 'total_debt_amount', 'annual_income', 'debt_to_income_ratio',
                           'income_employee', 'income_partner', 'income_other', 'expense_rent_mortgage', 'expense_debt_repayments', 'expense_alimony_other']:
                financial_context += f"- {key.replace('_', ' ').replace('q s0 ', '').replace('q s1 ', '').replace('q s2 ', '').replace('q s3 ', '')}: {value}\n"
        
        financial_context += "\n--- סוף מידע על המשתמש ---\n"


        for message in st.session_state.chat_messages:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])

        if prompt := st.chat_input("שאל אותי כל שאלה על מצבך הפיננסי או כלכלת המשפחה..."):
            st.session_state.chat_messages.append({"role": "user", "content": prompt})
            with st.chat_message("user"): st.markdown(prompt)

            with st.chat_message("assistant"):
                message_placeholder = st.empty()
                full_response = ""
                messages_for_api = [
                    {"role": "system", "content": f"אתה מומחה לכלכלת המשפחה בישראל. המשתמש סיפק את הנתונים הבאים: \n{financial_context}\n ענה בעברית. ספק ייעוץ פרקטי, ברור ואמפתי."}
                ] + [{"role": m["role"], "content": m["content"]} for m in st.session_state.chat_messages]
                
                try:
                    stream = client.chat.completions.create(model="gpt-3.5-turbo", messages=messages_for_api, stream=True)
                    for chunk in stream:
                        if chunk.choices[0].delta.content is not None:
                            full_response += chunk.choices[0].delta.content
                            message_placeholder.markdown(full_response + "▌")
                    message_placeholder.markdown(full_response)
                except Exception as e:
                    full_response = f"מצטער, התרחשה שגיאה: {e}"
                    message_placeholder.markdown(full_response)
            st.session_state.chat_messages.append({"role": "assistant", "content": full_response})
    else:
        st.warning("שירות הצ'אט אינו זמין (ייתכן שחסר מפתח API).")