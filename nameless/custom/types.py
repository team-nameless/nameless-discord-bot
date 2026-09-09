import discord

__all__ = ["NamelessTextable"]

NamelessTextable = discord.TextChannel | discord.Thread | discord.VoiceChannel
"""Channels that retrieving & sending data without quirks."""
