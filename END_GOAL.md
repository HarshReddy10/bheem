# BHEEM CLOSING AGENT — NORTH STAR

## 1. Primary Goal

The immediate product goal is a fully working WhatsApp course-sales closing agent.

A real user must be able to:

1. Send “Hi” to the Meta WhatsApp test number.
2. Receive a welcome message with native WhatsApp buttons or lists.
3. Select or type the name of a course.
4. Receive accurate course details including:
   - course name
   - duration
   - price
   - short description
5. Ask follow-up questions about:
   - syllabus
   - trainers
   - qualifications
   - eligibility
   - fees
   - duration
   - course delivery
   - placement support
6. Receive answers grounded in the existing RAG knowledge base.
7. Continue the same purchase journey after asking questions.
8. Confirm that they want to enrol.
9. Receive a real Razorpay Test Mode payment link.
10. Complete a Razorpay test payment.
11. Have the payment verified through a genuine Razorpay webhook signature.
12. Receive a WhatsApp confirmation containing:
   - course name
   - amount
   - internal order ID
   - Razorpay payment ID
13. Have the following stored in the database:
   - WhatsApp user
   - conversation
   - selected course
   - conversation state
   - order
   - amount
   - Razorpay payment-link ID
   - Razorpay payment ID
   - payment status
   - timestamps

This complete flow is the primary success condition.

## 2. Golden Customer Journey

Expected example:

User:
Hi

Bot:
Welcome to Placement & Training Services.
Which course are you interested in?

Buttons:
- View Courses
- Ask a Question
- Talk to an Advisor

User:
I am interested in the Data Science course.

Bot:
Displays the configured Data Science:
- duration
- price
- short description

Then asks:
Would you like to proceed with enrolment?

Buttons:
- Proceed to Payment
- Ask a Question
- View Other Courses

User:
Who teaches this course?

Bot:
Answers using RAG-grounded information.

Then asks:
Would you like to proceed with enrolment in the Data Science programme?

User presses:
Proceed to Payment

Bot:
Creates or reuses one active internal order and sends the Razorpay payment URL.

User completes payment.

Razorpay sends a verified webhook.

Bot:
Payment successful.

Course: Data Science
Amount: configured amount
Order ID: internal order ID
Payment ID: Razorpay payment ID

Your enrolment has been confirmed.

## 3. Required Architecture

The existing project must be evolved, not rewritten.

Reuse:

- FastAPI application
- Existing Meta WhatsApp client
- Existing webhook verification
- Existing Gemini provider
- Existing RAG service
- Existing Chroma knowledge base
- Existing user, conversation and message persistence
- Existing Razorpay integration where correct
- Existing company configuration system
- Existing knowledge repository

Add only the coordination and persistence required to complete the end-to-end journey.

There must be one canonical inbound message-processing pipeline.

The same pipeline must process:

- typed WhatsApp text
- reply-button selections
- list selections
- local test-chat requests

The normal RAG assistant and the closing agent must not behave as two separate bots.

## 4. Conversation State Requirements

The application must persist:

- current closing state
- selected course
- active order

Minimum states:

- GREETING
- DISCOVERING_COURSE
- ANSWERING_QUESTIONS
- AWAITING_PURCHASE_CONFIRMATION
- PAYMENT_PENDING
- PAID

Asking a RAG question must not erase:

- the selected course
- the current sales context
- the active order

A user may move temporarily into question-answering and then return naturally to the purchase journey.

## 5. Course and RAG Responsibilities

Structured catalogue data is the authority for:

- course ID
- course name
- aliases
- price
- currency
- duration
- availability
- checkout description

RAG is the authority for detailed informational questions such as:

- trainer background
- syllabus
- qualifications
- learning outcomes
- placement support
- eligibility
- policies

The system must not invent information missing from the knowledge base.

Missing production prices may remain clearly marked placeholders during testing.

## 6. Payment Requirements

For testing, use Razorpay Test Mode.

When the customer confirms purchase:

1. Create one internal order.
2. Generate a Razorpay payment link.
3. Store the link and payment-link ID.
4. Set the session to PAYMENT_PENDING.
5. Send the link through WhatsApp.

Repeated purchase confirmations must not create multiple active payment links.

Payment is considered successful only after:

- receiving the Razorpay webhook
- validating its HMAC signature
- identifying the correct order
- committing the order as paid

Customer text such as “I paid” is not sufficient.

Duplicate Razorpay webhook events must not duplicate payment processing.

## 7. WhatsApp UI Requirements

Use native Meta WhatsApp interactive UI where appropriate:

- reply buttons for up to three actions
- lists for larger course selections
- plain Razorpay URL for the first working payment version
- optional approved CTA templates later

The internal agent response must remain provider-independent.

The backend WhatsApp renderer converts structured responses into Meta payloads.

Route button and list interactions using stable IDs, not visible titles.

## 8. Definition of Done

The closing agent is finished only when all of the following pass:

1. “Hi” receives the correct greeting through the Meta test number.
2. A course can be selected through text.
3. A course can be selected through interactive UI.
4. The selected course is persisted.
5. A RAG question receives a grounded answer.
6. The selected course survives the RAG interaction.
7. Purchase confirmation creates one order.
8. Repeated confirmation does not create duplicate active orders.
9. Razorpay Test Mode returns a real payment URL.
10. The payment can be completed using Razorpay test credentials.
11. An invalid Razorpay webhook signature is rejected.
12. A valid successful webhook marks the order paid.
13. A duplicate webhook is safely ignored.
14. The payment and identifiers are stored in the database.
15. A WhatsApp payment confirmation is sent.
16. Automated tests pass.
17. A manual end-to-end test succeeds using the Meta test number.

## 9. Explicit Non-Goals for This Phase

Do not prioritise:

- n8n workflow visualisation
- Kubernetes
- production scaling
- advanced analytics dashboards
- multi-company support
- CRM integration
- human-agent dashboard
- production WhatsApp templates
- production Razorpay credentials
- major UI redesign
- unrelated admin functionality
- rewriting the RAG pipeline
- replacing FastAPI
- replacing the database architecture beyond what is necessary for this flow

These may be added only after the complete closing-agent journey works.

## 10. Change-Control Rule

Before changing code, every proposed change must identify:

- which North Star requirement it satisfies
- which existing component it reuses
- why the change is necessary
- whether it risks breaking the completed customer journey

Do not introduce architectural changes merely for elegance, abstraction or future scalability.

The simplest implementation that reliably completes the defined end-to-end journey is preferred.

## 11. Audit Instruction

After creating END_GOAL.md:

1. Compare the current implementation against every Definition of Done item.
2. Produce a checklist with:
   - complete
   - partially complete
   - missing
   - blocked by credentials or configuration
3. Do not rewrite completed components unnecessarily.
4. Implement only the missing or incorrect pieces.
5. Run automated tests.
6. Provide the exact manual test sequence.
