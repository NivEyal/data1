"""
צ'אטבוט פיננסי
"""
import streamlit as st
from openai import OpenAI
from config import OPENAI_MODEL


class FinancialChatbot:
    """צ'אטבוט לייעוץ פיננסי"""
    
    def __init__(self):
        self.client = self._initialize_openai_client()
        self.model = OPENAI_MODEL
    
    def _initialize_openai_client(self):
        """אתחול לקוח OpenAI"""
        try:
            return OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
        except Exception as e:
            st.error(f"שגיאה בטעינת מפתח OpenAI: {e}")
            return None
    
    def is_available(self):
        """בדיקה אם הצ'אטבוט זמין"""
        return self.client is not None
    
    def create_financial_context(self, analysis_data):
        """יצירת הקשר פיננסי למשתמש"""
        if not analysis_data.get('analysis_done', False):
            return ""
        
        context = f"""
--- סיכום פיננסי של המשתמש ---
סך חובות: {analysis_data.get('total_debts', 0):,.0f} ₪
הכנסה שנתית: {analysis_data.get('annual_income', 0):,.0f} ₪
יחס חוב להכנסה: {analysis_data.get('debt_to_income_ratio', 0):.2%}
"""
        
        if analysis_data.get('classification'):
            context += f"סיווג המצב: {analysis_data['classification']}\n"
        
        if analysis_data.get('collection_proceedings') is not None:
            context += f"הליכי גבייה: {'כן' if analysis_data['collection_proceedings'] else 'לא'}\n"
        
        if analysis_data.get('can_raise_funds') is not None:
            context += f"יכולת לגייס 50% מהחוב: {'כן' if analysis_data['can_raise_funds'] else 'לא'}\n"
        
        context += "--- סוף סיכום פיננסי ---\n"
        return context
    
    def get_response(self, user_message, financial_context=""):
        """קבלת תשובה מהצ'אטבוט"""
        if not self.client:
            return "מצטער, שירות הצ'אט אינו זמין כרגע."
        
        system_message = f"""
אתה מומחה לכלכלת המשפחה בישראל. 
המטרה שלך היא לספק ייעוץ פיננסי ברור, מעשי וקל להבנה.
ענה בעברית בצורה חמה ומקצועית.
{financial_context}
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
                temperature=0.7
            )
            return response
        except Exception as e:
            return f"מצטער, התרחשה שגיאה: {e}"
    
    def display_chat_interface(self, analysis_data):
        """הצגת ממשק הצ'אט"""
        st.header("💬 צ'אט עם מומחה כלכלת המשפחה")
        
        if not self.is_available():
            st.warning("שירות הצ'אט אינו זמין עקב בעיה בהגדרות.")
            return
        
        # הצגת הודעות קיימות
        for message in st.session_state.messages:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])
        
        # קלט חדש מהמשתמש
        if prompt := st.chat_input("שאל אותי כל שאלה על מצבך הפיננסי..."):
            # הוספת הודעת המשתמש
            st.session_state.messages.append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.markdown(prompt)
            
            # יצירת תשובה
            with st.chat_message("assistant"):
                message_placeholder = st.empty()
                full_response = ""
                
                financial_context = self.create_financial_context(analysis_data)
                response_stream = self.get_response(prompt, financial_context)
                
                if isinstance(response_stream, str):
                    # שגיאה
                    full_response = response_stream
                    message_placeholder.markdown(full_response)
                else:
                    # תשובה מוזרמת
                    for chunk in response_stream:
                        if chunk.choices[0].delta.content is not None:
                            full_response += chunk.choices[0].delta.content
                            message_placeholder.markdown(full_response + "▌")
                    message_placeholder.markdown(full_response)
            
            # שמירת התשובה
            st.session_state.messages.append({"role": "assistant", "content": full_response})