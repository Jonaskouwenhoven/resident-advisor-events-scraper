import requests
from bs4 import BeautifulSoup
from datetime import datetime
import json

from supabase import create_client
from config import settings

# Create your Supabase client
supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_ANON_KEY)

# -------------------------------------------------------------------
# 1) Parse the main Bandcamp "artist/music" page
# -------------------------------------------------------------------

def fetch_bandcamp_main_page(url):
    """
    Simple helper to fetch the raw HTML of the Bandcamp main/music page.
    """
    try:
        resp = requests.get(url)
        resp.raise_for_status()
        return resp.text
    except requests.exceptions.RequestException as e:
        print(f"Error fetching {url}: {e}")
        return None


def parse_bandcamp_main_page(html_content):
    """
    Parse the main Bandcamp '.../music' page to extract:
      - profile_banner_url (cover image)
      - profile_picture_url
      - artist_name
      - location
      - description
      - social_links
      - music_releases (list of album/track items)
    """
    soup = BeautifulSoup(html_content, "html.parser")
    
    # 1) Profile Banner (Cover Image) from .desktop-header img
    profile_banner_url = None
    desktop_header = soup.find("div", class_="desktop-header")
    if desktop_header:
        banner_img = desktop_header.find("img")
        if banner_img and banner_img.has_attr("src"):
            profile_banner_url = banner_img["src"]
    
    # 2) Profile Picture from <img class="band-photo">
    profile_picture_url = None
    band_photo_img = soup.find("img", class_="band-photo")
    if band_photo_img and band_photo_img.has_attr("src"):
        profile_picture_url = band_photo_img["src"]
    
    # 3) Artist Name & Location
    artist_name = None
    location = None
    band_name_location = soup.find("p", id="band-name-location")
    if band_name_location:
        # <span class="title">Kourosh</span>
        title_span = band_name_location.find("span", class_="title")
        if title_span:
            artist_name = title_span.get_text(strip=True)
        # <span class="location secondaryText">Amsterdam, Netherlands</span>
        loc_span = band_name_location.find("span", class_="location")
        if loc_span:
            location = loc_span.get_text(strip=True)
    
    # 4) Artist Description from <p id="bio-text">
    description = ""
    bio_text_p = soup.find("p", id="bio-text")
    if bio_text_p:
        description = bio_text_p.get_text(strip=True)
    
    # 5) Social or contact links from <ol id="band-links">
    social_links = []
    band_links_ol = soup.find("ol", id="band-links")
    if band_links_ol:
        for li in band_links_ol.find_all("li"):
            link_tag = li.find("a", href=True)
            if link_tag:
                social_links.append(link_tag["href"])
    
    # 6) Music releases from <ol id="music-grid">
    music_releases = []
    music_grid = soup.find("ol", id="music-grid")
    if music_grid:
        li_items = music_grid.find_all("li", class_="music-grid-item")
        for li in li_items:
            link = li.find("a", href=True)
            if not link:
                continue
            
            release_url = link["href"]  # relative URL (e.g. "/track/u-need-somebody")
            
            # Release title from <p class="title">
            title_tag = link.find("p", class_="title")
            release_title = title_tag.get_text(strip=True) if title_tag else "Untitled"

            # Artwork from <div class="art"><img src="...">
            image_url = None
            art_div = link.find("div", class_="art")
            if art_div:
                img_tag = art_div.find("img", src=True)
                if img_tag:
                    image_url = img_tag["src"]
            
            # Identify type by URL substring
            if "/track/" in release_url:
                release_type = "track"
            elif "/album/" in release_url:
                release_type = "album"
            else:
                release_type = "unknown"
            
            music_releases.append({
                "url": release_url,
                "title": release_title,
                "image_url": image_url,
                "type": release_type,
            })
    
    return {
        "profile_banner_url": profile_banner_url,
        "profile_picture_url": profile_picture_url,
        "artist_name": artist_name,
        "location": location,
        "description": description,
        "social_links": social_links,
        "music_releases": music_releases,
    }


