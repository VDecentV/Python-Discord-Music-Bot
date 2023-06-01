import asyncio
import logging
import os
import time

import discord
import yt_dlp as youtube_dl
from discord.ext import commands
from dotenv import load_dotenv
from pytube import Search

logging.basicConfig(level=logging.CRITICAL)

load_dotenv()
TOKEN = os.getenv("TOKEN")
intents = discord.Intents.all()
bot = discord.Bot(intents=intents)

if not discord.opus.is_loaded():
    discord.opus.load_opus('opus')

ffmpeg_options = {
    "options": "-vn",
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
}

audio_queue = {"Source": [], "Name": [], "Duration": [], "User": [], "URL": []}

voice_client = None
now_playing = None
currentDuration = None
timeElapsed = None


async def create_embed(ctx, title, message):
    embed = discord.Embed(title=title, description=f"{message}\n\u2800", color=0x000000)
    embed.set_footer(text=f"{ctx.author}", icon_url=(ctx.author).avatar.url)
    return embed


@bot.event
async def on_ready():
    print(f"Logged on as {bot.user}! ID = {bot.user.id}\n")


@bot.command(name="ping", with_app_command=True)
async def ping(ctx):
    title = "Latency"
    embed = await create_embed(
        ctx,
        title,
        f"Pong! {round(bot.latency*1000, 2)} ms",
    )
    await ctx.respond(embed=embed)


@bot.command()
async def play(ctx, song):
    global audio_queue
    global voice_client
    global now_playing
    global currentDuration
    global timeElapsed

    await ctx.defer()

    if ctx.author.voice is None:
        await ctx.respond("You need to be in a voice channel to use this command.")
        return

    voice_channel = ctx.author.voice.channel
    if voice_client is None:
        voice_client = await voice_channel.connect()
    elif voice_client.channel != voice_channel:
        await voice_client.move_to(voice_channel)

    userID = ctx.author.id
    url = None
    if str(song).startswith("https://youtu.be/"):
        url = f"https://www.youtube.com/watch?v={song[18:]}"
    try:
        results = Search(song).results
        first = results[0]
        video_id = first.video_id
        url = f"https://www.youtube.com/watch?v={video_id}"
    except Exception:
        print("error")

    ydl_opts = {
        "format": "bestaudio/best",
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ],
    }
    with youtube_dl.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        url2 = info["url"]
        try:
            length = info["duration"]
        except KeyError:
            length = 0

        audio_source = discord.FFmpegPCMAudio(url2, **ffmpeg_options)
        audio_length = f'{length//60 if length//60 < 60 else f"{(length//60) // 60}:{(length//60)%60}"}:{length%60 if length%60 > 9 else f"0{length%60}"}'

        if voice_client.is_playing():
            audio_queue["Source"].append(audio_source)
            audio_queue["Name"].append(info["title"])
            audio_queue["Duration"].append(audio_length)
            audio_queue["User"].append(userID)
            audio_queue["URL"].append(url)

            await ctx.respond(f"Added to queue: {url}")
        else:
            now_playing = info["title"]
            currentDuration = audio_length
            voice_client.play(
                audio_source,
                after=lambda e: print(f"Player error: {e}") if e else play_next(),
            )
            timeElapsed = round(time.time())

            await ctx.respond(f'Now playing: {info["title"]} - **{currentDuration}**')


async def users_in_vc(ctx):
    users = []

    voice_channel = ctx.author.voice.channel
    members = voice_channel.members
    for member in members:
        users.append(member.id)

    count = len(users)
    return count


@bot.command()
async def leave(ctx):
    global voice_client
    if ctx.author.voice is None:
        await ctx.respond("You need to be in a voice channel to use this command.")
        return

    role_names = [role.name for role in ctx.author.roles]
    if ("Bot Moderator" in role_names) or (await users_in_vc(ctx) == 2):
        await voice_client.disconnect()
        voice_client = None
        await ctx.respond("Disconnected from voice channel.")
    else:
        await ctx.respond("Insufficient permissions.")


@bot.command()
async def pause(ctx):
    global voice_client
    if ctx.author.voice is None:
        await ctx.respond("You need to be in a voice channel to use this command.")
        return

    role_names = [role.name for role in ctx.author.roles]
    if ("Bot Moderator" in role_names) or (await users_in_vc(ctx) == 2):
        if voice_client is not None and voice_client.is_playing():
            voice_client.pause()

        await ctx.respond("Paused")
    else:
        await ctx.respond("Insufficient permissions.")


@bot.command()
async def resume(ctx):
    global voice_client
    if ctx.author.voice is None:
        await ctx.respond("You need to be in a voice channel to use this command.")
        return

    role_names = [role.name for role in ctx.author.roles]
    if ("Bot Moderator" in role_names) or (await users_in_vc(ctx) == 2):
        if voice_client is not None and voice_client.is_paused():
            voice_client.resume()

        await ctx.respond("Resumed")
    else:
        await ctx.respond("Insufficient permissions.")


