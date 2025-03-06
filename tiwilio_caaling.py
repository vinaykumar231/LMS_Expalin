import os
from fastapi import FastAPI, HTTPException, Request, Response
from pydantic import BaseModel
from twilio.twiml.voice_response import VoiceResponse
from twilio.rest import Client
import openai
from fastapi.middleware.cors import CORSMiddleware
import json
import logging
import requests

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI()

# CORS middleware configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuration
# Configuration
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Assistant configuration
ASSISTANT_OPTIONS = {
    "name": "Call Maitri AI",
    "firstMessage": "Namaste! Mai AaIkAL System se bol raha hun. Aapki kya madad kar sakta hun?",
    "transcriber": {
        "provider": "deepgram",
        "model": "nova-2",
        "language": "hi",
    },
    "voice": {
        "provider": "cartesia",
        "voiceId": "bdab08ad-4137-4548-b9db-6142854c7525",
    },
    "model": {
        "provider": "openai",
        "model": "gpt-4",
        "messages": [
            {
                "role": "system",
                "content": """Aapko ICALL System ka sales representative banna hai. Aapka goal hai customers se friendly tareeke se baat karke unki requirement samajhna aur unhe ICALL System ka hiring portal suggest karna.

ICALL System ke Portal ke Key Features aur Fayde:

**AI-Based Resume Screening**:
- Multiple resumes ko ek saath screen kar sakta hai
- AI ke zariye best resumes ko select karna
- Time aur resources bachana

**Automatic & Flexible Interview Scheduling**:
- Automatic interview invitations
- Flexible interview timings
- Fast hiring process

**AI Interviewer**:
- Video call interviews
- Automatic interview scoring
- Unbiased evaluation

**Reports and Analytics**:
- Detailed hiring reports
- Data-driven insights
- Process optimization

**Job Application Module**:
- Custom job listings
- Multi-platform sharing
- Real-time tracking
- Candidate portal
- Notification system

Contact Details:
Phone: +91 9022049092, +919004175207
Email: contact@icallsystem.com
Address: Shop-9, Clover Grove CHSL, Garden Grove Complex, Borivali West, Mumbai - 400092"""
            }
        ]
    }
}

# Initialize clients
client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
openai.api_key = OPENAI_API_KEY

class CallRequest(BaseModel):
    phone_number: str

# Store conversation history
conversations = {}
TWILIO_Token=os.getenv("TWILIO_Token")
def transcribe_audio(audio_url):
    """Transcribe audio using Deepgram"""
    try:
        headers = {
            "Authorization": f"Token {TWILIO_Token}"
        }
        response = requests.post(
            "https://api.deepgram.com/v1/listen",
            headers=headers,
            json={
                "url": audio_url,
                "model": "nova-2",
                "language": "hi"
            }
        )
        return response.json().get("results", {}).get("channels", [{}])[0].get("alternatives", [{}])[0].get("transcript", "")
    except Exception as e:
        logger.error(f"Transcription error: {e}")
        return ""

def get_ai_response(message: str, conversation_history: list) -> str:
    """Get response from OpenAI based on conversation history"""
    try:
        messages = ASSISTANT_OPTIONS["model"]["messages"].copy()
        messages.extend(conversation_history)
        messages.append({"role": "user", "content": message})
        
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=messages,
            max_tokens=150,
            temperature=0.7
        )
        
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"Error getting AI response: {e}")
        return "Maaf kijiye, mujhe aapki baat samajhne mein dikkat ho rahi hai."

@app.post("/start-call/")
async def start_call(request: CallRequest):
    """Initialize a new call"""
    try:
        response = VoiceResponse()
        response.say(
            ASSISTANT_OPTIONS["firstMessage"],
            voice="alice",
            language="hi-IN"
        )
        response.record(
            action='/handle-recording',
            maxLength=30,
            playBeep=True
        )
        
        call = client.calls.create(
            twiml=str(response),
            to=request.phone_number,
            from_=TWILIO_PHONE_NUMBER,
            record=True
        )
        
        conversations[call.sid] = []
        
        return {"call_sid": call.sid, "status": "initiated"}
    except Exception as e:
        logger.error(f"Error starting call: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/handle-recording")
async def handle_recording(request: Request):
    """Handle the recorded audio from user"""
    try:
        form_data = await request.form()
        recording_url = form_data.get("RecordingUrl")
        call_sid = form_data.get("CallSid")
        
        # Transcribe the recording
        transcript = transcribe_audio(recording_url)
        
        # Get AI response
        conversation_history = conversations.get(call_sid, [])
        conversation_history.append({"role": "user", "content": transcript})
        ai_response = get_ai_response(transcript, conversation_history)
        conversation_history.append({"role": "assistant", "content": ai_response})
        conversations[call_sid] = conversation_history
        
        # Create response
        response = VoiceResponse()
        response.say(ai_response, voice="alice", language="hi-IN")
        response.record(
            action='/handle-recording',
            maxLength=30,
            playBeep=True
        )
        
        return Response(content=str(response), media_type="application/xml")
    except Exception as e:
        logger.error(f"Error handling recording: {e}")
        response = VoiceResponse()
        response.say(
            "Maaf kijiye, technical dikkat aa rahi hai. Kripya dobara koshish karein.",
            voice="alice",
            language="hi-IN"
        )
        return Response(content=str(response), media_type="application/xml")

@app.post("/end-call/")
async def end_call(call_sid: str):
    """End the call and cleanup"""
    try:
        call = client.calls(call_sid).update(status="completed")
        if call_sid in conversations:
            del conversations[call_sid]
        return {"status": "call ended", "call_sid": call_sid}
    except Exception as e:
        logger.error(f"Error ending call: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
