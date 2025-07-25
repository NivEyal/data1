"""
יועץ פיננסי וירטואלי
"""
import streamlit as st
from openai import OpenAI
from config import OPENAI_MODEL
import logging


class FinancialAdvisor:
    """יועץ פיננסי וירטואלי"""
    
    def __init__(self):
        self.client = self._initialize_client()
        self.model = OPENAI_MODEL
    
    def _initialize_client(self):
        """אתחול לקוח OpenAI"""
        try:
            api_key = st.secrets.get("OPENAI_API_KEY")
            if api_key:
                return OpenAI(api_key=api_key)
            else:
                st.error("מפתח OpenAI לא הוגדר")
                return None
        except Exception as e:
            st.error(f"שגיאה בהגדרת OpenAI: {e}")
            return None
    
    def is_available(self):
        """בדיקה אם השירות זמין"""
        return self.client is not None
    
    def create_context(self, financial_data):
        """יצירת הקשר פיננסי"""
        if not financial_data:
            return ""
        
        context = f"""
נתונים פיננסיים של המשתמש:
- הכנסה חודשית: {financial_data.get('total_income', 0):,.0f} ₪
- הוצאות קבועות: {financial_data.get('total_expenses', 0):,.0f} ₪
- סך חובות: {financial_data.get('total_debts', 0):,.0f} ₪
- יתרה חודשית: {financial_data.get('total_income', 0) - financial_data.get('total_expenses', 0):,.0f} ₪
- הכנסה שנתית: {financial_data.get('total_income', 0) * 12:,.0f} ₪
"""
        
        annual_income = financial_data.get('total_income', 0) * 12
        if annual_income > 0:
            ratio = financial_data.get('total_debts', 0) / annual_income
            context += f"- יחס חוב להכנסה: {ratio:.2%}\n"
        
        if financial_data.get('has_collection'):
            context += "- קיימים הליכי גבייה\n"
        
        if financial_data.get('can_raise_funds'):
            context += "- יכולת לגייס 50% מהחוב\n"
        
        return context
    
    def get_response(self, user_message, financial_context=""):
        """קבלת תשובה מהיועץ"""
        if not self.client:
            return "שירות הייעוץ אינו זמין כרגע"
        
        system_message = f"""
אתה יועץ פיננסי מומחה לכלכלת המשפחה בישראל.
ספק ייעוץ מעשי, ברור וחם בעברית.
התבסס על הנתונים הפיננסיים שסופקו.

{financial_context}

עקרונות מנחים:
1. תן עצות מעשיות וברורות
2. התייחס לנתונים הספציפיים
3. הסבר בפשטות ללא ז'רגון
4. הראה אמפתיה והבנה
5. הציע צעדים קונקרטיים
"""
        
        messages = [
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_message}
        ]
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                stream=True,
                temperature=0.7,
                max_tokens=1000
            )
            return response
        except Exception as e:
            logging.error(f"OpenAI API error: {e}")
            return f"מצטער, התרחשה שגיאה: {e}"
    
    def display_chat(self, financial_data=None):
        """הצגת ממשק הצ'אט"""
        st.header("💬 יועץ פיננסי וירטואלי")
        
        if not self.is_available():
            st.warning("שירות הייעוץ אינו זמין")
            return
        
        # אתחול הודעות
        if "messages" not in st.session_state:
            st.session_state.messages = []
        
        # הצגת הודעות קיימות
        for message in st.session_state.messages:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])
        
        # קלט חדש
        if prompt := st.chat_input("שאל אותי כל שאלה על מצבך הפיננסי..."):
            # הוספת הודעת המשתמש
            st.session_state.messages.append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.markdown(prompt)
            
            # יצירת תשובה
            with st.chat_message("assistant"):
                message_placeholder = st.empty()
                full_response = ""
                
                financial_context = self.create_context(financial_data)
                response_stream = self.get_response(prompt, financial_context)
                
                if isinstance(response_stream, str):
                    # שגיאה
                    full_response = response_stream
                    message_placeholder.markdown(full_response)
                else:
                    # תשובה מוזרמת
                    try:
                        for chunk in response_stream:
                            if chunk.choices[0].delta.content is not None:
                                full_response += chunk.choices[0].delta.content
                                message_placeholder.markdown(full_response + "▌")
                        message_placeholder.markdown(full_response)
                    except Exception as e:
                        full_response = f"שגיאה בקבלת תשובה: {e}"
                        message_placeholder.error(full_response)
            
            # שמירת התשובה
            st.session_state.messages.append({"role": "assistant", "content": full_response})