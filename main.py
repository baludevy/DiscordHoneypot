import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
from pymongo import MongoClient

client = MongoClient("localhost", 27017)
db = client["honeypot-testing"]
user_collection = db["blacklisted-users"]
channel_collection = db["honeypot_channels"]

channel_cache = {}

load_dotenv()
TOKEN = os.getenv("TOKEN")

if not TOKEN:
    print("bitch ahh where token")
    exit(1)

bot = commands.Bot(command_prefix="h!", intents=discord.Intents.all())

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
    
    print(f"loaded channels into cache: {channel_cache}")

class MyHelp(commands.HelpCommand):
    async def send_bot_help(self, mapping):
        channel = self.get_destination()
        await channel.send("run `h!set.channel` to set the channel for the bot to listen for messages in")

bot.help_command = MyHelp()

@bot.event
async def on_message(message: discord.Message) -> None:
    if not message.guild:
        return

    guild_id = message.guild.id
    if guild_id in channel_cache:
        if message.channel.id == channel_cache[guild_id]:
            if message.author.bot:
                await message.delete()
                await bot.process_commands(message)
                return
            if user_collection.find_one({"user_id": message.author.id}):
                print(f"{message.author.id} already in db")
            else:
                user_data = {"user_id": message.author.id}
                user_collection.insert_one(user_data)
                print(f"user {message.author.id} saved to db")

            await message.author.ban()
            await message.delete()

    await bot.process_commands(message)

@bot.command(name="set.channel")
@commands.has_permissions(administrator=True)
async def setchannel(ctx: commands.Context) -> None:
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

@bot.event
async def on_guild_channel_delete(channel: discord.TextChannel) -> None:
    guild_id = channel.guild.id
    if guild_id in channel_cache and channel_cache[guild_id] == channel.id:
        del channel_cache[guild_id]
        channel_collection.delete_one({"guild_id": guild_id})

@bot.event
async def on_guild_remove(guild: discord.Guild) -> None:
    guild_id = guild.id
    if guild_id in channel_cache:
        del channel_cache[guild_id]
        channel_collection.delete_one({"guild_id": guild_id})

bot.run(TOKEN)