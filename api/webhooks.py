import os
import hmac
import hashlib
import json
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse

app = FastAPI()

@app.post("/api/webhooks")
async def clerk_webhook(request: Request):
    # Get the webhook secret from environment
    webhook_secret = os.getenv("CLERK_WEBHOOK_SECRET")
    
    if not webhook_secret:
        raise HTTPException(status_code=500, detail="Webhook secret not configured")
    
    # Get the signature from headers
    svix_id = request.headers.get("svix-id")
    svix_timestamp = request.headers.get("svix-timestamp")
    svix_signature = request.headers.get("svix-signature")
    
    if not svix_id or not svix_timestamp or not svix_signature:
        raise HTTPException(status_code=400, detail="Missing svix headers")
    
    # Get the raw body
    body = await request.body()
    body_str = body.decode()
    
    # Verify the webhook signature
    signed_content = f"{svix_id}.{svix_timestamp}.{body_str}"
    expected_signature = hmac.new(
        webhook_secret.encode(),
        signed_content.encode(),
        hashlib.sha256
    ).hexdigest()
    
    # Compare signatures
    signature_parts = svix_signature.split(",")
    signature_valid = False
    for part in signature_parts:
        if part.startswith("v1,"):
            provided_signature = part[3:]
            if hmac.compare_digest(expected_signature, provided_signature):
                signature_valid = True
                break
    
    if not signature_valid:
        raise HTTPException(status_code=401, detail="Invalid signature")
    
    # Parse the webhook payload
    try:
        payload = json.loads(body_str)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    
    # Handle different event types
    event_type = payload.get("type")
    data = payload.get("data", {})
    
    print(f"Received webhook: {event_type}")
    print(f"Webhook data: {json.dumps(data, indent=2)}")
    
    # Handle subscription events
    if event_type == "subscription.created" or event_type == "subscription.updated":
        user_id = data.get("user_id")
        status = data.get("status")
        
        if user_id and status:
            # Update user metadata via Clerk API
            await update_user_metadata(user_id, status)
    
    elif event_type == "subscription.deleted" or event_type == "subscription.cancelled":
        user_id = data.get("user_id")
        if user_id:
            await update_user_metadata(user_id, "inactive")
    
    return JSONResponse(content={"success": True}, status_code=200)


async def update_user_metadata(user_id: str, subscription_status: str):
    """Update user's public metadata with subscription status"""
    import requests
    
    clerk_secret = os.getenv("CLERK_SECRET_KEY")
    if not clerk_secret:
        print("CLERK_SECRET_KEY not set")
        return
    
    url = f"https://api.clerk.com/v1/users/{user_id}"
    headers = {
        "Authorization": f"Bearer {clerk_secret}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "public_metadata": {
            "subscriptionStatus": subscription_status
        }
    }
    
    try:
        response = requests.patch(url, headers=headers, json=payload)
        if response.status_code == 200:
            print(f"Updated user {user_id} subscription status to {subscription_status}")
        else:
            print(f"Failed to update user metadata: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"Error updating user metadata: {e}")