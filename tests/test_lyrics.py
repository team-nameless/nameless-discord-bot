from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from nameless.command.music_downloader.lyrics import get_lyrics
from nameless.command.music_downloader.lyrics.lrclib import LrcLibLyrics
from nameless.command.music_downloader.lyrics.musixmatch import MusixMatchLyrics
from nameless.command.music_downloader.lyrics.shazam import ShazamLyrics


def test_lrclib_lyrics():
    session_mock = MagicMock()
    response_mock = MagicMock()
    response_mock.json.return_value = [
        {
            "track_name": "Title",
            "artist_name": "Artist",
            "syncedLyrics": "[00:10.00] Synced Lyrics\n[00:15.00] Line 2",
            "plainLyrics": "Plain Lyrics\nLine 2",
        }
    ]
    session_mock.get.return_value = response_mock

    lyrics = LrcLibLyrics("Title", "Artist", session=session_mock)
    assert lyrics.get_synced() == "[00:10.00] Synced Lyrics\n[00:15.00] Line 2"
    assert lyrics.get_unsynced() == "Plain Lyrics\nLine 2"


def test_musixmatch_lyrics():
    session_mock = MagicMock()

    # first request gets token
    token_response = MagicMock()
    token_response.json.return_value = {
        "message": {
            "header": {"status_code": 200},
            "body": {"user_token": "fake_token"},
        }
    }

    # second request gets subtitles/lyrics macro call
    macro_response = MagicMock()
    macro_response.json.return_value = {
        "message": {
            "header": {"status_code": 200},
            "body": {
                "macro_calls": {
                    "matcher.track.get": {"message": {"header": {"status_code": 200}}},
                    "track.lyrics.get": {
                        "message": {
                            "header": {"status_code": 200},
                            "body": {
                                "lyrics": {
                                    "lyrics_body": "MusixMatch Unsynced Lyrics\nLine 2",
                                    "restricted": False,
                                }
                            },
                        }
                    },
                    "track.subtitles.get": {
                        "message": {
                            "header": {"status_code": 200},
                            "body": {
                                "subtitle_list": [
                                    {
                                        "subtitle": {
                                            "subtitle_body": json.dumps(
                                                [
                                                    {
                                                        "time": {"minutes": 0, "seconds": 10, "hundredths": 0},
                                                        "text": "MusixMatch Synced Lyrics",
                                                    },
                                                    {
                                                        "time": {"minutes": 0, "seconds": 15, "hundredths": 0},
                                                        "text": "Line 2",
                                                    },
                                                ]
                                            )
                                        }
                                    }
                                ]
                            },
                        }
                    },
                }
            },
        }
    }

    session_mock.get.side_effect = [token_response, macro_response, macro_response]

    # reset class token to ensure it calls token endpoint
    MusixMatchLyrics.token = None

    lyrics = MusixMatchLyrics("Title", "Artist", session=session_mock)
    assert lyrics.get_synced() == "[00:10.00]MusixMatch Synced Lyrics\n[00:15.00]Line 2"
    assert lyrics.get_unsynced() == "MusixMatch Unsynced Lyrics\nLine 2"


def test_shazam_lyrics():
    session_mock = MagicMock()

    # 1st response (search GB): succeeds
    search_gb = MagicMock()
    search_gb.json.return_value = {
        "results": {
            "songs": {
                "data": [
                    {"id": "12345", "attributes": {"name": "Title", "hasLyrics": True, "hasTimeSyncedLyrics": True}}
                ]
            }
        }
    }

    # 2nd response (search JP): empty to trigger ValueError and continue
    search_jp = MagicMock()
    search_jp.json.return_value = {}

    # 3rd response (canonical page check): redirect matching canonical url regex
    redirect_response = MagicMock()
    redirect_response.text = '<link rel="canonical" href="https://www.shazam.com/song/canonical-url">'

    # 4th response (song page content): contains ld+json and synced lyrics pattern
    page_response = MagicMock()
    page_response.text = (
        '<script type="application/ld+json">\n'
        '{"recordingOf": {"lyrics": {"text": "Shazam Unsynced Lyrics\\nLine 2"}}}\n'
        "</script>\n"
        'self.__next_f.push([1,"5:[{\\"lyricLines\\":[{\\"startTimeInSeconds\\":\\"10.0\\",\\"content\\":\\"Synced Shazam Lyric Line\\"}]}]"])\n'
    )

    session_mock.get.side_effect = [search_gb, search_jp, redirect_response, page_response]

    lyrics = ShazamLyrics("Title", "Artist", session=session_mock)
    assert lyrics.get_synced() == "[00:10.00] Synced Shazam Lyric Line"
    assert lyrics.get_unsynced() == "Shazam Unsynced Lyrics\nLine 2"


def test_get_lyrics_fallback():
    mock_shazam = MagicMock()
    mock_shazam_inst = mock_shazam.return_value
    mock_shazam_inst.get_synced.return_value = None
    mock_shazam_inst.get_unsynced.return_value = None

    mock_musixmatch = MagicMock()
    mock_musixmatch_inst = mock_musixmatch.return_value
    mock_musixmatch_inst.get_synced.return_value = "MusixMatch Synced"

    mock_classes = {
        "shazam": mock_shazam,
        "musixmatch": mock_musixmatch,
    }

    with patch.dict("nameless.command.music_downloader.lyrics.PROVIDER_CLASSES", mock_classes, clear=True):
        res = get_lyrics("Title", "Artist")
        assert res == "MusixMatch Synced"
