# ruff: noqa: S607, PLC0415, S603

import base64
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from mutagen.flac import FLAC
from mutagen.flac import Picture as FLACPicture
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4
from mutagen.oggopus import OggOpus
from nameless.command.music_downloader.downloader.downloader import MusicDownloader
from nameless.command.music_downloader.downloader.tagger import (
    tag_flac,
    tag_mp3,
    tag_mp4,
    tag_opus,
)


def test_container_conversion_codec_selection():
    downloader = MusicDownloader()

    mock_provider = MagicMock()
    mock_provider.manifest = {"capabilities": {"requiresNativeContainerConversion": True}}

    def mock_get_provider(service_name: str):
        return mock_provider

    downloader.get_provider = mock_get_provider  # type: ignore

    track_meta = {
        "id": "test:123",
        "title": "Test Title",
        "artists": "Test Artist",
        "service": "test",
    }

    # test Case 1: Codec is FLAC
    mock_provider.download_track.return_value = {
        "success": True,
        "file_path": "dummy_path.m4a",
        "requires_container_conversion": True,
        "audio_codec": "flac",
    }

    with (
        patch("subprocess.run") as mock_run,
        patch("pathlib.Path.unlink") as mock_unlink,
        patch("nameless.command.music_downloader.downloader.downloader.embed_metadata") as mock_embed,
    ):
        downloader.download_track(track_meta, "test", "dummy_dir")

        assert mock_run.called
        cmd = mock_run.call_args[0][0]
        assert "-c:a" in cmd
        idx = cmd.index("-c:a")
        assert cmd[idx + 1] == "copy"

    # test Case 2: Codec is ALAC
    mock_provider.download_track.return_value = {
        "success": True,
        "file_path": "dummy_path.m4a",
        "requires_container_conversion": True,
        "audio_codec": "alac",
    }

    with (
        patch("subprocess.run") as mock_run,
        patch("pathlib.Path.unlink") as mock_unlink,  # noqa
        patch("nameless.command.music_downloader.downloader.downloader.embed_metadata") as mock_embed,  # noqa
    ):
        downloader.download_track(track_meta, "test", "dummy_dir")

        assert mock_run.called
        cmd = mock_run.call_args[0][0]
        assert "-c:a" in cmd
        idx = cmd.index("-c:a")
        assert cmd[idx + 1] == "flac"