# -------------------------------------------------------------------
# 2) Parse an individual Bandcamp album/track page
# -------------------------------------------------------------------

def fetch_bandcamp_html(url):
    """
    Fetches the raw HTML content from a Bandcamp album or track page.
    """
    try:
        response = requests.get(url)
        if response.status_code == 200:
            return response.text
        else:
            print(f"Failed to fetch URL. HTTP status code: {response.status_code}")
            return None
    except requests.exceptions.RequestException as e:
        print(f"Error fetching URL: {e}")
        return None


def parse_bandcamp_html(html_content):
    """
    Parses a Bandcamp album/track page (raw HTML) and returns
    a list of structured items (1 for an album or track, but an album
    can contain multiple "tracks" in the 'tracks' field).
    """
    soup = BeautifulSoup(html_content, "html.parser")

    # Check if it's a track or album page by table.track_list presence
    is_album = soup.find("table", class_="track_list") is not None

    # Extract common data
    title_tag = soup.find("h2", class_="trackTitle")
    title = title_tag.get_text(strip=True) if title_tag else ""

    # Extract artist
    artist = ""
    artist_section = soup.find("h3", class_="albumTitle") or soup.find("h3", style="margin:0px;")
    if artist_section:
        artist_tag = artist_section.find("a")
        artist = artist_tag.get_text(strip=True) if artist_tag else ""

    # Extract cover image
    cover_image_tag = soup.find("a", class_="popupImage")
    cover_image = cover_image_tag["href"] if cover_image_tag else ""

    # Extract tags
    tags_div = soup.find("div", class_="tralbumData tralbum-tags tralbum-tags-nu")
    tags = [tag.get_text(strip=True) for tag in tags_div.find_all("a")] if tags_div else []

    # Extract release date
    credits_div = soup.find("div", class_="tralbumData tralbum-credits")
    release_date = None
    if credits_div:
        for line in credits_div.stripped_strings:
            if line.startswith("released"):
                release_date = line.replace("released", "").strip()
                try:
                    release_date = datetime.strptime(release_date, "%B %d, %Y").strftime("%Y-%m-%d")
                except ValueError:
                    pass
                break

    # Extract description
    about_div = soup.find("div", class_="tralbumData tralbum-about")
    description = about_div.get_text(strip=True) if about_div else ""

    # Extract item_id for embedded player (from meta)
    meta_tag = soup.find("meta", {"name": "bc-page-properties"})
    item_id = None
    if meta_tag:
        meta_content = meta_tag.get("content", "")
        if "item_id" in meta_content:
            start_index = meta_content.find('"item_id":') + len('"item_id":')
            end_index = meta_content.find(",", start_index)
            item_id = meta_content[start_index:end_index].strip().replace('"', '')

    # Generate the embedded player iframe
    embedded_player = None
    if item_id:
        if is_album:
            embedded_player = f"""
            <iframe style="border: 0; width: 100%; height: 472px;"
                    src="https://bandcamp.com/EmbeddedPlayer/album={item_id}/size=large/bgcol=ffffff/linkcol=0687f5/artwork=small/transparent=true/"
                    seamless>
                <a href="https://bandcamp.com/album/{item_id}">{title} by {artist}</a>
            </iframe>
            """
        else:
            embedded_player = f"""
            <iframe style="border: 0; width: 100%; height: 120px;"
                    src="https://bandcamp.com/EmbeddedPlayer/track={item_id}/size=large/bgcol=ffffff/linkcol=0687f5/tracklist=false/artwork=small/transparent=true/"
                    seamless>
                <a href="https://bandcamp.com/track/{item_id}">{title} by {artist}</a>
            </iframe>
            """

    # Album-specific data
    tracks = []
    if is_album:
        track_rows = soup.find_all("tr", class_="track_row_view")
        for track_row in track_rows:
            track_title_tag = track_row.find("a", class_="track-title")
            track_title = track_title_tag.get_text(strip=True) if track_title_tag else ""

            track_duration_tag = track_row.find("span", class_="time")
            track_duration = track_duration_tag.get_text(strip=True) if track_duration_tag else ""

            track_href = track_row.find("a", href=True)
            track_url = track_href["href"] if track_href else ""

            tracks.append({
                "title": track_title,
                "duration": track_duration,
                "url": track_url
            })

    # Additional fields
    additional_fields = []
    if tags:
        for tag in tags:
            additional_fields.append({
                "id": hash(tag),
                "type": "tag",
                "label": "Genre Tag",
                "value": tag
            })
    if embedded_player:
        additional_fields.append({
            "id": hash(embedded_player),
            "type": "embedded_links",
            "label": "bandcamp",
            "value": {
                'url': embedded_player.strip(),
                'caption': ''
            }
        })

    # Construct the parsed JSON structure
    parsed_json = [
        {
            "title": title,
            "cover_image": cover_image,
            "short_description": "",
            "long_description": description,
            "creators": artist,
            "lineup": [],
            "event_date": f"{release_date} 00:00:00" if release_date else None,
            "has_comments": True,
            "ticket_type": "digital",
            "type_properties": {
                "tagg": "music",
                "eventTime": {
                    "end": {"date": None, "time": None},
                    "start": {"date": release_date, "time": None},
                },
                "digitalType": ""
            },
            "tracks": tracks if is_album else [],
            "created_at": None,
            "updated_at": None,
            "additional_fields": additional_fields,
            "vorm": "album" if is_album else "track",
            "tagg": "music",
            "preview_url": None,
            "main_creator_id": None,
            "co_creator_name": None
        }
    ]

    return parsed_json


