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
from openai import APIError # Specific import for API errors

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- OpenAI Client Setup ---
client = None # Initialize client to None
try:
    # Attempt to get API key from secrets
    api_key = st.secrets["OPENAI_API_KEY"]
    client = OpenAI(api_key=api_key)
    logging.info("OpenAI client initialized successfully.")
except Exception as e:
    logging.error(f"Error loading OpenAI API key or initializing client: {e}", exc_info=True)
    st.error(f"שגיאה בטעינת מפתח OpenAI או בהפעלת שירות הצ'אט: {e}. הצ'אטבוט עשוי לא לפעול כראוי.")
    # Client remains None

# --- Helper Functions ---
def clean_number_general(text):
    """Cleans numeric strings, handling currency symbols, commas, and parentheses."""
    if text is None: return None
    text = str(text).strip()
    text = re.sub(r'[₪,]', '', text)
    # Handle negative numbers in parentheses like (123.45)
    if text.startswith('(') and text.endswith(')'):
        text = '-' + text[1:-1]
    # Handle negative numbers ending with a dash like 123.45-
    if text.endswith('-'):
        text = '-' + text[:-1]
    try:
        # Attempt conversion to float, handles empty string after cleaning
        if text == "": return None
        return float(text)
    except ValueError:
        logging.warning(f"Could not convert '{text}' to float.");
        return None

def parse_date_general(date_str):
    """Parses date strings in multiple formats."""
    if date_str is None or pd.isna(date_str) or not isinstance(date_str, str): return None
    date_str = date_str.strip()
    if not date_str: return None
    try:
        return datetime.strptime(date_str, '%d/%m/%Y').date()
    except ValueError:
        try:
            return datetime.strptime(date_str, '%d/%m/%y').date()
        except ValueError:
            logging.warning(f"Could not parse date: {date_str}");
            return None

def normalize_text_general(text):
    """Normalizes Unicode text (removes potential hidden chars, ensures NFC)."""
    if text is None: return None
    # Replace various problematic spaces/chars before normalizing
    text = str(text).replace('\r', ' ').replace('\n', ' ').replace('\u200b', '').strip()
    # NFC normalization is standard for Hebrew
    return unicodedata.normalize('NFC', text)


# --- HAPOALIM PARSER ---
def extract_transactions_from_pdf_hapoalim(pdf_content_bytes, filename_for_logging="hapoalim_pdf"):
    """Extracts Date and Balance from Hapoalim PDF based on line patterns."""
    transactions = []
    try:
        doc = fitz.open(stream=pdf_content_bytes, filetype="pdf")
    except Exception as e:
        logging.error(f"Hapoalim: Failed to open/process PDF {filename_for_logging}: {e}", exc_info=True)
        return pd.DataFrame() # Return empty DataFrame on error

    # Patterns adjusted to be more robust and handle different potential white spaces
    # Pattern for date at the end of the line, preceded by variable white space
    date_pattern_end = re.compile(r"\s*(\d{1,2}/\d{1,2}/\d{4})\s*$")
    # Pattern for balance at the start of the line, preceded by optional spaces, currency, sign
    balance_pattern_start = re.compile(r"^\s*[₪]?[+\-]?\s*([\d,]+\.\d{2})")

    logging.info(f"Starting Hapoalim PDF parsing for {filename_for_logging}")

    for page_num, page in enumerate(doc):
        try:
            # Use 'text' with sort=True for better line order
            lines = page.get_text("text", sort=True).splitlines()
            logging.debug(f"Page {page_num + 1} has {len(lines)} lines.")

            for line_num, line_text in enumerate(lines):
                original_line = line_text # Keep original for potentially better pattern matching on raw text
                line_normalized = normalize_text_general(original_line) # Normalize for general checks

                if not line_normalized or len(line_normalized) < 10: continue # Skip very short or empty lines

                # Match date first, as it's a strong indicator of a transaction line ending
                date_match = date_pattern_end.search(original_line)
                if date_match:
                    date_str = date_match.group(1)
                    parsed_date = parse_date_general(date_str)

                    if parsed_date:
                        # Now try to find the balance at the beginning of the same line
                        balance_match = balance_pattern_start.search(original_line)
                        if balance_match:
                            balance_str = balance_match.group(1)
                            balance = clean_number_general(balance_str) # Use general cleaner

                            # Check if balance could be part of another number/text before it
                            # Simple check: ensure there's enough space or separation before the balance string starts
                            balance_start_index = balance_match.start()
                            if balance_start_index > 0:
                                char_before = original_line[balance_start_index - 1]
                                if char_before not in (' ', '₪', '-', '+'):
                                    # If the character before isn't a space or expected currency/sign,
                                    # it might not be the balance field we want. Skip this match.
                                    # This is a heuristic and might need tuning.
                                    logging.debug(f"Skipping line {line_num+1} due to unexpected char before balance: '{original_line[:balance_start_index]}'")
                                    continue


                            if balance is not None:
                                # Check if the line is not a header or footer line
                                lower_line = line_normalized.lower()
                                if "יתרה לסוף יום" in lower_line or "עובר ושב" in lower_line or "תנועות בחשבון" in lower_line or "עמוד" in lower_line:
                                    logging.debug(f"Skipping potential header/footer line: {original_line}")
                                    continue # Skip lines that look like headers/footers despite having date/number

                                transactions.append({
                                    'Date': parsed_date,
                                    'Balance': balance,
                                    # 'SourceFile': filename_for_logging, # Optional
                                    # 'LineText': original_line.strip()   # Optional
                                })
                                logging.debug(f"Hapoalim: Found transaction - Date: {parsed_date}, Balance: {balance}, Line: {original_line}")
                            else:
                                logging.debug(f"Hapoalim: Found date but failed to clean balance: {balance_str} in line: {original_line}")
                        else:
                            logging.debug(f"Hapoalim: Found date but no balance pattern match in line: {original_line}")
                    else:
                         logging.debug(f"Hapoalim: Found date pattern but failed to parse date string: {date_str} in line: {original_line}")
        except Exception as e:
            logging.error(f"Hapoalim: Error processing line {line_num+1} on page {page_num+1}: {e}", exc_info=True)
            continue # Continue to next line/page despite error

    doc.close()

    if not transactions:
        logging.warning(f"Hapoalim: No transactions found in {filename_for_logging}")
        return pd.DataFrame()

    df = pd.DataFrame(transactions)
    df['Date'] = pd.to_datetime(df['Date'])
    df['Balance'] = pd.to_numeric(df['Balance'])

    # Process duplicate dates: keep the last reported balance for each date
    df = df.sort_values(by=['Date', 'Balance']) # Sort by date, then balance (just in case order matters)
    df = df.drop_duplicates(subset='Date', keep='last').reset_index(drop=True)

    # Ensure dates are unique and sorted
    df = df.sort_values(by='Date').reset_index(drop=True)

    logging.info(f"Hapoalim: Successfully extracted {len(df)} unique balance points from {filename_for_logging}")
    return df[['Date', 'Balance']]


# --- LEUMI PARSER ---
# Helper functions specific to Leumi (or general but defined here)
def clean_transaction_amount_leumi(text):
    """Cleans Leumi transaction amount, handles potential unicode zero-width space."""
    if text is None or pd.isna(text) or text == '': return None
    text = str(text).strip().replace('₪', '').replace(',', '')
    # Remove zero-width non-breaking space sometimes found at the start
    text = text.lstrip('\u200b')
    # Leumi often has the decimal point as the thousands separator if not careful
    # Assuming standard format with '.' as decimal point.
    if '.' not in text:
         # If no dot, it's likely an integer amount, which is rare for transactions
         # Or it's malformed. Let's treat as None unless it's a large integer maybe?
         # Sticking to the original logic: requires a '.'
         return None # Or try converting as int/float if no dot? For now, stick to dot.

    try:
        # Handle cases like '1,234.56' after comma removal -> '1234.56'
        # Handle cases like '1.234.56' -> might be 1234.56
        # Simplified approach: just convert after basic cleaning
        val = float(text)

        # Basic sanity check for extremely large values that might indicate parsing errors
        if abs(val) > 100_000_000: # Adjusted threshold
             logging.warning(f"Leumi: Transaction amount seems excessively large: {val} from '{text}'. Skipping.")
             return None
        return val
    except ValueError:
        logging.warning(f"Leumi: Could not convert amount '{text}' to float.");
        return None

def clean_number_leumi(text):
     """Specific cleaner for Leumi numbers (balances often). Uses general cleaner."""
     return clean_number_general(text) # Re-use general cleaner, it handles (negative) etc.


def parse_date_leumi(date_str):
    """Specific date parser for Leumi. Uses general parser."""
    return parse_date_general(date_str) # Re-use general parser

def normalize_text_leumi(text):
    """Normalizes Leumi text, including potential Hebrew reversal correction."""
    if text is None or pd.isna(text): return None
    text = str(text).replace('\r', ' ').replace('\n', ' ')
    text = unicodedata.normalize('NFC', text.strip())
    # Check for presence of Hebrew characters
    if any('\u0590' <= char <= '\u05EA' for char in text):
       words = text.split()
       # Reverse words if Hebrew is detected. This is a common PDF extraction issue.
       reversed_text = ' '.join(words[::-1])
       return reversed_text
    return text

