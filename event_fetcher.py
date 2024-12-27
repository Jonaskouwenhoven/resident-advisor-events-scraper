


import requests
import argparse
from supabase import create_client
from config import settings




supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_ANON_KEY)

URL = "https://ra.co/graphql"
HEADERS = {
    "Content-Type": "application/json",
    "Referer": "https://ra.co/",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
}

# Initialize your Supabase client globally
# supabase: Client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

class VenueFetcher:
    def __init__(self, venue_id):
        self.venue_id = venue_id

    def get_venue_details(self):
        payload = {
            "operationName": "GET_VENUE_MOREON",
            "variables": {
                "excludeEventId": "0",
                "id": self.venue_id,
            },
            "query": """
            query GET_VENUE_MOREON($id: ID!, $excludeEventId: ID = 0) {
                venue(id: $id) {
                    id
                    name
                    logoUrl
                    photo
                    blurb
                    address
                    contentUrl
                    followerCount
                    capacity
                    topArtists {
                        name
                        contentUrl
                    }
                    eventCountThisYear
                    events(limit: 50, type: LATEST, excludeIds: [$excludeEventId]) {
                        id
                        title
                        interestedCount
                        date
                        startTime
                        endTime
                        contentUrl
                        flyerFront
                        images {
                            id
                            filename
                            alt
                            type
                            crop
                        }
                        artists {
                            id
                            name
                            contentUrl
                        }
                        venue {
                            id
                            name
                            address
                            contentUrl
                            capacity
                        }
                        pick {
                            id
                            blurb
                        }
                        isTicketed
                        attending
                        queueItEnabled
                        newEventForm
                    }
                }
            }
            """,
        }

        response = requests.post(URL, headers=HEADERS, json=payload)
        try:
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.RequestException as e:
            print(f"Request failed: {e}")
            raise
        except ValueError:
            print("Failed to decode JSON response")
            raise

        if "data" not in data or "venue" not in data["data"]:
            raise ValueError("Failed to fetch venue details")

        return data["data"]["venue"]


def create_venue_user_in_supabase(venue):
    user_payload = {
        "username": venue["name"],
        "email": f"venue_{venue['id']}@dummy.com",
        "password_hash": "hashed_dummy_password",
        "display_name": venue["name"],
        "isvenue": True,
        "description": venue.get("blurb", ""),
        "website_url": f"https://ra.co{venue.get('contentUrl','')}",  # For example
        "profile_picture_url": venue.get("logoUrl", ""),
    }
    try:
        response = supabase.table("users").insert(user_payload).execute()
        if response.data:
            return response.data[0]["id"]
        else:
            raise Exception("Failed to retrieve the newly created user ID.")
    except Exception as e:
        print(f"Error creating venue user in Supabase: {e}")
        raise e


def parse_ra_event_to_ticket(event, venue):
    # Combine date + startTime into one datetime if you wish, but keep it simple here.
    event_datetime = event.get("date", None)

    parsed_data = {
        "event_date": event_datetime,
        "title": event.get("title", "Untitled Event"),
        "cover_image": event.get("images", None)[0]['filename'],
        "short_description": venue.get("address", ""),
        "long_description": "",
        "creators": [],
        "lineup": [artist["name"] for artist in event.get("artists", [])],
        "has_comments": True,
        "ticket_type": "physical",
        "type_properties": {
            "host": venue.get("name", "Unknown Host"),
            "location": venue.get("address", "Unknown Location"),
        },
        "vorm": None,
        "tagg": None,
        "additional_fields": None,
        "preview_url": None,
        "co_creator_name": None,
        "host": venue.get("name", None),
    }

    return parsed_data


def upload_event_ticket_to_supabase(parsed_data, user_id):
    ticket_payload = {
        "event_date": parsed_data.get("event_date"),
        "title": parsed_data.get("title"),
        "cover_image": parsed_data.get("cover_image"),
        "short_description": parsed_data.get("short_description"),
        "long_description": parsed_data.get("long_description"),
        "creators": parsed_data.get("creators"),
        "lineup": parsed_data.get("lineup"),
        "has_comments": parsed_data.get("has_comments", None),
        "ticket_type": parsed_data.get("ticket_type", "physical"),
        "type_properties": {
            "host": parsed_data["type_properties"].get("host", "Unknown Host"),
            "location": parsed_data["type_properties"].get("location", "Unknown Location"),
        },
        "vorm": parsed_data.get("vorm", None),
        "tagg": parsed_data.get("tagg", None),
        "additional_fields": parsed_data.get("additional_fields", None),
        "preview_url": parsed_data.get("preview_url", None),
        "main_creator_id": user_id,  # The newly created venue user
        "co_creator_name": parsed_data.get("co_creator_name", None),
        "main_creator_name": parsed_data.get("host", None),
    }

    try:
        response = supabase.table("tickets").insert(ticket_payload).execute()
        if response.data:
            return {"ticket_id": response.data[0]["id"]}
        else:
            raise Exception("Failed to retrieve the newly created ticket ID.")
    except Exception as e:
        print(f"Error uploading to Supabase: {e}")
        raise e


def fetch_and_upload_venue_events(venue_id):
    venue_fetcher = VenueFetcher(venue_id)
    venue_details = venue_fetcher.get_venue_details()

    # Create or retrieve a user for this venue
    venue_user_id = create_venue_user_in_supabase(venue_details)

    # For each event in this venue, parse it & upload
    events = venue_details.get("events", [])
    for event in events:
        parsed_data = parse_ra_event_to_ticket(event, venue_details)
        upload_event_ticket_to_supabase(parsed_data, venue_user_id)

    print(f"Successfully uploaded {len(events)} events for venue {venue_id}.")


def main():
    parser = argparse.ArgumentParser(
        description="Fetch venue details from RA.co, create a venue user, and create events as tickets in Supabase."
    )
    parser.add_argument("venue_id", type=str, help="The ID of the RA.co venue (e.g., 137474).")
    args = parser.parse_args()

    fetch_and_upload_venue_events(args.venue_id)


if __name__ == "__main__":
    main()