# -------------------------------------------------------------------
# 3) Insert user and digital releases into Supabase
# -------------------------------------------------------------------

def create_bandcamp_user_in_supabase_from_main(parsed_data):
    """
    Creates a new 'users' record from the main page's parsed_data
    (profile banner, profile pic, artist name, etc.).
    """
    # Some fields in the 'users' table:
    #  username (required)
    #  email (required)
    #  password_hash (required)
    #  profile_picture_url
    #  profile_banner_url
    #  description
    #  social_links (jsonb)
    #  display_name
    #  isvenue (bool) -> we can set to False for an artist
    #  location -> if you want to store the city
    # etc.

    # Build a unique, placeholder email:
    artist_name = parsed_data["artist_name"] or "Unknown_Artist"
    slug_email = artist_name.replace(" ", "_").lower()
    if " " in artist_name:
        artist_name= artist_name.replace(" ", "")
    user_payload = {
        "username": artist_name,  # or slug_email
        "display_name": artist_name,
        "email": f"{slug_email}@dummy-bandcamp.com",   # placeholder
        "password_hash": "hashed_dummy_password",
        "profile_picture_url": parsed_data["profile_picture_url"],
        "profile_banner_url": parsed_data["profile_banner_url"],
        "description": parsed_data["description"] or "",
        "social_links": parsed_data["social_links"] or [],
        "isvenue": False,  # assuming "venue" means physical
        # optionally store location if you have a place for it, e.g. in description
        # or add another field "location" if your schema allows
    }

    try:
        response = supabase.table("users").insert(user_payload).execute()
        if response.data:
            return response.data[0]["id"]  # The newly created user's UUID
        else:
            raise Exception("Failed to retrieve newly created user ID.")
    except Exception as e:
        print(f"Error creating Bandcamp user in Supabase: {e}")
        raise e


