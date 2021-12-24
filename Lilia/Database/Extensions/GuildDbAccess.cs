﻿using System.Linq;
using Lilia.Database.Models;
using Microsoft.EntityFrameworkCore;

namespace Lilia.Database.Extensions
{
    public static class GuildDbAccess
    {
        public static DbGuild GetOrCreateGuildRecord(this LiliaDbContext ctx, ulong guildId)
        {
            DbSet<DbGuild> guilds = ctx.Guilds;
            DbGuild guild = guilds.FirstOrDefault(entity => entity.GuildId == guildId);

            if (guild == default(DbGuild))
            {
                guild = new DbGuild
                {
                    GuildId = guildId,
                    Ranking = 1
                };

                guilds.Add(guild);
            }

            ctx.SaveChanges();
            return guild;
        }
    }
}