"""Semantic search quality tests for the new knowledge base."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.rag import rag_service

rag_service.initialize()

queries = [
    # Placement services
    ("What placement services do you provide?", ["placement", "resume", "interview"]),
    ("What is the placement success rate?", ["79.5%", "eligible", "placed"]),
    ("Which companies do you partner with for placements?", ["Accenture", "TCS", "Infosys"]),
    
    # Training programs
    ("What training programs are available?", ["Full Stack", "Data Science", "DevOps"]),
    ("Tell me about the AI Engineering course", ["AI Engineering", "RAG", "22 weeks"]),
    ("What is the duration of the Data Science program?", ["28 weeks", "Data Science"]),
    
    # Fees
    ("What are the course fees?", ["₹"]),
    ("How much does Full Stack Development cost?", ["₹78,000", "Full Stack"]),
    ("Do you offer any discounts or scholarships?", ["discount", "alumni"]),
    
    # Duration
    ("How long is the Python Development course?", ["16 weeks", "Python"]),
    ("What is the duration of Cloud Computing program?", ["18 weeks", "Cloud"]),
    
    # Eligibility
    ("Who can enroll in PTS programs?", ["graduate", "professional", "career"]),
    ("What are the prerequisites for Machine Learning?", ["Python", "statistics"]),
    
    # Certifications
    ("Do you provide certificates?", ["certificate", "certification"]),
    ("What are the requirements for certification?", ["85%", "attendance", "project"]),
    
    # Contact information
    ("How can I contact the admissions team?", ["admissions@", "4712 8801"]),
    ("What is the WhatsApp support number?", ["+91 90085 44880"]),
    ("Where is your Bengaluru office located?", ["Richmond Road", "Bengaluru"]),
    
    # Refund policy
    ("What is the refund policy?", ["refund", "registration fee"]),
    
    # Instructors
    ("Who teaches the Full Stack course?", ["Ananya"]),
    
    # Success stories
    ("Tell me about student success stories", ["placed", "package", "LPA"]),
    ("What is the highest salary package achieved?", ["18.4 LPA", "Siddharth"]),
]

print(f"\n{'='*80}")
print(f"  SEMANTIC SEARCH QUALITY TEST — {len(queries)} queries")
print(f"  ChromaDB document count: {rag_service.document_count}")
print(f"{'='*80}\n")

passed = 0
failed = 0

for query, expected_terms in queries:
    results = rag_service.retrieve(query, top_k=3)
    combined = " ".join([r["content"] for r in results]).lower()
    
    found = [t for t in expected_terms if t.lower() in combined]
    missing = [t for t in expected_terms if t.lower() not in combined]
    
    status = "✅ PASS" if len(found) >= 1 else "❌ FAIL"
    if len(found) >= 1:
        passed += 1
    else:
        failed += 1
    
    top_score = results[0]["relevance_score"] if results else 0
    top_source = results[0]["source"] if results else "N/A"
    
    print(f"{status}  [{top_score:.3f}] Q: {query}")
    if missing:
        print(f"         Missing: {missing}")
    print(f"         Source: {top_source}")
    print()

print(f"{'='*80}")
print(f"  RESULTS: {passed}/{len(queries)} passed, {failed}/{len(queries)} failed")
print(f"{'='*80}\n")