def upload_bandcamp_release_to_supabase(parsed_data, user_id):
    """
    Insert one Bandcamp album/track (parsed_data) into the 'tickets' table,
    referencing 'main_creator_id' = user_id.
    """
    
    
    # check the length of the long description
    
    if len(parsed_data.get("long_description")) > 500:
        long_description = parsed_data.get("long_description")[:500]
    else:
        long_description = parsed_data.get("long_description")
    
    
    ticket_payload = {
        "event_date": parsed_data.get("event_date"),
        "title": parsed_data.get("title"),
        "cover_image": parsed_data.get("cover_image"),
        "short_description": "",
        "long_description": long_description,
        "creators": parsed_data.get("creators"),  # store as jsonb
        "lineup": parsed_data.get("lineup"),      # store as jsonb
        "has_comments": parsed_data.get("has_comments", True),
        "ticket_type": parsed_data.get("ticket_type", "digital"),
        "type_properties": parsed_data.get("type_properties", {}),
        "vorm": parsed_data.get("vorm"),
        "tagg": parsed_data.get("tagg"),
        "additional_fields": parsed_data.get("additional_fields", []),
        "preview_url": parsed_data.get("preview_url"),
        "main_creator_id": user_id,  
        "co_creator_name": parsed_data.get("co_creator_name", None),
        "main_creator_name": parsed_data.get("creators") or None,
    }
    try:
        response = supabase.table("tickets").insert(ticket_payload).execute()
        if response.data:
            return {"ticket_id": response.data[0]["id"]}
        else:
            raise Exception("Failed to retrieve the newly created ticket ID.")
    except Exception as e:
        print(f"Error uploading Bandcamp release to Supabase: {e}")
        raise e


# -------------------------------------------------------------------
# 4) High-level workflow: parse main page, create user, parse each release
# -------------------------------------------------------------------

def import_bandcamp_artist_and_releases(bandcamp_base_url):
    """
    1) Parse the main '.../music' page to get the artist data and release URLs.
    2) Create the user in Supabase.
    3) For each release (album or track link), fetch & parse, 
       then upload as a digital 'ticket' to Supabase.
    """
    # 1) Parse main page
    main_html = fetch_bandcamp_main_page(bandcamp_base_url)
    if not main_html:
        print("No HTML content retrieved from the main page, aborting.")
        return

    parsed_main = parse_bandcamp_main_page(main_html)
    if not parsed_main["artist_name"]:
        print("Could not determine artist name from main page.")
    
    # 2) Create user in Supabase (the Bandcamp artist)
    user_id = create_bandcamp_user_in_supabase_from_main(parsed_main)
    print(f"New user created in Supabase for artist '{parsed_main['artist_name']}' => {user_id}")

    # 3) For each release, fetch & parse
    base_domain = bandcamp_base_url.split("/music")[0]  # e.g. "https://kourosh666.bandcamp.com"
    total_imported = 0

    for release in parsed_main["music_releases"]:
        # Construct a full URL from the relative
        # e.g. base_domain + "/album/shocked-ep"
        full_release_url = requests.compat.urljoin(base_domain, release["url"])
        print(f"\nFetching release: {full_release_url}")
        
        release_html = fetch_bandcamp_html(full_release_url)
        if not release_html:
            print("Could not retrieve HTML for this release, skipping.")
            continue
        
        # parse_bandcamp_html returns a list of items (1 item for track or album)
        release_items = parse_bandcamp_html(release_html)
        for item in release_items:
            # item is a dict with keys: title, cover_image, short_description, ...
            upload_bandcamp_release_to_supabase(item, user_id)
            total_imported += 1
    
    print(f"\nDone! Imported {total_imported} release(s) for artist '{parsed_main['artist_name']}'.")


# -------------------------------------------------------------------
# 5) Example usage
# -------------------------------------------------------------------

if __name__ == "__main__":
    # Example: "https://kourosh666.bandcamp.com/music"
    bandcamp_url = "https://auralconduct.bandcamp.com/music"
    import_bandcamp_artist_and_releases(bandcamp_url)
