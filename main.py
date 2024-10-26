import datetime
import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
from pymongo import MongoClient

client = MongoClient("localhost", 27017)
db = client["honeypot-testing"]
user_collection = db["blacklisted-users"]
channel_collection = db["honeypot_channels"]
log_channel_collection = db["log_channels"]

channel_cache = {}
log_channel_cache = {}

load_dotenv()
TOKEN = os.getenv("TOKEN")

if not TOKEN:
    print("bitch ahh where token")
    exit(1)

activity = discord.Game("h!help")

bot = commands.Bot(command_prefix="h!", intents=discord.Intents.all(), activity=activity)


@bot.event
async def on_ready() -> None:
    print("READY")

    for channel_data in channel_collection.find():
        guild_id = channel_data["guild_id"]
        if bot.get_guild(guild_id) is not None:
            channel_cache[guild_id] = channel_data["channel_id"]
        else:
            channel_collection.delete_one({"guild_id": guild_id})
            print(f"removed guild {guild_id} from database (no longer in server)")

    for log_data in log_channel_collection.find():
        guild_id = log_data["guild_id"]
        if bot.get_guild(guild_id) is not None:
            log_channel_cache[guild_id] = log_data["channel_id"]
        else:
            log_channel_collection.delete_one({"guild_id": guild_id})
            print(f"removed log channel for guild {guild_id} from database")

    print(f"loaded channels into cache: {channel_cache}")
    print(f"loaded log channels into cache: {log_channel_cache}")


class MyHelp(commands.HelpCommand):
    async def send_bot_help(self, mapping):
        channel = self.get_destination()
        await channel.send(
            "run `h!set.channel` to set the channel for the bot to listen for messages in\nrun `h!set.logs` to set the channel for the bot to log stuff\nrun`h!disable` to disable the bot, and to remove your server from my database"
        )


bot.help_command = MyHelp()


@bot.event
async def on_message(message: discord.Message) -> None:
    if not message.guild:
        return

    guild_id = message.guild.id
    if guild_id in channel_cache:
        if message.channel.id == channel_cache[guild_id]:
            await message.delete()
            if message.author.bot:
                await bot.process_commands(message)
                return
            if user_collection.find_one({"user_id": message.author.id}):
                print(f"{message.author.id} already in db")
            else:
                user_data = {"user_id": message.author.id}
                user_collection.insert_one(user_data)
                print(f"user {message.author.id} saved to db")

            if guild_id in log_channel_cache:
                log_channel = bot.get_channel(log_channel_cache[guild_id])
                if log_channel:
                    if log_channel.permissions_for(log_channel.guild.me).send_messages:
                        embed = discord.Embed(
                            title="Someone reached into the honeypot",
                            description=f"A user was caught sending a message in the honeypot channel `({log_channel.id})`\n```{message.content}\n```",
                            colour=0xE8B551,
                        )

                        embed.set_author(
                            name="Honeypot",
                            icon_url="https://cdn.discordapp.com/avatars/1299044225538592768/2f84ce1bf85e3cdfe2d31f3293e41272?size=1024",
                        )
                        embed.set_footer(text="Honeypot Log")
                        await log_channel.send(embed=embed)

            if message.guild.me.guild_permissions.ban_members:
                await message.author.ban()
            else:
                print(f"Bot lacks permission to ban users in guild {guild_id}")
                if guild_id in log_channel_cache:
                    log_channel = bot.get_channel(log_channel_cache[guild_id])
                    if log_channel:
                        await log_channel.send(
                            "bot lacks permission to ban users, please make sure it has the `Ban Members` permission"
                        )

    await bot.process_commands(message)


async def check_admin(ctx: commands.Context):
    if not ctx.author.guild_permissions.administrator:
        await ctx.author.send("you need admin permissions to run this command")
        return False
    return True


@bot.command(name="set.channel")
async def setchannel(ctx: commands.Context) -> None:
    if not await check_admin(ctx):
        return

    if not ctx.guild or not isinstance(ctx.channel, discord.TextChannel):
        return

    guild_id = ctx.guild.id
    channel_id = ctx.channel.id

    if guild_id in channel_cache:
        old_channel = channel_cache[guild_id]
        if old_channel != channel_id:
            channel_collection.update_one(
                {"guild_id": guild_id}, {"$set": {"channel_id": channel_id}}
            )
        else:
            await ctx.author.send(
                f"the channel <#{channel_id}> is already set as the honeypot channel"
            )
            return
    else:
        channel_collection.insert_one({"guild_id": guild_id, "channel_id": channel_id})

    channel_cache[guild_id] = channel_id
    await ctx.channel.purge(limit=5)
    await ctx.author.send(
        f"the channel <#{channel_id}> was set as the honeypot channel"
    )


@bot.command(name="set.logs")
async def setlogs(ctx: commands.Context) -> None:
    if not await check_admin(ctx):
        return

    if not ctx.guild or not isinstance(ctx.channel, discord.TextChannel):
        return

    guild_id = ctx.guild.id
    log_channel_id = ctx.channel.id

    if guild_id in log_channel_cache:
        old_log_channel = log_channel_cache[guild_id]
        if old_log_channel != log_channel_id:
            log_channel_collection.update_one(
                {"guild_id": guild_id}, {"$set": {"channel_id": log_channel_id}}
            )
        else:
            await ctx.author.send(
                f"the channel <#{log_channel_id}> is already set as the log channel"
            )
            return
    else:
        log_channel_collection.insert_one(
            {"guild_id": guild_id, "channel_id": log_channel_id}
        )

    log_channel_cache[guild_id] = log_channel_id
    await ctx.author.send(f"the channel <#{log_channel_id}> was set as the log channel")


@bot.command(name="disable")
async def disable(ctx: commands.Context) -> None:
    if not await check_admin(ctx):
        return

    if not ctx.guild:
        return

    guild_id = ctx.guild.id

    if guild_id in channel_cache:
        del channel_cache[guild_id]
        channel_collection.delete_one({"guild_id": guild_id})
        await ctx.author.send("your server has been removed from the database")
    else:
        await ctx.author.send("no honeypot channel is set for this server")


@bot.event
async def on_guild_channel_delete(channel: discord.TextChannel) -> None:
    guild_id = channel.guild.id
    if guild_id in channel_cache and channel_cache[guild_id] == channel.id:
        del channel_cache[guild_id]
        channel_collection.delete_one({"guild_id": guild_id})
    if guild_id in log_channel_cache and log_channel_cache[guild_id] == channel.id:
        del log_channel_cache[guild_id]
        log_channel_collection.delete_one({"guild_id": guild_id})


@bot.event
async def on_guild_remove(guild: discord.Guild) -> None:
    guild_id = guild.id
    if guild_id in channel_cache:
        del channel_cache[guild_id]
        channel_collection.delete_one({"guild_id": guild_id})
    if guild_id in log_channel_cache:
        del log_channel_cache[guild_id]
        log_channel_collection.delete_one({"guild_id": guild_id})


bot.run(TOKEN)