def test_tagging_formats():
    metadata = {
        "title": "Song Title",
        "artists": "Song Artist",
        "album": "Song Album",
        "album_artist": "Album Artist",
        "track_number": 3,
        "total_tracks": 10,
        "disc_number": 1,
        "total_discs": 1,
        "release_date": "2023-01-01",
        "isrc": "US1234567890",
        "copyright": "Copyright 2023",
        "lyrics_lrc": "[00:00.00] Line 1\n[00:05.00] Line 2",
        "replaygain_track_gain": "-7.50 dB",
        "replaygain_track_peak": "0.990000",
        "replaygain_album_gain": "-8.20 dB",
        "replaygain_album_peak": "1.000000",
    }

    cover_bytes = b"fake_jpeg_cover_bytes"

    with tempfile.TemporaryDirectory() as tmpdir:
        # test FLAC tagging
        flac_path = Path(tmpdir) / "test.flac"
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-f",
                "lavfi",
                "-i",
                "anullsrc=r=44100:cl=stereo",
                "-t",
                "1",
                "-c:a",
                "flac",
                str(flac_path),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        tag_flac(str(flac_path), metadata, cover_bytes)

        audio_flac = FLAC(flac_path)
        assert audio_flac["title"] == ["Song Title"]
        assert audio_flac["artist"] == ["Song Artist"]
        assert audio_flac["album"] == ["Song Album"]
        assert audio_flac["albumartist"] == ["Album Artist"]
        assert audio_flac["tracknumber"] == ["3"]
        assert audio_flac["tracktotal"] == ["10"]
        assert audio_flac["discnumber"] == ["1"]
        assert audio_flac["disctotal"] == ["1"]
        assert audio_flac["date"] == ["2023-01-01"]
        assert audio_flac["isrc"] == ["US1234567890"]
        assert audio_flac["copyright"] == ["Copyright 2023"]
        assert audio_flac["lyrics"] == ["[00:00.00] Line 1\n[00:05.00] Line 2"]
        assert audio_flac["unsyncedlyrics"] == ["[00:00.00] Line 1\n[00:05.00] Line 2"]
        assert audio_flac["replaygain_track_gain"] == ["-7.50 dB"]
        assert audio_flac["replaygain_track_peak"] == ["0.990000"]
        assert audio_flac["replaygain_album_gain"] == ["-8.20 dB"]
        assert audio_flac["replaygain_album_peak"] == ["1.000000"]
        assert len(audio_flac.pictures) == 1
        assert audio_flac.pictures[0].data == cover_bytes

        # test MP4 tagging
        m4a_path = Path(tmpdir) / "test.m4a"
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-f",
                "lavfi",
                "-i",
                "anullsrc=r=44100:cl=stereo",
                "-t",
                "1",
                "-c:a",
                "alac",
                str(m4a_path),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        tag_mp4(str(m4a_path), metadata, cover_bytes)

        audio_mp4 = MP4(m4a_path)
        assert audio_mp4["\xa9nam"] == ["Song Title"]
        assert audio_mp4["\xa9ART"] == ["Song Artist"]
        assert audio_mp4["\xa9alb"] == ["Song Album"]
        assert audio_mp4["aART"] == ["Album Artist"]
        assert audio_mp4["\xa9day"] == ["2023-01-01"]
        assert audio_mp4["cprt"] == ["Copyright 2023"]
        assert audio_mp4["trkn"] == [(3, 10)]
        assert audio_mp4["disk"] == [(1, 1)]
        assert audio_mp4["----:com.apple.iTunes:ISRC"] == [b"US1234567890"]
        assert audio_mp4["\xa9lyr"] == ["[00:00.00] Line 1\n[00:05.00] Line 2"]
        assert audio_mp4["----:com.apple.iTunes:replaygain_track_gain"] == [b"-7.50 dB"]
        assert audio_mp4["----:com.apple.iTunes:replaygain_track_peak"] == [b"0.990000"]
        assert audio_mp4["----:com.apple.iTunes:replaygain_album_gain"] == [b"-8.20 dB"]
        assert audio_mp4["----:com.apple.iTunes:replaygain_album_peak"] == [b"1.000000"]
        assert len(audio_mp4["covr"]) == 1

        # test MP3 tagging
        mp3_path = Path(tmpdir) / "test.mp3"
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-f",
                "lavfi",
                "-i",
                "anullsrc=r=44100:cl=stereo",
                "-t",
                "1",
                "-c:a",
                "libmp3lame",
                str(mp3_path),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        tag_mp3(str(mp3_path), metadata, cover_bytes)

        audio_mp3 = MP3(mp3_path)
        assert audio_mp3["TIT2"].text == ["Song Title"]
        assert audio_mp3["TPE1"].text == ["Song Artist"]
        assert audio_mp3["TALB"].text == ["Song Album"]
        assert audio_mp3["TPE2"].text == ["Album Artist"]
        assert audio_mp3["TRCK"].text == ["3/10"]
        assert audio_mp3["TPOS"].text == ["1/1"]
        assert str(audio_mp3["TDRC"].text[0]) == "2023-01-01"
        assert audio_mp3["TCOP"].text == ["Copyright 2023"]

        # find USLT frame
        uslt_frames = [f for k, f in audio_mp3.items() if k.startswith("USLT")]
        assert len(uslt_frames) == 1
        assert uslt_frames[0].text == "[00:00.00] Line 1\n[00:05.00] Line 2"

        # check ReplayGain TXXX frames
        txxx_frames = {f.desc: f.text[0] for k, f in audio_mp3.items() if k.startswith("TXXX")}
        assert txxx_frames["replaygain_track_gain"] == "-7.50 dB"
        assert txxx_frames["replaygain_track_peak"] == "0.990000"
        assert txxx_frames["replaygain_album_gain"] == "-8.20 dB"
        assert txxx_frames["replaygain_album_peak"] == "1.000000"

        # check cover art
        apic_frames = [f for k, f in audio_mp3.items() if k.startswith("APIC")]
        assert len(apic_frames) == 1
        assert apic_frames[0].data == cover_bytes

        # test Opus tagging
        opus_path = Path(tmpdir) / "test.opus"
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-f",
                "lavfi",
                "-i",
                "anullsrc=r=48000:cl=stereo",
                "-t",
                "1",
                "-c:a",
                "libopus",
                str(opus_path),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        tag_opus(str(opus_path), metadata, cover_bytes)

        audio_opus = OggOpus(opus_path)
        assert audio_opus["title"] == ["Song Title"]
        assert audio_opus["artist"] == ["Song Artist"]
        assert audio_opus["album"] == ["Song Album"]
        assert audio_opus["albumartist"] == ["Album Artist"]
        assert audio_opus["tracknumber"] == ["3"]
        assert audio_opus["tracktotal"] == ["10"]
        assert audio_opus["discnumber"] == ["1"]
        assert audio_opus["disctotal"] == ["1"]
        assert audio_opus["date"] == ["2023-01-01"]
        assert audio_opus["isrc"] == ["US1234567890"]
        assert audio_opus["copyright"] == ["Copyright 2023"]
        assert audio_opus["lyrics"] == ["[00:00.00] Line 1\n[00:05.00] Line 2"]
        assert audio_opus["unsyncedlyrics"] == ["[00:00.00] Line 1\n[00:05.00] Line 2"]
        assert audio_opus["replaygain_track_gain"] == ["-7.50 dB"]
        assert audio_opus["replaygain_track_peak"] == ["0.990000"]
        assert audio_opus["replaygain_album_gain"] == ["-8.20 dB"]
        assert audio_opus["replaygain_album_peak"] == ["1.000000"]

        # parse base64 picture
        assert "metadata_block_picture" in audio_opus
        p_b64 = audio_opus["metadata_block_picture"][0]
        p_data = base64.b64decode(p_b64.encode("ascii"))
        pic = FLACPicture(p_data)
        assert pic.data == cover_bytes
        assert pic.mime == "image/jpeg"


