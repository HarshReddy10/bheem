"""End-to-end chatbot test with representative questions."""

import httpx
import json
import time

BASE = "http://localhost:8000"
PHONE = "+919876500001"

questions = [
    # Placement services
    "What placement services does PTS provide?",
    "What is the average salary package for placed students?",
    # Training programs
    "What training programs do you offer?",
    "Tell me about the AI Engineering and RAG Applications course",
    # Fees
    "How much does the Full Stack Development program cost?",
    "Do you offer EMI or instalment payment options?",
    # Duration
    "How long is the Data Science program?",
    # Eligibility
    "I am a commerce graduate. Can I join any of your programs?",
    # Certifications
    "Will I get a certificate after completing the course?",
    # Contact
    "How can I contact your admissions team?",
]

print(f"\n{'='*80}")
print(f"  CHATBOT END-TO-END TEST — {len(questions)} questions")
print(f"{'='*80}\n")

for i, q in enumerate(questions, 1):
    try:
        r = httpx.post(
            f"{BASE}/api/test-chat",
            json={"phone_number": PHONE, "message": q},
            timeout=60,
        )
        data = r.json()
        response = data.get("bot_response", "NO RESPONSE")
        # Truncate for display
        display = response[:300] + "..." if len(response) > 300 else response
        print(f"Q{i}: {q}")
        print(f"A{i}: {display}")
        print(f"{'─'*80}\n")
        time.sleep(1)  # avoid rate limiting
    except Exception as e:
        print(f"Q{i}: {q}")
        print(f"ERROR: {e}")
        print(f"{'─'*80}\n")

print(f"\n{'='*80}")
print(f"  CHATBOT TEST COMPLETE")
print(f"{'='*80}\n")
