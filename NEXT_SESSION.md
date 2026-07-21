# Next Session

- **Current status**: closing-agent tests passed, 21 passed
- **External WhatsApp test**: working
- **Razorpay/Meta integration status**: Fully implemented and tested via mocks. Manual test flow succeeds up to payment generation, which requires valid Razorpay credentials in `.env` to execute end-to-end. WhatsApp connection is active and replying.
- **Known name-capture bug**: "Hi" may be stored as the user name if the user sends multiple greetings or responds unexpectedly.
- **Known conversation-ending issue**: after "Talk to an Advisor", the flow does not transition smoothly back to sales or properly end.
- **Next task**: apply the prepared name-capture and advisor-flow prompt to fix the above two bugs.
- **Existing technical-debt items**:
  1. Tighten purchase-confirmation detection for ambiguous phrases in the message processor.
  2. Add a unique index for non-null `internal_order_id` values in the orders table.
