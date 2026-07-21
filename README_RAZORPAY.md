# Razorpay Integration - Testing Guide

The Closing Agent uses Razorpay for payment processing. This guide explains how to set up credentials for testing end-to-end without moving real money.

## 1. Getting Test Credentials

1. Go to [Razorpay Dashboard](https://dashboard.razorpay.com/) and create a free account.
2. Ensure you are in **Test Mode** (toggle at the top/side of the dashboard).
3. Navigate to **Settings > API Keys** and click **Generate Test Key**.
4. You will get a `Key Id` and `Key Secret`.

Add these to your `.env` file in the repository root:
```env
RAZORPAY_KEY_ID=rzp_test_your_key_id
RAZORPAY_KEY_SECRET=your_key_secret
RAZORPAY_WEBHOOK_SECRET=your_webhook_secret_here
```

## 2. Setting Up Webhooks (Optional for local testing)

To test webhooks locally, you can use ngrok or cloudflared to expose your local server.
1. In the Razorpay Dashboard, go to **Settings > Webhooks**.
2. Click **Add New Webhook**.
3. Set the Webhook URL to `https://your-ngrok-url.com/api/closing/razorpay-webhook`.
4. Add a secret (and put it in `RAZORPAY_WEBHOOK_SECRET` in `.env`).
5. Select the `payment.captured` and `payment.failed` events.

## 3. Test Cards / UPI

When you reach the Razorpay checkout screen in test mode, you can use these test details:

- **Cards**: Use any of the test cards provided by Razorpay (e.g., `4111 1111 1111 1111`, CVV: `111`, Expiry: any future date).
- **UPI**: Use `success@razorpay` for a successful payment or `failure@razorpay` for a failed payment.
- **Netbanking**: Select any bank, and it will give you options to simulate a success or failure response.

For a full list of test cards, see the [Razorpay Test Cards Documentation](https://razorpay.com/docs/payments/payments/test-card-details/).