def play_next():
    global now_playing
    global audio_queue
    global voice_client
    global timeElapsed
    global currentDuration

    if len(audio_queue["Source"]) > 0:
        now_playing = audio_queue["Name"][0]
        currentDuration = audio_queue["Duration"][0]
        audio_source = audio_queue["Source"].pop(0)
        audio_queue["Name"].pop(0)
        audio_queue["Duration"].pop(0)
        voice_client.play(
            audio_source,
            after=lambda e: print(f"Player error: {e}") if e else play_next(),
        )
        timeElapsed = round(time.time())

    else:
        now_playing = None


@bot.command()
async def queue(ctx):
    await ctx.defer()

    if ctx.author.voice is None:
        await ctx.respond("You need to be in a voice channel to use this command.")
        return

    global audio_queue

    if len(audio_queue["Source"]) == 0:
        await ctx.respond("The queue is currently empty.")
    else:
        queue_names_str = ""
        for i, title in enumerate(audio_queue["Name"]):
            queue_names_str += (
                f"**{i+1}.** {title} - **{audio_queue['Duration'][i]}**\n"
            )
        embed = await create_embed(ctx, "Queue", queue_names_str)
        await ctx.respond(embed=embed)


@bot.command()
async def remove(ctx, num: int):
    global audio_queue

    if ctx.author.voice is None:
        await ctx.respond("You need to be in a voice channel to use this command.")
        return

    role_names = [role.name for role in ctx.author.roles]
    if (
        ("Bot Moderator" in role_names)
        or (ctx.author.id == audio_queue["User"][num - 1])
        or (await users_in_vc(ctx) == 2)
    ):
        if num <= 0:
            await ctx.respond("Invalid queue number.")
            return
        elif len(audio_queue["Source"]) == 0:
            await ctx.respond("The queue is empty.")
            return

        if not (num > len(audio_queue["Source"])):
            queue_item = audio_queue["Name"].pop(num - 1)
            audio_queue["Source"].pop(num - 1)
            audio_queue["Duration"].pop(num - 1)
            audio_queue["URL"].pop(num - 1)
            audio_queue["User"].pop(num - 1)

            await ctx.respond(f"{queue_item} was removed from the queue.")
        else:
            await ctx.respond(
                "Queue number out of range. Refer to the queue by using the command /queue."
            )
    else:
        await ctx.respond("Insufficient permissions.")


@bot.command()
async def clear(ctx):
    global audio_queue
    global now_playing
    global duration

    if ctx.author.voice is None:
        await ctx.respond("You need to be in a voice channel to use this command.")
        return

    role_names = [role.name for role in ctx.author.roles]
    if ("Bot Moderator" in role_names) or (await users_in_vc(ctx) == 2):
        audio_queue["Name"] = []
        audio_queue["Source"] = []
        audio_queue["Duration"] = []
        audio_queue["URL"] = []
        audio_queue["User"] = []
        await ctx.respond("Queue cleared.")
    else:
        await ctx.respond("Insufficient permissions.")


@bot.command()
async def skip(ctx):
    global voice_client
    global now_playing
    if ctx.author.voice is None:
        await ctx.respond("You need to be in a voice channel to use this command.")
        return

    role_names = [role.name for role in ctx.author.roles]
    if ("Bot Moderator" in role_names) or (await users_in_vc(ctx) == 2):
        if voice_client is not None and voice_client.is_playing():
            voice_client.stop()
            now_playing = None

        await ctx.respond("Skipped")
    else:
        await ctx.respond("Insufficient permissions.")


@bot.command()
async def np(ctx):
    global timeElapsed
    global now_playing

    if not ctx.voice_client or not ctx.voice_client.is_playing():
        await ctx.send("No song is currently playing.")
        return

    elapsed = round(time.time()) - timeElapsed
    elapsed = f'{elapsed//60 if elapsed//60 < 60 else f"{(elapsed//60) // 60}:{(elapsed//60)%60}"}:{elapsed%60 if elapsed%60 > 9 else f"0{elapsed%60}"}'
    await ctx.respond(f"Now playing: **{now_playing}**\n{elapsed} / {currentDuration}")


@bot.event
async def on_voice_state_update(member, before, after):
    global voice_client
    if (
        voice_client is not None
        and voice_client.channel == before.channel
        and len(before.channel.members) == 1
    ):
        await voice_client.disconnect()
        voice_client = None


loop = asyncio.get_event_loop()
try:
    loop.run_until_complete(bot.start(TOKEN))
except KeyboardInterrupt:
    loop.run_until_complete(bot.logout())

finally:
    loop.close()
