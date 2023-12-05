
import wavelink


class Player(wavelink.Player):
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.autoplay = wavelink.AutoPlayMode.partial

        self._cog = None  # maybe useful for later
        self._should_send_play_now = True
        self._play_now_allowed = True
        self._trigger_channel_id = self.channel.id
        self._auto_play_queue = True

    @property
    def auto_play_queue(self) -> bool:
        return self._auto_play_queue
    
    @auto_play_queue.setter
    def auto_play_queue(self, value: bool):
        self._auto_play_queue = value

    @property
    def should_send_play_now(self) -> bool:
        return self._should_send_play_now
    
    @should_send_play_now.setter
    def should_send_play_now(self, value: bool):
        self._should_send_play_now = value

    @property
    def play_now_allowed(self) -> bool:
        return self._play_now_allowed
    
    @play_now_allowed.setter
    def play_now_allowed(self, value: bool):
        self._play_now_allowed = value

    @property
    def trigger_channel_id(self) -> int:
        return self._trigger_channel_id
    
    @trigger_channel_id.setter
    def trigger_channel_id(self, value: int):
        self._trigger_channel_id = value