# Parsing logic for a single line that is expected to be a transaction or balance line
# This version tries to match a specific structure common in extracted text
def parse_leumi_transaction_line_extracted_order_v2(line_text, previous_balance):
    """Attempts to parse a line assuming a specific column order from text extraction."""
    line = line_text.strip()
    if not line or len(line) < 15: return None # Skip empty or too short lines

    # Regex breakdown:
    # ^([\-\u200b\d,\.]+)    : Starts with balance (can have -, zero-width space, digits, comma, dot)
    # \s+                   : One or more spaces
    # (\d{1,3}(?:,\d{3})*\.\d{2})? : Optional transaction amount (digits, commas, dot, 2 decimals)
    # \s*(\S+)               : Optional part (usually empty or single char), followed by spaces
    # \s*(.*?)              : The description part (non-greedy match)
    # \s+                   : One or more spaces
    # (\d{1,2}/\d{1,2}/\d{2,4}) : The value date (day/month/year)
    # \s+                   : One or more spaces
    # (\d{1,2}/\d{1,2}/\d{2,4})$ : The transaction date (day/month/year) ending the line
    pattern = re.compile(
        r"^([\-\u200b\d,\.]+)\s+" # 1: Balance
        r"(\d{1,3}(?:,\d{3})*\.\d{2})?\s*" # 2: Optional Amount
        r"(\S+)?\s*"             # 3: Optional single non-space char/code (handle None)
        r"(.*?)\s+"              # 4: Description (non-greedy)
        r"(\d{1,2}/\d{1,2}/\d{2,4})\s+" # 5: Value Date
        r"(\d{1,2}/\d{1,2}/\d{2,4})$"   # 6: Transaction Date
    )

    match = pattern.match(line)
    if not match:
        # logging.debug(f"Leumi: Line did not match transaction pattern: {line}")
        return None # Line doesn't fit the expected transaction format

    # Extract groups
    balance_str = match.group(1)
    amount_str = match.group(2)
    # group 3 is the single char/code - not used for balance logic
    # group 4 is description - not used for balance logic
    value_date_str = match.group(5) # Value date - often the relevant date for balance
    transaction_date_str = match.group(6) # Transaction date

    # Use the Value Date as the primary date for the balance point
    parsed_date = parse_date_leumi(value_date_str)
    if not parsed_date:
        logging.debug(f"Leumi: Failed to parse value date '{value_date_str}' in line: {line}")
        return None

    current_balance = clean_number_leumi(balance_str)
    if current_balance is None:
        # This line might be a header or malformed if balance can't be parsed
        logging.debug(f"Leumi: Failed to parse balance '{balance_str}' in line: {line}")
        return None

    # We need an amount to perform the balance consistency check, but it's optional in the regex
    # If no amount is present, this might just be a balance forward line or similar,
    # but we can still capture the balance for this date.
    amount = clean_transaction_amount_leumi(amount_str) # Can be None

    debit = None; credit = None
    # Only attempt debit/credit calculation if we have an amount and a previous balance
    if amount is not None and amount != 0 and previous_balance is not None:
        balance_diff = round(current_balance - previous_balance, 2) # Calculate difference
        # Use a small tolerance for floating point comparisons
        tolerance = 0.01 # 1 agorot

        # Check if balance decreased by amount (debit)
        if abs(balance_diff + amount) <= tolerance:
             debit = amount
        # Check if balance increased by amount (credit)
        elif abs(balance_diff - amount) <= tolerance:
             credit = amount
        else:
            # If balance change doesn't match the amount, it could be a fee/interest line
            # or the previous balance was for a different date/account, or parsing error.
            # logging.debug(f"Leumi: Balance change ({balance_diff}) does not match amount ({amount}) for line: {line}")
            pass # Don't assign debit/credit if mismatch

    # Regardless of debit/credit match, return the date and the parsed balance.
    # The logic outside this function will decide whether to record this balance point.
    return {'Date': parsed_date, 'Balance': current_balance, 'Debit': debit, 'Credit': credit}


def extract_leumi_transactions_line_by_line(pdf_content_bytes, filename_for_logging="leumi_pdf"):
    """Extracts Date and Balance from Leumi PDF by processing lines."""
    transactions_data = []
    try:
        # Use pdfplumber for better table/layout awareness
        with pdfplumber.open(io.BytesIO(pdf_content_bytes)) as pdf:
            previous_balance = None
            found_first_balance = False # Track finding the very first balance on the page
            logging.info(f"Starting Leumi PDF parsing for {filename_for_logging}")

            for page_num, page in enumerate(pdf.pages):
                try:
                    # Extract text with layout=True to help maintain column alignment
                    text = page.extract_text(x_tolerance=2, y_tolerance=2, layout=True)
                    if not text:
                        logging.debug(f"Leumi: No text extracted from page {page_num + 1}")
                        continue

                    lines = text.splitlines()
                    logging.debug(f"Page {page_num + 1} has {len(lines)} extracted lines.")

                    for line_num, line_text in enumerate(lines):
                        normalized_line = normalize_text_leumi(line_text.strip())
                        if not normalized_line or len(normalized_line) < 10: continue # Skip short lines

                        # First, try to find a potential starting balance line on the page
                        # Look for patterns like "יתרה קודמת" or "יתרת סגירה קודמת" followed by a number
                        # Or the very first line that looks like a balance entry before any transactions
                        if not found_first_balance:
                            # More robust pattern for initial balance
                            initial_balance_match = re.search(r"(?:יתרה\s+קודמת|יתרת\s+סגירה\s+קודמת|יתרה\s+נכון\s+לתאריך)\s+([\-\u200b\d,\.]+)", normalized_line)
                            if initial_balance_match:
                                bal_str = initial_balance_match.group(1)
                                initial_bal = clean_number_leumi(bal_str)
                                if initial_bal is not None:
                                    previous_balance = initial_bal
                                    found_first_balance = True
                                    logging.debug(f"Leumi: Found initial balance on page {page_num+1}: {initial_bal} from line: {normalized_line}")
                                    continue # This line was a balance forward, not a transaction

                            # If no explicit "previous balance" line is found yet,
                            # try to parse the first line that matches the transaction structure
                            # as a potential starting point's balance.
                            if previous_balance is None:
                                initial_entry = parse_leumi_transaction_line_extracted_order_v2(normalized_line, None)
                                if initial_entry and initial_entry['Balance'] is not None:
                                     previous_balance = initial_entry['Balance']
                                     found_first_balance = True
                                     logging.debug(f"Leumi: Treating first parsed entry balance as initial balance: {previous_balance} from line: {normalized_line}")
                                     # Don't 'continue' here, let it potentially be added as the first data point if it has amount

                        # Now process potential transaction lines
                        parsed_data = parse_leumi_transaction_line_extracted_order_v2(normalized_line, previous_balance)

                        if parsed_data:
                            current_balance = parsed_data['Balance']
                            parsed_date = parsed_data['Date']

                            # Only add a balance point if it's associated with a transaction (Debit or Credit)
                            # or if it's the *very first* balance we found and parsed from a transaction line.
                            # This helps filter out intermediate balance lines that don't correspond to a single event.
                            # If previous_balance is None, this IS the first entry we are processing.
                            if parsed_data['Debit'] is not None or parsed_data['Credit'] is not None or previous_balance is None:
                                # If we just found the *first ever* balance from a transaction line,
                                # set the previous_balance for the *next* iteration.
                                if previous_balance is None:
                                    previous_balance = current_balance

                                # Only append if the date or balance is different from the last added entry
                                # to avoid duplicates from lines with the same date/balance
                                if not transactions_data or (transactions_data[-1]['Date'] != parsed_date or transactions_data[-1]['Balance'] != current_balance):
                                     transactions_data.append({'Date': parsed_date, 'Balance': current_balance})
                                     logging.debug(f"Leumi: Appended transaction balance - Date: {parsed_date}, Balance: {current_balance}, Line: {normalized_line}")

                                # Update previous_balance for the next iteration based on the current line's balance
                                previous_balance = current_balance
                            else:
                                # This line matched the format but had no associated amount,
                                # likely an intermediate balance line or a parsing anomaly.
                                # Just update previous_balance if we have one, but don't add a data point.
                                if current_balance is not None:
                                     previous_balance = current_balance
                                logging.debug(f"Leumi: Matched line format but no transaction amount detected, only updating previous balance if valid: {normalized_line}")

                        # else: logging.debug(f"Leumi: Line did not trigger parse_leumi_transaction_line_extracted_order_v2: {normalized_line}") # Too noisy
                except Exception as e:
                     logging.error(f"Leumi: Error processing line {line_num+1} on page {page_num+1}: {e}", exc_info=True)
                     continue # Continue processing other lines/pages

    except Exception as e:
        logging.error(f"Leumi: FATAL ERROR processing PDF {filename_for_logging}: {e}", exc_info=True)
        return pd.DataFrame()

    if not transactions_data:
        logging.warning(f"Leumi: No transaction balances found in {filename_for_logging}")
        return pd.DataFrame()

    df = pd.DataFrame(transactions_data)
    df['Date'] = pd.to_datetime(df['Date'])

    # Sort by date and keep the last balance for each day if multiple exist
    df = df.sort_values(by='Date').groupby('Date')['Balance'].last().reset_index()

    logging.info(f"Leumi: Successfully extracted {len(df)} unique balance points from {filename_for_logging}")
    return df[['Date', 'Balance']]


# --- DISCOUNT PARSER ---
def parse_discont_transaction_line(line_text):
    """Attempts to parse a line from Discount assuming specific date/balance placement."""
    line = line_text.strip()
    if not line or len(line) < 20: return None # Skip short lines

    # Look for the two dates at the end, they often anchor the line
    date_pattern = re.compile(r"(\d{1,2}/\d{1,2}/\d{2,4})\s+(\d{1,2}/\d{1,2}/\d{2,4})$")
    date_match = date_pattern.search(line)
    if not date_match:
        # logging.debug(f"Discount: Line did not end with date pattern: {line}")
        return None # Does not look like a transaction/balance line

    # Extract the text *before* the dates
    line_before_dates = line[:date_match.start()].strip()
    if not line_before_dates: return None

    # Now search for the balance and possibly amount at the start of this preceding text
    # Discount format can be tricky, but typically balance is the first number field.
    # Looking for two potential number fields at the start: balance and amount. We only need balance.
    balance_pattern_start = re.compile(r"^[₪]?\s*([+\-]?[\d,]+\.\d{2})(?:\s+[₪]?\s*[+\-]?[\d,]+\.\d{2})?") # Match balance, optional amount after
    balance_match = balance_pattern_start.search(line_before_dates)

    if not balance_match:
         # Sometimes balance might be preceded by code or small text. Try a slightly more flexible match
         balance_pattern_flexible = re.compile(r"^(?:.*?)\s*[₪]?\s*([+\-]?[\d,]+\.\d{2})(?:\s+[₪]?\s*[+\-]?[\d,]+\.\d{2})?") # Match balance anywhere after start, capturing the first number
         balance_match = balance_pattern_flexible.search(line_before_dates)
         if not balance_match:
            # logging.debug(f"Discount: Found dates but no clear balance pattern at start of '{line_before_dates}' from line: {line}")
            return None # No balance pattern found before dates

    # Get the balance string from the match
    balance_str = balance_match.group(1)
    balance = clean_number_general(balance_str) # Use general cleaner

    if balance is None:
        logging.debug(f"Discount: Found dates but failed to clean balance: {balance_str} in line: {line}")
        return None

    # Use the first date found (transaction date) for the balance point
    date_str = date_match.group(1)
    parsed_date = parse_date_general(date_str)

    if not parsed_date:
        logging.debug(f"Discount: Failed to parse date '{date_str}' from line: {line}")
        return None

    # Avoid header/footer lines that might match the pattern
    lower_line = line.lower()
    if "יתרת" in lower_line and "סגירה" in lower_line and "נכון" in lower_line:
         logging.debug(f"Discount: Skipping likely closing balance line: {line}")
         return None
    if "תאריך" in lower_line and "רישום" in lower_line and "תאריך" in lower_line and "ערך" in lower_line:
         logging.debug(f"Discount: Skipping likely header line: {line}")
         return None
    if "עמוד" in lower_line:
         logging.debug(f"Discount: Skipping likely footer line: {line}")
         return None


    # If we got here, it looks like a valid transaction/balance line
    logging.debug(f"Discount: Parsed transaction - Date: {parsed_date}, Balance: {balance}, Line: {line}")
    return {'Date': parsed_date, 'Balance': balance}

