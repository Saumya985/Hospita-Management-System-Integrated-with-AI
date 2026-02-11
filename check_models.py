import google.generativeai as genai

GEMINI_API_KEY = "AIzaSyCc8ifiQONm6TXMIPaBzd9EOl1U9_Swm34"
genai.configure(api_key=GEMINI_API_KEY)

print("Checking available models...")
try:
    for m in genai.list_models():
        if 'generateContent' in m.supported_generation_methods:
            print(f"- {m.name}")
except Exception as e:
    print(f"Error: {e}")