def test_uploader_registry_resolution():
    from unittest.mock import MagicMock

    from nameless.command.music_downloader.uploader import UPLOADER_REGISTRY
    from nameless.command.music_downloader.uploader.catbox.catbox import CatboxUploader
    from nameless.command.music_downloader.uploader.catbox.litterbox import LitterboxUploader
    from nameless.command.music_downloader.uploader.pomf.pomf import PomfUploader
    from nameless.command.music_downloader.uploader.telegram.telegram import TelegramUploader

    mock_session = MagicMock()
    mock_client = MagicMock()

    catbox = UPLOADER_REGISTRY["catbox"](session=mock_session)
    assert isinstance(catbox, CatboxUploader)

    litterbox = UPLOADER_REGISTRY["litterbox"](session=mock_session)
    assert isinstance(litterbox, LitterboxUploader)

    uguu = UPLOADER_REGISTRY["uguu"](session=mock_session)
    assert isinstance(uguu, PomfUploader)
    assert uguu.config.url == "https://uguu.se/"

    rokket = UPLOADER_REGISTRY["rokket"](session=mock_session)
    assert isinstance(rokket, PomfUploader)
    assert rokket.config.url == "https://rokket.space/"

    telegram = UPLOADER_REGISTRY["telegram"](tg_client=mock_client, chat_id=123456)
    assert isinstance(telegram, TelegramUploader)


def test_resolve_collection_flags():
    from nameless.command.music_downloader.helpers import resolve_collection_flags

    is_album, is_playlist = resolve_collection_flags({"type": "album"})
    assert is_album is True
    assert is_playlist is False

    is_album, is_playlist = resolve_collection_flags({"type": "playlist"})
    assert is_album is False
    assert is_playlist is True

    is_album, is_playlist = resolve_collection_flags({"type": "artist"})
    assert is_album is False
    assert is_playlist is True


@pytest.mark.anyio
async def test_package_downloaded_files_no_zip():
    import tempfile
    from unittest.mock import MagicMock

    from nameless.command.music_downloader.helpers import package_downloaded_files

    mock_ctx = MagicMock()
    mock_ctx.author.id = 123456

    mock_controller = MagicMock()

    with tempfile.TemporaryDirectory() as tmpdir:
        output_dir = Path(tmpdir)
        file1 = output_dir / "track1.flac"
        file2 = output_dir / "track2.flac"
        file1.write_bytes(b"data1")
        file2.write_bytes(b"data2")

        files, is_zip = await package_downloaded_files(output_dir, mock_ctx, mock_controller, zip_if_multiple=False)
        assert is_zip is False
        assert len(files) == 2
        assert files[0].name == "track1.flac"
        assert files[1].name == "track2.flac"


def test_build_upload_progress_line_multi_links():
    from nameless.command.music_downloader import Status
    from nameless.command.music_downloader.enums import StatusState

    status = Status()
    status._provider = "telegram"
    status._uploading_state = StatusState.COMPLETED

    status._download_url = "https://t.me/c/1234/5678"
    line = status.build_upload_progress_line()
    assert line == "Download link (Telegram): [Click here to download](https://t.me/c/1234/5678)"

    status._download_url = "https://t.me/c/1234/5678\nhttps://t.me/c/1234/5679"
    line = status.build_upload_progress_line()
    assert line == "Download links (Telegram): [Link 1](https://t.me/c/1234/5678), [Link 2](https://t.me/c/1234/5679)"