def extract_and_parse_discont_pdf(pdf_content_bytes, filename_for_logging="discount_pdf"):
    """Extracts Date and Balance from Discount PDF by processing lines."""
    transactions = []
    try:
        # Use pdfplumber for flexibility
        with pdfplumber.open(io.BytesIO(pdf_content_bytes)) as pdf:
            logging.info(f"Starting Discount PDF parsing for {filename_for_logging}")
            for page_num, page in enumerate(pdf.pages):
                try:
                    # Extract text with layout=True to help maintain column alignment
                    text = page.extract_text(x_tolerance=2, y_tolerance=2, layout=True)
                    if text:
                        lines = text.splitlines()
                        logging.debug(f"Page {page_num + 1} has {len(lines)} extracted lines.")
                        for line_num, line_text in enumerate(lines):
                            normalized_line = normalize_text_general(line_text) # Use general normalization
                            parsed = parse_discont_transaction_line(normalized_line)
                            if parsed:
                                # Avoid adding duplicate entries for the same date and balance,
                                # which can happen if the same line is extracted slightly differently
                                # or if multiple lines on a day have the same final balance (less likely but possible).
                                if not transactions or (transactions[-1]['Date'] != parsed['Date'] or transactions[-1]['Balance'] != parsed['Balance']):
                                     transactions.append(parsed)
                                else:
                                     logging.debug(f"Discount: Skipping duplicate date/balance entry for line: {normalized_line}")
                            # else: logging.debug(f"Discount: Line did not match transaction pattern: {normalized_line}") # Too noisy

                except Exception as e:
                    logging.error(f"Discount: Error processing page {page_num+1}: {e}", exc_info=True)
                    continue # Continue to next page despite error

    except Exception as e:
        logging.error(f"Discount: FATAL ERROR processing PDF {filename_for_logging}: {e}", exc_info=True)
        return pd.DataFrame()

    if not transactions:
        logging.warning(f"Discount: No transaction balances found in {filename_for_logging}")
        return pd.DataFrame()

    df = pd.DataFrame(transactions)
    df['Date'] = pd.to_datetime(df['Date'])

    # Sort by date and keep the last balance for each day
    df = df.sort_values(by='Date').groupby('Date')['Balance'].last().reset_index()

    logging.info(f"Discount: Successfully extracted {len(df)} unique balance points from {filename_for_logging}")
    return df[['Date', 'Balance']]


# --- CREDIT REPORT PARSER ---
# Constants and helpers defined here for completeness, though they are copied
COLUMN_HEADER_WORDS_CR = {
    "שם", "מקור", "מידע", "מדווח", "מזהה", "עסקה", "מספר", "עסקאות",
    "גובה", "מסגרת", "מסגרות", "סכום", "הלוואות", "מקורי", "יתרת", "חוב",
    "יתרה", "שלא", "שולמה", "במועד", "פרטי", "עסקה", "בנק", "אוצר" # Added "בנק", "אוצר"
}
BANK_KEYWORDS_CR = {"בנק", "בע\"מ", "אגוד", "דיסקונט", "לאומי", "הפועלים", "מזרחי",
                 "טפחות", "הבינלאומי", "מרכנתיל", "אוצר", "החייל", "ירושלים",
                 "איגוד", "מימון", "ישיר", "כרטיסי", "אשראי", "מקס", "פיננסים",
                 "כאל", "ישראכרט", "פועלים", "לאומי", "דיסקונט", "מזרחי", "טפחות", "בינלאומי", "מרכנתיל"} # Added variations

def clean_credit_number(text):
    """Specific cleaner for credit report numbers, uses general."""
    return clean_number_general(text)

def process_entry_final_cr(entry_data, section, all_rows_list):
    """Processes a collected entry (bank name + numbers) into structured data."""
    if not entry_data or not entry_data.get('bank') or not entry_data.get('numbers'):
        # logging.debug(f"CR: Skipping entry due to missing data: {entry_data}")
        return

    bank_name_raw = entry_data['bank']
    # Clean up common suffixes/prefixes and XX- identifiers
    bank_name_cleaned = re.sub(r'\s*XX-[\w\d\-]+.*', '', bank_name_raw).strip()
    # Remove numbers from the end that might be mistaken for part of the name
    bank_name_cleaned = re.sub(r'\s+\d{1,3}(?:,\d{3})*$', '', bank_name_cleaned).strip()
    # Clean common bank suffixes
    bank_name_cleaned = re.sub(r'\s+בע\"מ$', '', bank_name_cleaned, flags=re.IGNORECASE).strip()
    bank_name_cleaned = re.sub(r'\s+בנק$', '', bank_name_cleaned, flags=re.IGNORECASE).strip()
    bank_name_final = bank_name_cleaned if bank_name_cleaned else bank_name_raw

    # Add common bank suffix if it seems missing and it's a known bank
    is_likely_bank = any(kw in bank_name_final for kw in ["לאומי", "הפועלים", "דיסקונט", "מזרחי", "הבינלאומי", "מרכנתיל", "ירושלים", "איגוד", "טפחות"]) # Specific bank names
    if is_likely_bank and not bank_name_final.lower().endswith("בע\"מ"):
        bank_name_final += " בע\"מ"
    # Handle credit card companies which might end with בע"מ sometimes
    elif any(kw in bank_name_final for kw in ["מקס", "מימון ישיר", "כאל", "ישראכרט"]) and not bank_name_final.lower().endswith("בע\"מ"):
         # This is heuristic, some like "Max It Finance" might end with it naturally
         # For simplicity, only add if specific keywords match and it's missing.
         if "מקס איט פיננסים" in bank_name_final or "מימון ישיר" in bank_name_final:
              if not bank_name_final.lower().endswith("בע\"מ"):
                   bank_name_final += " בע\"מ"


    numbers_raw = entry_data['numbers']
    numbers = [clean_credit_number(n) for n in numbers_raw if clean_credit_number(n) is not None]

    num_count = len(numbers)
    limit_col, original_col, outstanding_col, unpaid_col = np.nan, np.nan, np.nan, np.nan

    if num_count >= 2:
        # Assign based on section and typical column count
        # Use get with default 0.0 or np.nan if index might be out of bounds
        val1 = numbers[0] if num_count > 0 else np.nan
        val2 = numbers[1] if num_count > 1 else np.nan
        val3 = numbers[2] if num_count > 2 else np.nan
        val4 = numbers[3] if num_count > 3 else np.nan

        if section in ["עו\"ש", "מסגרת אשראי"]: # Typically 3 numbers: Limit, Outstanding, Unpaid (Optional/0)
             limit_col = val1 # Should be limit
             outstanding_col = val2 if num_count > 1 else np.nan # Should be outstanding
             unpaid_col = val3 if num_count > 2 else 0.0 # Should be unpaid (often 0)
             # If only 2 numbers, assume Limit and Outstanding
             if num_count == 2:
                 limit_col = val1
                 outstanding_col = val2
                 unpaid_col = 0.0 # Assume 0 unpaid if not present

        elif section in ["הלוואה", "משכנתה"]: # Typically 3-4 numbers: Num Payments?, Original, Outstanding, Unpaid (Optional/0)
            if num_count >= 3:
                 # Heuristic: if the first number is a small integer, it might be num_payments
                 # Check if val1 is not NaN and is a small integer (e.g., < 500 for num payments)
                 if pd.notna(val1) and val1 == int(val1) and val1 < 500 and num_count >= 4:
                      # Assume first is Num Payments, then Original, Outstanding, Unpaid
                      original_col = val2 if num_count > 1 else np.nan
                      outstanding_col = val3 if num_count > 2 else np.nan
                      unpaid_col = val4 if num_count > 3 else 0.0
                 else:
                     # Assume it's Original, Outstanding, Unpaid
                     original_col = val1 # Should be original
                     outstanding_col = val2 if num_count > 1 else np.nan # Should be outstanding
                     unpaid_col = val3 if num_count > 2 else 0.0 # Should be unpaid (often 0)
            elif num_count == 2:
                 # Assume it's Original, Outstanding
                 original_col = val1
                 outstanding_col = val2
                 unpaid_col = 0.0 # Assume 0 unpaid if not present
            # If only 1 number? It's likely malformed, treat as missing.

        else: # Default case or other sections
            # Assume first is Original, second is Outstanding, third is Unpaid (if present)
            original_col = val1 if num_count > 0 else np.nan
            outstanding_col = val2 if num_count > 1 else np.nan
            unpaid_col = val3 if num_count > 2 else 0.0
            # Limit is not applicable here (np.nan)


        all_rows_list.append({
            "סוג עסקה": section,
            "שם בנק/מקור": bank_name_final,
            "גובה מסגרת": limit_col,
            "סכום מקורי": original_col,
            "יתרת חוב": outstanding_col,
            "יתרה שלא שולמה": unpaid_col
        })
        logging.debug(f"CR: Processed entry - Section: {section}, Bank: {bank_name_final}, Numbers: {numbers}, Result: {all_rows_list[-1]}")
    else:
        logging.debug(f"CR: Skipping entry due to insufficient numbers ({num_count}): {entry_data}")


