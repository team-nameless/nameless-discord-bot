from __future__ import annotations

import datetime
import logging
from typing import TYPE_CHECKING

import discord
import pomice
from discord.utils import escape_markdown

if TYPE_CHECKING:
    from nameless.command.music.player import CustomPlayer


def resolve_artist_name(name: str) -> str:
    if not name:
        return "N/A"
    name = escape_markdown(name, as_needed=True)
    return name.removesuffix(" - Topic")


@staticmethod
def format_duration(ms: float) -> str:
    if ms <= 0:
        return "00:00"

    seconds = ms // 1000
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)

    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"


def create_progress_bar(current: float, total: int, size: int = 18) -> str:
    if total <= 0:
        return "─" * size

    percentage = min(max(current / total, 0), 1)
    progress = int(size * percentage)
    progress = min(progress, size - 1)

    bar = "━" * progress + "🔘" + "─" * (size - progress - 1)
    return bar


def create_now_playing_embed(
    player: CustomPlayer,
    track: pomice.Track,
    user: discord.User | discord.Member | discord.ClientUser,
) -> discord.Embed:
    def get_status_icon() -> str:
        if player.is_paused:
            return "⏸️"
        return "▶️"

    status_text = "Autoplay" if player.is_current_track_autoplay else "Now Playing"

    current_pos = player.position
    total_duration = track.length
    progress_bar = create_progress_bar(current_pos, total_duration)
    current_pos_format = format_duration(current_pos)
    total_duration_format = format_duration(total_duration)
    logging.debug(f"{current_pos=}, {total_duration=}, {current_pos_format=}, {total_duration_format=}")

    embed = (
        discord.Embed(
            title=escape_markdown(track.title or "Unknown"),
            url=track.uri or None,
            color=discord.Color.orange(),
            timestamp=datetime.datetime.now(datetime.UTC),
        )
        .set_author(name=f"{get_status_icon()} {status_text}", icon_url=user.display_avatar.url)
        .set_thumbnail(url=track.thumbnail)
    )

    description = f"by **{resolve_artist_name(track.author)}**\n\n"
    description += f"`{current_pos_format}` {progress_bar} `{total_duration_format}`\n\n"

    loop_mode = "Off"
    if player.queue.loop_mode == pomice.LoopMode.TRACK:
        loop_mode = "🔂 Track"
    elif player.queue.loop_mode == pomice.LoopMode.QUEUE:
        loop_mode = "🔁 Queue"

    autoplay = "✅" if player.is_autoplay_enabled else "❌"

    status_line = f"🔊 **{player.volume}%** | 🔄 **{loop_mode}** | 📻 **Autoplay:** {autoplay}"
    description += status_line

    embed.description = description

    queue_len = len(player.queue)
    if queue_len > 0:
        next_track = player.queue[0]
        embed.add_field(
            name="⏭️ Up Next",
            value="{escape_markdown}[{title}]({uri})".format(
                escape_markdown=escape_markdown(next_track.title or "Unknown"),
                title=next_track.title or "Unknown",
                uri=next_track.uri or "N/A",
            ),
            inline=False,
        )
        embed.set_footer(text=f"{queue_len} track{'s' if queue_len > 1 else ''} remaining in queue")
    elif player.auto_queue or player.is_current_track_autoplay:
        embed.set_footer(
            text="Autoplay's playlist ({queue_len} remaining track{plural})".format(
                queue_len=len(player.auto_queue),
                plural="s" if len(player.auto_queue) != 1 else "",
            )
        )
    else:
        embed.set_footer(text="End of queue")

    return embed


def create_queue_embed(
    tracks: list[pomice.Track],
    page: int,
    total_pages: int,
    total_duration: int = 0,
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
        duration = format_duration(track.length)
        track_list.append(
            "`{index}.` **[{title}]({uri})**\n      by {artist} • {duration}".format(
                index=i + (page - 1) * 10,
                title=(track.title or "Unknown"),
                uri=track.uri or "N/A",
                artist=resolve_artist_name(track.author),
                duration=duration,
            )
        )
    embed.description = "\n\n".join(track_list)

    footer_text = f"Page {page}/{total_pages}"
    if total_duration > 0:
        footer_text += f" • Total Duration: {format_duration(total_duration)}"
    embed.set_footer(text=footer_text)

    return embed


def create_added_embed(tracks: list[pomice.Track], count: int) -> discord.Embed:
    if count == 1 and tracks:
        track = tracks[0]
        embed = discord.Embed(
            title="✅ Track Added",
            description=(
                "**[{title}]({uri})**\nby {artist}".format(
                    title=(track.title or "Unknown"),
                    uri=track.uri or "N/A",
                    artist=resolve_artist_name(track.author),
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


def create_error_embed(title: str, description: str) -> discord.Embed:
    return discord.Embed(
        title=f"❌ {title}",
        description=description,
        color=discord.Color.red(),
    )


def create_error_embed_from_exception(title: str, exception: Exception, print_stack: bool = False) -> discord.Embed:
    if print_stack:
        logging.error("An error occurred", exc_info=exception)
    return create_error_embed(title, str(exception))


def create_success_embed(title: str, description: str) -> discord.Embed:
    return discord.Embed(
        title=f"✅ {title}",
        description=description,
        color=discord.Color.green(),
    )


def create_info_embed(title: str, description: str) -> discord.Embed:
    return discord.Embed(
        title=f"ℹ️ {title}",
        description=description,
        color=discord.Color.blue(),
    )


def create_playlist_embed(playlist: pomice.Playlist) -> discord.Embed:
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
            value=format_duration(total_duration),
            inline=True,
        )

    return embed


def create_eq_preview_embed(player: CustomPlayer) -> discord.Embed:
    embed = discord.Embed(title="Equalizer Settings", color=discord.Color.blue())

    bands = [player.eq_bands.get(i, 0.0) for i in range(15)]
    chart = _generate_eq_chart(bands)
    embed.description = f"```\n{chart}\n```"

    if player.eq_bands:
        modified = ", ".join(f"Band {b}: {g:+.2f}" for b, g in sorted(player.eq_bands.items()))
        embed.add_field(name="Modified Bands", value=modified, inline=False)
    else:
        embed.add_field(name="Status", value="Flat (no adjustments)", inline=False)

    return embed


def _generate_eq_chart(bands: list[float]) -> str:
    blocks = " ▁▂▃▄▅▆▇█"

    lines: list[str] = []
    for gain in bands:
        normalized = int(((gain + 0.25) / 1.25) * 8)
        normalized = max(0, min(8, normalized))
        bar = blocks[normalized]
        lines.append(f"{bar} {gain:+.2f}")

    chart = ""
    for i, line in enumerate(lines):
        chart += f"Band {i:2d}: {line}\n"

    return chart
