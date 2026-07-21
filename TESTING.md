# Closing Agent Manual Testing Guide

This guide describes how to manually test the complete Closing Agent journey locally.

## Setup

1. **Environment Variables**: Ensure `.env` is configured with mock or real credentials.
2. **Start the Application**:
   ```bash
   python run.py
   ```
3. **Run Database Migration** (if not already done):
   ```bash
   python scripts/migrate_closing_agent.py
   ```

## Test Flow via `/api/test-chat`

You can simulate the entire flow locally using curl or an API client (like Postman or Insomnia), or by running `python verify_flow.py`.

### 1. Greeting & Name Capture
Send a greeting to start:
```bash
curl -X POST http://localhost:8000/api/test-chat \
  -H "Content-Type: application/json" \
  -d '{"phone_number": "919900000001", "message": "Hi"}'
```
Provide a name:
```bash
curl -X POST http://localhost:8000/api/test-chat \
  -H "Content-Type: application/json" \
  -d '{"phone_number": "919900000001", "message": "John Doe"}'
```

### 2. Course Selection
Select a course (e.g. Data Science):
```bash
curl -X POST http://localhost:8000/api/test-chat \
  -H "Content-Type: application/json" \
  -d '{"phone_number": "919900000001", "message": "course_data_science", "interactive": {"id": "course_data_science", "title": "Data Science"}}'
```

### 3. Ask a Question (RAG)
Ask a question about the course:
```bash
curl -X POST http://localhost:8000/api/test-chat \
  -H "Content-Type: application/json" \
  -d '{"phone_number": "919900000001", "message": "What is the syllabus?"}'
```

### 4. Proceed to Payment
Confirm purchase intent to generate a Razorpay link:
```bash
curl -X POST http://localhost:8000/api/test-chat \
  -H "Content-Type: application/json" \
  -d '{"phone_number": "919900000001", "message": "proceed_to_payment", "interactive": {"id": "proceed_to_payment", "title": "Proceed to Payment"}}'
```
*Note the internal_order_id or payment_link_id returned or logged.*

## Testing WhatsApp Webhook Externally

To test exactly as a user would on WhatsApp:
1. Go to your **Meta Developer Dashboard** -> **WhatsApp** -> **API Setup**.
2. Ensure you have your test number selected, and copy your `WHATSAPP_TOKEN` into `.env`.
3. In Meta Developer Dashboard -> **Configuration** -> **Webhook**, click "Edit".
4. Enter your public tunnel URL (e.g., from ngrok or cloudflare) ending in `/webhook`.
   - Example: `https://my-tunnel.ngrok-free.app/webhook`
5. Enter the `WHATSAPP_WEBHOOK_VERIFY_TOKEN` you set in `.env` and save.
6. Click **Manage** in Webhook fields and subscribe to `messages`.
7. Send a message to your test number from your personal WhatsApp to begin the journey.

## Testing Razorpay Webhook Externally

To test the end-to-end Razorpay integration with real callbacks:
1. Go to your **Razorpay Dashboard** -> **Account & Settings** -> **Webhooks**.
2. Click **Add New Webhook**.
3. Enter your public tunnel URL (e.g., from ngrok) ending in `/closing-agent/razorpay-webhook`.
   - Example: `https://my-tunnel.ngrok-free.app/closing-agent/razorpay-webhook`
4. Enter the `RAZORPAY_WEBHOOK_SECRET` you set in `.env` and save it to the dashboard.
5. Under **Active Events**, check the boxes for:
   - `payment_link.paid`
   - `payment_link.failed`
6. Click **Create Webhook**.
7. When you trigger the `proceed_to_payment` step in the bot, open the Razorpay payment link it provides.
8. Complete the payment using a Razorpay Test Card (e.g. `4111 1111 1111 1111`, any future expiry date).
9. You should automatically receive a success confirmation message on WhatsApp with your receipt!