def extract_credit_data_final_v13(pdf_content_bytes, filename_for_logging="credit_report_pdf"):
    """Extracts structured credit data from the report PDF."""
    extracted_rows = []
    try:
        with fitz.open(stream=pdf_content_bytes, filetype="pdf") as doc:
            current_section = None
            current_entry = None
            last_line_was_id = False
            potential_bank_continuation_candidate = False # Flag to indicate if the previous line might be part of a bank name

            # Patterns for identifying sections and numbers
            section_patterns = {
                "חשבון עובר ושב": "עו\"ש",
                "הלוואה": "הלוואה",
                "משכנתה": "משכנתה",
                "מסגרת אשראי מתחדשת": "מסגרת אשראי",
                "אחר": "אחר" # Catch-all for potential other sections
            }
             # Relaxed pattern for numbers, allowing optional leading/trailing spaces/chars
            number_line_pattern = re.compile(r"^\s*.*?(-?\d{1,3}(?:,\d{3})*\.?\d*)\s*.*?$")
            id_line_pattern = re.compile(r"^XX-[\w\d\-]+.*$") # Pattern for account/card ID line

            logging.info(f"Starting Credit Report PDF parsing for {filename_for_logging}")

            for page_num, page in enumerate(doc):
                try:
                    lines = page.get_text("text", sort=True).splitlines()
                    logging.debug(f"Page {page_num + 1} has {len(lines)} lines.")

                    for line_num, line_text in enumerate(lines):
                        line = normalize_text_general(line_text)
                        if not line: potential_bank_continuation_candidate = False; continue # Skip empty lines

                        # 1. Check for section headers
                        is_section_header = False
                        for header_keyword, section_name in section_patterns.items():
                            # Be strict about what counts as a section header line
                            if header_keyword in line and len(line) < len(header_keyword) + 25 and line.count(' ') < 6: # Heuristic limits
                                if current_entry and not current_entry.get('processed', False): # Process previous entry if exists
                                    process_entry_final_cr(current_entry, current_section, extracted_rows)
                                current_section = section_name
                                current_entry = None # Reset for the new section
                                last_line_was_id = False
                                potential_bank_continuation_candidate = False
                                is_section_header = True
                                logging.debug(f"CR: Detected section header: {line} -> {current_section}")
                                break # Stop checking section patterns
                        if is_section_header: continue # Move to the next line

                        # 2. Check for section or page footers/summaries (e.g., "סה"כ", "הודעה זו כוללת")
                        if line.startswith("סה\"כ") or line.startswith("הודעה זו כוללת") or "עמוד" in line:
                            if current_entry and not current_entry.get('processed', False):
                                process_entry_final_cr(current_entry, current_section, extracted_rows)
                            current_entry = None
                            last_line_was_id = False
                            potential_bank_continuation_candidate = False
                            logging.debug(f"CR: Detected summary/footer line: {line}")
                            continue # Skip this line

                        # Only process if inside a known section
                        if current_section:
                            # 3. Check for number lines (potential data points)
                            number_match = number_line_pattern.match(line)
                            if number_match:
                                if current_entry: # Must have a preceding bank name to attach numbers to
                                    try:
                                        # Clean the captured number string
                                        number_str = number_match.group(1)
                                        number = clean_credit_number(number_str)
                                        if number is not None:
                                            num_list = current_entry.get('numbers', [])

                                            # If the previous line was an ID, this is likely the first number set for a new entry
                                            if last_line_was_id:
                                                # Process the previous entry *before* starting a new one
                                                if current_entry and not current_entry.get('processed', False):
                                                     process_entry_final_cr(current_entry, current_section, extracted_rows)
                                                # Start a new entry with the previously captured bank name and the current number
                                                # Preserve the bank name, discard old numbers
                                                current_entry = {'bank': current_entry['bank'], 'numbers': [number], 'processed': False}
                                                logging.debug(f"CR: Detected number after ID line, starting new entry for bank '{current_entry['bank']}' with first number: {number}")
                                            else:
                                                 # Add number to the current entry's number list (limit to max expected columns)
                                                 if len(num_list) < 5: # Max 4 numbers expected + potential first ID number
                                                     current_entry['numbers'].append(number)
                                                     logging.debug(f"CR: Added number {number} to current entry for bank '{current_entry['bank']}'. Numbers: {current_entry['numbers']}")
                                                 else:
                                                     logging.debug(f"CR: Skipping extra number {number} for bank '{current_entry['bank']}'. Max numbers reached.")

                                        else:
                                            logging.debug(f"CR: Failed to clean number '{number_str}' from line: {line}")
                                    except ValueError: # Should be caught by clean_credit_number but double-check
                                        logging.debug(f"CR: ValueError cleaning number from line: {line}")

                                last_line_was_id = False # Number lines are not ID lines
                                potential_bank_continuation_candidate = False # Number line breaks bank name sequence
                                continue # Move to the next line

                            # 4. Check for ID lines (often precede numbers)
                            is_id_line = id_line_pattern.match(line)
                            if is_id_line:
                                last_line_was_id = True
                                potential_bank_continuation_candidate = False # ID line breaks bank name sequence
                                logging.debug(f"CR: Detected ID line: {line}")
                                continue # Move to the next line

                            # 5. Check for noise lines (headers within section, single chars etc.)
                            is_noise_line = any(word == line for word in COLUMN_HEADER_WORDS_CR) or line in [':', '.', '-', '—'] or (len(line.replace(' ','')) < 3 and not line.replace(' ','').isdigit())
                            if is_noise_line:
                                last_line_was_id = False
                                potential_bank_continuation_candidate = False
                                logging.debug(f"CR: Skipping likely noise line: {line}")
                                continue # Skip noise lines

                            # 6. If not header, footer, number, or ID line, it's likely a bank/source name or description
                            # Check if this line looks like a bank name or part of a bank name
                            # It shouldn't contain typical numbers or dates
                            contains_number = any(char.isdigit() for char in line)
                            contains_date_format = re.search(r"\d{1,2}/\d{1,2}/\d{2,4}", line)
                            # Check for common non-bank phrases that might appear
                            is_non_bank_phrase = any(phrase in line for phrase in ["סך הכל", "סהכ"]) # Add more if needed

                            if not contains_number and not contains_date_format and not is_non_bank_phrase:
                                cleaned_line = re.sub(r'\s*XX-[\w\d\-]+.*|\s+\d+$', '', line).strip() # Clean ID/trailing numbers again

                                # Check if this line is a *continuation* of a potential bank name from the previous line
                                # This happens when a bank name wraps onto the next line.
                                # Conditions: previous line flagged as potential continuation, we have a current_entry (meaning we found the start of a bank name), AND the current line seems like a valid continuation (starts with common continuation words or just seems like valid text).
                                common_continuations = ["לישראל", "בע\"מ", "ומשכנתאות", "נדל\"ן", "דיסקונט", "הראשון", "פיננסים", "איגוד", "אשראי"] # Add more common continuations
                                # Check if the cleaned line starts with one of these continuations OR if it just seems like descriptive text that could follow a bank name and isn't too short.
                                seems_like_continuation_text = any(cleaned_line.startswith(cont) for cont in common_continuations) or (len(cleaned_line) > 3 and ' ' in cleaned_line)


                                if potential_bank_continuation_candidate and current_entry and seems_like_continuation_text:
                                    # Append this line to the current bank name
                                    current_entry['bank'] = (current_entry['bank'] + " " + cleaned_line).replace(" בע\"מ בע\"מ", " בע\"מ").strip() # Avoid double "בע"מ"
                                    logging.debug(f"CR: Appended continuation '{cleaned_line}' to bank name. New bank name: '{current_entry['bank']}'")
                                    # Keep the continuation flag true, as a bank name could span multiple lines
                                    potential_bank_continuation_candidate = True
                                elif len(cleaned_line) > 3 and any(kw in cleaned_line for kw in BANK_KEYWORDS_CR): # Check if line is long enough and contains bank keywords
                                     # This looks like the start of a new bank entry
                                     if current_entry and not current_entry.get('processed', False): # Process the previous entry if one exists and wasn't processed
                                          process_entry_final_cr(current_entry, current_section, extracted_rows)
                                     # Start a new entry with this line as the bank name
                                     current_entry = {'bank': cleaned_line, 'numbers': [], 'processed': False}
                                     potential_bank_continuation_candidate = True # Next line *might* be a continuation
                                     logging.debug(f"CR: Started new entry with bank name: '{cleaned_line}'")
                                else:
                                     # This line doesn't seem to be a bank name or a continuation.
                                     # It might be a description line *after* the numbers, or just noise.
                                     # If we have a current entry, we could potentially process it now if it has numbers.
                                     if current_entry and current_entry.get('numbers') and not current_entry.get('processed', False):
                                         process_entry_final_cr(current_entry, current_section, extracted_rows)
                                         current_entry['processed'] = True # Mark as processed to avoid reprocessing

                                     potential_bank_continuation_candidate = False # Reset flag

                                last_line_was_id = False # This is not an ID line

                            else:
                                 # This line contains numbers/dates or known non-bank phrases,
                                 # so it's unlikely to be a bank name or its continuation.
                                 # If we have a current entry with numbers, process it now before discarding context.
                                 if current_entry and current_entry.get('numbers') and not current_entry.get('processed', False):
                                      process_entry_final_cr(current_entry, current_section, extracted_rows)
                                      current_entry['processed'] = True # Mark as processed

                                 last_line_was_id = False
                                 potential_bank_continuation_candidate = False # Break any bank name continuation sequence

                except Exception as e:
                    logging.error(f"CR: Error processing line {line_num+1} on page {page_num+1}: {e}", exc_info=True)
                    continue # Continue to next line/page despite error


            # After processing all lines, process the last entry if it exists and wasn't processed
            if current_entry and not current_entry.get('processed', False):
                process_entry_final_cr(current_entry, current_section, extracted_rows)

    except Exception as e:
        logging.error(f"CreditReport: FATAL ERROR processing {filename_for_logging}: {e}", exc_info=True)
        return pd.DataFrame() # Return empty DataFrame on fatal error

    if not extracted_rows:
        logging.warning(f"CreditReport: No structured entries found in {filename_for_logging}")
        return pd.DataFrame()

    df = pd.DataFrame(extracted_rows)

    # Define expected columns and ensure they exist
    final_cols = ["סוג עסקה", "שם בנק/מקור", "גובה מסגרת", "סכום מקורי", "יתרת חוב", "יתרה שלא שולמה"]
    for col in final_cols:
        if col not in df.columns:
            df[col] = np.nan # Add missing columns with NaN

    df = df[final_cols] # Reorder columns

    # Convert numeric columns, coercing errors to NaN
    for col in ["גובה מסגרת", "סכום מקורי", "יתרת חוב", "יתרה שלא שולמה"]:
        if col in df.columns:
             df[col] = pd.to_numeric(df[col], errors='coerce')
             # Replace NaN with 0 where appropriate (e.g., unpaid debt if not listed)
             if col == "יתרה שלא שולמה":
                  df[col] = df[col].fillna(0) # Assume 0 unpaid if missing

    # Filter out rows that ended up with no meaningful numeric data
    df = df.dropna(subset=['גובה מסגרת', 'סכום מקורי', 'יתרת חוב', 'יתרה שלא שולמה'], how='all').reset_index(drop=True)

    logging.info(f"CreditReport: Successfully extracted {len(df)} entries from {filename_for_logging}")

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
    """Resets all session state variables to their initial state."""
    logging.info("Resetting all application data.")
    st.session_state.app_stage = "welcome"
    st.session_state.questionnaire_stage = 0
    st.session_state.answers = {}
    st.session_state.classification_details = {}
    st.session_state.chat_messages = []
    st.session_state.df_bank_uploaded = pd.DataFrame()
    st.session_state.df_credit_uploaded = pd.DataFrame()
    st.session_state.bank_type_selected = "ללא דוח בנק"
    st.session_state.total_debt_from_credit_report = None


