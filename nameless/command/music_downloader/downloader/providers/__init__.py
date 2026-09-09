from .amazon import AmazonWebProvider
from .apple_music import AppleMusicWebProvider
from .deezer import DeezerWebProvider
from .qobuz_web import QobuzWebProvider
from .soundcloud import SoundcloudWebProvider
from .spotify_web import SpotifyWebProvider
from .tidal_web import TidalWebProvider
from .ytmusic import YoutubeMusicWebProvider

PROVIDER_CLASSES = {
    "tidal": TidalWebProvider,
    "qobuz": QobuzWebProvider,
    "amazon": AmazonWebProvider,
    "deezer": DeezerWebProvider,
    "apple": AppleMusicWebProvider,
    "soundcloud": SoundcloudWebProvider,
    "spoti": SpotifyWebProvider,
    "youtube": YoutubeMusicWebProvider,
}
