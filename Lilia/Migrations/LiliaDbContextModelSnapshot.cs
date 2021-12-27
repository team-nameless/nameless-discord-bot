﻿// <auto-generated />
using Lilia.Database;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Infrastructure;
using Microsoft.EntityFrameworkCore.Storage.ValueConversion;

#nullable disable

namespace Lilia.Migrations
{
    [DbContext(typeof(LiliaDbContext))]
    partial class LiliaDbContextModelSnapshot : ModelSnapshot
    {
        protected override void BuildModel(ModelBuilder modelBuilder)
        {
#pragma warning disable 612, 618
            modelBuilder.HasAnnotation("ProductVersion", "6.0.1");

            modelBuilder.Entity("Lilia.Database.Models.DbGuild", b =>
                {
                    b.Property<ulong>("DbGuildId")
                        .ValueGeneratedOnAdd()
                        .HasColumnType("INTEGER");

                    b.Property<ulong>("GuildId")
                        .HasColumnType("INTEGER");

                    b.Property<int>("Ranking")
                        .HasColumnType("INTEGER");

                    b.HasKey("DbGuildId");

                    b.ToTable("Guilds");
                });

            modelBuilder.Entity("Lilia.Database.Models.DbUser", b =>
                {
                    b.Property<ulong>("DbUserId")
                        .ValueGeneratedOnAdd()
                        .HasColumnType("INTEGER");

                    b.Property<string>("OsuMode")
                        .HasColumnType("TEXT");

                    b.Property<string>("OsuUsername")
                        .HasColumnType("TEXT");

                    b.Property<ulong>("Shards")
                        .HasColumnType("INTEGER");

                    b.Property<ulong>("UserId")
                        .HasColumnType("INTEGER");

                    b.HasKey("DbUserId");

                    b.ToTable("Users");
                });
#pragma warning restore 612, 618
        }
    }
}