# --- Streamlit App Layout ---
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
        # Reset only questionnaire state if skipping files
        st.session_state.questionnaire_stage = 0
        st.session_state.answers = {}
        st.session_state.classification_details = {}
        # Keep uploaded data if it exists, but clear derived debt
        st.session_state.total_debt_from_credit_report = None # Clear debt from credit report if skipping file step
        st.session_state.app_stage = "questionnaire"
        st.rerun()


elif st.session_state.app_stage == "file_upload":
    st.header("שלב 1: העלאת דוחות")

    bank_type_options = ["ללא דוח בנק", "הפועלים", "דיסקונט", "לאומי"]
    # Set default index to the currently selected type
    current_bank_type_index = bank_type_options.index(st.session_state.bank_type_selected) if st.session_state.bank_type_selected in bank_type_options else 0
    st.session_state.bank_type_selected = st.selectbox(
        "בחר סוג דוח בנק:",
        bank_type_options,
        index=current_bank_type_index,
        key="bank_type_selector_main"
    )

    uploaded_bank_file = None
    if st.session_state.bank_type_selected != "ללא דוח בנק":
        uploaded_bank_file = st.file_uploader(f"העלה דוח בנק ({st.session_state.bank_type_selected}) (קובץ PDF)", type="pdf", key="bank_pdf_uploader_main")
        if uploaded_bank_file and st.session_state.get('uploaded_bank_file_name') != uploaded_bank_file.name:
             # Clear previously processed bank data if a new file is uploaded
             st.session_state.df_bank_uploaded = pd.DataFrame()
             st.session_state.uploaded_bank_file_name = uploaded_bank_file.name # Store name to detect changes
             st.info(f"הקובץ {uploaded_bank_file.name} הועלה בהצלחה. לחץ על 'עבד קבצים' לעיבוד.")
        elif not uploaded_bank_file:
             st.session_state.uploaded_bank_file_name = None # Clear name if file is removed

    uploaded_credit_file = st.file_uploader("העלה דוח נתוני אשראי (קובץ PDF) (מומלץ)", type="pdf", key="credit_pdf_uploader_main")
    if uploaded_credit_file and st.session_state.get('uploaded_credit_file_name') != uploaded_credit_file.name:
         # Clear previously processed credit data if a new file is uploaded
         st.session_state.df_credit_uploaded = pd.DataFrame()
         st.session_state.total_debt_from_credit_report = None
         st.session_state.uploaded_credit_file_name = uploaded_credit_file.name # Store name
         st.info(f"הקובץ {uploaded_credit_file.name} הועלה בהצלחה. לחץ על 'עבד קבצים' לעיבוד.")
    elif not uploaded_credit_file:
         st.session_state.uploaded_credit_file_name = None # Clear name if file is removed


    if st.button("עבד קבצים והמשך לשאלון", key="process_files_button"):
        processed_bank = False
        processed_credit = False

        with st.spinner("מעבד קבצים..."):
            # Process Bank File
            st.session_state.df_bank_uploaded = pd.DataFrame() # Reset before processing new file
            if uploaded_bank_file is not None and st.session_state.bank_type_selected != "ללא דוח בנק":
                try:
                    bank_file_bytes = uploaded_bank_file.getvalue()
                    parser_func = None
                    if st.session_state.bank_type_selected == "הפועלים": parser_func = extract_transactions_from_pdf_hapoalim
                    elif st.session_state.bank_type_selected == "לאומי": parser_func = extract_leumi_transactions_line_by_line
                    elif st.session_state.bank_type_selected == "דיסקונט": parser_func = extract_and_parse_discont_pdf

                    if parser_func:
                        st.session_state.df_bank_uploaded = parser_func(bank_file_bytes, uploaded_bank_file.name)

                    if st.session_state.df_bank_uploaded.empty:
                        st.warning(f"לא הצלחנו לחלץ נתונים מדוח הבנק ({st.session_state.bank_type_selected}). אנא וודא/י שהקובץ תקין והפורמט נתמך.")
                    else:
                        st.success(f"דוח בנק ({st.session_state.bank_type_selected}) עובד בהצלחה!")
                        processed_bank = True
                except Exception as e:
                    logging.error(f"Error processing bank file {uploaded_bank_file.name}: {e}", exc_info=True)
                    st.error(f"אירעה שגיאה בעת עיבוד דוח הבנק: {e}")


            # Process Credit File
            st.session_state.df_credit_uploaded = pd.DataFrame() # Reset before processing new file
            st.session_state.total_debt_from_credit_report = None # Reset
            if uploaded_credit_file is not None:
                try:
                    credit_file_bytes = uploaded_credit_file.getvalue()
                    st.session_state.df_credit_uploaded = extract_credit_data_final_v13(credit_file_bytes, uploaded_credit_file.name)
                    if st.session_state.df_credit_uploaded.empty:
                        st.warning("לא הצלחנו לחלץ נתונים מדוח האשראי. אנא וודא/י שהקובץ תקין.")
                    else:
                        st.success("דוח נתוני אשראי עובד בהצלחה!")
                        processed_credit = True
                        if 'יתרת חוב' in st.session_state.df_credit_uploaded.columns:
                            # Sum up 'יתרת חוב', replacing NaNs with 0 before summing
                            total_debt = st.session_state.df_credit_uploaded['יתרת חוב'].fillna(0).sum()
                            st.session_state.total_debt_from_credit_report = total_debt
                            st.info(f"סך יתרת החוב שחושבה מדוח האשראי: {st.session_state.total_debt_from_credit_report:,.0f} ₪")
                        else:
                            st.warning("עמודת 'יתרת חוב' לא נמצאה בדוח האשראי המעובד.")

                except Exception as e:
                    logging.error(f"Error processing credit file {uploaded_credit_file.name}: {e}", exc_info=True)
                    st.error(f"אירעה שגיאה בעת עיבוד דוח נתוני האשראי: {e}")


        # Move to questionnaire regardless of successful processing,
        # but ensure questionnaire starts from stage 0 and clear chat
        st.session_state.app_stage = "questionnaire"
        st.session_state.questionnaire_stage = 0
        st.session_state.chat_messages = [] # Clear chat history when starting new questionnaire/analysis
        st.rerun()

    if st.button("דלג על העלאת קבצים והמשך לשאלון", key="skip_files_button"):
        # Clear any processed data if skipping files
        st.session_state.df_bank_uploaded = pd.DataFrame()
        st.session_state.df_credit_uploaded = pd.DataFrame()
        st.session_state.total_debt_from_credit_report = None
        st.session_state.bank_type_selected = "ללא דוח בנק" # Reset selector state
        st.session_state.app_stage = "questionnaire"
        st.session_state.questionnaire_stage = 0 # Start questionnaire from beginning
        st.session_state.chat_messages = [] # Clear chat history
        st.rerun()


