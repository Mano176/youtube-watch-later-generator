import os
from datetime import datetime
from dateutil import tz
import google_auth_oauthlib.flow
import googleapiclient.discovery
import googleapiclient.errors

scopes = ["https://www.googleapis.com/auth/youtube.readonly", "https://www.googleapis.com/auth/youtube.force-ssl"]

def main():
    year = 2023
    month = 8
    day = 30
    watch_later_id = "PLZYWg5AqfaidFawvfzcLXUAbVREhgHJCD"

    with open("channel_blacklist.txt", "r") as f:
        blacklisted_channels = [channel.strip() for channel in f.readlines()]
    with open("title_blacklist.txt", "r") as f:
        blacklisted_titles = [title.strip().lower() for title in f.readlines() if not title.startswith("//")]

    # Disable OAuthlib's HTTPS verification when running locally.
    # *DO NOT* leave this option enabled in production.
    os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"


    # Get credentials and create an API client
    flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file("client_secret.json", scopes)
    credentials = flow.run_local_server()
    api = googleapiclient.discovery.build("youtube", "v3", credentials=credentials)

    channel_ids = getSubscribedChannels(api, blacklisted_channels)
    print(f"Found {len(channel_ids)} channels")
    upload_playlist_ids = getUploadPlaylistIds(api, channel_ids)
    print(f"Found {len(upload_playlist_ids)} upload playlists")
    video_ids = getVideoIds(api, upload_playlist_ids, year, month, day, blacklisted_titles)
    print(f"Found {len(video_ids)} videos")
    addVideosToPlaylist(api, video_ids, watch_later_id)


def getSubscribedChannels(api, blacklisted_channels):
    channel_ids = []
    has_next_page = True
    page_token = None

    while has_next_page:
        request = api.subscriptions().list(
            pageToken=page_token,
            part="snippet",
            maxResults=50,
            mine=True
        )
        response = request.execute()
        if "nextPageToken" in response:
            page_token = response["nextPageToken"]
        else:
            has_next_page = False
        for item in response["items"]:
            if item["snippet"]["title"] in blacklisted_channels:
                continue
            channel_ids.append(item["snippet"]["resourceId"]["channelId"])
    return channel_ids


def getUploadPlaylistIds(api, channel_ids):
    upload_playlist_ids = []
    has_next_page = True
    page_token = None
    while has_next_page:
        request = api.channels().list(
            pageToken=page_token,
            part="contentDetails",
            id=",".join(channel_ids),
            maxResults=50,
        )
        response = request.execute()
        if "nextPageToken" in response:
            page_token = response["nextPageToken"]
        else:
            has_next_page = False
        for item in response["items"]:
            upload_playlist_ids.append(item["contentDetails"]["relatedPlaylists"]["uploads"])
    return upload_playlist_ids


def getVideoIds(api, upload_playlist_ids, year, month, day, blacklisted_titles):
    local_date = f"{str(year).zfill(2)}-{str(month).zfill(2)}-{str(day).zfill(2)}T00:00:00"
    local_date = datetime.strptime(local_date, '%Y-%m-%dT%H:%M:%S').replace(tzinfo=tz.tzlocal())
    utc = tz.gettz("UTC")
    video_ids = []
    for playlist_id in upload_playlist_ids:
        has_next_page = True
        page_token = None
        while has_next_page:
            request = api.playlistItems().list(
                pageToken=page_token,
                part="snippet",
                playlistId=playlist_id,
                maxResults=50,
            )
            response = request.execute()
            if "nextPageToken" in response:
                page_token = response["nextPageToken"]
            else:
                has_next_page = False
            for item in response["items"]:
                published_at = item["snippet"]["publishedAt"][:-1]
                api_date = datetime.strptime(published_at, '%Y-%m-%dT%H:%M:%S').replace(tzinfo=utc)
                if local_date > api_date:
                    has_next_page = False
                    break
                is_blacklisted = False
                for blacklisted_title in blacklisted_titles:
                    if blacklisted_title in item["snippet"]["title"].lower():
                        is_blacklisted = True
                        break
                if is_blacklisted:
                    continue
                video_ids.append((item["snippet"]["resourceId"]["videoId"], published_at))
    video_ids.sort(key=lambda x: x[1])
    video_ids = [x[0] for x in video_ids]
    return video_ids


def addVideosToPlaylist(api, video_ids, playlist_id):
    for video_id in video_ids:
        print(f"adding {video_id} to playlist")
        request = api.playlistItems().insert(
            part="snippet",
            body={
                "snippet": {
                    "playlistId": playlist_id,
                    "resourceId": {
                    "kind": "youtube#video",
                    "videoId": video_id
                    }
                }
            }
        )
        request.execute()


if __name__ == "__main__":
    main()