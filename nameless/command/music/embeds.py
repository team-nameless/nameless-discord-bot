import datetime
from typing import TYPE_CHECKING

import discord
import pomice
from discord.utils import escape_markdown

if TYPE_CHECKING:
    from nameless.command.music.player import CustomPlayer


class EmbedGenerator:
    @staticmethod
    def resolve_artist_name(name: str) -> str:
        if not name:
            return "N/A"
        name = escape_markdown(name, as_needed=True)
        return name.removesuffix(" - Topic")

    @staticmethod
    def format_duration(ms: int) -> str:
        if ms == 0:
            return "Live Stream"

        seconds = ms // 1000
        minutes, seconds = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)

        if hours:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        return f"{minutes}:{seconds:02d}"

    def create_now_playing_embed(
        self,
        player: "CustomPlayer",
        track: pomice.Track,
        user: discord.User | discord.Member | discord.ClientUser,
    ) -> discord.Embed:
        def get_status_icon() -> str:
            icon = "⏸️" if player.is_paused else "▶️"
            if player.queue.loop_mode == pomice.LoopMode.TRACK:
                icon += "🔂"
            elif player.queue.loop_mode == pomice.LoopMode.QUEUE:
                icon += "🔁"
            return icon

        status_text = "Autoplaying" if track.isrc else "Now playing"
        track_type = "stream" if track.is_stream else "track"

        embed = (
            discord.Embed(
                timestamp=datetime.datetime.now(datetime.UTC),
                color=discord.Color.orange(),
            )
            .set_author(
                name=f"{get_status_icon()} {status_text} {track_type}",
                icon_url=user.display_avatar.url,
            )
            .add_field(
                name="🎵 Title",
                value=escape_markdown(track.title or "Unknown"),
                inline=True,
            )
            .add_field(
                name="👤 Artist",
                value=self.resolve_artist_name(track.author),
                inline=True,
            )
            .add_field(
                name="⏱️ Duration",
                value=self.format_duration(track.length),
                inline=True,
            )
            .add_field(
                name="🔗 Source",
                value=f"[{track.track_type.value.title()}]({track.uri})" if track.uri else "N/A",
                inline=False,
            )
            .set_thumbnail(url=track.thumbnail or "")
        )

        if player.queue.loop_mode != pomice.LoopMode.TRACK and not track.is_stream and player.queue:
            next_track = player.queue[0]
            embed.add_field(
                name="⏭️ Next Track",
                value=(
                    f"[{escape_markdown(next_track.title) if next_track.title else 'Unknown'} "
                    f"by {self.resolve_artist_name(next_track.author)}]({next_track.uri or 'N/A'})"
                ),
                inline=False,
            )

        return embed

    def create_queue_embed(
        self,
        tracks: list[pomice.Track],
        page: int,
        total_pages: int,
        title: str = "🎵 Queue",
    ) -> discord.Embed:
        embed = discord.Embed(
            title=title,
            color=discord.Color.blue(),
            timestamp=datetime.datetime.now(datetime.UTC),
        )

        if not tracks:
            embed.description = "No tracks in this section"
            return embed

        track_list: list[str] = []
        for i, track in enumerate(tracks, start=1):
            duration = self.format_duration(track.length)
            track_list.append(
                "`{index}.` **[{title}]({uri})**\n      by {artist} • {duration}".format(
                    index=i,
                    title=escape_markdown(track.title or "Unknown"),
                    uri=track.uri or "N/A",
                    artist=self.resolve_artist_name(track.author),
                    duration=duration,
                )
            )
        embed.description = "\n\n".join(track_list)
        embed.set_footer(text=f"Page {page}/{total_pages}")

        return embed

    def create_added_embed(self, tracks: list[pomice.Track], count: int) -> discord.Embed:
        if count == 1 and tracks:
            track = tracks[0]
            embed = discord.Embed(
                title="✅ Track Added",
                description=(
                    "**[{title}]({uri})**\nby {artist}".format(
                        title=escape_markdown(track.title or "Unknown"),
                        uri=track.uri or "N/A",
                        artist=self.resolve_artist_name(track.author),
                    )
                ),
                color=discord.Color.green(),
            )
            embed.set_thumbnail(url=track.thumbnail or "")
        else:
            embed = discord.Embed(
                title="✅ Tracks Added",
                description=f"Added **{count}** track{'s' if count != 1 else ''} to the queue",
                color=discord.Color.green(),
            )

        return embed

    def create_error_embed(self, title: str, description: str) -> discord.Embed:
        return discord.Embed(
            title=f"❌ {title}",
            description=description,
            color=discord.Color.red(),
        )

    def create_success_embed(self, title: str, description: str) -> discord.Embed:
        return discord.Embed(
            title=f"✅ {title}",
            description=description,
            color=discord.Color.green(),
        )

    def create_info_embed(self, title: str, description: str) -> discord.Embed:
        return discord.Embed(
            title=f"ℹ️ {title}",
            description=description,
            color=discord.Color.blue(),
        )

    def create_playlist_embed(self, playlist: pomice.Playlist) -> discord.Embed:
        embed = discord.Embed(
            title="📋 Playlist Added",
            description=f"**{playlist.name}**",
            color=discord.Color.green(),
        )

        embed.add_field(
            name="📊 Track Count",
            value=str(len(playlist.tracks)),
            inline=True,
        )

        if playlist.tracks:
            total_duration = sum(track.length for track in playlist.tracks if track.length)
            embed.add_field(
                name="⏱️ Total Duration",
                value=self.format_duration(total_duration),
                inline=True,
            )

        return embed