elif st.session_state.app_stage == "questionnaire":
    st.header("שלב 2: שאלון פיננסי")
    st.markdown("אנא ענה/י על השאלות הבאות כדי לעזור לנו להבין טוב יותר את מצבך הפיננסי.")

    q_stage = st.session_state.questionnaire_stage

    # --- Questionnaire Stages ---

    # Stage 0: Initial Questions
    if q_stage == 0:
        st.subheader("חלק א': שאלות פתיחה")
        st.session_state.answers['q1_unusual_event'] = st.text_area("1. האם קרה משהו חריג שבגללו פנית?", value=st.session_state.answers.get('q1_unusual_event', ''), key="q_s0_q1")
        st.session_state.answers['q2_other_funding'] = st.text_area("2. האם יש מקורות מימון אחרים שבדקת?", value=st.session_state.answers.get('q2_other_funding', ''), key="q_s0_q2")
        # Use a more explicit key for the boolean value from the radio
        existing_loans_bool_key = 'q3_existing_loans_bool_radio'
        default_loan_bool_index = ("לא","כן").index(st.session_state.answers.get(existing_loans_bool_key, 'לא'))
        st.session_state.answers[existing_loans_bool_key] = st.radio(
            "3. האם קיימות הלוואות נוספות (לא משכנתא)?",
            ("כן", "לא"),
            index=default_loan_bool_index,
            key="q_s0_q3_bool"
        )
        # Only ask for amount if "כן" is selected
        if st.session_state.answers[existing_loans_bool_key] == "כן":
            # Use a different key for the numeric amount
            st.session_state.answers['q3_loan_repayment_amount'] = st.number_input(
                "מה גובה ההחזר החודשי הכולל עליהן?",
                min_value=0.0, value=float(st.session_state.answers.get('q3_loan_repayment_amount', 0.0)), step=100.0, key="q_s0_q3_amount"
            )
        else:
            st.session_state.answers['q3_loan_repayment_amount'] = 0.0 # Ensure it's 0 if "לא"
        
        balanced_bool_key = 'q4_financially_balanced_bool_radio'
        default_balanced_index = ("כן","בערך","לא").index(st.session_state.answers.get(balanced_bool_key, 'כן'))
        st.session_state.answers[balanced_bool_key] = st.radio(
            "4. האם אתם מאוזנים כלכלית כרגע (הכנסות מכסות הוצאות)?",
            ("כן", "בערך", "לא"),
            index=default_balanced_index,
            key="q_s0_q4_bool"
        )
        st.session_state.answers['q4_situation_change_next_year'] = st.text_area("האם המצב הכלכלי צפוי להשתנות משמעותית בשנה הקרובה?", value=st.session_state.answers.get('q4_situation_change_next_year', ''), key="q_s0_q4_change")
        
        if st.button("הבא", key="q_s0_next"):
            st.session_state.questionnaire_stage += 1
            st.rerun()

    # Stage 1: Income
    elif q_stage == 1:
        st.subheader("חלק ב': הכנסות (נטו חודשי, לפני החזרי הלוואות)")
        st.session_state.answers['income_employee'] = st.number_input("הכנסתך (נטו):", min_value=0.0, value=float(st.session_state.answers.get('income_employee', 0.0)), step=100.0, key="q_s1_inc_emp")
        st.session_state.answers['income_partner'] = st.number_input("הכנסת בן/בת הזוג (נטו):", min_value=0.0, value=float(st.session_state.answers.get('income_partner', 0.0)), step=100.0, key="q_s1_inc_partner")
        st.session_state.answers['income_other'] = st.number_input("הכנסות נוספות (קצבאות, שכר דירה וכו'):", min_value=0.0, value=float(st.session_state.answers.get('income_other', 0.0)), step=100.0, key="q_s1_inc_other")
        
        # Calculate and store total net income
        total_net_income = sum(float(st.session_state.answers.get(k,0.0)) for k in ['income_employee','income_partner','income_other'])
        st.session_state.answers['total_net_income'] = total_net_income
        st.metric("סך הכנסות נטו (חודשי):", f"{total_net_income:,.0f} ₪")
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("הקודם", key="q_s1_prev"): st.session_state.questionnaire_stage -= 1; st.rerun()
        with col2:
            if st.button("הבא", key="q_s1_next"): st.session_state.questionnaire_stage += 1; st.rerun()

    # Stage 2: Fixed Expenses
    elif q_stage == 2:
        st.subheader("חלק ג': הוצאות קבועות חודשיות")
        st.session_state.answers['expense_rent_mortgage'] = st.number_input("שכירות / החזר משכנתא:", min_value=0.0, value=float(st.session_state.answers.get('expense_rent_mortgage', 0.0)), step=100.0, key="q_s2_exp_rent")
        # Use the amount entered in Q3 as default if it exists
        default_debt_repayment = float(st.session_state.answers.get('q3_loan_repayment_amount', 0.0))
        st.session_state.answers['expense_debt_repayments'] = st.number_input(
            "החזרי הלוואות נוספות (לא משכנתא, כולל כרטיסי אשראי אם יש החזר קבוע):",
            min_value=0.0, value=float(st.session_state.answers.get('expense_debt_repayments', default_debt_repayment)), step=100.0, key="q_s2_exp_debt"
        )
        st.session_state.answers['expense_alimony_other'] = st.number_input("מזונות / הוצאות קבועות גדולות אחרות (למשל: חסכון קבוע, ביטוחים גבוהים):", min_value=0.0, value=float(st.session_state.answers.get('expense_alimony_other', 0.0)), step=100.0, key="q_s2_exp_alimony")
        
        # Calculate and store total fixed expenses
        total_fixed_expenses = sum(float(st.session_state.answers.get(k,0.0)) for k in ['expense_rent_mortgage','expense_debt_repayments','expense_alimony_other'])
        st.session_state.answers['total_fixed_expenses'] = total_fixed_expenses
        st.metric("סך הוצאות קבועות:", f"{total_fixed_expenses:,.0f} ₪")
        
        # Calculate and store monthly balance after fixed expenses
        total_net_income = float(st.session_state.answers.get('total_net_income', 0.0))
        monthly_balance = total_net_income - total_fixed_expenses
        st.session_state.answers['monthly_balance'] = monthly_balance
        st.metric("יתרה פנויה חודשית (הכנסות פחות קבועות):", f"{monthly_balance:,.0f} ₪")
        if monthly_balance < 0: st.warning("שימו לב: ההוצאות הקבועות גבוהות מההכנסות נטו.")


        col1, col2 = st.columns(2)
        with col1:
            if st.button("הקודם", key="q_s2_prev"): st.session_state.questionnaire_stage -= 1; st.rerun()
        with col2:
            if st.button("הבא", key="q_s2_next"): st.session_state.questionnaire_stage += 1; st.rerun()

    # Stage 3: Total Debts & Arrears
    elif q_stage == 3:
        st.subheader("חלק ד': חובות ופיגורים")

        # If total debt was calculated from credit report, use it as default and inform the user
        default_total_debt = float(st.session_state.answers.get('total_debt_amount', 0.0)) # Use previous answer as base default
        if st.session_state.total_debt_from_credit_report is not None:
            # If credit report debt is available, prefer it as the default initial value for the input
            default_total_debt = st.session_state.total_debt_from_credit_report
            st.info(f"סך יתרת החוב שחושבה מדוח האשראי שהועלה הוא: {st.session_state.total_debt_from_credit_report:,.0f} ₪. **ניתן לעדכן את הסכום למטה אם קיימים חובות נוספים שלא מופיעים בדוח.**")
        else:
             st.info("אנא הזן/י את סך כל החובות הקיימים (למעט משכנתא).")


        st.session_state.answers['total_debt_amount'] = st.number_input(
            "מה היקף החובות הכולל שלך (למעט משכנתא)?",
            min_value=0.0, value=float(st.session_state.answers.get('total_debt_amount', default_total_debt)), step=100.0, key="q_s3_total_debt"
        )

        # Store the *final* value entered/defaulted after the user interaction with the number_input
        final_total_debt = float(st.session_state.answers['total_debt_amount'])

        arrears_key = 'arrears_collection_proceedings_radio'
        default_arrears_index = ("לא","כן").index(st.session_state.answers.get(arrears_key, 'לא'))
        st.session_state.answers[arrears_key] = st.radio(
            "האם קיימים פיגורים משמעותיים בתשלומים או הליכי גבייה פעילים נגדך?",
            ("כן", "לא"),
            index=default_arrears_index,
            key="q_s3_arrears"
        )

        col1, col2 = st.columns(2)
        with col1:
            if st.button("הקודם", key="q_s3_prev"): st.session_state.questionnaire_stage -= 1; st.rerun()
        with col2:
            if st.button("סיום שאלון וקבלת סיכום", key="q_s3_next_finish"):
                # Ensure numeric values are floats for calculations
                current_total_debt = float(st.session_state.answers.get('total_debt_amount', 0.0))
                current_total_net_income = float(st.session_state.answers.get('total_net_income', 0.0))

                # Calculate Debt-to-Income Ratio based on the final debt amount from the input
                annual_income = current_total_net_income * 12
                st.session_state.answers['annual_income'] = annual_income # Store annual income

                # Avoid division by zero
                if annual_income > 0:
                     st.session_state.answers['debt_to_income_ratio'] = current_total_debt / annual_income
                else:
                     st.session_state.answers['debt_to_income_ratio'] = float('inf') if current_total_debt > 0 else 0.0

                # Determine Classification based on the ratio and arrears
                ratio = st.session_state.answers['debt_to_income_ratio']
                arrears_exist = st.session_state.answers.get(arrears_key, 'לא') == 'כן'

                # Default classification details
                classification = "לא נקבע"
                description = "לא הושלם סיווג ראשוני."
                color = "gray"
                next_stage = "summary" # Default destination

                if arrears_exist:
                    classification = "אדום"
                    description = "קיימים פיגורים משמעותיים או הליכי גבייה."
                    color = "red"
                    next_stage = "summary" # Go directly to summary

                elif ratio < 1:
                    classification = "ירוק"
                    description = "סך החוב נמוך מההכנסה השנתית."
                    color = "green"
                    next_stage = "summary" # Go directly to summary

                elif 1 <= ratio <= 2:
                    classification = "צהוב (בבדיקה)"
                    description = "סך החוב בגובה ההכנסה של 1-2 שנים."
                    color = "orange"
                    next_stage = 100 # Go to special intermediate stage for Yellow

                else: # ratio > 2
                    classification = "אדום"
                    description = "סך החוב גבוה מההכנסה של שנתיים או יותר."
                    color = "red"
                    next_stage = "summary" # Go directly to summary

                st.session_state.classification_details = {
                    'classification': classification,
                    'description': description,
                    'color': color
                }

                if next_stage == "summary":
                    st.session_state.app_stage = "summary"
                    st.session_state.questionnaire_stage = -1 # Indicate questionnaire is finished
                else: # next_stage == 100
                    st.session_state.questionnaire_stage = next_stage

                st.rerun()

    # Stage 100: Intermediate questions for Yellow classification
    elif q_stage == 100:
        st.subheader("שאלות הבהרה נוספות")
        st.warning(f"תוצאות ראשוניות: יחס החוב להכנסה שלך הוא {st.session_state.answers.get('debt_to_income_ratio', 0.0):.2f}. ({st.session_state.classification_details.get('description')})")

        arrears_exist = st.session_state.answers.get('arrears_collection_proceedings_radio', 'לא') == 'כן'

        if arrears_exist:
             # This case should theoretically be caught in stage 3, but double-check
             st.error("נמצא שקיימים הליכי גבייה. מצב זה מסווג כ'אדום'.")
             st.session_state.classification_details.update({'classification': "אדום", 'description': st.session_state.classification_details.get('description','') + " קיימים הליכי גבייה.", 'color': "red"})
             if st.button("המשך לסיכום", key="q_s100_to_summary_red_recheck"):
                 st.session_state.app_stage = "summary"
                 st.session_state.questionnaire_stage = -1
                 st.rerun()
        else:
            total_debt = float(st.session_state.answers.get('total_debt_amount', 0.0))
            fifty_percent_debt = total_debt * 0.5
            st.session_state.answers['can_raise_50_percent_radio'] = st.radio(
                f"האם תוכל/י לגייס סכום השווה לכ-50% מסך החובות הלא מגובים במשכנתא ({fifty_percent_debt:,.0f} ₪) ממקורות תמיכה (משפחה, חברים) תוך זמן סביר (עד מספר חודשים)?",
                ("כן", "לא"),
                index=("לא","כן").index(st.session_state.answers.get('can_raise_50_percent_radio', 'לא')),
                key="q_s100_q_raise_funds"
            )
            if st.button("המשך לסיכום", key="q_s100_to_summary_yellow_check"):
                if st.session_state.answers.get('can_raise_50_percent_radio', 'לא') == "כן":
                    st.session_state.classification_details.update({'classification': "צהוב", 'description': st.session_state.classification_details.get('description','') + " אין הליכי גבייה ויכולת לגייס 50% מהחוב.", 'color': "orange"})
                else:
                    st.session_state.classification_details.update({'classification': "אדום", 'description': st.session_state.classification_details.get('description','') + " אין הליכי גבייה אך אין יכולת לגייס 50% מהחוב ממקורות תמיכה.", 'color': "red"})

                st.session_state.app_stage = "summary"
                st.session_state.questionnaire_stage = -1
                st.rerun()

        if st.button("חזור לשלב הקודם בשאלון", key="q_s100_prev"):
            st.session_state.questionnaire_stage = 3; st.rerun()


