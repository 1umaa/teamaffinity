import os
import datetime
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

def main():
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
    refresh_token = os.getenv("GOOGLE_REFRESH_TOKEN")
    calendar_id = os.getenv("GOOGLE_CALENDAR_ID")

    if not all([client_id, client_secret, refresh_token, calendar_id]):
        print("❌ Missing one or more Google Calendar environment variables.")
        return

    creds = Credentials.from_authorized_user_info({
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
    })

    try:
        service = build("calendar", "v3", credentials=creds)

        today = datetime.date.today()
        tomorrow = today + datetime.timedelta(days=1)

        event = {
            "summary": "📅 Test Event from Railway",
            "description": "Testing if Railway can access Google Calendar API",
            "start": {"date": str(today)},
            "end": {"date": str(tomorrow)},
            "colorId": "1"
        }

        created_event = service.events().insert(
            calendarId=calendar_id,
            body=event
        ).execute()

        print(f"✅ Event created successfully: {created_event.get('htmlLink')}")

    except Exception as e:
        print("❌ Error creating calendar event:", e)

if __name__ == "__main__":
    main()