elif st.session_state.app_stage == "summary":
    st.header("שלב 3: סיכום, ויזואליזציות וייעוץ")
    st.markdown("להלן סיכום הנתונים שאספנו והניתוח הראשוני.")

    # Retrieve calculated metrics from questionnaire (ensure keys match and handle potential None/errors)
    total_net_income_ans = float(st.session_state.answers.get('total_net_income', 0.0))
    total_fixed_expenses_ans = float(st.session_state.answers.get('total_fixed_expenses', 0.0))
    monthly_balance_ans = float(st.session_state.answers.get('monthly_balance', 0.0))
    total_debt_amount_ans = float(st.session_state.answers.get('total_debt_amount', 0.0))
    annual_income_ans = float(st.session_state.answers.get('annual_income', 0.0))
    debt_to_income_ratio_ans = float(st.session_state.answers.get('debt_to_income_ratio', 0.0))


    st.subheader("📊 סיכום נתונים פיננסיים")
    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("💰 סך הכנסות נטו (חודשי)", f"{total_net_income_ans:,.0f} ₪")
        st.metric("💸 סך הוצאות קבועות (חודשי)", f"{total_fixed_expenses_ans:,.0f} ₪")

    with col2:
        st.metric("📊 יתרה פנויה (חודשי)", f"{monthly_balance_ans:,.0f} ₪")
        st.metric("📈 הכנסה שנתית", f"{annual_income_ans:,.0f} ₪")

    with col3:
        st.metric("🏦 סך חובות (ללא משכנתא)", f"{total_debt_amount_ans:,.0f} ₪")
        if st.session_state.total_debt_from_credit_report is not None and abs(st.session_state.total_debt_from_credit_report - total_debt_amount_ans) > 1: # Check if they differ significantly
             st.caption(f"(מדוח אשראי שנותח: {st.session_state.total_debt_from_credit_report:,.0f} ₪)")
        st.metric("⚖️ יחס חוב להכנסה שנתית", f"{debt_to_income_ratio_ans:.2%}")


    # Display classification and recommendations
    st.subheader("סיווג מצב פיננסי והמלצה ראשונית:")
    classification = st.session_state.classification_details.get('classification', "לא נקבע")
    description = st.session_state.classification_details.get('description', "")
    color = st.session_state.classification_details.get('color', "gray")

    if color == "green":
        st.success(f"🟢 **סיווג: {classification}**")
        st.markdown("""
        **מצב טוב.** יחס החוב להכנסה נמוך. זהו מצב יציב המאפשר גמישות פיננסית.
        * **המלצה ראשונית:** נהל/י את מצבך הפיננסי בתשומת לב, אך אין דחיפות מיידית לטיפול בחובות בדרכים מיוחדות. שקול/י אפיקי חיסכון או השקעה. דוח האשראי יכול לעזור לך להבין את המגבלות הקיימות ואולי לשפר תנאים עתידיים.
        """)
    elif color == "orange":
        st.warning(f"🟡 **סיווג: {classification}**")
        st.markdown("""
        **מצב הדורש בדיקה ותשומת לב.** יחס החוב להכנסה מעיד על פוטנציאל קושי, אך המצב אינו אקוטי בהכרח, במיוחד אם יש יתרה פנויה חודשית.
        * **המלצה ראשונית:** מומלץ לבחון לעומק את פירוט החובות (בדוח האשראי) וההוצאות (דרך דוח הבנק או מעקב אישי). נסה/י לבנות תוכנית פעולה לצמצום החובות, אולי על ידי הגדלת הכנסות או קיצוץ בהוצאות לא קבועות. צ'אט עם היועץ הווירטואלי יכול לעזור לזהות נקודות לשיפור.
        """)
    elif color == "red":
        st.error(f"🔴 **סיווג: {classification}**")
        st.markdown("""
        **מצב קשה הדורש התערבות מיידית.** יחס החוב להכנסה גבוה או שקיימים הליכי גבייה. המצב דורש טיפול דחוף כדי למנוע הסלמה.
        * **המלצה ראשונית:** חשוב לפנות בהקדם לייעוץ מקצועי, בין אם במסגרת שירות ציבורי (כמו "פעמונים") או יועץ פיננסי פרטי המתמחה בטיפול בחובות. ייתכן שיהיה צורך בבניית תוכנית פריסה מחדש של חובות או צעדים אחרים. אל תתעלם/י מהמצב.
        """)
    else:
         st.info(f"⚫ **סיווג: {classification}**")
         st.markdown("""
         **הסיווג לא הושלם.** ייתכן שחסרים נתונים בשאלון.
         * **המלצה ראשונית:** אנא השלם/י את השאלון כדי לקבל סיווג והמלצה ראשונית.
         """)

    st.markdown("---")
    st.subheader("🎨 ויזואליזציות מרכזיות")

    # Visualization 1: Debt Breakdown from Credit Report (Pie Chart)
    if not st.session_state.df_credit_uploaded.empty and 'סוג עסקה' in st.session_state.df_credit_uploaded.columns and 'יתרת חוב' in st.session_state.df_credit_uploaded.columns:
        # Ensure 'יתרת חוב' is numeric and fill NaNs with 0 before summing
        st.session_state.df_credit_uploaded['יתרת חוב_numeric'] = pd.to_numeric(st.session_state.df_credit_uploaded['יתרת חוב'], errors='coerce').fillna(0)
        debt_summary = st.session_state.df_credit_uploaded.groupby("סוג עסקה")["יתרת חוב_numeric"].sum().reset_index()
        debt_summary = debt_summary[debt_summary['יתרת חוב_numeric'] > 0] # Only show slices with actual debt

        if not debt_summary.empty:
            fig_debt_pie = px.pie(
                debt_summary,
                values='יתרת חוב_numeric',
                names='סוג עסקה',
                title='פירוט יתרות חוב (מדוח נתוני אשראי)',
                color_discrete_sequence=px.colors.qualitative.Pastel
            )
            fig_debt_pie.update_traces(textposition='inside', textinfo='percent+label')
            st.plotly_chart(fig_debt_pie, use_container_width=True)
        else:
             st.info("אין נתוני חוב משמעותיים בדוח האשראי להצגה.")

    # Visualization 2: Debt vs. Income (Bar Chart) - Using data from questionnaire/final calculation
    # Only show if both debt and income are positive, or one is positive and the other is zero
    if total_debt_amount_ans > 0 or annual_income_ans > 0 :
        comparison_data = pd.DataFrame({
            'קטגוריה': ['סך חובות (ללא משכנתא)', 'הכנסה שנתית'],
            'סכום': [total_debt_amount_ans, annual_income_ans]
        })
        fig_debt_income_bar = px.bar(
            comparison_data,
            x='קטגוריה',
            y='סכום',
            title='השוואת סך חובות להכנסה שנתית',
            color='קטגוריה',
            text_auto=True, # Automatically show values on bars
            labels={'קטגוריה': '', 'סכום': 'סכום ב₪'} # Improve axis labels
        )
        fig_debt_income_bar.update_layout(yaxis_tickformat='~s') # Format y-axis for large numbers (e.g., 1M, 1k)
        st.plotly_chart(fig_debt_income_bar, use_container_width=True)
    else:
         st.info("אין נתוני חוב או הכנסה להצגת השוואה.")


    # Visualization 3: Bank Balance Trend (Line Chart)
    if not st.session_state.df_bank_uploaded.empty:
        st.subheader(f"מגמת יתרת חשבון בנק ({st.session_state.bank_type_selected})")
        df_bank_plot = st.session_state.df_bank_uploaded.dropna(subset=['Date', 'Balance'])
        if not df_bank_plot.empty:
            # Sort by date before plotting to ensure correct line trend
            df_bank_plot = df_bank_plot.sort_values(by='Date').reset_index(drop=True)
            fig_balance_trend = px.line(
                df_bank_plot,
                x='Date',
                y='Balance',
                title=f'מגמת יתרת חשבון בנק',
                markers=True # Show data points
            )
            fig_balance_trend.update_layout(yaxis_tickformat='~s') # Format y-axis
            st.plotly_chart(fig_balance_trend, use_container_width=True)
        else:
             st.info(f"אין נתוני יתרות תקינים בדוח הבנק ({st.session_state.bank_type_selected}) להצגה.")
    elif st.session_state.bank_type_selected != "ללא דוח בנק":
        st.info(f"לא הועלה או לא הצלחנו לעבד דוח בנק ({st.session_state.bank_type_selected}).")
    else:
         st.info("לא נבחר סוג דוח בנק או לא הועלה קובץ.")


    # Display DataFrames (optional expander)
    with st.expander("הצג נתונים גולמיים שחולצו מדוחות שהועלו"):
        if not st.session_state.df_credit_uploaded.empty:
            st.write("נתוני אשראי מחולצים:")
            # Format numeric columns nicely
            styled_credit_df = st.session_state.df_credit_uploaded.style.format({
                'גובה מסגרת': "{:,.0f}",
                'סכום מקורי': "{:,.0f}",
                'יתרת חוב': "{:,.0f}",
                'יתרה שלא שולמה': "{:,.0f}"
            })
            st.dataframe(styled_credit_df, use_container_width=True)
        else:
            st.write("לא הועלה או לא עובד דוח נתוני אשראי.")

        st.markdown("---") # Separator inside expander

        if not st.session_state.df_bank_uploaded.empty:
            st.write(f"נתוני יתרות בנק מחולצים ({st.session_state.bank_type_selected}):")
            # Format numeric columns nicely
            styled_bank_df = st.session_state.df_bank_uploaded.style.format({"Balance": '{:,.2f}'})
            st.dataframe(styled_bank_df, use_container_width=True)
        else:
             if st.session_state.bank_type_selected != "ללא דוח בנק":
                st.write(f"לא הועלה או לא עובד דוח בנק מסוג {st.session_state.bank_type_selected}.")
             else:
                 st.write("לא נבחר או הועלה דוח בנק.")


    st.markdown("---")
    # --- Chatbot Interface ---
    st.header("💬 צ'אט עם יועץ פיננסי וירטואלי")
    if client:
        st.markdown("שאל/י כל שאלה על מצבך הפיננסי, הנתונים שהוצגו, או כלכלת המשפחה.")

        # Prepare context for chatbot
        financial_context = "סיכום המצב הפיננסי של המשתמש:\n"
        financial_context += f"- סך הכנסות נטו חודשיות (משאלון): {total_net_income_ans:,.0f} ₪\n"
        financial_context += f"- סך הוצאות קבועות חודשיות (משאלון): {total_fixed_expenses_ans:,.0f} ₪\n"
        financial_context += f"- מאזן חודשי (יתרה פנויה): {monthly_balance_ans:,.0f} ₪\n"
        financial_context += f"- סך חובות (ללא משכנתא, לאחר שאלון ואולי עדכון מדוח): {total_debt_amount_ans:,.0f} ₪\n"

        # Add credit report details if available
        if st.session_state.total_debt_from_credit_report is not None:
            financial_context += f"  - מתוכם, סך יתרת חוב מדוח אשראי שנותח: {st.session_state.total_debt_from_credit_report:,.0f} ₪\n"
            if not st.session_state.df_credit_uploaded.empty:
                financial_context += "  - פירוט חובות מדוח נתוני אשראי (עיקרי):\n"
                # Ensure 'יתרת חוב' and 'יתרה שלא שולמה' are numeric and handle NaNs
                df_credit_cleaned = st.session_state.df_credit_uploaded.copy()
                df_credit_cleaned['יתרת חוב'] = pd.to_numeric(df_credit_cleaned['יתרת חוב'], errors='coerce').fillna(0)
                df_credit_cleaned['יתרה שלא שולמה'] = pd.to_numeric(df_credit_cleaned['יתרה שלא שולמה'], errors='coerce').fillna(0)

                # Limit the number of entries listed to avoid exceeding context window
                max_credit_entries_to_list = 10
                for i, row in df_credit_cleaned.head(max_credit_entries_to_list).iterrows():
                     financial_context += f"    - {row.get('סוג עסקה', 'לא ידוע')} ב{row.get('שם בנק/מקור', 'לא ידוע')}: יתרת חוב {row['יתרת חוב']:,.0f} ₪ (שולם בפיגור: {row['יתרה שלא שולמה']:,.0f} ₪)\n"
                if len(df_credit_cleaned) > max_credit_entries_to_list:
                    financial_context += f"    ... ועוד {len(df_credit_cleaned) - max_credit_entries_to_list} פריטים בדוח האשראי.\n"

        # Add bank balance trend info if available
        if not st.session_state.df_bank_uploaded.empty:
            financial_context += f"- נותח דוח בנק מסוג: {st.session_state.bank_type_selected}\n"
            # Provide summary stats for bank balance trend
            df_bank_plot = st.session_state.df_bank_uploaded.dropna(subset=['Date', 'Balance'])
            if not df_bank_plot.empty:
                start_date = df_bank_plot['Date'].min().strftime('%d/%m/%Y')
                end_date = df_bank_plot['Date'].max().strftime('%d/%m/%Y')
                start_balance = df_bank_plot.loc[df_bank_plot['Date'].idxmin(), 'Balance']
                end_balance = df_bank_plot.loc[df_bank_plot['Date'].idxmax(), 'Balance']
                financial_context += f"  - מגמת יתרת חשבון בנק לתקופה מ-{start_date} עד {end_date}:\n"
                financial_context += f"    - יתרת פתיחה: {start_balance:,.0f} ₪\n"
                financial_context += f"    - יתרת סגירה: {end_balance:,.0f} ₪\n"
                financial_context += f"    - שינוי בתקופה: {(end_balance - start_balance):,.0f} ₪\n"


        financial_context += f"- הכנסה שנתית: {annual_income_ans:,.0f} ₪\n"
        financial_context += f"- יחס חוב להכנסה שנתית: {debt_to_income_ratio_ans:.2%}\n"
        financial_context += f"- סיווג מצב פיננסי ראשוני: {classification} ({description})\n"
        financial_context += "\nתשובות נוספות מהשאלון:\n"

        # Include relevant questionnaire answers, skipping technical keys or ones already summarized
        for key, value in st.session_state.answers.items():
            # Skip purely technical keys, or keys already explicitly listed/summarized above
            if key in ['total_net_income', 'total_fixed_expenses', 'monthly_balance', 'total_debt_amount', 'annual_income', 'debt_to_income_ratio',
                       'income_employee', 'income_partner', 'income_other', 'expense_rent_mortgage', 'expense_debt_repayments', 'expense_alimony_other',
                       'q3_existing_loans_bool_radio', 'q4_financially_balanced_bool_radio', 'arrears_collection_proceedings_radio', 'can_raise_50_percent_radio']:
                continue

            # Format keys nicely for context
            display_key = key.replace('_', ' ').replace('q1 ', '1. ').replace('q2 ', '2. ').replace('q3 loan repayment amount', '3. גובה החזר הלוואות נוספות').replace('q4 situation change next year', '4. שינוי צפוי במצב בשנה הקרובה').replace('q3 loan repayment amount', 'החזר הלוואות חודשי').replace('q_s0_q1', '1. האם קרה משהו חריג').replace('q_s0_q2', '2. מקורות מימון אחרים').replace('q_s0_q4_change', 'שינוי צפוי במצב').replace('can raise 50 percent', 'יכולת לגייס 50% מהחוב').strip()

            # Add to context
            financial_context += f"- {display_key}: {value}\n"

        financial_context += "\n--- סוף מידע על המשתמש ---\n"
        financial_context += "אתה יועץ פיננסי מנוסה, ענה בעברית רהוטה וידידותית, התבסס על הנתונים שסופקו. השתמש בסיווג המצב (ירוק/צהוב/אדום) כבסיס להמלצות. הצע צעדים קונקרטיים בהתאם למצב. אל תמציא נתונים שלא סופקו. אם מידע חסר, ציין זאת. אם השאלה ספציפית לנתון בדוח, התייחס לנתון זה."


        # Display chat messages from history
        for message in st.session_state.chat_messages:
            # Use markdown to render user and assistant messages
            with st.chat_message(message["role"]):
                st.markdown(message["content"])

        # Handle new user input
        if prompt := st.chat_input("שאל אותי כל שאלה על מצבך הפיננסי או כלכלת המשפחה..."):
            # Add user message to state and display
            st.session_state.chat_messages.append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.markdown(prompt)

            # Add a temporary assistant placeholder to state immediately
            # This ensures the history maintains the correct user, assistant, user, assistant... structure
            st.session_state.chat_messages.append({"role": "assistant", "content": ""})
            # Get the index of the newly added placeholder message
            assistant_message_index = len(st.session_state.chat_messages) - 1

            # Prepare messages for API: system message + all previous messages (excluding the temporary placeholder)
            messages_for_api = [
                {"role": "system", "content": financial_context}
            ] + [{"role": m["role"], "content": m["content"]} for m in st.session_state.chat_messages[:-1]] # Use history *before* the current assistant turn


            with st.chat_message("assistant"):
                message_placeholder = st.empty()
                full_response = ""
                try:
                    # Call the OpenAI API with streaming enabled
                    stream = client.chat.completions.create(
                        model="gpt-4o-mini", # Using a more cost-effective model suitable for text chat
                        messages=messages_for_api,
                        stream=True
                    )

                    # Process the streamed response
                    for chunk in stream:
                        if chunk.choices[0].delta.content is not None:
                            full_response += chunk.choices[0].delta.content
                            # Update placeholder with partial response + typing indicator
                            message_placeholder.markdown(full_response + "▌")

                    # Final update of placeholder with complete response
                    message_placeholder.markdown(full_response)

                except APIError as e:
                    logging.error(f"OpenAI API Error (Status Code {e.status_code}): {e.response.text}", exc_info=True)
                    full_response = f"אירעה שגיאה בתקשורת עם שירות הייעוץ הווירטואלי (שגיאה {e.status_code}). ייתכן שהבקשה ארוכה מדי או שיש בעיה אחרת. אנא נסה/י לשאול שאלה קצרה יותר או פנה/י לתמיכה אם הבעיה נמשכת."
                    message_placeholder.error(full_response) # Display error to user
                except Exception as e:
                    logging.error(f"An unexpected error occurred during OpenAI API call: {e}", exc_info=True)
                    full_response = f"אירעה שגיאה בלתי צפויה: {e}. אנא נסה/י שוב מאוחר יותר."
                    message_placeholder.error(full_response) # Display generic error

                # Update the content of the assistant's message in session state
                # This is crucial for the history to be correct for the next turn
                st.session_state.chat_messages[assistant_message_index]["content"] = full_response

            # Rerun the app to display the updated chat history
            st.rerun()

    else:
        st.warning("שירות הצ'אט אינו זמין. אנא ודא/י שמפתח ה-API של OpenAI הוגדר כהלכה בסביבה.")
